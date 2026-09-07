"""Small ctypes wrapper for the Windows APIs used by the application."""

from __future__ import annotations

import ctypes
import os
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from resurface.features.hover_window_controls.platform.accessibility import (
    AccessibleCaptionTarget,
    CaptionAccessibilityDetector,
)
from resurface.features.hover_window_controls.app.data_export import (
    DataExportResult,
    DataImportResult,
)
from resurface.features.hover_window_controls.app.identity import DISPLAY_NAME
from resurface.features.hover_window_controls.core.hover_controller import (
    CaptionAction,
    DetectionSource,
    HoverProbe,
    HoverTarget,
)
from resurface.features.hover_window_controls.vision.detection import (
    ApplicationIdentity,
    CaptionVisionDetector,
    VisionContext,
    VisionMatch,
    VisionProfile,
    VisionSnapshot,
    TrackedApplication,
    TrackedAsset,
)

ERROR_ACCESS_DENIED = 5
ERROR_TIMEOUT = 1460
GA_ROOT = 2
GWL_STYLE = -16
GWL_EXSTYLE = -20

DWMWA_CAPTION_BUTTON_BOUNDS = 5
DWMWA_EXTENDED_FRAME_BOUNDS = 9
MONITOR_DEFAULTTONEAREST = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SM_CXSIZE = 30
SM_CYSIZE = 31

HTMINBUTTON = 8
HTMAXBUTTON = 9
HTCLOSE = 20

MF_BYCOMMAND = 0x00000000
MF_GRAYED = 0x00000001
MF_DISABLED = 0x00000002

SC_MINIMIZE = 0xF020
SC_MAXIMIZE = 0xF030
SC_CLOSE = 0xF060
SC_RESTORE = 0xF120

SMTO_BLOCK = 0x0001
SMTO_ABORTIFHUNG = 0x0002
WM_NCHITTEST = 0x0084
WM_SYSCOMMAND = 0x0112

WS_MAXIMIZEBOX = 0x00010000
WS_MINIMIZEBOX = 0x00020000
WS_SYSMENU = 0x00080000
WS_CHILD = 0x40000000
WS_EX_LAYOUTRTL = 0x00400000

TASKBAR_CLASSES = frozenset({"Shell_TrayWnd", "Shell_SecondaryTrayWnd"})

_UINT_ERROR = 0xFFFFFFFF


@dataclass(frozen=True)
class CalibrationTarget:
    hwnd: int
    application_name: str
    window_title: str

    @property
    def label(self) -> str:
        return f"{self.application_name} — {self.window_title}"


@dataclass(frozen=True)
class CalibrationCaptureResult:
    snapshot: Optional[VisionSnapshot] = None
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return self.snapshot is not None


def sort_calibration_targets(
    targets: list[CalibrationTarget],
) -> list[CalibrationTarget]:
    return sorted(
        targets,
        key=lambda target: (
            target.application_name.casefold(),
            target.window_title.casefold(),
            target.hwnd,
        ),
    )


def action_for_hit_test(hit_test: int) -> Optional[CaptionAction]:
    return {
        HTMINBUTTON: CaptionAction.MINIMIZE,
        HTMAXBUTTON: CaptionAction.MAXIMIZE_RESTORE,
        HTCLOSE: CaptionAction.CLOSE,
    }.get(hit_test)


def probe_for_hit_test_result(
    *,
    hwnd: int,
    sent: bool,
    hit_test: int = 0,
    error: int = 0,
) -> HoverProbe:
    if not sent:
        if error == ERROR_ACCESS_DENIED:
            return HoverProbe.no_target(hwnd)
        return HoverProbe.transient(hwnd)

    action = action_for_hit_test(hit_test)
    if action is None:
        return HoverProbe.no_target(hwnd)
    return HoverProbe.confirmed(HoverTarget(hwnd, action))


def system_command_for(action: CaptionAction, is_zoomed: bool = False) -> int:
    if action is CaptionAction.MINIMIZE:
        return SC_MINIMIZE
    if action is CaptionAction.MAXIMIZE_RESTORE:
        return SC_RESTORE if is_zoomed else SC_MAXIMIZE
    if action is CaptionAction.CLOSE:
        return SC_CLOSE
    raise ValueError(f"Unsupported caption action: {action!r}")


def geometry_action_at_point(
    *,
    point: tuple[int, int],
    bounds: tuple[int, int, int, int],
    button_width: int,
    button_height: int,
    style: int,
    ex_style: int,
    close_enabled: bool,
    fullscreen: bool,
) -> Optional[CaptionAction]:
    """Infer only a strict, style-compatible standard caption layout."""
    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    if (
        fullscreen
        or not close_enabled
        or not style & WS_SYSMENU
        or style & WS_CHILD
        or button_width <= 0
        or button_height <= 0
        or width < button_width * 4
        or height < button_height * 2
    ):
        return None

    actions = [CaptionAction.CLOSE]
    if style & WS_MAXIMIZEBOX:
        actions.append(CaptionAction.MAXIMIZE_RESTORE)
    if style & WS_MINIMIZEBOX:
        actions.append(CaptionAction.MINIMIZE)
    if len(actions) < 2:
        return None

    x, y = point
    if not top <= y < top + button_height:
        return None

    rtl = bool(ex_style & WS_EX_LAYOUTRTL)
    for index, action in enumerate(actions):
        if rtl:
            slot_left = left + index * button_width
            slot_right = slot_left + button_width
        else:
            slot_right = right - index * button_width
            slot_left = slot_right - button_width
        if slot_left <= x < slot_right:
            return action
    return None


def caption_asset_layout(
    *,
    context: VisionContext,
    button_width: int,
    button_height: int,
    style: int,
    ex_style: int,
    close_enabled: bool,
    fullscreen: bool,
    caption_bounds: Optional[tuple[int, int, int, int]] = None,
) -> tuple[
    dict[CaptionAction, tuple[int, int, int, int]],
    dict[CaptionAction, str],
    dict[CaptionAction, str],
]:
    assignments = {}
    statuses = {}
    visuals = {
        action: (
            "restore"
            if action is CaptionAction.MAXIMIZE_RESTORE
            and context.identity.window_state == "maximized"
            else (
                "maximize"
                if action is CaptionAction.MAXIMIZE_RESTORE
                else action.name.lower()
            )
        )
        for action in CaptionAction
    }
    available = {
        CaptionAction.CLOSE: bool(style & WS_SYSMENU and close_enabled),
        CaptionAction.MAXIMIZE_RESTORE: bool(style & WS_MAXIMIZEBOX),
        CaptionAction.MINIMIZE: bool(style & WS_MINIMIZEBOX),
    }
    for action, is_available in available.items():
        statuses[action] = "unresolved" if is_available else "unavailable"

    left, top, right, bottom = context.bounds
    if (
        fullscreen
        or style & WS_CHILD
        or button_width <= 0
        or button_height <= 0
        or right - left < button_width * 4
        or bottom - top < button_height * 2
    ):
        return assignments, statuses, visuals

    ordered = [
        action
        for action in (
            CaptionAction.CLOSE,
            CaptionAction.MAXIMIZE_RESTORE,
            CaptionAction.MINIMIZE,
        )
        if available[action]
    ]
    crop_left, crop_top, crop_right, crop_bottom = (
        CaptionVisionDetector.capture_rect(context)
    )
    rtl = bool(ex_style & WS_EX_LAYOUTRTL)
    if caption_bounds is not None:
        region_left, region_top, region_right, region_bottom = caption_bounds
        if (
            region_left < region_right
            and region_top < region_bottom
            and left <= region_left < region_right <= right
            and top <= region_top < region_bottom <= bottom
        ):
            count = len(ordered)
            for index, action in enumerate(ordered):
                if rtl:
                    slot_left = region_left + round(
                        index * (region_right - region_left) / count
                    )
                    slot_right = region_left + round(
                        (index + 1)
                        * (region_right - region_left)
                        / count
                    )
                else:
                    slot_left = region_right - round(
                        (index + 1)
                        * (region_right - region_left)
                        / count
                    )
                    slot_right = region_right - round(
                        index * (region_right - region_left) / count
                    )
                if (
                    crop_left <= slot_left < slot_right <= crop_right
                    and crop_top <= region_top
                    < region_bottom
                    <= crop_bottom
                ):
                    assignments[action] = (
                        slot_left - crop_left,
                        region_top - crop_top,
                        slot_right - crop_left,
                        region_bottom - crop_top,
                    )
                    statuses[action] = "available"
            if len(assignments) == len(ordered):
                return assignments, statuses, visuals

    for index, action in enumerate(ordered):
        if rtl:
            slot_left = left + index * button_width
            slot_right = slot_left + button_width
        else:
            slot_right = right - index * button_width
            slot_left = slot_right - button_width
        slot_bottom = top + button_height
        if (
            crop_left <= slot_left < slot_right <= crop_right
            and crop_top <= top < slot_bottom <= crop_bottom
        ):
            assignments[action] = (
                slot_left - crop_left,
                top - crop_top,
                slot_right - crop_left,
                slot_bottom - crop_top,
            )
            statuses[action] = "available"
    return assignments, statuses, visuals


def is_within_caption_buttons(
    rect: tuple[int, int, int, int],
    caption_bounds: Optional[tuple[int, int, int, int]],
) -> bool:
    if caption_bounds is None:
        return True
    return (
        caption_bounds[0] <= rect[0] < rect[2] <= caption_bounds[2]
        and caption_bounds[1] <= rect[1] < rect[3] <= caption_bounds[3]
    )


def is_point_within_caption_buttons(
    point: tuple[int, int],
    caption_bounds: Optional[tuple[int, int, int, int]],
) -> bool:
    if caption_bounds is None:
        return False
    return (
        caption_bounds[0] <= point[0] < caption_bounds[2]
        and caption_bounds[1] <= point[1] < caption_bounds[3]
    )


def is_caption_point_allowed(
    point: tuple[int, int],
    caption_bounds: Optional[tuple[int, int, int, int]],
    native_probe: HoverProbe,
) -> bool:
    return (
        native_probe.target is not None
        or is_point_within_caption_buttons(point, caption_bounds)
    )


def caption_button_region(
    *,
    bounds: tuple[int, int, int, int],
    button_width: int,
    button_height: int,
    style: int,
    ex_style: int,
    close_enabled: bool,
    fullscreen: bool,
    native_bounds: Optional[tuple[int, int, int, int]],
) -> Optional[tuple[int, int, int, int]]:
    """Return the only screen region permitted to trigger caption actions."""
    left, top, right, bottom = bounds
    if (
        fullscreen
        or style & WS_CHILD
        or button_width <= 0
        or button_height <= 0
    ):
        return None

    button_count = sum(
        (
            bool(style & WS_SYSMENU and close_enabled),
            bool(style & WS_MAXIMIZEBOX),
            bool(style & WS_MINIMIZEBOX),
        )
    )
    if button_count == 0:
        return None

    if native_bounds is not None:
        return native_bounds

    region_width = button_count * button_width
    region_bottom = min(bottom, top + button_height)
    if style & WS_EX_LAYOUTRTL:
        return (left, top, min(right, left + region_width), region_bottom)
    return (max(left, right - region_width), top, right, region_bottom)


def is_fullscreen_layout(
    *,
    bounds: tuple[int, int, int, int],
    monitor_bounds: tuple[int, int, int, int],
    is_zoomed: bool,
) -> bool:
    return not is_zoomed and bounds == monitor_bounds


def resolve_caption_probe(
    *,
    hwnd: int,
    accessible: Optional[AccessibleCaptionTarget],
    vision: Optional[VisionMatch],
    native_probe: HoverProbe,
    geometry_action: Optional[CaptionAction],
    vision_overrides_accessibility: bool = False,
) -> HoverProbe:
    if vision is not None and vision_overrides_accessibility:
        return HoverProbe.confirmed(
            HoverTarget(
                hwnd,
                vision.action,
                DetectionSource.VISION,
                vision_id=vision.profile_id,
            )
        )
    if accessible is not None:
        return HoverProbe.confirmed(
            HoverTarget(
                hwnd,
                accessible.action,
                DetectionSource.ACCESSIBILITY,
                accessible.runtime_id,
            )
        )
    if vision is not None:
        return HoverProbe.confirmed(
            HoverTarget(
                hwnd,
                vision.action,
                DetectionSource.VISION,
                vision_id=vision.profile_id,
            )
        )
    if native_probe.target is not None:
        return native_probe
    if geometry_action is not None:
        return HoverProbe.confirmed(
            HoverTarget(
                hwnd,
                geometry_action,
                DetectionSource.GEOMETRY,
            )
        )
    return native_probe


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", wintypes.DWORD),
        ("dwStrucVersion", wintypes.DWORD),
        ("dwFileVersionMS", wintypes.DWORD),
        ("dwFileVersionLS", wintypes.DWORD),
        ("dwProductVersionMS", wintypes.DWORD),
        ("dwProductVersionLS", wintypes.DWORD),
        ("dwFileFlagsMask", wintypes.DWORD),
        ("dwFileFlags", wintypes.DWORD),
        ("dwFileOS", wintypes.DWORD),
        ("dwFileType", wintypes.DWORD),
        ("dwFileSubtype", wintypes.DWORD),
        ("dwFileDateMS", wintypes.DWORD),
        ("dwFileDateLS", wintypes.DWORD),
    ]


class Win32WindowApi:
    HIT_TEST_TIMEOUT_MS = 150
    ACCESSIBILITY_TIMEOUT_MS = 75
    MAX_ACCESSIBILITY_TIMEOUT_MS = 200

    def __init__(
        self,
        accessibility: Optional[CaptionAccessibilityDetector] = None,
        vision: Optional[CaptionVisionDetector] = None,
    ) -> None:
        if os.name != "nt":
            raise OSError(f"{DISPLAY_NAME} only supports Windows")

        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._version = ctypes.WinDLL("version", use_last_error=True)
        self._accessibility = accessibility or CaptionAccessibilityDetector()
        self._vision = vision or CaptionVisionDetector()
        self._process_metadata_cache: dict[int, tuple[str, str, str]] = {}
        self._theme = self._application_theme()
        self._configure_functions()

    def _configure_functions(self) -> None:
        user32 = self._user32

        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetClassNameW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.IsZoomed.argtypes = [wintypes.HWND]
        user32.IsZoomed.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        enum_callback = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )
        self._enum_windows_callback_type = enum_callback
        user32.EnumWindows.argtypes = [enum_callback, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
        user32.GetSystemMenu.restype = wintypes.HMENU
        user32.GetMenuState.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMenuState.restype = wintypes.UINT
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        user32.SendMessageTimeoutW.restype = wintypes.LPARAM
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [
            wintypes.HMONITOR,
            ctypes.POINTER(MONITORINFO),
        ]
        user32.GetMonitorInfoW.restype = wintypes.BOOL

        get_dpi = getattr(user32, "GetDpiForWindow", None)
        if get_dpi is not None:
            get_dpi.argtypes = [wintypes.HWND]
            get_dpi.restype = wintypes.UINT
        self._get_dpi_for_window = get_dpi

        get_metric_for_dpi = getattr(user32, "GetSystemMetricsForDpi", None)
        if get_metric_for_dpi is not None:
            get_metric_for_dpi.argtypes = [ctypes.c_int, wintypes.UINT]
            get_metric_for_dpi.restype = ctypes.c_int
        self._get_system_metrics_for_dpi = get_metric_for_dpi
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int

        self._dwmapi.DwmGetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        self._dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

        self._kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self._kernel32.OpenProcess.restype = wintypes.HANDLE
        self._kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL

        self._version.GetFileVersionInfoSizeW.argtypes = [
            wintypes.LPCWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        self._version.GetFileVersionInfoW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
        ]
        self._version.GetFileVersionInfoW.restype = wintypes.BOOL
        self._version.VerQueryValueW.argtypes = [
            wintypes.LPCVOID,
            wintypes.LPCWSTR,
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.UINT),
        ]
        self._version.VerQueryValueW.restype = wintypes.BOOL

        get_window_long = getattr(user32, "GetWindowLongPtrW", None)
        if get_window_long is None:
            get_window_long = user32.GetWindowLongW
        get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
        get_window_long.restype = ctypes.c_ssize_t
        self._get_window_long = get_window_long

    def start(self) -> None:
        self._accessibility.start()
        self._vision.start()

    def stop(self) -> None:
        self._vision.stop()
        self._accessibility.stop()

    @staticmethod
    def _point_lparam(point: wintypes.POINT) -> int:
        return (point.x & 0xFFFF) | ((point.y & 0xFFFF) << 16)

    def probe_at_cursor(
        self, timeout_ms: Optional[int] = None
    ) -> HoverProbe:
        point = wintypes.POINT()
        if not self._user32.GetCursorPos(ctypes.byref(point)):
            return HoverProbe.transient()

        child_hwnd = self._user32.WindowFromPoint(point)
        if not child_hwnd:
            return HoverProbe.no_target()
        hwnd = self._user32.GetAncestor(child_hwnd, GA_ROOT)
        if not hwnd:
            return HoverProbe.no_target()
        hwnd_value = int(hwnd)

        class_name = self._window_class(hwnd)
        if class_name in TASKBAR_CLASSES:
            return HoverProbe.no_target(hwnd_value)

        bounds = self._window_bounds(hwnd)
        if bounds is None:
            return HoverProbe.transient(hwnd_value)
        caption_bounds = self._caption_button_bounds(hwnd, bounds)
        dpi = self._window_dpi(hwnd)
        button_width, button_height = self._caption_metrics(dpi)
        caption_band_height = max(button_height * 2, (64 * dpi) // 96)

        result = ctypes.c_size_t()
        ctypes.set_last_error(0)
        sent = self._user32.SendMessageTimeoutW(
            hwnd,
            WM_NCHITTEST,
            0,
            self._point_lparam(point),
            SMTO_BLOCK | SMTO_ABORTIFHUNG,
            self.HIT_TEST_TIMEOUT_MS if timeout_ms is None else timeout_ms,
            ctypes.byref(result),
        )
        native_probe = probe_for_hit_test_result(
            hwnd=hwnd_value,
            sent=bool(sent),
            hit_test=int(result.value),
            error=ctypes.get_last_error(),
        )

        style = int(self._get_window_long(hwnd, GWL_STYLE))
        ex_style = int(self._get_window_long(hwnd, GWL_EXSTYLE))
        close_enabled = self._close_is_available(hwnd)
        fullscreen = self._is_fullscreen(hwnd, bounds)
        caption_bounds = caption_button_region(
            bounds=bounds,
            button_width=button_width,
            button_height=button_height,
            style=style,
            ex_style=ex_style,
            close_enabled=close_enabled,
            fullscreen=fullscreen,
            native_bounds=caption_bounds,
        )
        if fullscreen or not is_caption_point_allowed(
            (point.x, point.y),
            caption_bounds,
            native_probe,
        ):
            return HoverProbe.no_target(hwnd_value)

        process_id = self._window_process_id(hwnd)
        accessible_target = None
        if (
            bounds[0] <= point.x < bounds[2]
            and bounds[1] <= point.y < bounds[1] + caption_band_height
            and process_id
        ):
            accessibility_timeout = min(
                self.MAX_ACCESSIBILITY_TIMEOUT_MS,
                self.ACCESSIBILITY_TIMEOUT_MS
                if timeout_ms is None
                else timeout_ms,
            )
            accessible = self._accessibility.probe(
                point=(point.x, point.y),
                root_hwnd=hwnd_value,
                process_id=process_id,
                root_bounds=bounds,
                caption_band_height=caption_band_height,
                timeout_ms=accessibility_timeout,
            )
            if accessible.target is not None:
                accessible_target = accessible.target
                if (
                    accessible_target.rect
                    and not is_within_caption_buttons(
                        accessible_target.rect,
                        caption_bounds,
                    )
                ):
                    accessible_target = None

        context = self._vision_context(
            hwnd,
            bounds,
            dpi,
            process_id,
            class_name,
            ex_style,
        )

        def observe(probe: HoverProbe) -> HoverProbe:
            if probe.target is None or context is None:
                return probe
            standard_layout = (
                native_probe.target is not None
                or probe.target.source
                in (DetectionSource.NATIVE, DetectionSource.GEOMETRY)
            )
            if standard_layout:
                assignments, statuses, visuals = caption_asset_layout(
                    context=context,
                    button_width=button_width,
                    button_height=button_height,
                    style=style,
                    ex_style=ex_style,
                    close_enabled=close_enabled,
                    fullscreen=fullscreen,
                    caption_bounds=caption_bounds,
                )
            else:
                assignments = {}
                statuses = {
                    action: "unresolved" for action in CaptionAction
                }
                visuals = {
                    action: (
                        "restore"
                        if action is CaptionAction.MAXIMIZE_RESTORE
                        and context.identity.window_state == "maximized"
                        else (
                            "maximize"
                            if action is CaptionAction.MAXIMIZE_RESTORE
                            else action.name.lower()
                        )
                    )
                    for action in CaptionAction
                }
                if (
                    probe.target.source is DetectionSource.ACCESSIBILITY
                    and accessible_target is not None
                    and accessible_target.rect
                ):
                    crop_left, crop_top, crop_right, crop_bottom = (
                        self._vision.capture_rect(context)
                    )
                    rect_left, rect_top, rect_right, rect_bottom = (
                        accessible_target.rect
                    )
                    if (
                        crop_left <= rect_left < rect_right <= crop_right
                        and crop_top <= rect_top < rect_bottom <= crop_bottom
                    ):
                        assignments[accessible_target.action] = (
                            rect_left - crop_left,
                            rect_top - crop_top,
                            rect_right - crop_left,
                            rect_bottom - crop_top,
                        )
                        statuses[accessible_target.action] = "available"
            self._vision.observe_caption_assets(
                context,
                assignments,
                statuses,
                visuals,
            )
            return probe

        final = timeout_ms is not None
        vision_eligible = False
        if context is not None:
            vision_bounds = self._vision.capture_rect(context)
            vision_eligible = (
                vision_bounds[0] <= point.x < vision_bounds[2]
                and vision_bounds[1] <= point.y < vision_bounds[3]
                and is_point_within_caption_buttons(
                    (point.x, point.y),
                    caption_bounds,
                )
            )
        if context is not None and vision_eligible:
            calibrated = self._vision.probe_calibrated(
                context,
                (point.x, point.y),
                final=final,
            )
            if calibrated is not None:
                return observe(
                    resolve_caption_probe(
                        hwnd=hwnd_value,
                        accessible=accessible_target,
                        vision=calibrated,
                        native_probe=native_probe,
                        geometry_action=None,
                        vision_overrides_accessibility=True,
                    )
                )

        if accessible_target is not None:
            return observe(
                resolve_caption_probe(
                    hwnd=hwnd_value,
                    accessible=accessible_target,
                    vision=None,
                    native_probe=native_probe,
                    geometry_action=None,
                )
            )

        if native_probe.target is not None:
            return observe(native_probe)

        if context is not None and vision_eligible:
            automatic = self._vision.probe_automatic(
                context,
                (point.x, point.y),
                final=final,
            )
            if automatic is not None:
                return observe(
                    resolve_caption_probe(
                        hwnd=hwnd_value,
                        accessible=None,
                        vision=automatic,
                        native_probe=native_probe,
                        geometry_action=None,
                    )
                )

        geometry_action = geometry_action_at_point(
            point=(point.x, point.y),
            bounds=bounds,
            button_width=button_width,
            button_height=button_height,
            style=style,
            ex_style=ex_style,
            close_enabled=close_enabled,
            fullscreen=fullscreen,
        )
        return observe(
            resolve_caption_probe(
                hwnd=hwnd_value,
                accessible=accessible_target,
                vision=None,
                native_probe=native_probe,
                geometry_action=geometry_action,
            )
        )

    def is_action_available(self, target: HoverTarget) -> bool:
        hwnd = wintypes.HWND(target.hwnd)
        if not self._user32.IsWindow(hwnd) or not self._user32.IsWindowVisible(hwnd):
            return False

        if target.source is DetectionSource.ACCESSIBILITY:
            # The exact UIA control was already required to be enabled and is
            # re-resolved by runtime ID immediately before this check.
            return True
        if target.source is DetectionSource.VISION:
            return True

        style = int(self._get_window_long(hwnd, GWL_STYLE))
        if target.action is CaptionAction.MINIMIZE:
            return bool(style & WS_MINIMIZEBOX)
        if target.action is CaptionAction.MAXIMIZE_RESTORE:
            return bool(style & WS_MAXIMIZEBOX)

        return self._close_is_available(hwnd)

    def _close_is_available(self, hwnd: wintypes.HWND) -> bool:
        menu = self._user32.GetSystemMenu(hwnd, False)
        if not menu:
            return False
        state = int(self._user32.GetMenuState(menu, SC_CLOSE, MF_BYCOMMAND))
        if state == _UINT_ERROR:
            return False
        return not bool(state & (MF_DISABLED | MF_GRAYED))

    def _window_class(self, hwnd: wintypes.HWND) -> str:
        buffer = ctypes.create_unicode_buffer(256)
        if not self._user32.GetClassNameW(hwnd, buffer, len(buffer)):
            return ""
        return buffer.value

    def _window_process_id(self, hwnd: wintypes.HWND) -> int:
        process_id = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(
            hwnd,
            ctypes.byref(process_id),
        )
        return int(process_id.value)

    def _window_title(self, hwnd: wintypes.HWND) -> str:
        length = int(self._user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        if not self._user32.GetWindowTextW(hwnd, buffer, len(buffer)):
            return ""
        return buffer.value.strip()

    def _process_path(self, process_id: int) -> str:
        handle = self._kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            process_id,
        )
        if not handle:
            return ""
        try:
            capacity = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(capacity.value)
            if not self._kernel32.QueryFullProcessImageNameW(
                handle,
                0,
                buffer,
                ctypes.byref(capacity),
            ):
                return ""
            return os.path.normcase(os.path.abspath(buffer.value))
        finally:
            self._kernel32.CloseHandle(handle)

    def _file_version(self, path: str) -> str:
        ignored = wintypes.DWORD()
        size = self._version.GetFileVersionInfoSizeW(
            path,
            ctypes.byref(ignored),
        )
        if not size:
            try:
                stat = os.stat(path)
                return f"unversioned-{stat.st_size}-{stat.st_mtime_ns}"
            except OSError:
                return "unknown"
        buffer = ctypes.create_string_buffer(size)
        if not self._version.GetFileVersionInfoW(path, 0, size, buffer):
            return "unknown"
        value = wintypes.LPVOID()
        length = wintypes.UINT()
        if not self._version.VerQueryValueW(
            buffer,
            "\\",
            ctypes.byref(value),
            ctypes.byref(length),
        ):
            return "unknown"
        info = ctypes.cast(
            value,
            ctypes.POINTER(VS_FIXEDFILEINFO),
        ).contents
        return ".".join(
            str(part)
            for part in (
                info.dwFileVersionMS >> 16,
                info.dwFileVersionMS & 0xFFFF,
                info.dwFileVersionLS >> 16,
                info.dwFileVersionLS & 0xFFFF,
            )
        )

    @staticmethod
    def _application_theme() -> str:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                (
                    r"Software\Microsoft\Windows\CurrentVersion"
                    r"\Themes\Personalize"
                ),
            ) as key:
                value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return "light" if value else "dark"
        except OSError:
            return "unknown"

    def _process_metadata(self, process_id: int) -> tuple[str, str, str]:
        metadata = self._process_metadata_cache.get(process_id)
        if metadata is None:
            path = self._process_path(process_id)
            metadata = (
                path,
                self._file_version(path) if path else "unknown",
                Path(path).stem if path else "",
            )
            self._process_metadata_cache[process_id] = metadata
        return metadata

    def _vision_context(
        self,
        hwnd: wintypes.HWND,
        bounds: tuple[int, int, int, int],
        dpi: int,
        process_id: int,
        class_name: str,
        ex_style: int,
    ) -> Optional[VisionContext]:
        path, version, friendly_name = self._process_metadata(process_id)
        if not path:
            return None
        identity = ApplicationIdentity(
            executable_path=path,
            executable_version=version,
            friendly_name=friendly_name,
            window_class=class_name,
            dpi=dpi,
            theme=self._theme,
            caption_side=(
                "left" if ex_style & WS_EX_LAYOUTRTL else "right"
            ),
            window_state=(
                "maximized"
                if self._user32.IsZoomed(hwnd)
                else "normal"
            ),
        )
        return VisionContext(int(hwnd), bounds, dpi, identity)

    def list_calibration_targets(self) -> list[CalibrationTarget]:
        targets: list[CalibrationTarget] = []

        def collect(hwnd, _lparam) -> bool:
            if (
                not self._user32.IsWindowVisible(hwnd)
                or self._user32.IsIconic(hwnd)
                or int(self._get_window_long(hwnd, GWL_STYLE)) & WS_CHILD
            ):
                return True
            class_name = self._window_class(hwnd)
            title = self._window_title(hwnd)
            if class_name in TASKBAR_CLASSES or not title:
                return True
            process_id = self._window_process_id(hwnd)
            if process_id == os.getpid():
                return True
            _path, _version, application_name = self._process_metadata(
                process_id
            )
            if not application_name or self._window_bounds(hwnd) is None:
                return True
            targets.append(
                CalibrationTarget(int(hwnd), application_name, title)
            )
            return True

        callback = self._enum_windows_callback_type(collect)
        self._user32.EnumWindows(callback, 0)
        return sort_calibration_targets(targets)

    def capture_vision_calibration(
        self,
        hwnd_value: int,
    ) -> CalibrationCaptureResult:
        hwnd = wintypes.HWND(hwnd_value)
        if (
            not self._user32.IsWindow(hwnd)
            or not self._user32.IsWindowVisible(hwnd)
            or self._user32.IsIconic(hwnd)
        ):
            return CalibrationCaptureResult(
                error=(
                    "The selected window is no longer available. "
                    "Refresh the open-window list and try again."
                )
            )
        if self._window_class(hwnd) in TASKBAR_CLASSES:
            return CalibrationCaptureResult(
                error="Windows taskbar surfaces cannot be calibrated."
            )
        bounds = self._window_bounds(hwnd)
        if bounds is None:
            return CalibrationCaptureResult(
                error="Windows did not provide usable window bounds."
            )
        process_id = self._window_process_id(hwnd)
        ex_style = int(self._get_window_long(hwnd, GWL_EXSTYLE))
        context = self._vision_context(
            hwnd,
            bounds,
            self._window_dpi(hwnd),
            process_id,
            self._window_class(hwnd),
            ex_style,
        )
        if context is None:
            return CalibrationCaptureResult(
                error=(
                    "The application executable identity could not be read. "
                    "Check that both applications use the same privilege "
                    "level."
                )
            )
        snapshot = self._vision.snapshot(context, window_capture=True)
        if snapshot is None:
            return CalibrationCaptureResult(
                error=(
                    "The caption corner could not be captured or contained "
                    "no usable image. Protected windows are unsupported."
                )
            )
        return CalibrationCaptureResult(snapshot=snapshot)

    def save_vision_calibration(
        self,
        snapshot: VisionSnapshot,
        assignments: dict[CaptionAction, tuple[int, int, int, int]],
    ) -> VisionProfile:
        return self._vision.save_calibration(snapshot, assignments)

    def list_tracked_calibration_apps(self) -> list[TrackedApplication]:
        return self._vision.list_tracked_applications()

    def list_tracked_calibration_assets(
        self,
        application: TrackedApplication,
    ) -> list[TrackedAsset]:
        return self._vision.list_tracked_assets(application)

    def update_tracked_calibration(
        self,
        asset: TrackedAsset,
        rect: tuple[int, int, int, int],
    ) -> TrackedAsset:
        return self._vision.update_tracked_rect(asset, rect)

    def clear_vision_cache(self) -> None:
        self._vision.clear_cache()

    def export_all_data(
        self,
        destination_parent: Path,
    ) -> DataExportResult | None:
        return self._vision.export_all_data(destination_parent)

    def import_all_data(self, source_directory: Path) -> DataImportResult:
        return self._vision.import_all_data(source_directory)

    def _window_bounds(
        self, hwnd: wintypes.HWND
    ) -> Optional[tuple[int, int, int, int]]:
        rect = wintypes.RECT()
        result = self._dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        if result != 0 and not self._user32.GetWindowRect(
            hwnd, ctypes.byref(rect)
        ):
            return None
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return None
        return (rect.left, rect.top, rect.right, rect.bottom)

    def _caption_button_bounds(
        self,
        hwnd: wintypes.HWND,
        window_bounds: tuple[int, int, int, int],
    ) -> Optional[tuple[int, int, int, int]]:
        rect = wintypes.RECT()
        result = self._dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_CAPTION_BUTTON_BOUNDS,
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        width = window_bounds[2] - window_bounds[0]
        height = window_bounds[3] - window_bounds[1]
        if (
            result != 0
            or not 0 <= rect.left < rect.right <= width
            or not 0 <= rect.top < rect.bottom <= height
        ):
            return None
        return (
            window_bounds[0] + rect.left,
            window_bounds[1] + rect.top,
            window_bounds[0] + rect.right,
            window_bounds[1] + rect.bottom,
        )

    def _window_dpi(self, hwnd: wintypes.HWND) -> int:
        if self._get_dpi_for_window is None:
            return 96
        return max(int(self._get_dpi_for_window(hwnd)), 96)

    def _caption_metrics(self, dpi: int) -> tuple[int, int]:
        if self._get_system_metrics_for_dpi is not None:
            return (
                int(self._get_system_metrics_for_dpi(SM_CXSIZE, dpi)),
                int(self._get_system_metrics_for_dpi(SM_CYSIZE, dpi)),
            )
        return (
            max(1, self._user32.GetSystemMetrics(SM_CXSIZE) * dpi // 96),
            max(1, self._user32.GetSystemMetrics(SM_CYSIZE) * dpi // 96),
        )

    def _is_fullscreen(
        self,
        hwnd: wintypes.HWND,
        bounds: tuple[int, int, int, int],
    ) -> bool:
        monitor = self._user32.MonitorFromWindow(
            hwnd,
            MONITOR_DEFAULTTONEAREST,
        )
        if not monitor:
            return False
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if not self._user32.GetMonitorInfoW(
            monitor, ctypes.byref(info)
        ):
            return False
        monitor_bounds = (
            info.rcMonitor.left,
            info.rcMonitor.top,
            info.rcMonitor.right,
            info.rcMonitor.bottom,
        )
        return is_fullscreen_layout(
            bounds=bounds,
            monitor_bounds=monitor_bounds,
            is_zoomed=bool(self._user32.IsZoomed(hwnd)),
        )

    def execute(self, target: HoverTarget) -> bool:
        hwnd = wintypes.HWND(target.hwnd)
        if not self._user32.IsWindow(hwnd):
            return False
        command = system_command_for(
            target.action,
            is_zoomed=bool(self._user32.IsZoomed(hwnd)),
        )
        return bool(
            self._user32.PostMessageW(hwnd, WM_SYSCOMMAND, command, 0)
        )

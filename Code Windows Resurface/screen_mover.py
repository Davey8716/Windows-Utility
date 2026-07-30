from __future__ import annotations

import ctypes
import queue
import sys
import threading
import time
import traceback
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from pynput import mouse

import psutil
import win32api
import win32con
import win32gui
import win32process

from state_manager import load_state


TITLE_BAR_SIDE_MARGIN = 60
TITLE_BAR_BUTTON_GAP = 180
DOCK_WIDTH = 180
DOCK_HEIGHT = 30
DOCK_TOP_OFFSET = 14
DOCK_RESTORED_TOP_OFFSET = 2
LOOP_SLEEP = 0.03
WINDOW_MOVE_SETTLE_SECONDS = 0.2
SELF_WINDOW_DOCK_TITLE_CLEARANCE = 166
DOCK_SIDE_PADDING = 13
DOCK_ICON_SPACING_REDUCTION = 2
DOCK_TRANSPARENT_COLOR = win32api.RGB(255, 255, 255)
DOCK_ARROW_COLOR = win32api.RGB(45, 125, 210)
DOCK_ICON_FOLDER = "Icon Pngs"
DOCK_ICON_THEME_BLACK = "Black"
DOCK_ICON_THEME_WHITE = "White"
DOCK_ICON_DEFAULT_THEME = DOCK_ICON_THEME_BLACK
DOCK_DARK_BAR_ICON_THEME = DOCK_ICON_THEME_WHITE
DOCK_LIGHT_BAR_ICON_THEME = DOCK_ICON_THEME_BLACK
DOCK_THEME_LUMINANCE_THRESHOLD = 150
DOCK_THEME_HYSTERESIS = 5
DOCK_DARK_BAR_LUMINANCE_MAX = DOCK_THEME_LUMINANCE_THRESHOLD - DOCK_THEME_HYSTERESIS
DOCK_LIGHT_BAR_LUMINANCE_MIN = DOCK_THEME_LUMINANCE_THRESHOLD + DOCK_THEME_HYSTERESIS
DOCK_ACTIONS = (
    ("FAR_LEFT", "<<"),
    ("LEFT", "<"),
    ("RIGHT", ">"),
    ("FAR_RIGHT", ">>"),
    ("MINIMIZE", "_"),
    ("MAXIMIZE", "[]"),
)
DOCK_ACTION_ICON_FILES = {
    "FAR_LEFT": "Far Left.png",
    "LEFT": "Left.png",
    "RIGHT": "Right.png",
    "FAR_RIGHT": "Far Right.png",
    "MINIMIZE": "Minimize.png",
    "MAXIMIZE": "Maximize.png",
}
MONITOR_MOVE_ACTIONS = {"FAR_LEFT", "LEFT", "RIGHT", "FAR_RIGHT"}
LRESULT = getattr(wintypes, "LRESULT", ctypes.c_ssize_t)
WNDPROC_TYPE = ctypes.WINFUNCTYPE(
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
DOCK_ACTIONS_DICT = dict(DOCK_ACTIONS)


def is_steam_game_executable(executable_path) -> bool:
    """Return whether an executable is installed beneath steamapps/common."""
    if not executable_path:
        return False

    path_parts = [
        part.casefold()
        for part in str(executable_path).replace("/", "\\").split("\\")
        if part
    ]
    return any(
        path_parts[index : index + 2] == ["steamapps", "common"]
        and index + 3 < len(path_parts)
        for index in range(len(path_parts) - 1)
    )


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ("GdiplusVersion", ctypes.c_uint32),
        ("DebugEventCallback", ctypes.c_void_p),
        ("SuppressBackgroundThread", ctypes.c_int),
        ("SuppressExternalCodecs", ctypes.c_int),
    ]


class DockIconRenderer:
    def __init__(self):
        self._gdiplus = None
        self._token = ctypes.c_void_p()
        self._images: dict[tuple[str, str], ctypes.c_void_p | None] = {}
        self._startup_attempted = False

    def draw_action(self, hdc, action: str, theme: str) -> bool:
        image = self._image_for_action(action, theme)
        if not image:
            return False

        graphics = ctypes.c_void_p()
        if self._gdiplus.GdipCreateFromHDC(int(hdc), ctypes.byref(graphics)) != 0:
            return False

        try:
            status = self._gdiplus.GdipDrawImageRectI(
                graphics,
                image,
                0,
                0,
                DOCK_WIDTH,
                DOCK_HEIGHT,
            )
            return status == 0
        finally:
            self._gdiplus.GdipDeleteGraphics(graphics)

    def dispose(self) -> None:
        if self._gdiplus is not None:
            for image in self._images.values():
                if image:
                    try:
                        self._gdiplus.GdipDisposeImage(image)
                    except Exception:
                        pass

            if self._token:
                try:
                    self._gdiplus.GdiplusShutdown(self._token)
                except Exception:
                    pass

        self._gdiplus = None
        self._token = ctypes.c_void_p()
        self._images.clear()
        self._startup_attempted = False

    def preload_themes(self, themes) -> None:
        for theme in themes:
            for action, _label in DOCK_ACTIONS:
                self._image_for_action(action, theme)

    def _image_for_action(self, action: str, theme: str):
        cache_key = (theme, action)
        if cache_key in self._images:
            return self._images[cache_key]

        image = self._load_image(action, theme)
        self._images[cache_key] = image
        return image

    def _load_image(self, action: str, theme: str):
        if not self._ensure_gdiplus():
            return None

        filename = DOCK_ACTION_ICON_FILES.get(action)
        if not filename:
            return None

        for icon_dir in _dock_icon_directories(theme):
            icon_path = icon_dir / filename
            if not icon_path.is_file():
                continue

            image = ctypes.c_void_p()
            status = self._gdiplus.GdipLoadImageFromFile(
                str(icon_path),
                ctypes.byref(image),
            )
            if status == 0 and image:
                return image

        return None

    def _ensure_gdiplus(self) -> bool:
        if self._gdiplus is not None:
            return True
        if self._startup_attempted:
            return False

        self._startup_attempted = True
        try:
            self._gdiplus = ctypes.windll.gdiplus
            startup_input = GdiplusStartupInput(1, None, 0, 0)
            status = self._gdiplus.GdiplusStartup(
                ctypes.byref(self._token),
                ctypes.byref(startup_input),
                None,
            )
            if status != 0:
                self._gdiplus = None
                return False
        except Exception:
            self._gdiplus = None
            return False

        return True


def _dock_icon_directories(theme: str | None = None) -> list[Path]:
    directories: list[Path] = []
    theme = str(theme or "").strip()

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        directories.extend(_dock_icon_directory_candidates(Path(bundle_root), theme))

    directories.extend(
        _dock_icon_directory_candidates(Path(sys.executable).resolve().parent, theme)
    )
    directories.extend(
        _dock_icon_directory_candidates(Path(__file__).resolve().parent.parent, theme)
    )

    return directories


def _dock_icon_directory_candidates(root: Path, theme: str) -> list[Path]:
    base_dir = root / DOCK_ICON_FOLDER
    if not theme:
        return [base_dir]
    return [base_dir / theme, base_dir]


def _dock_icon_theme_for_luminance(
    luminance: float | None,
    current_theme: str | None = None,
) -> str:
    if luminance is None:
        return DOCK_ICON_DEFAULT_THEME
    if luminance <= DOCK_DARK_BAR_LUMINANCE_MAX:
        return DOCK_DARK_BAR_ICON_THEME
    if luminance >= DOCK_LIGHT_BAR_LUMINANCE_MIN:
        return DOCK_LIGHT_BAR_ICON_THEME
    if current_theme in {DOCK_ICON_THEME_BLACK, DOCK_ICON_THEME_WHITE}:
        return current_theme
    return DOCK_DARK_BAR_ICON_THEME


def _dock_icon_theme_for_rect(rect, current_theme: str | None = None) -> str:
    luminance = _average_screen_luminance(rect)
    return _dock_icon_theme_for_luminance(luminance, current_theme)


def _average_screen_luminance(rect) -> float | None:
    left, top, right, bottom = rect
    width = max(0, int(right - left))
    height = max(0, int(bottom - top))
    if width == 0 or height == 0:
        return None

    sample_x_count = min(9, width)
    sample_y_count = min(3, height)
    screen_hdc = None
    total = 0.0
    count = 0

    try:
        screen_hdc = win32gui.GetDC(0)
        for x_index in range(sample_x_count):
            x = int(left + ((x_index + 0.5) * width / sample_x_count))
            for y_index in range(sample_y_count):
                y = int(top + ((y_index + 0.5) * height / sample_y_count))
                color = win32gui.GetPixel(screen_hdc, x, y)
                if color == -1:
                    continue
                red = color & 0xFF
                green = (color >> 8) & 0xFF
                blue = (color >> 16) & 0xFF
                total += (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
                count += 1
    except Exception:
        return None
    finally:
        if screen_hdc is not None:
            try:
                win32gui.ReleaseDC(0, screen_hdc)
            except Exception:
                pass

    if count == 0:
        return None
    return total / count


def _resolve_target_monitor_index(current_idx, monitor_count, direction):
    if direction == "LEFT":
        return max(0, current_idx - 1)
    if direction == "RIGHT":
        return min(monitor_count - 1, current_idx + 1)
    if direction == "FAR_LEFT":
        return 0
    if direction == "FAR_RIGHT":
        return monitor_count - 1
    return current_idx


def _monitor_handles():
    return [monitor[0] for monitor in win32api.EnumDisplayMonitors()]


def get_window_monitor_position(hwnd):
    try:
        monitor_handles = _monitor_handles()
    except Exception:
        return None, 0

    monitor_count = len(monitor_handles)
    if monitor_count == 0:
        return None, 0

    try:
        current_monitor = win32api.MonitorFromWindow(hwnd)
        current_idx = monitor_handles.index(current_monitor)
    except Exception:
        return None, monitor_count

    return current_idx, monitor_count


def window_supports_maximize(hwnd):
    try:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return True
    except Exception:
        return True

    try:
        style = int(win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE))
    except Exception:
        return True

    return bool(style & win32con.WS_MAXIMIZEBOX)


def window_is_fullscreen(hwnd, rect=None):
    if not hwnd:
        return False

    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMAXIMIZED:
            return False
    except Exception:
        pass

    try:
        if rect is None:
            rect = win32gui.GetWindowRect(hwnd)
        monitor = win32api.MonitorFromWindow(
            hwnd,
            getattr(win32con, "MONITOR_DEFAULTTONEAREST", 2),
        )
        monitor_rect = win32api.GetMonitorInfo(monitor)["Monitor"]
    except Exception:
        return False

    left, top, right, bottom = rect
    mon_left, mon_top, mon_right, mon_bottom = monitor_rect
    return (
        left <= mon_left
        and top <= mon_top
        and right >= mon_right
        and bottom >= mon_bottom
    )


def get_visible_dock_actions(hwnd):
    current_idx, monitor_count = get_window_monitor_position(hwnd)
    visible_monitor_actions = set()

    if monitor_count > 1:
        if current_idx is None:
            visible_monitor_actions = set(MONITOR_MOVE_ACTIONS)
        else:
            if current_idx > 0:
                visible_monitor_actions.update({"FAR_LEFT", "LEFT"})
            if current_idx < monitor_count - 1:
                visible_monitor_actions.update({"RIGHT", "FAR_RIGHT"})

    visible_actions = tuple(
        action
        for action, _label in DOCK_ACTIONS
        if action not in MONITOR_MOVE_ACTIONS or action in visible_monitor_actions
    )

    if "MAXIMIZE" in visible_actions and not window_supports_maximize(hwnd):
        visible_actions = tuple(
            action for action in visible_actions if action != "MAXIMIZE"
        )

    return visible_actions


def move_window_to_monitor(hwnd, direction):
    try:
        monitors = win32api.EnumDisplayMonitors()
        if len(monitors) < 2:
            print("[MOVE] Only one monitor detected; skipping move.")
            return

        current_monitor = win32api.MonitorFromWindow(hwnd)
        monitor_handles = [monitor[0] for monitor in monitors]
        try:
            current_idx = monitor_handles.index(current_monitor)
        except ValueError:
            print("[MOVE] Could not resolve current monitor.")
            return

        target_idx = _resolve_target_monitor_index(
            current_idx,
            len(monitors),
            direction,
        )
        if target_idx == current_idx:
            return

        source_info = win32api.GetMonitorInfo(monitor_handles[current_idx])
        target_info = win32api.GetMonitorInfo(monitor_handles[target_idx])
        s_left, s_top, _, _ = source_info["Work"]
        t_left, t_top, t_right, t_bottom = target_info["Work"]

        placement = win32gui.GetWindowPlacement(hwnd)
        show_cmd = placement[1]
        was_maximized = show_cmd == win32con.SW_SHOWMAXIMIZED

        if show_cmd == win32con.SW_SHOWMINIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.02)

        if was_maximized:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.02)

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top

        rel_x = left - s_left
        rel_y = top - s_top
        max_x = max(t_left, t_right - width)
        max_y = max(t_top, t_bottom - height)
        new_x = min(max(t_left + rel_x, t_left), max_x)
        new_y = min(max(t_top + rel_y, t_top), max_y)

        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOP,
            new_x,
            new_y,
            width,
            height,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
        )

        if was_maximized:
            time.sleep(0.02)
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)

        print(f"[MOVE] Window moved {direction} to monitor index {target_idx}.")
    except Exception as exc:
        print(f"[ERROR] move_window_to_monitor: {exc}")


def minimize_window(hwnd):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    except Exception as exc:
        print(f"[ERROR] minimize_window: {exc}")


def maximize_window(hwnd):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    except Exception as exc:
        print(f"[ERROR] maximize_window: {exc}")


def perform_window_action(hwnd, action):
    if action == "MINIMIZE":
        minimize_window(hwnd)
        return
    if action == "MAXIMIZE":
        maximize_window(hwnd)
        return
    move_window_to_monitor(hwnd, action)


class DockOverlayButton:
    def __init__(self, worker, *, overlay_name=None):
        self.worker = worker
        self.hwnd = None
        self.target_hwnd = None
        self.rect = None
        self.visible = False
        self.visible_actions = tuple(action for action, _label in DOCK_ACTIONS)
        self.icon_theme = DOCK_ICON_DEFAULT_THEME
        normalized_name = "".join(
            character if str(character).isalnum() else "_"
            for character in str(overlay_name or id(self))
        )
        self._class_name = f"WindowsResurfaceDockOverlay_{normalized_name}_{id(self)}"
        self._wnd_proc = None
        self._icon_renderer = DockIconRenderer()

    def _ensure_window(self):
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            return

        hinstance = win32api.GetModuleHandle(None)
        self._wnd_proc = WNDPROC_TYPE(self._window_proc)

        wndclass = win32gui.WNDCLASS()
        wndclass.hInstance = hinstance
        wndclass.lpszClassName = self._class_name
        wndclass.lpfnWndProc = self._wnd_proc

        try:
            win32gui.RegisterClass(wndclass)
        except win32gui.error:
            pass

        self.hwnd = win32gui.CreateWindowEx(
            win32con.WS_EX_TOPMOST
            | win32con.WS_EX_TOOLWINDOW
            | win32con.WS_EX_LAYERED
            | win32con.WS_EX_TRANSPARENT,
            self._class_name,
            "",
            win32con.WS_POPUP,
            0,
            0,
            DOCK_WIDTH,
            DOCK_HEIGHT,
            0,
            0,
            hinstance,
            None,
        )
        win32gui.SetLayeredWindowAttributes(
            self.hwnd,
            DOCK_TRANSPARENT_COLOR,
            0,
            win32con.LWA_COLORKEY,
        )

    def preload_icons(self) -> None:
        self._icon_renderer.preload_themes(
            (DOCK_ICON_THEME_BLACK, DOCK_ICON_THEME_WHITE),
        )

    def _window_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == win32con.WM_PAINT:
                return self._paint(hwnd)

            if msg == win32con.WM_ERASEBKGND:
                return 1

            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
        except Exception as exc:
            print(f"[DOCK] WNDPROC error: {exc}")
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _icon_centers(self, left, right, icon_count):
        icon_count = max(0, int(icon_count))
        if icon_count == 0:
            return []
        if icon_count <= 1:
            return [left + ((right - left) / 2.0)]

        default_step = (right - left) / icon_count
        icon_step = max(1.0, default_step - DOCK_ICON_SPACING_REDUCTION)
        total_span = icon_step * (icon_count - 1)
        min_start = left + DOCK_SIDE_PADDING
        max_start = right - DOCK_SIDE_PADDING - total_span
        centered_start = left + (((right - left) - total_span) / 2.0)
        start = min(max(centered_start, min_start), max_start)
        return [start + (index * icon_step) for index in range(icon_count)]

    def _action_layout(self, left, right):
        actions = tuple(self.visible_actions)
        all_actions = tuple(action for action, _label in DOCK_ACTIONS)
        centers = self._icon_centers(left, right, len(all_actions))
        if not centers:
            return []

        icon_step = centers[1] - centers[0]
        center_by_action = dict(zip(all_actions, centers))

        return [
            (
                action,
                DOCK_ACTIONS_DICT[action],
                center_by_action[action],
                center_by_action[action] - (icon_step / 2.0),
                center_by_action[action] + (icon_step / 2.0),
            )
            for action in actions
            if action in center_by_action
        ]

    def _paint(self, hwnd):
        hdc, paint_struct = win32gui.BeginPaint(hwnd)

        try:
            left, top, right, bottom = win32gui.GetClientRect(hwnd)
            bg = win32gui.CreateSolidBrush(DOCK_TRANSPARENT_COLOR)
            win32gui.FillRect(hdc, (left, top, right, bottom), bg)
            win32gui.SetBkMode(hdc, win32con.TRANSPARENT)

            logfont = win32gui.LOGFONT()
            logfont.lfHeight = -18
            logfont.lfWeight = 700
            logfont.lfFaceName = "Segoe UI Symbol"
            logfont.lfQuality = getattr(win32con, "NONANTIALIASED_QUALITY", 3)
            font = win32gui.CreateFontIndirect(logfont)
            old_font = win32gui.SelectObject(hdc, font)

            vertical_center = (top + bottom) // 2
            for action, label, _center_x, seg_left, seg_right in self._action_layout(
                left,
                right,
            ):
                if self._icon_renderer.draw_action(hdc, action, self.icon_theme):
                    continue

                _text_width, text_height = win32gui.GetTextExtentPoint32(hdc, label)
                text_rect = (
                    int(seg_left),
                    int(vertical_center - (text_height / 2.0)),
                    int(seg_right),
                    int(vertical_center + (text_height / 2.0)),
                )

                win32gui.SetTextColor(hdc, DOCK_ARROW_COLOR)
                win32gui.DrawText(
                    hdc,
                    label,
                    -1,
                    text_rect,
                    win32con.DT_CENTER | win32con.DT_VCENTER | win32con.DT_SINGLELINE,
                )

            win32gui.SelectObject(hdc, old_font)
            win32gui.DeleteObject(font)
            win32gui.DeleteObject(bg)
        finally:
            win32gui.EndPaint(hwnd, paint_struct)

        return 0

    def show_for_target(self, target_hwnd, rect, actions):
        self._ensure_window()
        visible_actions = tuple(actions)
        if not visible_actions:
            self.hide()
            return

        left, top, right, _ = rect
        x = left + max(TITLE_BAR_SIDE_MARGIN, ((right - left) - DOCK_WIDTH) // 2)
        if self.worker.app_hwnd and target_hwnd == self.worker.app_hwnd:
            min_x = left + SELF_WINDOW_DOCK_TITLE_CLEARANCE
            max_x = right - DOCK_WIDTH
            x = min(max(x, min_x), max_x)
        y = top + DOCK_TOP_OFFSET
        try:
            placement = win32gui.GetWindowPlacement(target_hwnd)
            show_cmd = placement[1]
            if show_cmd != win32con.SW_SHOWMAXIMIZED:
                y = top + DOCK_RESTORED_TOP_OFFSET
        except Exception:
            pass
        new_rect = (x, y, x + DOCK_WIDTH, y + DOCK_HEIGHT)
        needs_theme_sample = (
            target_hwnd != self.target_hwnd
            or new_rect != self.rect
            or visible_actions != self.visible_actions
            or not self.visible
        )
        icon_theme = self.icon_theme
        if needs_theme_sample:
            current_theme = (
                self.icon_theme
                if self.visible
                and target_hwnd == self.target_hwnd
                and new_rect == self.rect
                else None
            )
            icon_theme = _dock_icon_theme_for_rect(new_rect, current_theme)
        should_update = (
            target_hwnd != self.target_hwnd
            or new_rect != self.rect
            or visible_actions != self.visible_actions
            or icon_theme != self.icon_theme
            or not self.visible
        )

        self.target_hwnd = target_hwnd
        self.rect = new_rect
        self.visible_actions = visible_actions
        self.icon_theme = icon_theme
        if not should_update:
            return

        win32gui.SetWindowPos(
            self.hwnd,
            win32con.HWND_TOPMOST,
            x,
            y,
            DOCK_WIDTH,
            DOCK_HEIGHT,
            win32con.SWP_SHOWWINDOW,
        )
        self.visible = True
        win32gui.InvalidateRect(self.hwnd, None, True)

    def contains_point(self, x, y):
        if not self.rect or not self.target_hwnd:
            return False

        left, top, right, bottom = self.rect
        return left <= x < right and top <= y < bottom

    def hit_test(self, x, y):
        if not self.contains_point(x, y):
            return None

        left, top, right, bottom = self.rect
        for action, _label, _center_x, seg_left, seg_right in self._action_layout(
            left,
            right,
        ):
            if seg_left <= x < seg_right:
                return action
        return None

    def hide(self):
        self.target_hwnd = None
        self.rect = None
        self.visible_actions = tuple(action for action, _label in DOCK_ACTIONS)
        self.icon_theme = DOCK_ICON_DEFAULT_THEME
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            win32gui.ShowWindow(self.hwnd, win32con.SW_HIDE)
        self.visible = False

    def destroy(self):
        self.target_hwnd = None
        self.rect = None
        self.visible = False
        self.visible_actions = tuple(action for action, _label in DOCK_ACTIONS)
        self.icon_theme = DOCK_ICON_DEFAULT_THEME
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            try:
                win32gui.DestroyWindow(self.hwnd)
            except win32gui.error:
                pass
        self.hwnd = None
        self._icon_renderer.dispose()


class ScreenMover:
    def __init__(
        self,
        *,
        name="ScreenMoverWorker",
        app_hwnd=None,
        self_action_dispatch: Callable[[str], None] | None = None,
    ):
        self.name = str(name).strip() or "ScreenMoverWorker"
        self.dock_overlay = DockOverlayButton(self, overlay_name=self.name)
        self.thread = None
        self.mouse_listener = None
        self.lock = threading.Lock()
        self.command_queue: queue.Queue[tuple[str, tuple]] = queue.Queue()
        self.stop_event = threading.Event()

        self.title_bar_dock_enabled = True
        self.activation_button = "middle"
        self.force_running = False
        self._desired_title_bar_dock_enabled = True
        self._desired_activation_button = "middle"
        self._desired_force_running = False
        self.app_hwnd = app_hwnd
        self.self_action_dispatch = self_action_dispatch
        self._last_title_bar_hwnd = None
        self._last_title_bar_rect = None
        self._suppress_dock_until = 0.0

    def configure(self, *, app_hwnd=None, self_action_dispatch=None, settings=None):
        state = settings or load_state()
        with self.lock:
            if app_hwnd is not None:
                self.app_hwnd = app_hwnd
            if self_action_dispatch is not None:
                self.self_action_dispatch = self_action_dispatch
            self._desired_activation_button = self._load_activation_button(state)
            self._desired_title_bar_dock_enabled = bool(
                state.get("title_bar_dock_enabled", True)
            )

    def refresh_from_state(self):
        state = load_state()
        self.update_settings(
            title_bar_dock_enabled=bool(state.get("title_bar_dock_enabled", True)),
            activation_button=self._load_activation_button(state),
        )

    def update_settings(
        self,
        *,
        title_bar_dock_enabled=None,
        activation_button=None,
        force_running=None,
    ):
        with self.lock:
            if title_bar_dock_enabled is not None:
                self._desired_title_bar_dock_enabled = bool(title_bar_dock_enabled)
            if activation_button is not None:
                self._desired_activation_button = self._normalize_activation_button(
                    activation_button
                )
            if force_running is not None:
                self._desired_force_running = bool(force_running)

            desired_dock = self._desired_title_bar_dock_enabled
            desired_button = self._desired_activation_button
            desired_force = self._desired_force_running
            thread = self.thread
            thread_alive = bool(thread and thread.is_alive())

        should_run = self._service_enabled(desired_dock, desired_button, desired_force)
        if should_run:
            if thread_alive:
                self._queue_command(
                    "settings",
                    desired_dock,
                    desired_button,
                    desired_force,
                )
            else:
                self.start()
            return

        if thread_alive:
            self._queue_command(
                "settings",
                desired_dock,
                desired_button,
                desired_force,
            )
        self.stop()

    def request_click(self, x, y, button):
        with self.lock:
            thread = self.thread
            thread_alive = bool(thread and thread.is_alive())

        if thread_alive:
            self._queue_command("click", x, y, button)

    def request_action(self, action):
        action_value = str(action or "").strip().upper()
        if action_value not in DOCK_ACTIONS_DICT:
            return

        with self.lock:
            thread = self.thread
            thread_alive = bool(thread and thread.is_alive())

        if thread_alive:
            self._queue_command("action", action_value)

    def _normalize_activation_button(self, button) -> str:
        button_value = str(button).strip().lower()
        if button_value in {"left", "middle", "right", "off"}:
            return button_value
        return "middle"

    def _service_enabled(
        self,
        title_bar_dock_enabled,
        activation_button,
        force_running=False,
    ) -> bool:
        return (
            bool(force_running)
            or bool(title_bar_dock_enabled)
            or activation_button != "off"
        )

    def _load_activation_button(self, state):
        button = str(state.get("screen_mover_activation_button", "")).strip().lower()
        if button in {"left", "middle", "right", "off"}:
            return button

        if "mmb_activation_enabled" in state:
            return "middle" if bool(state.get("mmb_activation_enabled", True)) else "off"

        return "middle"

    def _activation_button_matches(self, button) -> bool:
        mapping = {
            "left": mouse.Button.left,
            "middle": mouse.Button.middle,
            "right": mouse.Button.right,
        }
        expected = mapping.get(self.activation_button)
        return expected is not None and button == expected

    def _queue_command(self, command, *payload):
        self.command_queue.put((command, payload))

    def _pump_messages(self):
        try:
            win32gui.PumpWaitingMessages()
        except Exception:
            pass

    def _get_window_exe(self, hwnd):
        try:
            _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
            return psutil.Process(pid).name().lower()
        except Exception:
            return ""

    def _is_steam_game_window(self, hwnd):
        try:
            _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
            executable_path = psutil.Process(pid).exe()
        except Exception:
            return False
        return is_steam_game_executable(executable_path)

    def _is_file_explorer_window(self, hwnd):
        try:
            class_name = win32gui.GetClassName(hwnd)
        except Exception:
            return False
        return class_name in {"CabinetWClass", "ExploreWClass"}

    def _is_system_window(self, hwnd):
        exe = self._get_window_exe(hwnd)
        if exe == "explorer.exe" and self._is_file_explorer_window(hwnd):
            return False
        return exe in {
            "explorer.exe",
            "shellexperiencehost.exe",
            "startmenuexperiencehost.exe",
            "searchhost.exe",
            "widgets.exe",
            "dwm.exe",
        }

    def _is_owned_by_app(self, hwnd):
        if not self.app_hwnd or not hwnd or hwnd == self.app_hwnd:
            return False

        try:
            owner_hwnd = win32gui.GetWindow(hwnd, getattr(win32con, "GW_OWNER", 4))
        except Exception:
            return False

        return owner_hwnd == self.app_hwnd

    def _is_window_eligible(self, hwnd):
        if not hwnd or not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False
        if hwnd == self.app_hwnd or hwnd == self.dock_overlay.hwnd:
            return False
        if self._is_owned_by_app(hwnd):
            return False
        if self._is_system_window(hwnd):
            return False
        title = win32gui.GetWindowText(hwnd).strip()
        return bool(title)

    def _is_window_fullscreen(self, hwnd, rect=None):
        return window_is_fullscreen(hwnd, rect)

    def _is_self_window_eligible(self, hwnd):
        if not self.app_hwnd or hwnd != self.app_hwnd:
            return False
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False
        return True

    def _get_root_window(self, hwnd):
        if not hwnd:
            return None
        try:
            return win32gui.GetAncestor(hwnd, getattr(win32con, "GA_ROOT", 2))
        except Exception:
            return hwnd

    def _get_caption_height(self):
        return (
            win32api.GetSystemMetrics(win32con.SM_CYCAPTION)
            + win32api.GetSystemMetrics(win32con.SM_CYFRAME)
            + 8
        )

    def _is_left_button_pressed(self):
        try:
            return bool(win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000)
        except Exception:
            return False

    def _reset_title_bar_tracking(self):
        self._last_title_bar_hwnd = None
        self._last_title_bar_rect = None
        self._suppress_dock_until = 0.0

    def _track_title_bar_motion(self, hwnd, rect):
        now = time.monotonic()

        if hwnd != self._last_title_bar_hwnd:
            self._last_title_bar_hwnd = hwnd
            self._last_title_bar_rect = rect
            return False

        if rect != self._last_title_bar_rect:
            self._last_title_bar_rect = rect
            self._suppress_dock_until = now + WINDOW_MOVE_SETTLE_SECONDS
            return True

        return now < self._suppress_dock_until

    def _title_bar_candidate(self):
        try:
            cursor_x, cursor_y = win32gui.GetCursorPos()
            if self.dock_overlay.contains_point(cursor_x, cursor_y):
                hwnd = self.dock_overlay.target_hwnd
                if self._is_steam_game_window(hwnd):
                    return None, None
                rect = win32gui.GetWindowRect(hwnd)
                if self._is_window_fullscreen(hwnd, rect):
                    return None, None
                return hwnd, rect

            raw_hwnd = win32gui.WindowFromPoint((cursor_x, cursor_y))
        except Exception:
            return None, None

        hwnd = self._get_root_window(raw_hwnd)
        if not (self._is_window_eligible(hwnd) or self._is_self_window_eligible(hwnd)):
            return None, None
        if self._is_steam_game_window(hwnd):
            return None, None

        try:
            rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            return None, None

        if self._is_window_fullscreen(hwnd, rect):
            return None, None

        left, top, right, _ = rect
        width = right - left
        if width < (TITLE_BAR_SIDE_MARGIN * 2) + DOCK_WIDTH:
            return None, None

        caption_bottom = top + self._get_caption_height()
        if not (top <= cursor_y <= caption_bottom):
            return None, None

        if not (left + TITLE_BAR_SIDE_MARGIN <= cursor_x <= right - TITLE_BAR_BUTTON_GAP):
            return None, None

        if self._is_left_button_pressed():
            self._last_title_bar_hwnd = hwnd
            self._last_title_bar_rect = rect
            self._suppress_dock_until = time.monotonic() + WINDOW_MOVE_SETTLE_SECONDS
            return None, None

        if self._track_title_bar_motion(hwnd, rect):
            return None, None

        return hwnd, rect

    def _update_title_bar_dock(self):
        if not self.title_bar_dock_enabled:
            self.dock_overlay.hide()
            return

        hwnd, rect = self._title_bar_candidate()
        if not hwnd:
            self.dock_overlay.hide()
            return

        self.dock_overlay.show_for_target(
            hwnd,
            rect,
            self._visible_dock_actions(hwnd),
        )

    def _visible_dock_actions(self, hwnd):
        visible_actions = get_visible_dock_actions(hwnd)
        if hwnd == self.app_hwnd:
            return tuple(action for action in visible_actions if action != "MAXIMIZE")
        return visible_actions

    def _apply_settings(
        self,
        title_bar_dock_enabled,
        activation_button,
        force_running=False,
    ):
        self.title_bar_dock_enabled = bool(title_bar_dock_enabled)
        self.activation_button = self._normalize_activation_button(activation_button)
        self.force_running = bool(force_running)
        self._reset_title_bar_tracking()
        if not self.title_bar_dock_enabled:
            self.dock_overlay.hide()

    def _handle_click(self, x, y, button):
        if self.activation_button == "off" or not self._activation_button_matches(button):
            return

        direction = self.dock_overlay.hit_test(x, y)
        target = self.dock_overlay.target_hwnd
        if not direction or not target:
            return

        self.dock_overlay.hide()
        self._dispatch_window_action(target, direction)

    def _handle_action(self, action):
        target = self._foreground_action_target()
        if not target:
            return
        self._dispatch_window_action(target, action)

    def _foreground_action_target(self):
        try:
            hwnd = win32gui.GetForegroundWindow()
        except Exception:
            return None

        hwnd = self._get_root_window(hwnd)
        if not hwnd or hwnd == self.dock_overlay.hwnd:
            return None

        try:
            rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            rect = None

        if self._is_window_fullscreen(hwnd, rect):
            return None

        if self._is_window_eligible(hwnd) or self._is_self_window_eligible(hwnd):
            return hwnd
        return None

    def _dispatch_window_action(self, target_hwnd, action):
        if target_hwnd == self.app_hwnd:
            if action == "MAXIMIZE":
                return
            if callable(self.self_action_dispatch):
                try:
                    self.self_action_dispatch(action)
                except Exception as exc:
                    print(f"[SCREEN_MOVER] Failed to dispatch self action {action}: {exc}")
            else:
                print(
                    f"[SCREEN_MOVER] Missing GUI dispatch for self action {action}; ignoring."
                )
            return

        if not self._is_window_eligible(target_hwnd):
            return

        perform_window_action(target_hwnd, action)

    def _drain_command_queue(self):
        while True:
            try:
                command, payload = self.command_queue.get_nowait()
            except queue.Empty:
                return

            if command == "settings":
                self._apply_settings(*payload)
            elif command == "click":
                self._handle_click(*payload)
            elif command == "action":
                self._handle_action(*payload)
            elif command == "stop":
                self.stop_event.set()

    def worker_loop(self):
        print("[THREAD] Screen mover loop started.")

        with self.lock:
            desired_dock = self._desired_title_bar_dock_enabled
            desired_button = self._desired_activation_button
            desired_force = self._desired_force_running

        self._apply_settings(desired_dock, desired_button, desired_force)
        try:
            self.dock_overlay.preload_icons()
        except Exception as exc:
            print(f"[DOCK] Failed to preload dock icons: {exc}")

        try:
            while not self.stop_event.is_set():
                self._pump_messages()
                self._drain_command_queue()
                if self.stop_event.is_set():
                    break
                self._update_title_bar_dock()
                time.sleep(LOOP_SLEEP)
        except Exception as exc:
            print(f"[THREAD] Screen mover loop crashed: {exc}")
            traceback.print_exc()
        finally:
            try:
                self.dock_overlay.hide()
            except Exception as exc:
                print(f"[DOCK] Failed to hide overlay during shutdown: {exc}")

            try:
                self.dock_overlay.destroy()
            except Exception as exc:
                print(f"[DOCK] Failed to destroy overlay during shutdown: {exc}")

            with self.lock:
                if threading.current_thread() is self.thread:
                    self.thread = None

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return

            if not self._service_enabled(
                self._desired_title_bar_dock_enabled,
                self._desired_activation_button,
                self._desired_force_running,
            ):
                return

            self.stop_event = threading.Event()
            self.command_queue = queue.Queue()
            self.thread = threading.Thread(
                target=self.worker_loop,
                name=self.name,
                daemon=True,
            )
            self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
            thread = self.thread
            listener = self.mouse_listener

        thread.start()
        try:
            listener.start()
        except Exception as exc:
            print(f"[SCREEN_MOVER] Failed to start mouse listener: {exc}")
            self.stop()

    def stop(self):
        with self.lock:
            thread = self.thread
            thread_alive = bool(thread and thread.is_alive())
            listener = self.mouse_listener
            self.mouse_listener = None

            if not thread_alive:
                self.thread = None
            else:
                self.stop_event.set()
                self._queue_command("stop")

        if listener:
            try:
                listener.stop()
            except Exception as exc:
                print(f"[SCREEN_MOVER] Failed to stop mouse listener: {exc}")

        if thread_alive and thread is not None:
            thread.join(timeout=1.0)
            if thread.is_alive():
                print("[SCREEN_MOVER] Worker thread did not exit within 1.0s.")

    def on_mouse_click(self, x, y, button, pressed):
        if not pressed:
            return
        self.request_click(x, y, button)


ScreenMoverWorker = ScreenMover
SCREEN_MOVER = ScreenMover()

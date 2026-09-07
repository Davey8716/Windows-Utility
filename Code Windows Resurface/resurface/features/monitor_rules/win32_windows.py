"""Win32 discovery and placement operations for monitor rules."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

import psutil
import win32api
import win32con
import win32gui
import win32process

from .rule_schema import _clean_text, _normalize_path, normalize_monitor_rule


SYSTEM_EXECUTABLES = {
    "applicationframehost.exe",
    "dwm.exe",
    "explorer.exe",
    "searchhost.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "textinputhost.exe",
    "widgets.exe",
}


def enumerate_monitors() -> list[dict]:
    monitors = []
    for index, monitor_tuple in enumerate(win32api.EnumDisplayMonitors(), start=1):
        handle = monitor_tuple[0]
        info = win32api.GetMonitorInfo(handle)
        work = tuple(info["Work"])
        rect = tuple(info["Monitor"])
        device = _clean_text(info.get("Device")) or str(handle)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        primary = bool(info.get("Flags", 0) & 1)
        label = f"Monitor {index} - {width} x {height}"
        if primary:
            label += " (Primary)"
        monitors.append(
            {
                "handle": handle,
                "device": device,
                "label": label,
                "rect": rect,
                "work": work,
                "primary": primary,
            }
        )
    return monitors


def _monitor_by_device(device: str, monitors=None) -> dict | None:
    wanted = _clean_text(device).casefold()
    for monitor in monitors if monitors is not None else enumerate_monitors():
        if _clean_text(monitor.get("device")).casefold() == wanted:
            return monitor
    return None


def _process_details(hwnd) -> tuple[str, str, int, float]:
    try:
        _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        name = _clean_text(process.name()).casefold()
        try:
            path = _normalize_path(process.exe())
        except (psutil.Error, OSError):
            path = ""
        try:
            started_at = float(process.create_time())
        except (psutil.Error, OSError, TypeError, ValueError):
            started_at = 0.0
        return name, path, int(pid), started_at
    except (psutil.Error, OSError, win32gui.error):
        return "", "", 0, 0.0


def _is_cloaked(hwnd) -> bool:
    try:
        cloaked = wintypes.DWORD()
        result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd,
            14,  # DWMWA_CLOAKED
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )
        return result == 0 and bool(cloaked.value)
    except Exception:
        return False


def window_details(hwnd, *, app_hwnd=None) -> dict | None:
    """Return rule-matching details for an eligible top-level window.

    ``app_hwnd`` remains accepted for compatibility with existing callers, but the
    Windows Resurface window is deliberately eligible so the app can manage its
    own monitor placement.
    """
    try:
        if not hwnd or not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return None
        if win32gui.GetParent(hwnd):
            return None
        if win32gui.GetWindow(hwnd, getattr(win32con, "GW_OWNER", 4)):
            return None
        ex_style = int(win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE))
        if ex_style & win32con.WS_EX_TOOLWINDOW:
            return None
        if _is_cloaked(hwnd):
            return None
        title = _clean_text(win32gui.GetWindowText(hwnd))
        if not title:
            return None
        class_name = _clean_text(win32gui.GetClassName(hwnd))
    except (win32gui.error, OSError):
        return None

    executable_name, executable_path, process_id, process_started_at = _process_details(hwnd)
    if not executable_name:
        return None
    if executable_name in SYSTEM_EXECUTABLES:
        return None
    return {
        "hwnd": int(hwnd),
        "title": title,
        "class_name": class_name,
        "executable_name": executable_name,
        "executable_path": executable_path,
        "process_id": process_id,
        "process_started_at": process_started_at,
    }


def enumerate_eligible_windows(*, app_hwnd=None) -> list[dict]:
    windows = []

    def callback(hwnd, _extra):
        details = window_details(hwnd, app_hwnd=app_hwnd)
        if details is not None:
            windows.append(details)

    try:
        win32gui.EnumWindows(callback, None)
    except win32gui.error:
        return []
    windows.sort(key=lambda item: (item["executable_name"], item["title"].casefold()))
    return windows


def _window_placement_rect(hwnd) -> tuple[tuple, tuple[int, int, int, int]]:
    placement = win32gui.GetWindowPlacement(hwnd)
    show_command = placement[1]
    if show_command in (win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED):
        return placement, tuple(placement[4])
    return placement, tuple(win32gui.GetWindowRect(hwnd))


def capture_window_geometry(hwnd) -> dict | None:
    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] in (win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED):
            rect = tuple(placement[4])
        else:
            rect = tuple(win32gui.GetWindowRect(hwnd))
        monitor_handle = win32api.MonitorFromWindow(
            hwnd, getattr(win32con, "MONITOR_DEFAULTTONEAREST", 2)
        )
        work = tuple(win32api.GetMonitorInfo(monitor_handle)["Work"])
    except (win32gui.error, OSError):
        return None
    left, top, right, bottom = rect
    return {
        "x_offset": left - work[0],
        "y_offset": top - work[1],
        "width": max(1, right - left),
        "height": max(1, bottom - top),
    }


def _clamped_position(work, x, y, width, height) -> tuple[int, int]:
    left, top, right, bottom = work
    width = min(max(1, width), max(1, right - left))
    height = min(max(1, height), max(1, bottom - top))
    return min(max(x, left), right - width), min(max(y, top), bottom - height)


def window_monitor_device(hwnd) -> str:
    try:
        handle = win32api.MonitorFromWindow(
            hwnd, getattr(win32con, "MONITOR_DEFAULTTONEAREST", 2)
        )
        return _clean_text(win32api.GetMonitorInfo(handle).get("Device"))
    except (win32gui.error, OSError):
        return ""


def apply_monitor_rule(hwnd, rule: dict, *, monitors=None) -> bool:
    normalized = normalize_monitor_rule(rule)
    if normalized is None:
        return False
    try:
        available = enumerate_monitors() if monitors is None else monitors
        target = _monitor_by_device(normalized["target_device"], available)
        if target is None or not win32gui.IsWindow(hwnd):
            return False

        placement, rect = _window_placement_rect(hwnd)
        show_command = placement[1]
        left, top, right, bottom = rect
        width, height = max(1, right - left), max(1, bottom - top)
        target_work = tuple(target["work"])
        mode = normalized["placement_mode"]

        if mode == "saved_geometry":
            geometry = normalized["saved_geometry"]
            width = min(geometry["width"], target_work[2] - target_work[0])
            height = min(geometry["height"], target_work[3] - target_work[1])
            x = target_work[0] + geometry["x_offset"]
            y = target_work[1] + geometry["y_offset"]
        else:
            source_handle = win32api.MonitorFromWindow(
                hwnd, getattr(win32con, "MONITOR_DEFAULTTONEAREST", 2)
            )
            source_work = tuple(win32api.GetMonitorInfo(source_handle)["Work"])
            x = target_work[0] + (left - source_work[0])
            y = target_work[1] + (top - source_work[1])

        x, y = _clamped_position(target_work, x, y, width, height)
        if mode == "maximize" and show_command in (
            win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED
        ):
            if (
                show_command == win32con.SW_SHOWMAXIMIZED
                and window_monitor_device(hwnd).casefold()
                == normalized["target_device"].casefold()
            ):
                return True
            # Avoid a visible restore/maximize cycle, including taskbar restores.
            # Some apps ignore cross-monitor SetWindowPlacement, so retain the
            # existing move sequence unless the target monitor is confirmed.
            try:
                win32gui.SetWindowPlacement(
                    hwnd,
                    (
                        placement[0],
                        win32con.SW_SHOWMAXIMIZED,
                        placement[2],
                        (target_work[0], target_work[1]),
                        (x, y, x + width, y + height),
                    ),
                )
                if (
                    window_monitor_device(hwnd).casefold()
                    == normalized["target_device"].casefold()
                ):
                    return True
            except (win32gui.error, OSError):
                pass
        if show_command in (win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOP,
            x,
            y,
            width,
            height,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
        )
        if mode == "maximize":
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        return True
    except (win32gui.error, OSError, ValueError, KeyError) as exc:
        print(f"[MONITOR_RULES] Failed to place window {hwnd}: {exc}")
        return False


def _left_mouse_pressed() -> bool:
    try:
        return bool(win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000)
    except Exception:
        return False


def _window_exists(hwnd) -> bool:
    return bool(win32gui.IsWindow(hwnd))

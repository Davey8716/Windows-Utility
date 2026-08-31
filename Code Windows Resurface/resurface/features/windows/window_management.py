from __future__ import annotations

import ctypes
from collections.abc import Callable, Sequence
from typing import Literal

import win32con
import win32gui


WindowState = Literal["closed", "minimized", "open"]


def should_skip_window(hwnd: int, skip_hwnd: int) -> bool:
    if hwnd == skip_hwnd or not win32gui.IsWindowVisible(hwnd):
        return True
    title = win32gui.GetWindowText(hwnd)
    if not title.strip() or win32gui.GetParent(hwnd) != 0:
        return True
    try:
        class_name = win32gui.GetClassName(hwnd)
    except Exception:
        class_name = ""
    return class_name == "ApplicationFrameWindow" and title.strip().lower().startswith("settings")


def minimize_all_except_gui(skip_hwnd: int) -> None:
    def enum_handler(hwnd, _):
        if should_skip_window(hwnd, skip_hwnd):
            return
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception:
            pass

    win32gui.EnumWindows(enum_handler, None)


def restore_all_except_gui(skip_hwnd: int) -> None:
    def enum_handler(hwnd, _):
        if should_skip_window(hwnd, skip_hwnd):
            return
        try:
            if win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMINIMIZED:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        except Exception:
            pass

    win32gui.EnumWindows(enum_handler, None)


def _is_window_minimized(hwnd: int) -> bool:
    try:
        if win32gui.IsIconic(hwnd):
            return True
    except Exception:
        pass
    try:
        return win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMINIMIZED
    except Exception:
        return False


def _is_top_level_window(hwnd: int) -> bool:
    try:
        return bool(win32gui.IsWindow(hwnd)) and win32gui.GetParent(hwnd) == 0
    except Exception:
        return False


def _is_window_cloaked(hwnd: int) -> bool:
    cloaked = ctypes.c_int(0)
    try:
        result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            int(hwnd), 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        )
    except Exception:
        return False
    return result == 0 and bool(cloaked.value)


def _is_trackable_top_level_window(hwnd: int) -> bool:
    if not _is_top_level_window(hwnd) or _is_window_cloaked(hwnd):
        return False
    try:
        if win32gui.IsWindowVisible(hwnd):
            return True
    except Exception:
        pass
    return _is_window_minimized(hwnd)


def _title_matches_any_candidate(title: str, normalized_candidates: list[str]) -> bool:
    normalized_title = title.casefold()
    return any(
        normalized_title == candidate
        or normalized_title.endswith(f" - {candidate}")
        or candidate in normalized_title
        for candidate in normalized_candidates
    )


def find_windows_by_title_candidates(title_candidates: Sequence[str]) -> list[int]:
    normalized = [value.strip().casefold() for value in title_candidates if value and value.strip()]
    if not normalized:
        return []
    handles: list[int] = []

    def enum_handler(hwnd, _):
        if not _is_trackable_top_level_window(hwnd):
            return
        try:
            title = win32gui.GetWindowText(hwnd).strip()
        except Exception:
            title = ""
        if title and _title_matches_any_candidate(title, normalized):
            handles.append(hwnd)

    try:
        win32gui.EnumWindows(enum_handler, None)
    except Exception as exc:
        print(f"[DEBUG] find_windows_by_title_candidates failed: {exc}")
    return handles


def focus_window_handles(handles: Sequence[int]) -> bool:
    for hwnd in handles:
        try:
            command = win32con.SW_RESTORE if _is_window_minimized(hwnd) else win32con.SW_SHOW
            win32gui.ShowWindow(hwnd, command)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as exc:
            print(f"[DEBUG] focus_window_handles failed for hwnd {hwnd}: {exc}")
    return False


def maximize_window_handles(handles: Sequence[int]) -> bool:
    for hwnd in handles:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as exc:
            print(f"[DEBUG] maximize_window_handles failed for hwnd {hwnd}: {exc}")
    return False


def close_window_handles(handles: Sequence[int]) -> bool:
    closed_any = False
    for hwnd in handles:
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            closed_any = True
        except Exception as exc:
            print(f"[DEBUG] close_window_handles failed for hwnd {hwnd}: {exc}")
    return closed_any


def get_window_state_for_handles(handles: Sequence[int]) -> WindowState:
    trackable = [hwnd for hwnd in handles if _is_trackable_top_level_window(hwnd)]
    if not trackable:
        return "closed"
    minimized_found = False
    for hwnd in trackable:
        try:
            if not _is_window_minimized(hwnd):
                return "open"
            minimized_found = True
        except Exception:
            continue
    return "minimized" if minimized_found else "closed"


class WindowManagementService:
    def find_by_titles(self, title_candidates: Sequence[str]) -> list[int]:
        return find_windows_by_title_candidates(title_candidates)

    def focus_handles(self, handles: Sequence[int]) -> bool:
        return focus_window_handles(handles)

    def maximize_handles(self, handles: Sequence[int]) -> bool:
        return maximize_window_handles(handles)

    def close_handles(self, handles: Sequence[int]) -> bool:
        return close_window_handles(handles)

    def state_for_handles(self, handles: Sequence[int]) -> WindowState:
        return get_window_state_for_handles(handles)

    def open_or_focus_titles(self, title_candidates: Sequence[str], launch: Callable[[], object]) -> bool:
        if self.focus_handles(self.find_by_titles(title_candidates)):
            return True
        try:
            launch()
            return True
        except Exception as exc:
            print(f"[DEBUG] open_or_focus_window_titles failed for {title_candidates}: {exc}")
            return False

    def close_titles(self, title_candidates: Sequence[str]) -> bool:
        return self.close_handles(self.find_by_titles(title_candidates))

    def focus_titles(self, title_candidates: Sequence[str]) -> bool:
        return self.focus_handles(self.find_by_titles(title_candidates))

    def maximize_titles(self, title_candidates: Sequence[str]) -> bool:
        return self.maximize_handles(self.find_by_titles(title_candidates))

    def get_titles_state(self, title_candidates: Sequence[str]) -> WindowState:
        return self.state_for_handles(self.find_by_titles(title_candidates))

    def minimize_all_except(self, skip_hwnd: int) -> None:
        minimize_all_except_gui(skip_hwnd)

    def restore_all_except(self, skip_hwnd: int) -> None:
        restore_all_except_gui(skip_hwnd)

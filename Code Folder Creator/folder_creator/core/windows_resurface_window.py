"""Windows-specific helpers for returning to the Windows Resurface window."""

import ctypes
from ctypes import wintypes


WINDOW_TITLE = "Windows Resurface"
SW_RESTORE = 9


def focus_windows_resurface() -> bool:
    """Restore and foreground the running Windows Resurface main window."""
    user32 = ctypes.windll.user32
    matching_windows: list[int] = []

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def find_window(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title_length = user32.GetWindowTextLengthW(hwnd)
        if title_length <= 0:
            return True
        title = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title, len(title))
        if title.value == WINDOW_TITLE:
            matching_windows.append(hwnd)
            return False
        return True

    try:
        user32.EnumWindows(find_window, 0)
        if not matching_windows:
            return False
        hwnd = matching_windows[0]
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        return False
    return True

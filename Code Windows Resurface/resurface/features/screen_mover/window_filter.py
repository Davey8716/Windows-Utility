"""Window and process eligibility helpers for Screen Mover."""

from __future__ import annotations

import psutil
import win32con
import win32gui
import win32process


SYSTEM_EXECUTABLES = {
    "explorer.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "searchhost.exe",
    "widgets.exe",
    "dwm.exe",
}
FILE_EXPLORER_CLASSES = {"CabinetWClass", "ExploreWClass"}


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


def get_window_executable_name(hwnd):
    try:
        _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name().lower()
    except Exception:
        return ""


def is_steam_game_window(hwnd):
    try:
        _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        executable_path = psutil.Process(pid).exe()
    except Exception:
        return False
    return is_steam_game_executable(executable_path)


def is_file_explorer_window(hwnd):
    try:
        class_name = win32gui.GetClassName(hwnd)
    except Exception:
        return False
    return class_name in FILE_EXPLORER_CLASSES


def is_system_window(
    hwnd,
    *,
    executable_name_getter=get_window_executable_name,
    file_explorer_check=is_file_explorer_window,
):
    executable_name = executable_name_getter(hwnd)
    if executable_name == "explorer.exe" and file_explorer_check(hwnd):
        return False
    return executable_name in SYSTEM_EXECUTABLES


def is_owned_by_app(hwnd, app_hwnd):
    if not app_hwnd or not hwnd or hwnd == app_hwnd:
        return False

    try:
        owner_hwnd = win32gui.GetWindow(hwnd, getattr(win32con, "GW_OWNER", 4))
    except Exception:
        return False

    return owner_hwnd == app_hwnd


def is_window_eligible(
    hwnd,
    *,
    app_hwnd=None,
    dock_hwnd=None,
    owned_by_app_check=None,
    system_window_check=None,
):
    if not hwnd or not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
        return False
    if hwnd == app_hwnd or hwnd == dock_hwnd:
        return False
    owned_by_app_check = owned_by_app_check or (
        lambda candidate: is_owned_by_app(candidate, app_hwnd)
    )
    system_window_check = system_window_check or is_system_window
    if owned_by_app_check(hwnd):
        return False
    if system_window_check(hwnd):
        return False
    title = win32gui.GetWindowText(hwnd).strip()
    return bool(title)


def is_self_window_eligible(hwnd, app_hwnd):
    if not app_hwnd or hwnd != app_hwnd:
        return False
    if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
        return False
    return True


def get_root_window(hwnd):
    if not hwnd:
        return None
    try:
        return win32gui.GetAncestor(hwnd, getattr(win32con, "GA_ROOT", 2))
    except Exception:
        return hwnd

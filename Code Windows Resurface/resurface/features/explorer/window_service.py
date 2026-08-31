from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pythoncom
import win32com.client
import win32gui

from resurface.features.windows.window_management import WindowManagementService


def normalize_folder_path(path: str | None) -> str:
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.abspath(path))
    except Exception:
        return str(path).strip().casefold()


def _get_shell_window_folder_path(window) -> str:
    try:
        return str(getattr(window.Document.Folder.Self, "Path", "") or "")
    except Exception:
        return ""


def _is_explorer_folder_window(hwnd: int, folder_name: str) -> bool:
    try:
        if not win32gui.IsWindowVisible(hwnd):
            return False
    except Exception:
        return False
    try:
        class_name = win32gui.GetClassName(hwnd)
    except Exception:
        class_name = ""
    if class_name not in {"CabinetWClass", "ExploreWClass"}:
        return False
    try:
        title = win32gui.GetWindowText(hwnd).strip()
    except Exception:
        title = ""
    normalized_title = title.casefold()
    normalized_name = folder_name.casefold()
    return bool(title) and (
        normalized_title == normalized_name
        or normalized_title.endswith(f" - {normalized_name}")
        or normalized_name in normalized_title
    )


class ExplorerWindowService:
    def __init__(self, windows: WindowManagementService):
        self.windows = windows

    def find_by_title(self, title: str) -> list[int]:
        normalized_title = title.strip()
        if not normalized_title:
            return []
        handles: list[int] = []

        def enum_handler(hwnd, _):
            if _is_explorer_folder_window(hwnd, normalized_title):
                handles.append(hwnd)

        try:
            win32gui.EnumWindows(enum_handler, None)
        except Exception as exc:
            print(f"[DEBUG] find_explorer_windows_by_title failed: {exc}")
        return handles

    def find_for_folder(self, path: str) -> list[int]:
        normalized_target = normalize_folder_path(path)
        if not normalized_target:
            return []
        handles: list[int] = []
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass
        try:
            shell_windows = win32com.client.Dispatch("Shell.Application").Windows()
        except Exception as exc:
            print(f"[DEBUG] find_explorer_windows_for_folder failed: {exc}")
            shell_windows = []
        for window in shell_windows:
            try:
                hwnd = int(window.HWND)
            except Exception:
                continue
            folder_path = _get_shell_window_folder_path(window)
            if folder_path and normalize_folder_path(folder_path) == normalized_target:
                handles.append(hwnd)
        if handles:
            return handles
        folder_name = Path(path).name.strip()
        return self.find_by_title(folder_name) if folder_name else []

    def focus_folder(self, path: str) -> bool:
        return self.windows.focus_handles(self.find_for_folder(path))

    def is_folder_open(self, path: str) -> bool:
        return bool(self.find_for_folder(path))

    def close_folder(self, path: str) -> bool:
        return self.windows.close_handles(self.find_for_folder(path))

    def open_or_focus_folder(self, path: str, launch: Callable[[], object] | None = None) -> bool:
        normalized = normalize_folder_path(path)
        if not normalized:
            return False
        if self.windows.focus_handles(self.find_for_folder(normalized)):
            return True
        try:
            launch() if launch is not None else os.startfile(normalized)
            return True
        except Exception as exc:
            print(f"[DEBUG] open_or_focus_folder_path failed for {normalized}: {exc}")
            return False

    def open_or_focus_title(self, title: str, launch: Callable[[], object]) -> bool:
        if self.windows.focus_handles(self.find_by_title(title)):
            return True
        try:
            launch()
            return True
        except Exception as exc:
            print(f"[DEBUG] open_or_focus_explorer_title failed for {title}: {exc}")
            return False

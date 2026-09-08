"""Compatibility facade for utility actions while callers migrate to services."""

from __future__ import annotations

import ctypes
import os

from PySide6.QtCore import Qt

from resurface.features.desktop.desktop_icon_layout import restore_desktop_icon_layout, save_desktop_icon_layout
from resurface.features.desktop.zen_mode import ZenModeService
from resurface.features.explorer.window_service import ExplorerWindowService
from resurface.features.recycle_bin.service import RecycleBinService
from resurface.features.system.router_service import RouterService
from resurface.features.taskbar.backup_service import TaskbarBackupService
from resurface.features.windows.window_management import WindowManagementService


class UtilityActionsManager:
    """Legacy app adapter; new consumers should depend on focused services."""

    def __init__(self, app=None, *, windows=None, explorer=None, recycle_bin=None, taskbar_backup=None, zen_mode=None, router=None):
        self.app = app
        self.windows = windows or WindowManagementService()
        self.explorer = explorer or ExplorerWindowService(self.windows)
        self.recycle_bin = recycle_bin or RecycleBinService(self.windows)
        self.taskbar_backup = taskbar_backup or TaskbarBackupService()
        self.zen_mode = zen_mode or ZenModeService()
        self.router = router or RouterService()

    def _save_settings(self) -> None:
        save = getattr(self.app, "save_all_settings", None)
        if callable(save):
            save()

    def _default_path(self, method_name: str) -> str | None:
        resolver = getattr(self.app, method_name, None)
        return resolver() if callable(resolver) else None

    def _main_window_handle(self) -> int | None:
        if self.app and hasattr(self.app, "winId"):
            return int(self.app.winId())
        if self.app and hasattr(self.app, "winfo_id"):
            child_hwnd = self.app.winfo_id()
            parent_hwnd = ctypes.windll.user32.GetParent(child_hwnd)
            return parent_hwnd if parent_hwnd else child_hwnd
        return None

    def toggle_power_buttons(self, enabled: bool | None = None):
        if enabled is None:
            enabled = bool(getattr(getattr(self.app, "power_toggle_var", None), "get", lambda: False)())
        self._save_settings()
        return enabled

    def open_router_page(self) -> str | None:
        return self.router.open_router_page()

    def maximize_all_toggle(self, enabled: bool | None = None):
        if enabled is None:
            maximize_var = getattr(self.app, "maximize_all_var", None)
            enabled = bool(getattr(maximize_var, "get", lambda: True)()) if maximize_var is not None else not bool(getattr(getattr(self.app, "minimize_all_var", None), "get", lambda: False)())
        print(f"[INFO] Maximize All toggled -> {enabled}")
        hwnd = self._main_window_handle()
        if hwnd:
            (self.windows.restore_all_except if enabled else self.windows.minimize_all_except)(hwnd)
        self._save_settings()
        return enabled

    def usb_reminder_toggle(self, enabled: bool | None = None):
        if enabled is None:
            enabled = bool(getattr(getattr(self.app, "usb_reminder_var", None), "get", lambda: False)())
        if self.app:
            self.app.usb_reminder_enabled = enabled
        self._save_settings()
        return enabled

    def theme_toggle(self, dark_mode: bool | None = None):
        if dark_mode is None:
            dark_mode = bool(getattr(getattr(self.app, "theme_var", None), "get", lambda: False)())
        if self.app:
            self.app.dark_mode_enabled = dark_mode
        self._save_settings()
        return dark_mode

    def tooltips_toggle(self, enabled: bool | None = None):
        if enabled is None:
            enabled = bool(getattr(getattr(self.app, "tooltips_enabled_var", None), "get", lambda: False)())
        if self.app:
            self.app.tooltips_enabled = enabled
        self._save_settings()
        return enabled

    def always_on_top_toggle(self, enabled: bool | None = None):
        if enabled is None:
            enabled = bool(getattr(getattr(self.app, "always_on_top_var", None), "get", lambda: False)())
        if self.app:
            self.app.main_always_on_top_enabled = enabled
            self.app.right_always_on_top_enabled = enabled
            apply_topmost = getattr(self.app, "_set_main_window_topmost_state", None)
            if callable(apply_topmost):
                apply_topmost(enabled)
            elif hasattr(self.app, "setWindowFlag"):
                self.app.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
                self.app.show()
        self._save_settings()
        return enabled

    def backup_pinned_shortcuts(self, backup_folder: str | None = None) -> int:
        backup_folder = backup_folder or self._default_path("get_default_taskbar_backup_dir")
        if not backup_folder:
            print("[BACKUP] ERROR: No backup folder provided")
            return 0
        backup = getattr(self.taskbar_backup, "backup", None)
        if callable(backup):
            result = backup(backup_folder)
            if result.completed:
                self._save_settings()
            return result.count
        count = self.taskbar_backup.backup_pinned_shortcuts(backup_folder)
        self._save_settings()
        return count

    def open_recycle_bin(self) -> bool:
        return self.recycle_bin.open()

    def empty_recycle_bin(self) -> bool:
        return self.recycle_bin.empty()

    def cleanup_recycle_bin_items_older_than(self, days: int) -> int:
        return self.recycle_bin.cleanup_items_older_than(days)

    def is_recycle_bin_open(self) -> bool:
        return self.recycle_bin.is_open()

    def close_recycle_bin(self) -> bool:
        return self.recycle_bin.close()

    def _resolve_backup_folder(self, path: str | None) -> str | None:
        return path or self._default_path("get_default_taskbar_backup_dir")

    def open_backup_folder(self, path: str | None = None) -> bool:
        path = self._resolve_backup_folder(path)
        if not path:
            print("[DEBUG] open_backup_folder: no path resolved")
            return False
        if self.explorer.focus_folder(path):
            return True
        try:
            os.makedirs(path, exist_ok=True)
            os.startfile(path)
            return True
        except Exception as exc:
            print(f"[DEBUG] open_backup_folder failed: {exc}")
            return False

    def focus_backup_folder(self, path: str | None = None) -> bool:
        path = self._resolve_backup_folder(path)
        return self.explorer.focus_folder(path) if path else False

    def open_or_focus_folder_path(self, path: str, launch=None) -> bool:
        return self.explorer.open_or_focus_folder(path, launch)

    def is_backup_folder_open(self, path: str | None = None) -> bool:
        path = self._resolve_backup_folder(path)
        return self.explorer.is_folder_open(path) if path else False

    def close_backup_folder(self, path: str | None = None) -> bool:
        path = self._resolve_backup_folder(path)
        return self.explorer.close_folder(path) if path else False

    def capture_desktop_layout(self, out_path: str | None = None) -> int:
        out_path = out_path or self._default_path("get_default_desktop_layout_path")
        if not out_path:
            return 0
        try:
            count = save_desktop_icon_layout(out_path)
            if self.app and hasattr(self.app, "saved_state"):
                self.app.saved_state["desktop_layout_last_path"] = out_path
            self._save_settings()
            return count
        except Exception as exc:
            print("[DESKTOP ICONS] Capture failed:", exc)
            return 0

    def restore_desktop_layout(self, path: str | None = None) -> int:
        path = path or self._default_path("get_default_desktop_layout_path")
        if not path:
            return 0
        try:
            count = restore_desktop_icon_layout(path)
            self._save_settings()
            return count
        except Exception as exc:
            print("[DESKTOP ICONS] Restore failed:", exc)
            return 0

    def desktop_zen_mode_toggle(self, enabled: bool | None = None) -> bool | None:
        if enabled is None:
            enabled = bool(getattr(getattr(self.app, "desktop_zen_mode_var", None), "get", lambda: False)())
        result = self.zen_mode.set_enabled(enabled)
        if result is None:
            return None
        if self.app:
            self.app.desktop_zen_mode_enabled = enabled
        self._save_settings()
        return result

    def minimize_all_toggle(self, enabled: bool | None = None):
        if enabled is None:
            enabled = bool(getattr(getattr(self.app, "minimize_all_var", None), "get", lambda: False)())
        self.maximize_all_toggle(not enabled)
        return enabled

    def desktop_icons_visible(self) -> bool | None:
        return self.zen_mode.icons_visible()

    def open_or_focus_explorer_title(self, title: str, launch) -> bool:
        return self.explorer.open_or_focus_title(title, launch)

    def open_or_focus_window_titles(self, title_candidates, launch) -> bool:
        return self.windows.open_or_focus_titles(title_candidates, launch)

    def close_window_titles(self, title_candidates) -> bool:
        return self.windows.close_titles(title_candidates)

    def focus_window_titles(self, title_candidates) -> bool:
        return self.windows.focus_titles(title_candidates)

    def maximize_window_titles(self, title_candidates) -> bool:
        return self.windows.maximize_titles(title_candidates)

    def get_window_titles_state(self, title_candidates) -> str:
        return self.windows.get_titles_state(title_candidates)


def theme_intent(dark_mode: bool) -> bool:
    print(f"[THEME] Theme intent set -> {'Dark' if dark_mode else 'Light'}")
    return dark_mode


def usb_reminder_intent(enabled: bool) -> bool:
    print(f"[INFO] USB Reminder intent -> {enabled}")
    return enabled

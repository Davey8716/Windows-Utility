import subprocess
import webbrowser
import ctypes
import win32gui
import win32con
import os
import shutil
from pathlib import Path
from PySide6.QtCore import Qt

from screen_mover import SCREEN_MOVER
from desktop_icon_layout import save_desktop_icon_layout
from desktop_icon_layout import restore_desktop_icon_layout


class UtilityActionsManager:
    def __init__(self, app=None):
        """
        Qt-aligned utility actions manager.

        NOTE:
        - app is optional to keep compatibility while migrating.
        - Do NOT call Tk/CTk widget methods here.
        """
        self.app = app

    def toggle_power_buttons(self, enabled: bool | None = None):
        """
        Qt-aligned:
        - If 'enabled' is provided, use it.
        - Else (compat), attempt to read from self.app.power_toggle_var if present.
        - Returns: enabled (bool)

        UI layer is responsible for:
        - show/hide right column
        - button styling / visibility
        - label text updates
        """
        if enabled is None:
            enabled = bool(getattr(getattr(self.app, "power_toggle_var", None), "get", lambda: False)())

        if self.app and hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

        return enabled

    def open_router_page(self) -> str | None:
        """
        Auto-detect default gateway and open router page in browser.

        Returns:
            gateway (str) if opened, else None
        """
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            result = subprocess.check_output(
                "ipconfig",
                text=True,
                errors="ignore",
                startupinfo=startupinfo,
            )

            gateway = None
            for line in result.splitlines():
                if "Default Gateway" in line:
                    parts = line.split(":")
                    if len(parts) > 1:
                        gw = parts[1].strip()
                        if gw and gw != "0.0.0.0":
                            gateway = gw
                            break

            if gateway:
                webbrowser.open(f"http://{gateway}")
                print(f"[ROUTER] Opening router at {gateway}")
                return gateway

            print("[ROUTER] No default gateway found")
            return None

        except Exception as e:
            print("[ROUTER] Failed:", e)
            return None

    def minimize_all_toggle(self, enabled: bool | None = None):
        if enabled is None:
            enabled = bool(
                getattr(
                    getattr(self.app, "minimize_all_var", None),
                    "get",
                    lambda: False
                )()
            )

        print(f"[INFO] Min/Max All toggled → {enabled}")

        hwnd = None
        if self.app and hasattr(self.app, "winId"):
            # Qt window
            hwnd = int(self.app.winId())
        elif self.app and hasattr(self.app, "winfo_id"):
            # Legacy Tk window (migration only)
            child_hwnd = self.app.winfo_id()
            parent_hwnd = ctypes.windll.user32.GetParent(child_hwnd)
            hwnd = parent_hwnd if parent_hwnd else child_hwnd

        if hwnd:
            if enabled:
                minimize_all_except_gui(hwnd)
            else:
                restore_all_except_gui(hwnd)

        if self.app and hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

        return enabled

    def usb_reminder_toggle(self, enabled: bool | None = None):
        if enabled is None:
            enabled = bool(
                getattr(
                    getattr(self.app, "usb_reminder_var", None),
                    "get",
                    lambda: False
                )()
            )

        if self.app:
            setattr(self.app, "usb_reminder_enabled", enabled)

        if self.app and hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

        return enabled

    def theme_toggle(self, dark_mode: bool | None = None):
        if dark_mode is None:
            dark_mode = bool(
                getattr(
                    getattr(self.app, "theme_var", None),
                    "get",
                    lambda: False
                )()
            )

        if self.app:
            setattr(self.app, "dark_mode_enabled", dark_mode)

        if self.app and hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

        return dark_mode

    def tooltips_toggle(self, enabled: bool | None = None):
        if enabled is None:
            enabled = bool(
                getattr(
                    getattr(self.app, "tooltips_enabled_var", None),
                    "get",
                    lambda: False
                )()
            )

        if self.app:
            self.app.tooltips_enabled = enabled

        if self.app and hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

        return enabled

    def always_on_top_toggle(self, enabled: bool | None = None):
        if enabled is None:
            enabled = bool(
                getattr(
                    getattr(self.app, "always_on_top_var", None),
                    "get",
                    lambda: False
                )()
            )

        if self.app:
            self.app.main_always_on_top_enabled = enabled
            self.app.right_always_on_top_enabled = enabled

            # Qt window handling (preferred)
            if hasattr(self.app, "setWindowFlag"):
                self.app.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
                self.app.show()

        if self.app and hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

        return enabled

    def backup_pinned_shortcuts(self, backup_folder: str | None = None) -> int:
        print("[BACKUP] Starting backup of pinned shortcuts…")

        pinned_path = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"
        )

        if not os.path.isdir(pinned_path):
            print("[BACKUP] ERROR: Pinned folder not found:", pinned_path)
            return 0

        if backup_folder is None and self.app:
            backup_folder = getattr(
                self.app,
                "get_default_taskbar_backup_dir",
                lambda: None
            )()

        if not backup_folder:
            print("[BACKUP] ERROR: No backup folder provided")
            return 0

        try:
            os.makedirs(backup_folder, exist_ok=True)
        except Exception as e:
            print("[BACKUP] ERROR: Cannot create backup folder:", e)
            return 0

        count = 0
        for name in os.listdir(pinned_path):
            if name.lower().endswith(".lnk"):
                src = os.path.join(pinned_path, name)
                dst = os.path.join(backup_folder, name)
                try:
                    shutil.copy2(src, dst)
                    count += 1
                except Exception as e:
                    print(f"[BACKUP] Failed to copy {name}: {e}")

        print(f"[BACKUP] Completed. {count} shortcuts copied.")

        if self.app and hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

        return count

    def open_backup_folder(self, path: str | None = None) -> bool:
        if path is None and self.app:
            path = getattr(
                self.app,
                "get_default_taskbar_backup_dir",
                lambda: None
            )()

        if not path:
            print("[DEBUG] open_backup_folder: no path resolved")
            return False

        try:
            os.makedirs(path, exist_ok=True)
            os.startfile(path)
            return True
        except Exception as e:
            print(f"[DEBUG] open_backup_folder failed: {e}")
            return False

    def is_backup_folder_open(self, path: str | None = None) -> bool:
        resolved_path = _resolve_backup_folder_path(path, self.app)
        if not resolved_path:
            return False

        return bool(find_explorer_windows_for_folder(resolved_path))

    def close_backup_folder(self, path: str | None = None) -> bool:
        resolved_path = _resolve_backup_folder_path(path, self.app)
        if not resolved_path:
            return False

        handles = find_explorer_windows_for_folder(resolved_path)
        closed_any = False
        for hwnd in handles:
            try:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                closed_any = True
            except Exception as e:
                print(f"[DEBUG] close_backup_folder failed for hwnd {hwnd}: {e}")

        return closed_any

    def capture_desktop_layout(self, out_path: str | None = None) -> int:
        if not out_path and self.app:
            out_path = getattr(
                self.app,
                "get_default_desktop_layout_path",
                lambda: None
            )()

        if not out_path:
            return 0

        try:
            count = save_desktop_icon_layout(out_path)

            if self.app:
                if hasattr(self.app, "saved_state"):
                    self.app.saved_state["desktop_layout_last_path"] = out_path

                if hasattr(self.app, "save_all_settings"):
                    self.app.save_all_settings()

            return count

        except Exception as e:
            print("[DESKTOP ICONS] Capture failed:", e)
            return 0

    def restore_desktop_layout(self, path: str | None = None) -> int:
        if not path and self.app:
            path = getattr(
                self.app,
                "get_default_desktop_layout_path",
                lambda: None
            )()

        if not path:
            return 0

        try:
            count = restore_desktop_icon_layout(path)

            if self.app and hasattr(self.app, "save_all_settings"):
                self.app.save_all_settings()

            return count

        except Exception as e:
            print("[DESKTOP ICONS] Restore failed:", e)
            return 0

def _should_skip(hwnd: int, skip_hwnd: int) -> bool:
    if hwnd == skip_hwnd:
        return True

    if not win32gui.IsWindowVisible(hwnd):
        return True

    title = win32gui.GetWindowText(hwnd)
    if not title.strip():
        return True

    if win32gui.GetParent(hwnd) != 0:
        return True

    try:
        class_name = win32gui.GetClassName(hwnd)
    except Exception:
        class_name = ""

    normalized_title = title.strip().lower()
    if class_name == "ApplicationFrameWindow" and normalized_title.startswith("settings"):
        return True

    return False

def minimize_all_except_gui(skip_hwnd: int) -> None:
    def enum_handler(hwnd, _):
        if _should_skip(hwnd, skip_hwnd):
            return
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception:
            pass

    win32gui.EnumWindows(enum_handler, None)

def restore_all_except_gui(skip_hwnd: int) -> None:
    def enum_handler(hwnd, _):
        if _should_skip(hwnd, skip_hwnd):
            return

        try:
            placement = win32gui.GetWindowPlacement(hwnd)
            show_cmd = placement[1]
            if show_cmd == win32con.SW_SHOWMINIMIZED:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        except Exception:
            pass

    win32gui.EnumWindows(enum_handler, None)

def theme_intent(dark_mode: bool) -> bool:
    print(f"[THEME] Theme intent set → {'Dark' if dark_mode else 'Light'}")
    return dark_mode

def usb_reminder_intent(enabled: bool) -> bool:
    print(f"[INFO] USB Reminder intent → {enabled}")
    return enabled

def mover_options_intent(enabled: bool) -> bool:
    print(f"[INFO] Screen Mover options intent → {enabled}")
    return enabled


def _resolve_backup_folder_path(path: str | None, app=None) -> str | None:
    if path:
        return path

    if app:
        return getattr(
            app,
            "get_default_taskbar_backup_dir",
            lambda: None
        )()

    return None


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

    if not title:
        return False

    normalized_title = title.casefold()
    normalized_folder_name = folder_name.casefold()
    return (
        normalized_title == normalized_folder_name
        or normalized_title.endswith(f" - {normalized_folder_name}")
        or normalized_folder_name in normalized_title
    )


def find_explorer_windows_for_folder(path: str) -> list[int]:
    folder_name = Path(path).name.strip()
    if not folder_name:
        return []

    handles: list[int] = []

    def enum_handler(hwnd, _):
        if _is_explorer_folder_window(hwnd, folder_name):
            handles.append(hwnd)

    try:
        win32gui.EnumWindows(enum_handler, None)
    except Exception as e:
        print(f"[DEBUG] find_explorer_windows_for_folder failed: {e}")

    return handles

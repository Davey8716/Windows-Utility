import subprocess
import webbrowser
import ctypes
import win32gui
import win32con
import os
import shutil
from PySide6.QtCore import Qt

from screen_mover import SCREEN_MOVER
from desktop_icon_layout import save_desktop_icon_layout
from desktop_icon_layout import restore_desktop_icon_layout


# ===================================================================
#  Utility Actions Manager (Qt-aligned: no Tk/CTk imports)
#  - This file may still be called by the Qt UI layer.
#  - UI widgets / layouts are not manipulated here.
# ===================================================================

class UtilityActionsManager:
    def __init__(self, app=None):
        """
        Qt-aligned utility actions manager.

        NOTE:
        - app is optional to keep compatibility while migrating.
        - Do NOT call Tk/CTk widget methods here.
        """
        self.app = app

    # ===================================================================
    #  Power Buttons Toggle
    # ===================================================================
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
            # Back-compat during migration (remove later)
            enabled = bool(getattr(getattr(self.app, "power_toggle_var", None), "get", lambda: False)())

        # Persist via app if available (Qt layer can own this later)
        if self.app and hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

        return enabled

    # ===================================================================
    #  Router Auto-Detect & Open
    # ===================================================================
    def open_router_page(self) -> str | None:
        """
        Auto-detect default gateway and open router page in browser.

        Returns:
            gateway (str) if opened, else None
        """
        try:
            result = subprocess.check_output("ipconfig", text=True, errors="ignore")

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


    # ===================================================================
    #  Minimize / Restore All Windows Except GUI
    # ===================================================================

    def minimize_all_toggle(self, enabled: bool | None = None):
        """
        Qt-aligned:
        - If enabled is provided, use it
        - Otherwise (migration compat) read from app if present
        - Returns enabled state
        """
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

    # ===================================================================
    #  USB Reminder Toggle
    # ===================================================================

    def usb_reminder_toggle(self, enabled: bool | None = None):
        """
        Qt-aligned:
        - Backend toggle only
        - UI enables/disables controls elsewhere
        """
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

    # ===================================================================
    #  Theme Toggle (Dark / Light)
    # ===================================================================

    def theme_toggle(self, dark_mode: bool | None = None):
        """
        Qt-aligned:
        - This method only decides theme intent
        - Qt layer applies palettes / styles
        """
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

    # ===================================================================
    #  Tooltips Toggle
    # ===================================================================

    def tooltips_toggle(self, enabled: bool | None = None):
        """
        Qt-aligned:
        - Stores tooltip enablement state
        - UI decides how / whether to show tooltips
        """
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

    # ===================================================================
    #  Always-On-Top Toggle
    # ===================================================================

    def always_on_top_toggle(self, enabled: bool | None = None):
        """
        Qt-aligned:
        - Applies topmost intent
        - Qt layer handles window flags
        """
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


        # ===================================================================
    #  Auto-Align (Screen Mover)
    # ===================================================================

    def auto_align_toggle(self, enabled: bool | None = None):
        """
        Qt-aligned:
        - Toggles backend auto-align behaviour only
        - UI updates handled elsewhere
        """
        if enabled is None:
            enabled = bool(
                getattr(
                    getattr(self.app, "auto_align_var", None),
                    "get",
                    lambda: False
                )()
            )

        SCREEN_MOVER.auto_align_enabled = enabled

        if self.app and hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

        return enabled

    # ===================================================================
    #  Organising Utilities - Backup Pinned Shortcuts
    # ===================================================================

    def backup_pinned_shortcuts(self, backup_folder: str | None = None) -> int:
        """
        Back up Windows taskbar pinned shortcuts.

        Args:
            backup_folder: destination folder (Qt should supply this)

        Returns:
            Number of shortcuts copied
        """
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

    # ===================================================================
    #  Organising Utilities - Open Backup Folder
    # ===================================================================

    def open_backup_folder(self, path: str | None = None) -> bool:
        """
        Opens the backup folder.

        Returns:
            True if opened, False otherwise
        """
        if path is None and self.app:
            path = getattr(
                self.app,
                "get_default_taskbar_backup_dir",
                lambda: None
            )()

        if path and os.path.isdir(path):
            os.startfile(path)
            return True

        print("[DEBUG] open_backup_folder: path does not exist")
        return False

    # ===================================================================
    #  Desktop Icon Layout - Capture
    # ===================================================================

    def capture_desktop_layout(self, out_path: str | None = None) -> int:
        """
        Capture desktop icon layout.

        Args:
            out_path: destination JSON file path

        Returns:
            Number of icons captured
        """
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

    # ===================================================================
    #  Desktop Icon Layout - Restore
    # ===================================================================

    def restore_desktop_layout(self, path: str | None = None) -> int:
        """
        Restore desktop icon layout from a JSON file.

        Args:
            path: path to layout JSON (Qt file dialog supplies this)

        Returns:
            Number of icons restored
        """
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


# ===================================================================
#  Minimize / Restore All Windows Except GUI (PURE BACKEND HELPERS)
# ===================================================================

def _should_skip(hwnd: int, skip_hwnd: int) -> bool:
    """
    Decide whether a window should be skipped during minimize/restore.
    Qt / Tk agnostic.
    """
    if hwnd == skip_hwnd:
        return True

    if not win32gui.IsWindowVisible(hwnd):
        return True

    # Skip shell windows without title
    title = win32gui.GetWindowText(hwnd)
    if not title.strip():
        return True

    # Only handle top-level windows
    if win32gui.GetParent(hwnd) != 0:
        return True

    return False


# ------------------------------------------------------------
#  Minimize All Except GUI
# ------------------------------------------------------------

def minimize_all_except_gui(skip_hwnd: int) -> None:
    """
    Minimize all top-level windows except the provided window handle.
    Qt / Tk agnostic.
    """
    print("[MIN/MAX] Minimizing all windows except GUI…")

    def enum_handler(hwnd, _):
        if _should_skip(hwnd, skip_hwnd):
            return
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception:
            pass

    win32gui.EnumWindows(enum_handler, None)


# ------------------------------------------------------------
#  Restore All Except GUI
# ------------------------------------------------------------

def restore_all_except_gui(skip_hwnd: int) -> None:
    """
    Restore all minimized top-level windows except the provided window handle.
    Qt / Tk agnostic.
    """
    print("[MIN/MAX] Restoring all minimized windows except GUI…")

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


# ------------------------------------------------------------
#  Theme Intent Helper (Qt-aligned)
# ------------------------------------------------------------

def theme_intent(dark_mode: bool) -> bool:
    """
    Backend-only theme intent.
    Qt layer applies palettes / stylesheets.

    Returns:
        dark_mode (bool)
    """
    print(f"[THEME] Theme intent set → {'Dark' if dark_mode else 'Light'}")
    return dark_mode

# ===================================================================
#  USB Reminder / Screen Mover – Backend State Helpers (Qt-aligned)
# ===================================================================

def usb_reminder_intent(enabled: bool) -> bool:
    """
    Backend-only helper for USB reminder enablement.

    Qt layer responsibilities:
    - Enable / disable related controls
    - Update visuals / labels
    - Persist UI state if needed
    """
    print(f"[INFO] USB Reminder intent → {enabled}")
    return enabled


def mover_options_intent(enabled: bool) -> bool:
    """
    Backend-only helper for Screen Mover sub-options (MMB + auto-align).

    Qt layer responsibilities:
    - Enable / disable MMB toggle
    - Enable / disable auto-align toggle
    """
    print(f"[INFO] Screen Mover options intent → {enabled}")
    return enabled

import ctypes
import os
import psutil
import shutil
import subprocess
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

import win32con
import win32gui
import win32process
import pythoncom
import win32com.client
from PySide6.QtCore import Qt

from resurface.features.desktop.desktop_icon_layout import (
    desktop_icons_visible,
    restore_desktop_icon_layout,
    save_desktop_icon_layout,
    set_desktop_icons_visible,
)
from resurface.features.screen_mover.screen_mover import SCREEN_MOVER


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

    def maximize_all_toggle(self, enabled: bool | None = None):
        if enabled is None:
            maximize_var = getattr(self.app, "maximize_all_var", None)
            if maximize_var is not None:
                enabled = bool(getattr(maximize_var, "get", lambda: True)())
            else:
                enabled = not bool(
                    getattr(
                        getattr(self.app, "minimize_all_var", None),
                        "get",
                        lambda: False,
                    )()
                )

        print(f"[INFO] Maximize All toggled -> {enabled}")

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
                restore_all_except_gui(hwnd)
            else:
                minimize_all_except_gui(hwnd)

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

            apply_topmost = getattr(self.app, "_set_main_window_topmost_state", None)
            if callable(apply_topmost):
                apply_topmost(enabled)
            elif hasattr(self.app, "setWindowFlag"):
                self.app.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
                self.app.show()

        if self.app and hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

        return enabled

    def backup_pinned_shortcuts(self, backup_folder: str | None = None) -> int:
        print("[BACKUP] Starting backup of pinned shortcuts...")

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

    def open_recycle_bin(self) -> bool:
        try:
            subprocess.Popen(
                ["explorer.exe", "shell:RecycleBinFolder"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            print("[RECYCLE BIN] Failed to open:", e)
            return False

    def empty_recycle_bin(self) -> bool:
        no_confirmation = 0x00000001
        no_progress = 0x00000002
        no_sound = 0x00000004
        flags = no_confirmation | no_progress | no_sound

        try:
            result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
            if result not in (0,):
                print(f"[RECYCLE BIN] SHEmptyRecycleBinW returned {result}")
                return False
            return True
        except Exception as e:
            print("[RECYCLE BIN] Failed to empty:", e)
            return False

    def cleanup_recycle_bin_items_older_than(self, days: int) -> int:
        if days <= 0:
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        deleted_count = 0

        for metadata_path in _iter_recycle_bin_metadata_files():
            deleted_at = _read_recycle_bin_deleted_at(metadata_path)
            if deleted_at is None or deleted_at > cutoff:
                continue

            if _delete_recycle_bin_entry(metadata_path):
                deleted_count += 1

        return deleted_count

    def is_recycle_bin_open(self) -> bool:
        return bool(find_recycle_bin_explorer_windows())

    def close_recycle_bin(self) -> bool:
        handles = [entry["hwnd"] for entry in find_recycle_bin_explorer_windows()]
        closed_any = False
        for hwnd in handles:
            try:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                closed_any = True
            except Exception as e:
                print(f"[DEBUG] close_recycle_bin failed for hwnd {hwnd}: {e}")

        return closed_any

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

        if self.focus_backup_folder(path):
            return True

        try:
            os.makedirs(path, exist_ok=True)
            os.startfile(path)
            return True
        except Exception as e:
            print(f"[DEBUG] open_backup_folder failed: {e}")
            return False

    def focus_backup_folder(self, path: str | None = None) -> bool:
        resolved_path = _resolve_backup_folder_path(path, self.app)
        if not resolved_path:
            return False

        handles = find_explorer_windows_for_folder(resolved_path)
        return focus_window_handles(handles)

    def open_or_focus_folder_path(
        self,
        path: str,
        launch=None,
    ) -> bool:
        normalized_path = _normalize_folder_path(path)
        if not normalized_path:
            return False

        if focus_window_handles(find_explorer_windows_for_folder(normalized_path)):
            return True

        try:
            if launch is not None:
                launch()
            else:
                os.startfile(normalized_path)
            return True
        except Exception as e:
            print(
                "[DEBUG] open_or_focus_folder_path failed for "
                f"{normalized_path}: {e}"
            )
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

    def desktop_zen_mode_toggle(self, enabled: bool | None = None) -> bool | None:
        if enabled is None:
            enabled = bool(
                getattr(
                    getattr(self.app, "desktop_zen_mode_var", None),
                    "get",
                    lambda: False
                )()
            )

        try:
            changed = set_desktop_icons_visible(not enabled)
        except Exception as e:
            print("[DESKTOP ICONS] Visibility change failed:", e)
            return None

        if not changed:
            print("[DESKTOP ICONS] Desktop list view not found")
            return None

        if self.app:
            self.app.desktop_zen_mode_enabled = enabled

        if self.app and hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

        return enabled

    def minimize_all_toggle(self, enabled: bool | None = None):
        if enabled is None:
            enabled = bool(
                getattr(
                    getattr(self.app, "minimize_all_var", None),
                    "get",
                    lambda: False,
                )()
            )

        self.maximize_all_toggle(not enabled)
        return enabled

    def desktop_icons_visible(self) -> bool | None:
        try:
            return desktop_icons_visible()
        except Exception as e:
            print("[DESKTOP ICONS] Visibility read failed:", e)
            return None

    def open_or_focus_explorer_title(
        self,
        title: str,
        launch,
    ) -> bool:
        if focus_window_handles(find_explorer_windows_by_title(title)):
            return True

        try:
            launch()
            return True
        except Exception as e:
            print(f"[DEBUG] open_or_focus_explorer_title failed for {title}: {e}")
            return False

    def open_or_focus_window_titles(
        self,
        title_candidates: list[str] | tuple[str, ...],
        launch,
    ) -> bool:
        if focus_window_handles(find_windows_by_title_candidates(title_candidates)):
            return True

        try:
            launch()
            return True
        except Exception as e:
            print(
                "[DEBUG] open_or_focus_window_titles failed for "
                f"{title_candidates}: {e}"
            )
            return False

    def close_window_titles(
        self,
        title_candidates: list[str] | tuple[str, ...],
    ) -> bool:
        return close_window_handles(find_windows_by_title_candidates(title_candidates))

    def focus_window_titles(
        self,
        title_candidates: list[str] | tuple[str, ...],
    ) -> bool:
        return focus_window_handles(find_windows_by_title_candidates(title_candidates))

    def maximize_window_titles(
        self,
        title_candidates: list[str] | tuple[str, ...],
    ) -> bool:
        return maximize_window_handles(
            find_windows_by_title_candidates(title_candidates)
        )

    def get_window_titles_state(
        self,
        title_candidates: list[str] | tuple[str, ...],
    ) -> str:
        return get_window_state_for_handles(
            find_windows_by_title_candidates(title_candidates)
        )

def _iter_recycle_bin_metadata_files():
    for drive_root in _iter_windows_drive_roots():
        recycle_root = drive_root / "$Recycle.Bin"
        if not recycle_root.exists():
            continue

        try:
            for metadata_path in recycle_root.rglob("$I*"):
                if metadata_path.is_file():
                    yield metadata_path
        except (OSError, PermissionError):
            continue


def _iter_windows_drive_roots():
    try:
        drive_mask = ctypes.windll.kernel32.GetLogicalDrives()
    except Exception:
        drive_mask = 0

    for index in range(26):
        if not (drive_mask & (1 << index)):
            continue

        drive_letter = chr(ord("A") + index)
        drive_root = Path(f"{drive_letter}:\\")
        if drive_root.exists():
            yield drive_root


def _read_recycle_bin_deleted_at(metadata_path: Path) -> datetime | None:
    try:
        with metadata_path.open("rb") as metadata_file:
            header = metadata_file.read(24)
    except OSError:
        return None

    if len(header) < 24:
        return None

    filetime = int.from_bytes(header[16:24], "little", signed=False)
    if filetime <= 0:
        return None

    return _filetime_to_utc_datetime(filetime)


def _filetime_to_utc_datetime(filetime: int) -> datetime:
    unix_epoch_offset = 116444736000000000
    return datetime.fromtimestamp(
        (filetime - unix_epoch_offset) / 10_000_000,
        tz=timezone.utc,
    )


def _delete_recycle_bin_entry(metadata_path: Path) -> bool:
    resource_path = metadata_path.with_name(
        "$R" + metadata_path.name[2:]
    )

    deleted_any = False

    for path in (metadata_path, resource_path):
        if not path.exists():
            continue

        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=False)
            else:
                path.unlink()
            deleted_any = True
        except OSError as e:
            print(f"[RECYCLE BIN] Failed to delete {path}: {e}")
            return False

    return deleted_any

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
    print(f"[THEME] Theme intent set -> {'Dark' if dark_mode else 'Light'}")
    return dark_mode

def usb_reminder_intent(enabled: bool) -> bool:
    print(f"[INFO] USB Reminder intent -> {enabled}")
    return enabled

def mover_options_intent(enabled: bool) -> bool:
    print(f"[INFO] Screen Mover options intent -> {enabled}")
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
    normalized_target_path = _normalize_folder_path(path)
    if not normalized_target_path:
        return []

    handles: list[int] = []

    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    try:
        shell = win32com.client.Dispatch("Shell.Application")
        shell_windows = shell.Windows()
    except Exception as e:
        print(f"[DEBUG] find_explorer_windows_for_folder failed: {e}")
        shell_windows = []

    for window in shell_windows:
        try:
            hwnd = int(window.HWND)
        except Exception:
            continue

        window_folder_path = _get_shell_window_folder_path(window)
        if not window_folder_path:
            continue

        if _normalize_folder_path(window_folder_path) == normalized_target_path:
            handles.append(hwnd)

    if handles:
        return handles

    folder_name = Path(path).name.strip()
    if not folder_name:
        return []

    return find_explorer_windows_by_title(folder_name)


def find_explorer_windows_by_title(title: str) -> list[int]:
    normalized_title = title.strip()
    if not normalized_title:
        return []

    handles: list[int] = []

    def enum_handler(hwnd, _):
        if _is_explorer_folder_window(hwnd, normalized_title):
            handles.append(hwnd)

    try:
        win32gui.EnumWindows(enum_handler, None)
    except Exception as e:
        print(f"[DEBUG] find_explorer_windows_by_title failed: {e}")

    return handles


def focus_window_handles(handles: list[int]) -> bool:
    focused_any = False
    for hwnd in handles:
        try:
            if _is_window_minimized(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(hwnd)
            focused_any = True
            break
        except Exception as e:
            print(f"[DEBUG] focus_window_handles failed for hwnd {hwnd}: {e}")

    return focused_any


def maximize_window_handles(handles: list[int]) -> bool:
    focused_any = False
    for hwnd in handles:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            win32gui.SetForegroundWindow(hwnd)
            focused_any = True
            break
        except Exception as e:
            print(f"[DEBUG] maximize_window_handles failed for hwnd {hwnd}: {e}")

    return focused_any


def close_window_handles(handles: list[int]) -> bool:
    closed_any = False
    for hwnd in handles:
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            closed_any = True
        except Exception as e:
            print(f"[DEBUG] close_window_handles failed for hwnd {hwnd}: {e}")

    return closed_any


def get_window_state_for_handles(handles: list[int]) -> str:
    if not handles:
        return "closed"

    trackable_top_level_handles = [
        hwnd for hwnd in handles if _is_trackable_top_level_window(hwnd)
    ]
    if not trackable_top_level_handles:
        return "closed"

    minimized_found = False
    for hwnd in trackable_top_level_handles:
        try:
            if not _is_window_minimized(hwnd):
                return "open"
            minimized_found = True
        except Exception:
            continue

    return "minimized" if minimized_found else "closed"


def _is_window_minimized(hwnd: int) -> bool:
    try:
        if win32gui.IsIconic(hwnd):
            return True
    except Exception:
        pass

    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        show_cmd = placement[1]
        return show_cmd == win32con.SW_SHOWMINIMIZED
    except Exception:
        return False


def find_windows_by_title_candidates(
    title_candidates: list[str] | tuple[str, ...],
) -> list[int]:
    normalized_candidates = [
        candidate.strip().casefold()
        for candidate in title_candidates
        if candidate and candidate.strip()
    ]
    if not normalized_candidates:
        return []

    handles: list[int] = []

    def enum_handler(hwnd, _):
        if _is_trackable_top_level_window(hwnd):
            title = _get_window_title(hwnd)
            if title and _title_matches_any_candidate(title, normalized_candidates):
                handles.append(hwnd)

    try:
        win32gui.EnumWindows(enum_handler, None)
    except Exception as e:
        print(f"[DEBUG] find_windows_by_title_candidates failed: {e}")

    return handles


def _is_top_level_window(hwnd: int) -> bool:
    try:
        if not win32gui.IsWindow(hwnd):
            return False
    except Exception:
        return False

    try:
        if win32gui.GetParent(hwnd) != 0:
            return False
    except Exception:
        return False

    return True


def _get_window_pid(hwnd: int) -> int:
    try:
        _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        return int(pid)
    except Exception:
        return 0


def _get_window_process_name(hwnd: int) -> str:
    pid = _get_window_pid(hwnd)
    if pid <= 0:
        return ""

    try:
        return psutil.Process(pid).name().casefold()
    except Exception:
        return ""


def _get_window_class_name(hwnd: int) -> str:
    try:
        return win32gui.GetClassName(hwnd).strip()
    except Exception:
        return ""


def _is_visible_top_level_window(hwnd: int) -> bool:
    if not _is_top_level_window(hwnd):
        return False

    try:
        if not win32gui.IsWindowVisible(hwnd):
            return False
    except Exception:
        return False

    return True


def _is_trackable_top_level_window(hwnd: int) -> bool:
    if not _is_top_level_window(hwnd):
        return False

    if _is_window_cloaked(hwnd):
        return False

    try:
        if win32gui.IsWindowVisible(hwnd):
            return True
    except Exception:
        pass

    return _is_window_minimized(hwnd)


def _is_window_cloaked(hwnd: int) -> bool:
    DWMWA_CLOAKED = 14
    cloaked = ctypes.c_int(0)

    try:
        result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            int(hwnd),
            DWMWA_CLOAKED,
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )
    except Exception:
        return False

    if result != 0:
        return False

    return bool(cloaked.value)


def _get_window_title(hwnd: int) -> str:
    try:
        return win32gui.GetWindowText(hwnd).strip()
    except Exception:
        return ""


def _title_matches_any_candidate(
    title: str,
    normalized_candidates: list[str],
) -> bool:
    normalized_title = title.casefold()
    return any(
        normalized_title == candidate
        or normalized_title.endswith(f" - {candidate}")
        or candidate in normalized_title
        for candidate in normalized_candidates
    )


def _get_shell_window_folder_path(window) -> str:
    try:
        folder = window.Document.Folder
        folder_self = folder.Self
        return str(getattr(folder_self, "Path", "") or "")
    except Exception:
        return ""


def _normalize_folder_path(path: str | None) -> str:
    if not path:
        return ""

    try:
        return os.path.normcase(os.path.abspath(path))
    except Exception:
        return str(path).strip().casefold()


RECYCLE_BIN_CLSID = "{645FF040-5081-101B-9F08-00AA002F954E}"


def find_recycle_bin_explorer_windows() -> list[dict[str, int]]:
    windows: list[dict[str, int]] = []

    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    try:
        shell = win32com.client.Dispatch("Shell.Application")
        shell_windows = shell.Windows()
    except Exception as e:
        print(f"[DEBUG] find_recycle_bin_explorer_windows failed: {e}")
        return windows

    for window in shell_windows:
        try:
            hwnd = int(window.HWND)
        except Exception:
            continue

        try:
            folder = window.Document.Folder
            folder_self = folder.Self
        except Exception:
            continue

        try:
            folder_path = str(getattr(folder_self, "Path", "") or "")
        except Exception:
            folder_path = ""

        try:
            folder_name = str(getattr(folder_self, "Name", "") or "")
        except Exception:
            folder_name = ""

        normalized_path = folder_path.casefold()
        normalized_name = folder_name.casefold()
        if (
            RECYCLE_BIN_CLSID.casefold() not in normalized_path
            and "recycle bin" != normalized_name
        ):
            continue

        try:
            _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            pid = 0

        windows.append({"hwnd": hwnd, "pid": int(pid)})

    return windows

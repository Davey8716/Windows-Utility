import os
import shutil
import subprocess
import sys
import inspect
from pathlib import Path

import psutil
from PIL import ImageGrab
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLineEdit
import win32api
import win32con
import win32gui
import win32process

from resurface.core.state_manager import save_state
from resurface.core.saved_folder_names import add_saved_folder_name
from resurface.features.system.utility_toggles import (
    _should_skip,
    focus_window_handles,
)


PROJECT_ROOT_ENV_VAR = "WIN11_RESURFACE_PROJECT_ROOT"


class DesktopOperationsMixin:
    def _should_minimize_after_use(self) -> bool:
        app_state = getattr(self, "state", None)
        if isinstance(app_state, dict):
            return bool(app_state.get("minimize_after_use_enabled", True))
        return True

    def _minimize_self_if_configured(self) -> bool:
        if not self._should_minimize_after_use():
            return False
        self.showMinimized()
        return True

    def _run_with_optional_minimize(
        self,
        action,
        *,
        delay_ms_when_minimized: int = 0,
    ) -> None:
        if self._minimize_self_if_configured():
            if delay_ms_when_minimized > 0:
                QTimer.singleShot(delay_ms_when_minimized, action)
                return
        action()

    def _run_with_forced_desktop_minimize(
        self,
        action,
        *,
        delay_ms_after_minimize: int = 500,
        capture_spec: dict | None = None,
    ) -> None:
        tracked_windows = []
        hwnd = None
        if hasattr(self, "winId"):
            try:
                hwnd = int(self.winId())
            except Exception:
                hwnd = None

        if hwnd:
            tracked_windows = self._collect_screenshot_windows_to_minimize(hwnd)
            self._minimize_tracked_screenshot_windows(tracked_windows)

        try:
            self.showMinimized()
        except Exception as exc:
            print(f"[SCREENSHOT] App minimize failed: {exc}")

        def run_action():
            action(tracked_windows, hwnd, capture_spec)

        if delay_ms_after_minimize > 0:
            QTimer.singleShot(delay_ms_after_minimize, run_action)
            return

        run_action()

    def _collect_screenshot_windows_to_minimize(self, skip_hwnd: int) -> list[int]:
        handles = []

        def enum_handler(hwnd, _):
            if _should_skip(hwnd, skip_hwnd):
                return

            try:
                placement = win32gui.GetWindowPlacement(hwnd)
            except Exception:
                return

            if placement[1] == win32con.SW_SHOWMINIMIZED:
                return

            handles.append(hwnd)

        try:
            win32gui.EnumWindows(enum_handler, None)
        except Exception as exc:
            print(f"[SCREENSHOT] Window enumeration failed: {exc}")

        return handles

    def _minimize_tracked_screenshot_windows(self, handles: list[int]) -> None:
        for hwnd in handles:
            try:
                if win32gui.IsWindow(hwnd) and not win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            except Exception as exc:
                print(f"[SCREENSHOT] Window minimize failed for {hwnd}: {exc}")

    def _restore_tracked_screenshot_windows(self, handles: list[int]) -> None:
        for hwnd in handles:
            try:
                if win32gui.IsWindow(hwnd) and win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            except Exception as exc:
                print(f"[SCREENSHOT] Window restore failed for {hwnd}: {exc}")

    def _restore_post_screenshot_state(
        self,
        tracked_windows: list[int],
        app_hwnd: int | None,
    ) -> bool:
        self._restore_tracked_screenshot_windows(tracked_windows)

        if self._should_minimize_after_use():
            return False

        if app_hwnd:
            try:
                if win32gui.IsWindow(app_hwnd) and win32gui.IsIconic(app_hwnd):
                    self.showNormal()
                    self.raise_()
                    self.activateWindow()
            except Exception as exc:
                print(f"[SCREENSHOT] App restore failed: {exc}")

        return True

    def _save_state_safely(self, state: dict) -> None:
        save_state_fn = self._get_app_module_attr("save_state", save_state)
        try:
            save_state_fn(state)
        except Exception as exc:
            print(f"[STATE] Save failed: {exc}")

    def _show_organizing_timed_message(
        self,
        icon,
        title: str,
        text: str,
        timeout_ms: int = 10_000,
        show_close_now_button: bool = False,
    ):
        show_timed_message = self._show_timed_message
        try:
            params = inspect.signature(show_timed_message).parameters
        except (TypeError, ValueError):
            params = {}

        if "merge_group" in params and "merge_title" in params:
            return show_timed_message(
                icon,
                title,
                text,
                timeout_ms=timeout_ms,
                merge_group="organizing_utilities",
                merge_title="General Organising Utilities",
                show_close_now_button=show_close_now_button,
            )

        return show_timed_message(
            icon,
            title,
            text,
            timeout_ms=timeout_ms,
            show_close_now_button=show_close_now_button,
        )

    def _get_app_module_attr(self, name: str, default):
        module = sys.modules.get(self.__class__.__module__)
        return getattr(module, name, default)

    def take_desktop_screenshot(self):
        capture_spec = self._build_desktop_screenshot_capture_spec()
        if capture_spec is None:
            return

        existing_paths = capture_spec["existing_paths"]
        if existing_paths:
            question = self._show_modal_message(
                self._message_box_icon("Question"),
                "Overwrite Desktop Screenshots",
                (
                    "Desktop screenshots already exist in the master backup folder."
                    "\n\nOverwrite the current saved screenshot set?"
                ),
                self._message_box_button("Yes")
                | self._message_box_button("Cancel"),
                self._message_box_button("Cancel"),
            )
            if question != self._message_box_button("Yes"):
                return

        self._run_with_forced_desktop_minimize(
            self._capture_desktop_screenshot,
            delay_ms_after_minimize=500,
            capture_spec=capture_spec,
        )

    def _enumerate_monitor_rects(self):
        monitors = []
        for index, monitor in enumerate(win32api.EnumDisplayMonitors(), start=1):
            monitor_info = win32api.GetMonitorInfo(monitor[0])
            left, top, right, bottom = monitor_info["Monitor"]
            monitors.append(
                {
                    "index": index,
                    "rect": (left, top, right, bottom),
                }
            )
        return monitors

    def _build_desktop_screenshot_capture_spec(self):
        monitors = self._enumerate_monitor_rects()
        path_type = self._get_app_module_attr("Path", Path)
        save_dir = path_type(self._get_master_backup_dir())
        save_dir.mkdir(parents=True, exist_ok=True)

        if not monitors:
            monitors = [{"index": 1, "rect": None}]

        target_paths = [
            save_dir / f"DesktopScreenshot_Monitor{monitor['index']}.png"
            for monitor in monitors
        ]

        existing_pattern_paths = sorted(
            save_dir.glob("DesktopScreenshot_Monitor*.png")
        )
        stale_paths = [
            path for path in existing_pattern_paths if path not in target_paths
        ]
        existing_paths = [
            path for path in [*target_paths, *stale_paths] if path.exists()
        ]

        return {
            "monitors": monitors,
            "save_dir": save_dir,
            "target_paths": target_paths,
            "stale_paths": stale_paths,
            "existing_paths": existing_paths,
        }

    def _capture_desktop_screenshot(
        self,
        tracked_windows: list[int] | None = None,
        app_hwnd: int | None = None,
        capture_spec: dict | None = None,
    ):
        save_paths = []
        tracked_windows = list(tracked_windows or [])
        try:
            capture_spec = capture_spec or self._build_desktop_screenshot_capture_spec()
            monitors = list(capture_spec.get("monitors") or [])
            img = ImageGrab.grab(all_screens=True)

            if not monitors:
                width, height = img.size
                monitors = [{"index": 1, "rect": (0, 0, width, height)}]

            save_state_fn = self._get_app_module_attr("save_state", save_state)
            save_dir = capture_spec["save_dir"]
            target_paths = list(capture_spec.get("target_paths") or [])
            stale_paths = list(capture_spec.get("stale_paths") or [])

            normalized_monitors = []
            if monitors and monitors[0].get("rect") is None:
                width, height = img.size
                normalized_monitors = [{"index": 1, "rect": (0, 0, width, height)}]
                target_paths = [save_dir / "DesktopScreenshot_Monitor1.png"]
            else:
                normalized_monitors = monitors

            virtual_left = min(monitor["rect"][0] for monitor in normalized_monitors)
            virtual_top = min(monitor["rect"][1] for monitor in normalized_monitors)

            for monitor, save_path in zip(normalized_monitors, target_paths):
                left, top, right, bottom = monitor["rect"]
                crop_box = (
                    left - virtual_left,
                    top - virtual_top,
                    right - virtual_left,
                    bottom - virtual_top,
                )
                monitor_img = img.crop(crop_box)
                monitor_img.save(save_path)
                save_paths.append(save_path)

            for stale_path in stale_paths:
                if stale_path.exists():
                    stale_path.unlink(missing_ok=True)

            if save_paths:
                self.state["desktop_screenshot_last_path"] = str(save_paths[0])
            self.state["desktop_screenshot_last_dir"] = str(save_dir)
            try:
                save_state_fn(self.state)
            except Exception as exc:
                print(f"[STATE] Save failed: {exc}")

            count = len(save_paths)
            if count <= 3:
                saved_suffix = "\n".join(path.name for path in save_paths)
                saved_summary = f"\nSaved files:\n{saved_suffix}"
            else:
                saved_summary = ""

            print(f"[SCREENSHOT] Saved {count} monitor screenshot(s) to: {save_dir}")
            app_restored = self._restore_post_screenshot_state(
                tracked_windows,
                app_hwnd,
            )
            if app_restored:
                self._show_organizing_timed_message(
                    self._message_box_icon("Information"),
                    "Desktop Screenshot",
                    (
                        f"Saved {count} desktop screenshot(s) to:\n{save_dir}"
                        f"{saved_summary}"
                    ),
                    timeout_ms=5_000,
                    show_close_now_button=True,
                )

        except Exception as exc:
            for save_path in save_paths:
                try:
                    save_path.unlink(missing_ok=True)
                except Exception:
                    pass
            self._restore_post_screenshot_state(tracked_windows, app_hwnd)
            print("[SCREENSHOT] Error:", exc)
            if not self._should_minimize_after_use():
                self._show_organizing_timed_message(
                    self._message_box_icon("Warning"),
                    "Desktop Screenshot",
                    f"Could not save desktop screenshot:\n{exc}",
                    timeout_ms=5_000,
                    show_close_now_button=True,
                )

    def backup_taskbar_apps(self):
        def action():
            backup_dir = self.get_default_taskbar_backup_dir()
            count = self.actions.backup_pinned_shortcuts(backup_dir)

            if count > 0:
                self._show_organizing_timed_message(
                    self._message_box_icon("Information"),
                    "Backup Taskbar",
                    f"Backed up {count} taskbar shortcut(s) to:\n{backup_dir}",
                    show_close_now_button=True,
                )
                return

            self._show_organizing_timed_message(
                self._message_box_icon("Warning"),
                "Backup Taskbar",
                "No taskbar shortcuts were backed up.",
                show_close_now_button=True,
            )

        self._run_with_optional_minimize(action)

    def open_taskbar_backup_folder(self):
        def action():
            path = self.get_default_taskbar_backup_dir()
            if self.actions.is_backup_folder_open(path):
                closed = self.actions.close_backup_folder(path)
                self._refresh_taskbar_backup_folder_button()

                if closed:
                    return

                self._show_modal_message(
                    self._message_box_icon("Warning"),
                    "Close Backup Folder",
                    f"Could not close backup folder:\n{path}",
                    self._message_box_button("Ok"),
                    self._message_box_button("Ok"),
                )
                return

            opened = self.actions.open_backup_folder(path)
            self._refresh_taskbar_backup_folder_button()

            if opened:
                QTimer.singleShot(500, self._refresh_taskbar_backup_folder_button)
                return

            self._show_modal_message(
                self._message_box_icon("Warning"),
                "Open Backup Folder",
                f"Could not open backup folder:\n{path}",
                self._message_box_button("Ok"),
                self._message_box_button("Ok"),
            )

        self._run_with_optional_minimize(action)

    def capture_desktop_layout(self):
        def action():
            out_path = self.get_default_desktop_layout_path()
            count = self.actions.capture_desktop_layout(out_path)

            if count > 0:
                self._show_organizing_timed_message(
                    self._message_box_icon("Information"),
                    "Desktop Layout",
                    f"Captured desktop layout with {count} icon position(s) saved to:\n{out_path}",
                    show_close_now_button=True,
                )
                return

            self._show_organizing_timed_message(
                self._message_box_icon("Warning"),
                "Desktop Layout",
                f"Could not capture desktop layout to:\n{out_path}",
                show_close_now_button=True,
            )

        self._run_with_optional_minimize(action)

    def restore_desktop_layout(self):
        def action():
            layout_path = self.get_default_desktop_layout_path()
            count = self.actions.restore_desktop_layout(layout_path)

            if count > 0:
                self._show_organizing_timed_message(
                    self._message_box_icon("Information"),
                    "Desktop Layout",
                    f"Desktop icons restored from:\n{layout_path}",
                    show_close_now_button=True,
                )
                return

            self._show_organizing_timed_message(
                self._message_box_icon("Warning"),
                "Desktop Layout",
                f"Could not restore desktop layout from:\n{layout_path}",
                show_close_now_button=True,
            )

        self._run_with_optional_minimize(action)

    def export_bookmarks(self):
        out_paths = self.right_tools_panel._run_brave_export()
        if isinstance(out_paths, str) and out_paths:
            exported_paths = [out_paths]
        elif isinstance(out_paths, (list, tuple)) and out_paths:
            exported_paths = list(out_paths)
        else:
            exported_paths = []

        if exported_paths:
            self._show_organizing_timed_message(
                self._message_box_icon("Information"),
                "Export Bookmarks",
                "Bookmarks exported to:\n" + "\n".join(exported_paths),
            )
            return

        if out_paths is False:
            self._show_organizing_timed_message(
                self._message_box_icon("Warning"),
                "Export Bookmarks",
                "Could not export bookmarks.",
            )

    def open_recycle_bin(self):
        def action():
            if self.actions.open_recycle_bin():
                return

            self._show_timed_message(
                self._message_box_icon("Warning"),
                "Recycle Bin",
                "Could not open Recycle Bin.",
            )

        self._run_with_optional_minimize(action)

    def empty_recycle_bin(self):
        question = self._show_modal_message(
            self._message_box_icon("NoIcon"),
            "Empty Recycle Bin",
            "Permanently delete all items currently in Recycle Bin?",
            self._message_box_button("Yes") | self._message_box_button("Cancel"),
            self._message_box_button("Cancel"),
        )
        if question != self._message_box_button("Yes"):
            return

        def action():
            try:
                if self.actions.empty_recycle_bin():
                    self._show_timed_message(
                        self._message_box_icon("Information"),
                        "Recycle Bin",
                        "Recycle Bin emptied.",
                        show_close_now_button=True,
                    )
                    return

                self._show_timed_message(
                    self._message_box_icon("NoIcon"),
                    "Recycle Bin",
                    "Could not empty Recycle Bin.",
                    show_close_now_button=True,
                )
            finally:
                close_recycle_bin = getattr(self.actions, "close_recycle_bin", None)
                if callable(close_recycle_bin):
                    close_recycle_bin()

        self._run_with_optional_minimize(action)

    def run_recycle_bin_auto_cleanup(self):
        if not self.state.get("recycle_bin_auto_clean_enabled", False):
            return

        self._run_recycle_bin_age_cleanup(automatic=True)

    def run_recycle_bin_cleanup_now(self):
        self._run_recycle_bin_age_cleanup(automatic=False)

    def _run_recycle_bin_age_cleanup(self, *, automatic: bool):
        days = int(self.state.get("recycle_bin_age_rule_days", 30))
        should_show_automatic_popup = (
            not automatic
            or self.state.get("recycle_bin_last_auto_clean_popup_days") != days
        )
        if days <= 0:
            if not automatic:
                self._show_timed_message(
                    self._message_box_icon("Warning"),
                    "Recycle Bin Cleanup",
                    "Choose a valid age rule before running cleanup.",
                )
            return

        if not automatic:
            question = self._show_modal_message(
                self._message_box_icon("NoIcon"),
                "Recycle Bin Cleanup",
                f"Permanently delete Recycle Bin items older than {days} days?",
                self._message_box_button("Yes") | self._message_box_button("Cancel"),
                self._message_box_button("Cancel"),
            )
            if question != self._message_box_button("Yes"):
                return

        def action():
            try:
                deleted_count = self.actions.cleanup_recycle_bin_items_older_than(days)
                if deleted_count > 0:
                    title = "Recycle Bin Auto-Clean" if automatic else "Recycle Bin Cleanup"
                    if should_show_automatic_popup:
                        self._show_timed_message(
                            self._message_box_icon("Information"),
                            title,
                            f"Deleted {deleted_count} Recycle Bin item(s) older than {days} days.",
                            show_close_now_button=True,
                        )
                    if automatic and should_show_automatic_popup:
                        self.state["recycle_bin_last_auto_clean_popup_days"] = days
                        self._save_state_safely(self.state)
                    return

                if automatic:
                    if should_show_automatic_popup:
                        self._show_timed_message(
                            self._message_box_icon("Information"),
                            "Recycle Bin Auto-Clean",
                            f"No Recycle Bin items older than {days} days were found.",
                            show_close_now_button=True,
                        )
                        self.state["recycle_bin_last_auto_clean_popup_days"] = days
                        self._save_state_safely(self.state)
                    return

                self._show_timed_message(
                    self._message_box_icon("Information"),
                    "Recycle Bin Cleanup",
                    f"No Recycle Bin items older than {days} days were found.",
                    show_close_now_button=True,
                )
            finally:
                if not automatic:
                    close_recycle_bin = getattr(self.actions, "close_recycle_bin", None)
                    if callable(close_recycle_bin):
                        close_recycle_bin()

        if automatic:
            action()
            return

        self._run_with_optional_minimize(action)

    def _create_desktop_folder(self, folder_input: QLineEdit):
        path_type = self._get_app_module_attr("Path", Path)
        folder_name = folder_input.text().strip()
        if not folder_name:
            return

        def action():
            desktop = path_type.home() / "Desktop"
            new_path = desktop / folder_name

            try:
                if new_path.exists():
                    self._show_organizing_timed_message(
                        self._message_box_icon("NoIcon"),
                        "Folder to Desktop",
                        "A folder with that name already exists on Desktop.",
                        show_close_now_button=True,
                    )
                    return

                new_path.mkdir(parents=True, exist_ok=False)
                save_name_toggle = getattr(self, "save_folder_name_toggle", None)
                if save_name_toggle is not None and save_name_toggle.isChecked():
                    saved_names = add_saved_folder_name(folder_name)
                    refresh_saved_names = getattr(
                        self, "refresh_saved_folder_names", None
                    )
                    if callable(refresh_saved_names):
                        refresh_saved_names(saved_names)
                    save_name_toggle.setChecked(False)
                folder_input.clear()
                self._show_organizing_timed_message(
                    self._message_box_icon("Information"),
                    "Folder to Desktop",
                    f"Created desktop folder:\n{new_path}",
                    show_close_now_button=True,
                )

            except Exception as exc:
                self._show_organizing_timed_message(
                    self._message_box_icon("NoIcon"),
                    "Folder to Desktop",
                    f"Could not create folder:\n{exc}",
                    show_close_now_button=True,
                )

        self._run_with_optional_minimize(action)

    def open_folder_creator(self):
        project_root = self._resolve_windows_resurface_project_root()
        project_dir = project_root / "Code Folder Creator"
        title_candidates = [
            "Folder Generator",
            "Folder Creator",
            "Code Folder Creator",
        ]
        launch_target = self._resolve_folder_creator_launch_target(project_dir)

        if launch_target is None:
            self._show_organizing_timed_message(
                self._message_box_icon("Warning"),
                "Folder Creator",
                f"Could not open Folder Creator from:\n{project_dir}",
                show_close_now_button=True,
            )
            return

        self.showMinimized()

        if self._focus_folder_creator_window_handles(title_candidates, launch_target):
            return

        try:
            subprocess.Popen(
                self._python_script_command(launch_target),
                cwd=str(project_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            print(f"[DEBUG] open_folder_creator failed for {launch_target}: {exc}")
            self._restore_after_folder_creator_launch_failure()
            self._show_organizing_timed_message(
                self._message_box_icon("Warning"),
                "Folder Creator",
                f"Could not open Folder Creator from:\n{project_dir}",
                show_close_now_button=True,
            )
            return

        QTimer.singleShot(
            100,
            lambda: self._focus_folder_creator_window_with_retry(
                title_candidates,
                launch_target,
            ),
        )

    def _focus_folder_creator_window_with_retry(
        self,
        title_candidates: list[str] | tuple[str, ...],
        launch_target: Path,
        *,
        attempt: int = 0,
        max_attempts: int = 20,
    ) -> None:
        if self._focus_folder_creator_window_handles(title_candidates, launch_target):
            return
        if attempt >= max_attempts:
            return
        QTimer.singleShot(
            150,
            lambda: self._focus_folder_creator_window_with_retry(
                title_candidates,
                launch_target,
                attempt=attempt + 1,
                max_attempts=max_attempts,
            ),
        )

    def _restore_after_folder_creator_launch_failure(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _resolve_folder_creator_launch_target(
        self,
        project_dir: Path,
    ) -> Path | None:
        main_path = project_dir.resolve() / "main.py"
        if main_path.is_file():
            return main_path
        return None

    def _focus_folder_creator_window_handles(
        self,
        title_candidates: list[str] | tuple[str, ...],
        launch_target: Path,
    ) -> bool:
        return focus_window_handles(
            self._folder_creator_window_handles(title_candidates, launch_target)
        )

    def _folder_creator_window_handles(
        self,
        title_candidates: list[str] | tuple[str, ...],
        launch_target: Path,
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
            try:
                title = win32gui.GetWindowText(hwnd).strip()
            except Exception:
                return True

            if not title:
                return True

            normalized_title = title.casefold()
            title_matches = any(
                normalized_title == candidate
                or normalized_title.endswith(f" - {candidate}")
                or candidate in normalized_title
                for candidate in normalized_candidates
            )
            if not title_matches:
                return True

            if self._window_process_references_script(hwnd, launch_target):
                handles.append(hwnd)

            return True

        try:
            win32gui.EnumWindows(enum_handler, None)
        except Exception as e:
            print(f"[DEBUG] _folder_creator_window_handles failed: {e}")

        return handles

    def _window_process_references_script(
        self,
        hwnd: int,
        script_path: Path,
    ) -> bool:
        try:
            _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            cmdline = process.cmdline()
            cwd = process.cwd()
        except Exception:
            return False

        normalized_script = str(script_path.resolve()).casefold()
        cwd_path = Path(cwd) if cwd else None

        for arg in cmdline:
            if not arg:
                continue

            arg_path = Path(arg.strip('"'))
            paths_to_check = [arg_path]
            if not arg_path.is_absolute() and cwd_path is not None:
                paths_to_check.append(cwd_path / arg_path)

            for path_to_check in paths_to_check:
                try:
                    if str(path_to_check.resolve()).casefold() == normalized_script:
                        return True
                except OSError:
                    continue

        return False

    def _resolve_windows_resurface_project_root(self) -> Path:
        for candidate in self._windows_resurface_project_root_candidates():
            candidate_root = candidate.resolve()
            if self._is_windows_resurface_project_root(candidate_root):
                return candidate_root

        return Path(__file__).resolve().parents[4]

    def _windows_resurface_project_root_candidates(self) -> tuple[Path, ...]:
        candidates = []

        env_path = os.environ.get(PROJECT_ROOT_ENV_VAR)
        if env_path:
            candidates.append(Path(env_path))

        source_root = Path(__file__).resolve().parents[4]
        candidates.append(source_root)

        cwd = Path.cwd().resolve()
        candidates.extend((cwd, *cwd.parents))

        candidates.append(Path.home() / "Desktop" / "Projects" / "Win-11-Resurface")

        unique_candidates = []
        seen = set()
        for candidate in candidates:
            candidate_str = str(candidate)
            if candidate_str in seen:
                continue
            seen.add(candidate_str)
            unique_candidates.append(candidate)

        return tuple(unique_candidates)

    def _is_windows_resurface_project_root(self, path: Path) -> bool:
        return (path / "Code Windows Resurface" / "main.py").is_file()

    def _python_script_command(self, script_path: Path) -> list[str]:
        executable_path = Path(sys.executable)
        executable_name = executable_path.name.lower()
        if executable_name.startswith("python"):
            return [str(executable_path), str(script_path)]

        python_path = shutil.which("python")
        if python_path:
            return [python_path, str(script_path)]

        py_launcher_path = shutil.which("py")
        if py_launcher_path:
            return [py_launcher_path, "-3", str(script_path)]

        return ["python", str(script_path)]

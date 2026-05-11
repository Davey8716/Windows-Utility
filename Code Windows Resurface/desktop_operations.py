import os
import subprocess
import sys
import inspect
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLineEdit

from state_manager import save_state
from utility_toggles import minimize_all_except_gui


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
    ) -> None:
        hwnd = None
        if hasattr(self, "winId"):
            try:
                hwnd = int(self.winId())
            except Exception:
                hwnd = None

        if hwnd:
            try:
                minimize_all_except_gui(hwnd)
            except Exception as exc:
                print(f"[SCREENSHOT] Global minimize failed: {exc}")

        try:
            self.showMinimized()
        except Exception as exc:
            print(f"[SCREENSHOT] App minimize failed: {exc}")

        if delay_ms_after_minimize > 0:
            QTimer.singleShot(delay_ms_after_minimize, action)
            return

        action()

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
        self._run_with_forced_desktop_minimize(
            self._capture_desktop_screenshot,
            delay_ms_after_minimize=500,
        )

    def _capture_desktop_screenshot(self):
        try:
            img = ImageGrab.grab()

            default_name = (
                f"DesktopScreenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )
            path_type = self._get_app_module_attr("Path", Path)
            save_state_fn = self._get_app_module_attr("save_state", save_state)
            save_dir = path_type(self._get_master_backup_dir())
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / default_name

            img.save(save_path)
            self.state["desktop_screenshot_last_path"] = str(save_path)
            try:
                save_state_fn(self.state)
            except Exception as exc:
                print(f"[STATE] Save failed: {exc}")
            print(f"[SCREENSHOT] Saved: {save_path}")
            self._show_organizing_timed_message(
                self._message_box_icon("Information"),
                "Desktop Screenshot",
                f"Desktop screenshot saved to:\n{save_path}",
                timeout_ms=5_000,
                show_close_now_button=True,
            )

        except Exception as exc:
            print("[SCREENSHOT] Error:", exc)
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
        save_state_fn = self._get_app_module_attr("save_state", save_state)
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
                folder_input.clear()
                self.state["folder_to_desktop_name"] = ""
                try:
                    save_state_fn(self.state)
                except Exception as exc:
                    print(f"[STATE] Save failed: {exc}")
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
        project_dir = Path(__file__).resolve().parent.parent / "Code Folder Creator"
        title_candidates = [
            "Folder Generator",
            "Folder Creator",
            "Code Folder Creator",
        ]
        launch_target = self._resolve_folder_creator_launch_target(project_dir)

        def launch():
            if launch_target is None:
                os.makedirs(project_dir, exist_ok=True)
                os.startfile(str(project_dir))
                return

            if launch_target.suffix.lower() in {".py", ".pyw"}:
                subprocess.Popen(
                    [sys.executable, str(launch_target)],
                    cwd=str(project_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

            if launch_target.suffix.lower() in {".bat", ".cmd"}:
                subprocess.Popen(
                    [str(launch_target)],
                    cwd=str(project_dir),
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

            subprocess.Popen(
                [str(launch_target)],
                cwd=str(project_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        def action():
            if launch_target is None:
                opened = self.actions.open_or_focus_folder_path(
                    str(project_dir),
                    launch=launch,
                )
            else:
                window_state = self.actions.get_window_titles_state(title_candidates)
                if window_state != "closed":
                    closed = self.actions.close_window_titles(title_candidates)
                    if closed:
                        QTimer.singleShot(
                            300,
                            self._monitor_folder_creator_window,
                        )
                        return

                self._begin_folder_creator_z_order_handoff(title_candidates)
                opened = self.actions.open_or_focus_window_titles(
                    title_candidates,
                    launch,
                )

                if opened:
                    self._focus_folder_creator_window(title_candidates)
                    return

            if opened:
                return

            self._restore_folder_creator_parent_topmost()
            self._show_organizing_timed_message(
                self._message_box_icon("Warning"),
                "Folder Creator",
                f"Could not open Folder Creator from:\n{project_dir}",
                show_close_now_button=True,
            )

        self._run_with_optional_minimize(action)

    def _resolve_folder_creator_launch_target(
        self,
        project_dir: Path,
    ) -> Path | None:
        candidate_names = (
            "main.py",
            "main.pyw",
            "app.py",
            "app.pyw",
            "run.py",
            "run.pyw",
            "launcher.py",
            "launcher.pyw",
            "start.py",
            "start.pyw",
            "Folder Creator.exe",
            "folder_creator.exe",
            "launch.bat",
            "start.bat",
        )

        for candidate_name in candidate_names:
            candidate_path = project_dir / candidate_name
            if candidate_path.exists():
                return candidate_path

        return None

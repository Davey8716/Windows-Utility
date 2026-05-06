import sys
import inspect
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLineEdit

from state_manager import save_state


class DesktopOperationsMixin:
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
                merge_title="Organising Utilities",
            )

        return show_timed_message(
            icon,
            title,
            text,
            timeout_ms=timeout_ms,
        )

    def _get_app_module_attr(self, name: str, default):
        module = sys.modules.get(self.__class__.__module__)
        return getattr(module, name, default)

    def take_desktop_screenshot(self):
        self.showMinimized()
        QTimer.singleShot(
            250,
            self._capture_desktop_screenshot,
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
            )

        except Exception as exc:
            print("[SCREENSHOT] Error:", exc)
            self._show_organizing_timed_message(
                self._message_box_icon("Warning"),
                "Desktop Screenshot",
                f"Could not save desktop screenshot:\n{exc}",
                timeout_ms=5_000,
            )

    def backup_taskbar_apps(self):
        backup_dir = self.get_default_taskbar_backup_dir()
        count = self.actions.backup_pinned_shortcuts(backup_dir)

        if count > 0:
            self._show_organizing_timed_message(
                self._message_box_icon("Information"),
                "Backup Taskbar",
                f"Backed up {count} taskbar shortcut(s) to:\n{backup_dir}",
            )
            return

        self._show_organizing_timed_message(
            self._message_box_icon("Warning"),
            "Backup Taskbar",
            "No taskbar shortcuts were backed up.",
        )

    def open_taskbar_backup_folder(self):
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

    def capture_desktop_layout(self):
        out_path = self.get_default_desktop_layout_path()
        count = self.actions.capture_desktop_layout(out_path)

        if count > 0:
            self._show_organizing_timed_message(
                self._message_box_icon("Information"),
                "Desktop Layout",
                f"Captured desktop layout with {count} icon position(s) saved to:\n{out_path}",
            )
            return

        self._show_organizing_timed_message(
            self._message_box_icon("Warning"),
            "Desktop Layout",
            f"Could not capture desktop layout to:\n{out_path}",
        )

    def restore_desktop_layout(self):
        layout_path = self.get_default_desktop_layout_path()
        count = self.actions.restore_desktop_layout(layout_path)

        if count > 0:
            self._show_organizing_timed_message(
                self._message_box_icon("Information"),
                "Desktop Layout",
                f"Desktop icons restored from:\n{layout_path}",
            )
            return

        self._show_organizing_timed_message(
            self._message_box_icon("Warning"),
            "Desktop Layout",
            f"Could not restore desktop layout from:\n{layout_path}",
        )

    def export_bookmarks(self):
        out_path = self.right_tools_panel._run_brave_export()
        if isinstance(out_path, str) and out_path:
            self._show_organizing_timed_message(
                self._message_box_icon("Information"),
                "Export Bookmarks",
                f"Bookmarks exported to:\n{out_path}",
            )
            return

        if out_path is False:
            self._show_organizing_timed_message(
                self._message_box_icon("Warning"),
                "Export Bookmarks",
                "Could not export bookmarks.",
            )

    def open_recycle_bin(self):
        if self.actions.open_recycle_bin():
            return

        self._show_timed_message(
            self._message_box_icon("Warning"),
            "Recycle Bin",
            "Could not open Recycle Bin.",
        )

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

        if self.actions.empty_recycle_bin():
            self._show_timed_message(
                self._message_box_icon("Information"),
                "Recycle Bin",
                "Recycle Bin emptied.",
            )
            return

        self._show_timed_message(
            self._message_box_icon("Warning"),
            "Recycle Bin",
            "Could not empty Recycle Bin.",
        )

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

        deleted_count = self.actions.cleanup_recycle_bin_items_older_than(days)
        if deleted_count > 0:
            title = "Recycle Bin Auto-Clean" if automatic else "Recycle Bin Cleanup"
            if should_show_automatic_popup:
                self._show_timed_message(
                    self._message_box_icon("Information"),
                    title,
                    f"Deleted {deleted_count} Recycle Bin item(s) older than {days} days.",
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
                )
                self.state["recycle_bin_last_auto_clean_popup_days"] = days
                self._save_state_safely(self.state)
            return

        self._show_timed_message(
            self._message_box_icon("Information"),
            "Recycle Bin Cleanup",
            f"No Recycle Bin items older than {days} days were found.",
        )

    def _create_desktop_folder(self, folder_input: QLineEdit):
        path_type = self._get_app_module_attr("Path", Path)
        save_state_fn = self._get_app_module_attr("save_state", save_state)
        folder_name = folder_input.text().strip()
        if not folder_name:
            return

        desktop = path_type.home() / "Desktop"
        new_path = desktop / folder_name

        try:
            if new_path.exists():
                self._show_organizing_timed_message(
                    self._message_box_icon("Warning"),
                    "Folder to Desktop",
                    "A folder with that name already exists on Desktop.",
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
            )

        except Exception as exc:
            self._show_organizing_timed_message(
                self._message_box_icon("Warning"),
                "Folder to Desktop",
                f"Could not create folder:\n{exc}",
            )

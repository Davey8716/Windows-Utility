from __future__ import annotations

import inspect
import os
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from resurface.core.state_manager import save_state
from resurface.features.bookmarks.universal_bookmarks_export import BraveBookmarksExporter
from resurface.features.desktop.desktop_icon_layout import (
    restore_desktop_icon_layout,
    save_desktop_icon_layout,
)
from resurface.features.desktop.screenshot_service import (
    ScreenshotCapturePlan,
    ScreenshotService,
)


class OrganisingActionsController:
    # These utility actions are deliberately visually distinct from the
    # application-wide square message boxes.
    POPUP_CORNER_RADIUS = 12

    def __init__(self, app, screenshot_service: ScreenshotService, taskbar_service, explorer_service):
        self.app = app
        self.screenshot_service = screenshot_service
        self.taskbar_service = taskbar_service
        self.explorer_service = explorer_service

    def should_minimize_after_use(self) -> bool:
        return bool(self.app.state.get("minimize_after_use_enabled", True))

    def minimize_self_if_configured(self) -> bool:
        if not self.should_minimize_after_use():
            return False
        self.app.showMinimized()
        return True

    def run_with_optional_minimize(self, action, *, delay_ms_when_minimized: int = 0) -> None:
        if self.minimize_self_if_configured() and delay_ms_when_minimized > 0:
            QTimer.singleShot(delay_ms_when_minimized, action)
            return
        action()

    def show_timed_message(
        self, icon, title: str, text: str, timeout_ms: int = 10_000,
        show_close_now_button: bool = False,
    ):
        show_message = self.app._show_timed_message
        try:
            params = inspect.signature(show_message).parameters
        except (TypeError, ValueError):
            params = {}
        options = {
            "timeout_ms": timeout_ms,
            "show_close_now_button": show_close_now_button,
        }
        if "popup_corner_radius" in params:
            options["popup_corner_radius"] = self.POPUP_CORNER_RADIUS
        if "merge_group" in params and "merge_title" in params:
            options.update(
                merge_group="organizing_utilities",
                merge_title="General Organising Utilities",
            )
        return show_message(icon, title, text, **options)

    def show_modal_message(self, icon, title: str, text: str, buttons, default_button):
        """Show an organising-utility confirmation with its rounded treatment."""
        show_message = self.app._show_modal_message
        try:
            params = inspect.signature(show_message).parameters
        except (TypeError, ValueError):
            params = {}
        options = (
            {"popup_corner_radius": self.POPUP_CORNER_RADIUS}
            if "popup_corner_radius" in params else {}
        )
        return show_message(icon, title, text, buttons, default_button, **options)

    def _save_state_safely(self) -> None:
        try:
            save_state(self.app.state)
        except Exception as exc:
            print(f"[STATE] Save failed: {exc}")

    def take_desktop_screenshot(self) -> None:
        plan = self.screenshot_service.build_capture_plan(self.app.get_default_screenshot_path())
        if plan.existing_paths:
            answer = self.show_modal_message(
                self.app._message_box_icon("Question"),
                "Overwrite Desktop Screenshots",
                "Desktop screenshots already exist in the screenshots backup folder."
                "\n\nOverwrite the current saved screenshot set?",
                self.app._message_box_button("Yes") | self.app._message_box_button("Cancel"),
                self.app._message_box_button("Cancel"),
            )
            if answer != self.app._message_box_button("Yes"):
                return
        self._run_forced_screenshot_capture(plan)

    def _run_forced_screenshot_capture(self, plan: ScreenshotCapturePlan) -> None:
        app_hwnd = None
        try:
            app_hwnd = int(self.app.winId())
        except Exception:
            pass
        tracked = self.screenshot_service.collect_windows_to_minimize(app_hwnd) if app_hwnd else ()
        self.screenshot_service.minimize_windows(tracked)
        try:
            self.app.showMinimized()
        except Exception as exc:
            print(f"[SCREENSHOT] App minimize failed: {exc}")
        QTimer.singleShot(500, lambda: self._capture_desktop_screenshot(plan, tracked, app_hwnd))

    def _restore_post_screenshot_state(self, tracked, app_hwnd: int | None) -> bool:
        self.screenshot_service.restore_windows(tracked)
        if self.should_minimize_after_use():
            return False
        if app_hwnd:
            try:
                self.app.showNormal()
                self.app.raise_()
                self.app.activateWindow()
            except Exception as exc:
                print(f"[SCREENSHOT] App restore failed: {exc}")
        return True

    def _capture_desktop_screenshot(self, plan, tracked, app_hwnd) -> None:
        result = self.screenshot_service.capture(plan)
        app_restored = self._restore_post_screenshot_state(tracked, app_hwnd)
        if not result.succeeded:
            print(f"[SCREENSHOT] Error: {result.error}")
            if app_restored:
                self.show_timed_message(
                    self.app._message_box_icon("Warning"), "Desktop Screenshot",
                    f"Could not save desktop screenshot:\n{result.error}",
                    timeout_ms=5_000, show_close_now_button=True,
                )
            return
        paths = result.saved_paths
        self.app.state["desktop_screenshot_last_path"] = str(paths[0])
        self.app.state["desktop_screenshot_last_dir"] = str(plan.save_dir)
        self._save_state_safely()
        print(f"[SCREENSHOT] Saved {len(paths)} monitor screenshot(s) to: {plan.save_dir}")
        if app_restored:
            summary = ""
            if len(paths) <= 3:
                summary = "\nSaved files:\n" + "\n".join(path.name for path in paths)
            self.show_timed_message(
                self.app._message_box_icon("Information"), "Desktop Screenshot",
                f"Saved {len(paths)} desktop screenshot(s) to:\n{plan.save_dir}{summary}",
                timeout_ms=5_000, show_close_now_button=True,
            )

    def backup_taskbar_apps(self) -> None:
        def action():
            backup_dir = self.app.get_default_taskbar_backup_dir()
            result = self.taskbar_service.backup(backup_dir)
            if result.completed and hasattr(self.app, "save_all_settings"):
                self.app.save_all_settings()
            if result.count > 0:
                self.show_timed_message(
                    self.app._message_box_icon("Information"), "Backup Taskbar",
                    f"Backed up {result.count} taskbar shortcut(s) to:\n{backup_dir}",
                    show_close_now_button=True,
                )
            else:
                self.show_timed_message(
                    self.app._message_box_icon("Warning"), "Backup Taskbar",
                    "No taskbar shortcuts were backed up.", show_close_now_button=True,
                )
        self.run_with_optional_minimize(action)

    def open_taskbar_backup_folder(self) -> None:
        def action():
            path = self.app.get_default_taskbar_backup_dir()
            if self.explorer_service.is_folder_open(path):
                closed = self.explorer_service.close_folder(path)
                self.app._refresh_taskbar_backup_folder_button()
                if not closed:
                    self._backup_folder_error("Close Backup Folder", "close", path)
                return
            def launch_folder():
                Path(path).mkdir(parents=True, exist_ok=True)
                os.startfile(path)

            opened = self.explorer_service.open_or_focus_folder(path, launch_folder)
            self.app._refresh_taskbar_backup_folder_button()
            if opened:
                QTimer.singleShot(500, self.app._refresh_taskbar_backup_folder_button)
            else:
                self._backup_folder_error("Open Backup Folder", "open", path)
        self.run_with_optional_minimize(action)

    def _backup_folder_error(self, title: str, verb: str, path: str) -> None:
        self.show_modal_message(
            self.app._message_box_icon("Warning"), title,
            f"Could not {verb} backup folder:\n{path}",
            self.app._message_box_button("Ok"), self.app._message_box_button("Ok"),
        )

    def capture_desktop_layout(self) -> None:
        answer = self.show_modal_message(
            self.app._message_box_icon("Question"),
            "Capture Desktop Layout",
            "Save the current desktop icon layout?",
            self.app._message_box_button("Yes") | self.app._message_box_button("Cancel"),
            self.app._message_box_button("Cancel"),
        )
        if answer != self.app._message_box_button("Yes"):
            return

        def action():
            path = self.app.get_default_desktop_layout_path()
            try:
                count = save_desktop_icon_layout(path)
                self.app.saved_state["desktop_layout_last_path"] = path
                if hasattr(self.app, "save_all_settings"):
                    self.app.save_all_settings()
            except Exception as exc:
                print(f"[DESKTOP ICONS] Capture failed: {exc}")
                count = 0
            icon = "Information" if count > 0 else "Warning"
            text = (
                f"Captured desktop layout with {count} icon position(s) saved to:\n{path}"
                if count > 0 else f"Could not capture desktop layout to:\n{path}"
            )
            self.show_timed_message(self.app._message_box_icon(icon), "Desktop Layout", text, show_close_now_button=True)
        self.run_with_optional_minimize(action)

    def restore_desktop_layout(self) -> None:
        def action():
            path = self.app.get_default_desktop_layout_path()
            try:
                count = restore_desktop_icon_layout(path)
                if hasattr(self.app, "save_all_settings"):
                    self.app.save_all_settings()
            except Exception as exc:
                print(f"[DESKTOP ICONS] Restore failed: {exc}")
                count = 0
            icon = "Information" if count > 0 else "Warning"
            text = f"Desktop icons restored from:\n{path}" if count > 0 else f"Could not restore desktop layout from:\n{path}"
            self.show_timed_message(self.app._message_box_icon(icon), "Desktop Layout", text, show_close_now_button=True)
        self.run_with_optional_minimize(action)

    def export_bookmarks(self) -> None:
        result = self.run_bookmarks_export()
        if result:
            self.show_timed_message(
                self.app._message_box_icon("Information"), "Export Bookmarks",
                "Bookmarks exported to:\n" + "\n".join(result),
                show_close_now_button=True,
            )
        elif result is False:
            self.show_timed_message(
                self.app._message_box_icon("Warning"), "Export Bookmarks",
                "Could not export bookmarks.",
            )

    def run_bookmarks_export(self) -> list[str] | None | bool:
        output_dir = Path(self.app.get_default_bookmarks_export_dir())
        output_dir.mkdir(parents=True, exist_ok=True)
        exporters = [exporter for exporter in BraveBookmarksExporter.supported_exporters() if exporter.has_bookmarks()]
        if not exporters:
            return False
        targets = [(exporter, output_dir / exporter.output_filename) for exporter in exporters]
        prompt = "Export bookmarks to:\n" + "\n".join(str(path) for _, path in targets)
        if any(path.exists() for _, path in targets):
            prompt += "\n\nExisting bookmark export files in this list will be overwritten."
        answer = self.show_modal_message(
            QMessageBox.Icon.NoIcon, "Export Bookmarks", prompt,
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer != QMessageBox.StandardButton.Save:
            return None
        exported: list[str] = []

        def action():
            for exporter, path in targets:
                if exporter.export_to_file(str(path)):
                    exported.append(str(path))

        self.run_with_optional_minimize(action)
        if exported:
            self._save_state_safely()
            return exported
        return False

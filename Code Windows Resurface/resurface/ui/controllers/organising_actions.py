from __future__ import annotations

import inspect
import os
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QMessageBox

from resurface.core.state_manager import save_state
from resurface.features.bookmarks.universal_bookmarks_export import BraveBookmarksExporter
from resurface.features.desktop.desktop_icon_layout import (
    alphabetise_desktop_icon_groups,
    capture_desktop_icon_layout,
    desktop_icon_groups_are_alphabetised,
    restore_desktop_icon_layout,
    save_desktop_icon_layout,
)
from resurface.features.desktop.screenshot_service import (
    ScreenshotCapturePlan,
    ScreenshotService,
)


def _format_desktop_layout_path(path: str) -> str:
    """Break the layout folder onto its own line for compact notifications."""
    directory, filename = os.path.split(path)
    if not directory or not filename:
        return path

    parent_directory, layout_directory = os.path.split(directory)
    if parent_directory and layout_directory:
        return f"{parent_directory}{os.sep}\n{layout_directory}{os.sep}{filename}"
    return f"{directory}{os.sep}\n{filename}"


class OrganisingActionsController:
    # These utility actions are deliberately visually distinct from the
    # application-wide square message boxes.
    POPUP_CORNER_RADIUS = 12
    # Reserve generous visual margins because the rendered message label uses
    # the styled popup font, which can be wider than the application font used
    # to calculate the line breaks.
    MODAL_PATH_TEXT_WIDTH = 280
    TIMED_PATH_TEXT_WIDTH = 270
    AUTO_EXPORT_INTERVALS = frozenset(("off", "daily", "weekly", "monthly"))
    AUTO_EXPORT_TIMER_INTERVAL_MS = 60_000
    AUTO_EXPORT_RETENTION = 10

    def __init__(self, app, screenshot_service: ScreenshotService, taskbar_service, explorer_service):
        self.app = app
        self.screenshot_service = screenshot_service
        self.taskbar_service = taskbar_service
        self.explorer_service = explorer_service
        self._bookmark_auto_export_timer: QTimer | None = None
        self._bookmark_auto_export_error_shown = False
        self._alphabetise_groups_monitor_timer: QTimer | None = None

    @staticmethod
    def _now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_utc_timestamp(value) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _add_calendar_month(value: datetime) -> datetime:
        month = value.month + 1
        year = value.year + (month > 12)
        month = 1 if month > 12 else month
        day = min(value.day, monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)

    def _bookmark_auto_export_interval(self) -> str:
        interval = self.app.state.get("bookmark_auto_export_interval", "off")
        return interval if interval in self.AUTO_EXPORT_INTERVALS else "off"

    def _bookmark_auto_export_is_due(self, now: datetime | None = None) -> bool:
        interval = self._bookmark_auto_export_interval()
        if interval == "off":
            return False
        last_success = self._parse_utc_timestamp(
            self.app.state.get("bookmark_auto_export_last_checked_at")
            or self.app.state.get("bookmark_auto_export_last_success_at")
        )
        if last_success is None:
            return True
        now = now or self._now_utc()
        if interval == "daily":
            return now >= last_success + timedelta(days=1)
        if interval == "weekly":
            return now >= last_success + timedelta(days=7)
        return now >= self._add_calendar_month(last_success)

    def _update_auto_export_page_status(self) -> None:
        page = getattr(getattr(self.app, "pages", None), "organising_utilities_page", None)
        if page is not None:
            page.set_auto_export_status(
                self._bookmark_auto_export_interval(),
                self.app.state.get("bookmark_auto_export_last_success_at"),
            )

    def _set_alphabetise_groups_available(self, available: bool) -> bool:
        page = getattr(getattr(self.app, "pages", None), "organising_utilities_page", None)
        if page is None or not hasattr(page, "set_alphabetise_groups_available"):
            return False
        page.set_alphabetise_groups_available(available)
        return True

    def _start_alphabetise_groups_monitor(self) -> None:
        if self._alphabetise_groups_monitor_timer is not None:
            return
        if not self._set_alphabetise_groups_available(False):
            return
        timer = QTimer()
        timer.setInterval(1_000)
        timer.timeout.connect(self._check_alphabetise_groups_state)
        self._alphabetise_groups_monitor_timer = timer
        timer.start()

    def _stop_alphabetise_groups_monitor(self, *, make_available: bool) -> None:
        timer = self._alphabetise_groups_monitor_timer
        if timer is not None:
            timer.stop()
        self._alphabetise_groups_monitor_timer = None
        if make_available:
            self._set_alphabetise_groups_available(True)

    def _check_alphabetise_groups_state(self) -> None:
        try:
            is_alphabetised = desktop_icon_groups_are_alphabetised(
                capture_desktop_icon_layout()
            )
        except Exception as exc:
            print(f"[DESKTOP ICONS] Could not check group alphabetisation: {exc}")
            self._stop_alphabetise_groups_monitor(make_available=True)
            return
        if not is_alphabetised:
            self._stop_alphabetise_groups_monitor(make_available=True)

    def set_bookmark_auto_export(self, interval: str) -> None:
        interval = interval if interval in self.AUTO_EXPORT_INTERVALS else "off"
        self.app.state["bookmark_auto_export_interval"] = interval
        self._save_state_safely()
        self._update_auto_export_page_status()
        if interval != "off":
            self._run_bookmark_auto_export_if_due()

    def start_bookmark_auto_export_scheduler(self) -> None:
        if self._bookmark_auto_export_timer is None:
            timer = QTimer(self.app)
            timer.setInterval(self.AUTO_EXPORT_TIMER_INTERVAL_MS)
            timer.timeout.connect(self._run_bookmark_auto_export_if_due)
            self._bookmark_auto_export_timer = timer
            timer.start()
        QTimer.singleShot(0, self._run_bookmark_auto_export_if_due)

    def stop_bookmark_auto_export_scheduler(self) -> None:
        if self._bookmark_auto_export_timer is not None:
            self._bookmark_auto_export_timer.stop()

    def _run_bookmark_auto_export_if_due(self) -> None:
        if self._bookmark_auto_export_is_due():
            self.run_bookmarks_auto_export()

    def run_bookmarks_auto_export_now(self) -> list[str] | bool:
        """Force one unattended snapshot without changing the saved schedule."""
        try:
            return self.run_bookmarks_auto_export(force=True)
        finally:
            self._update_auto_export_page_status()

    def _automatic_bookmark_filename(self, exporter, now: datetime) -> str:
        local_timestamp = now.astimezone().strftime("%Y-%m-%d_%H-%M-%S")
        return f"{exporter.export_stem}_Bookmarks_Auto_{local_timestamp}.html"

    def _prune_automatic_bookmark_exports(self, output_dir: Path, exporter) -> None:
        pattern = f"{exporter.export_stem}_Bookmarks_Auto_*.html"
        snapshots = sorted(
            output_dir.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True
        )
        for snapshot in snapshots[self.AUTO_EXPORT_RETENTION:]:
            try:
                snapshot.unlink()
            except OSError:
                pass

    def _show_bookmark_auto_export_error(self, detail: str) -> None:
        if self._bookmark_auto_export_error_shown:
            return
        self._bookmark_auto_export_error_shown = True
        self.show_timed_message(
            self.app._message_box_icon("Warning"), "Bookmark Auto-Export",
            f"Automatic bookmark export could not run.\n{detail}",
            show_close_now_button=True,
        )

    def _show_bookmark_auto_export_success(
        self, exported: list[str], output_dir: Path
    ) -> None:
        count = len(exported)
        noun = "snapshot" if count == 1 else "snapshots"
        self.show_timed_message(
            self.app._message_box_icon("Information"), "Bookmark Auto-Export",
            f"{count} bookmark {noun} saved to:\n{output_dir}",
            timeout_ms=5_000,
            show_close_now_button=True,
            fixed_popup_width=380,
            center_text_block=True,
            anchor_to_tray=True,
        )

    def run_bookmarks_auto_export(self, *, force: bool = False) -> list[str] | bool:
        if not getattr(self.app, "has_master_backup_path", lambda: True)():
            self._show_bookmark_auto_export_error("Set a Master Backup Path and try again.")
            return False
        try:
            output_dir = Path(self.app.get_default_bookmarks_export_dir())
            output_dir.mkdir(parents=True, exist_ok=True)
            exporters = BraveBookmarksExporter.supported_exporters()
            fingerprints = {}
            for exporter in exporters:
                fingerprint = exporter.bookmark_fingerprint()
                if fingerprint is not None:
                    fingerprints[exporter.export_stem] = fingerprint
            if not fingerprints:
                self._show_bookmark_auto_export_error("No supported browser bookmarks were found.")
                return False
            now = self._now_utc()
            previous_fingerprints = self.app.state.get(
                "bookmark_auto_export_fingerprints", {}
            )
            if not isinstance(previous_fingerprints, dict):
                previous_fingerprints = {}
            changed_exporters = (
                [
                    exporter for exporter in exporters
                    if exporter.export_stem in fingerprints
                ]
                if force
                else [
                    exporter for exporter in exporters
                    if exporter.export_stem in fingerprints
                    and fingerprints[exporter.export_stem]
                    != previous_fingerprints.get(exporter.export_stem)
                ]
            )
            if not changed_exporters:
                self.app.state["bookmark_auto_export_last_checked_at"] = now.isoformat()
                self._save_state_safely()
                return []
            exported: list[str] = []
            saved_fingerprints = dict(previous_fingerprints)
            for exporter in changed_exporters:
                path = output_dir / self._automatic_bookmark_filename(exporter, now)
                if exporter.export_to_file(str(path)):
                    exported.append(str(path))
                    saved_fingerprints[exporter.export_stem] = fingerprints[exporter.export_stem]
                    self._prune_automatic_bookmark_exports(output_dir, exporter)
            if not exported:
                self._show_bookmark_auto_export_error("No bookmark files could be created.")
                return False
        except Exception as exc:
            self._show_bookmark_auto_export_error(str(exc))
            return False
        self.app.state["bookmark_auto_export_last_success_at"] = now.isoformat()
        self.app.state["bookmark_auto_export_last_checked_at"] = now.isoformat()
        self.app.state["bookmark_auto_export_fingerprints"] = saved_fingerprints
        self._bookmark_auto_export_error_shown = False
        self._save_state_safely()
        self._update_auto_export_page_status()
        self._show_bookmark_auto_export_success(exported, output_dir)
        return exported

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

    def _require_master_backup_path(self) -> bool:
        has_master_backup_path = getattr(
            self.app, "has_master_backup_path", lambda: True
        )
        if has_master_backup_path():
            return True
        self.show_modal_message(
            self.app._message_box_icon("Warning"),
            "Master Backup Path Required",
            "Choose a Master Backup Path before creating, restoring, or "
            "exporting backups.",
            self.app._message_box_button("Ok"),
            self.app._message_box_button("Ok"),
        )
        return False

    def show_timed_message(
        self, icon, title: str, text: str, timeout_ms: int = 10_000,
        show_close_now_button: bool = False,
        text_block_width: int | None = None,
        fixed_popup_width: int | None = None,
        center_text_block: bool = False,
        anchor_to_tray: bool = False,
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
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in params.values()
        )
        def accepts(name: str) -> bool:
            return name in params or accepts_kwargs
        if text_block_width is not None and accepts("text_block_width"):
            options["text_block_width"] = text_block_width
        if fixed_popup_width is not None and accepts("fixed_popup_width"):
            options["fixed_popup_width"] = fixed_popup_width
        if center_text_block and accepts("center_text_block"):
            options["center_text_block"] = True
        if accepts("popup_corner_radius"):
            options["popup_corner_radius"] = self.POPUP_CORNER_RADIUS
        if anchor_to_tray and accepts("anchor_to_tray"):
            options["anchor_to_tray"] = True
        if not anchor_to_tray and accepts("merge_group") and accepts("merge_title"):
            options.update(
                merge_group="organizing_utilities",
                merge_title="General Organising Utilities",
            )
        return show_message(icon, title, text, **options)

    def show_modal_message(
        self,
        icon,
        title: str,
        text: str,
        buttons,
        default_button,
        *,
        text_block_width: int | None = None,
        fixed_popup_width: int | None = None,
        center_text_block: bool = False,
    ):
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
        if text_block_width is not None and "text_block_width" in params:
            options["text_block_width"] = text_block_width
        if fixed_popup_width is not None and "fixed_popup_width" in params:
            options["fixed_popup_width"] = fixed_popup_width
        if center_text_block and "center_text_block" in params:
            options["center_text_block"] = True
        return show_message(icon, title, text, buttons, default_button, **options)

    def _save_state_safely(self) -> None:
        try:
            save_state(self.app.state)
        except Exception as exc:
            print(f"[STATE] Save failed: {exc}")

    def _popup_font_metrics(self) -> QFontMetrics:
        get_font = getattr(self.app, "font", None)
        if callable(get_font):
            try:
                return QFontMetrics(get_font())
            except (TypeError, RuntimeError):
                pass
        application = QApplication.instance()
        if application is not None:
            return QFontMetrics(application.font())
        return QFontMetrics(QFont())

    def _wrap_popup_path(self, path: str | Path, maximum_width: int) -> str:
        """Wrap a path at readable boundaries without dropping characters."""
        path_text = str(path)
        metrics = self._popup_font_metrics()
        lines: list[str] = []
        remaining = path_text
        while remaining:
            if metrics.horizontalAdvance(remaining) <= maximum_width:
                lines.append(remaining)
                break

            fitting_indexes = [
                index
                for index in range(1, len(remaining) + 1)
                if metrics.horizontalAdvance(remaining[:index]) <= maximum_width
            ]
            if not fitting_indexes:
                lines.append(remaining[0])
                remaining = remaining[1:]
                continue

            readable_indexes = [
                index
                for index in fitting_indexes
                if remaining[index - 1] in "\\/_-"
            ]
            split_at = max(readable_indexes or fitting_indexes)
            lines.append(remaining[:split_at])
            remaining = remaining[split_at:]

        return "\n".join(lines)

    def take_desktop_screenshot(self) -> None:
        if not self._require_master_backup_path():
            return
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
        summary = ""
        if len(paths) <= 3:
            summary = "\nSaved files:\n" + "\n".join(
                self._wrap_popup_path(path.name, self.TIMED_PATH_TEXT_WIDTH)
                for path in paths
            )
        self.show_timed_message(
            self.app._message_box_icon("Information"), "Desktop Screenshot",
            "Saved "
            f"{len(paths)} desktop screenshot(s) to:\n"
            f"{self._wrap_popup_path(plan.save_dir, self.TIMED_PATH_TEXT_WIDTH)}"
            f"{summary}",
            timeout_ms=10_000, show_close_now_button=True,
            fixed_popup_width=380, center_text_block=True,
        )

    def backup_taskbar_apps(self) -> None:
        if not self._require_master_backup_path():
            return
        answer = self.show_modal_message(
            self.app._message_box_icon("Question"),
            "Backup Taskbar",
            "Back up the current pinned taskbar shortcuts?\nExisting shortcuts"
            "with the same names in the\n backup folder will be overwritten.",
            self.app._message_box_button("Yes") | self.app._message_box_button("Cancel"),
            self.app._message_box_button("Cancel"),
            text_block_width=320,
            center_text_block=True,
        )
        if answer != self.app._message_box_button("Yes"):
            return

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
        if not self._require_master_backup_path():
            return
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
        if not self._require_master_backup_path():
            return
        answer = self.show_modal_message(
            self.app._message_box_icon("Question"),
            "Capture Desktop Layout",
            "Save the current desktop icon layout?\nThe existing saved layout"
            "will be overwritten.",
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
                "Captured desktop layout with "
                f"{count} icon position(s) saved to:\n"
                f"{_format_desktop_layout_path(path)}"
                if count > 0 else f"Could not capture desktop layout to:\n{path}"
            )
            self.show_timed_message(
                self.app._message_box_icon(icon),
                "Desktop Layout",
                text,
                show_close_now_button=True,
                text_block_width=360,
                center_text_block=True,
            )
        self.run_with_optional_minimize(action)

    def restore_desktop_layout(self) -> None:
        if not self._require_master_backup_path():
            return
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
            if count > 0:
                text = f"Desktop icons restored from:\n{_format_desktop_layout_path(path)}"
            else:
                text = f"Could not restore desktop layout from:\n{path}"
            self.show_timed_message(
                self.app._message_box_icon(icon),
                "Desktop Layout",
                text,
                show_close_now_button=True,
                text_block_width=360 if count > 0 else None,
            )
        self.run_with_optional_minimize(action)

    def alphabetise_desktop_groups(self) -> None:
        answer = self.show_modal_message(
            self.app._message_box_icon("Question"),
            "Alphabetise Desktop Groups",
            "Alphabetise icons within each detected desktop group?\n"
            "Their groups will stay in place, but icon positions will change.",
            self.app._message_box_button("Yes") | self.app._message_box_button("Cancel"),
            self.app._message_box_button("Cancel"),
        )
        if answer != self.app._message_box_button("Yes"):
            return

        def action():
            try:
                group_count, icon_count = alphabetise_desktop_icon_groups()
            except Exception as exc:
                print(f"[DESKTOP ICONS] Group alphabetisation failed: {exc}")
                group_count, icon_count = 0, 0
            icon = "Information" if icon_count > 0 else "Warning"
            text = (
                f"Alphabetised {icon_count} icon(s) within {group_count} desktop group(s)."
                if icon_count > 0
                else "Could not alphabetise the detected desktop groups."
            )
            if icon_count > 0:
                self._start_alphabetise_groups_monitor()
            self.show_timed_message(
                self.app._message_box_icon(icon),
                "Desktop Groups",
                text,
                show_close_now_button=True,
                text_block_width=360,
                center_text_block=True,
            )

        action()

    def export_bookmarks(self) -> None:
        if not self._require_master_backup_path():
            return
        result = self.run_bookmarks_export()
        if result:
            self.show_timed_message(
                self.app._message_box_icon("Information"), "Export Bookmarks",
                "Bookmarks exported to:\n"
                + "\n".join(
                    self._wrap_popup_path(path, self.TIMED_PATH_TEXT_WIDTH)
                    for path in result
                ),
                show_close_now_button=True,
                fixed_popup_width=380, center_text_block=True,
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
        prompt = "Export bookmarks to:\n" + "\n".join(
            self._wrap_popup_path(path, self.MODAL_PATH_TEXT_WIDTH)
            for _, path in targets
        )
        if any(path.exists() for _, path in targets):
            prompt += "\n\nExisting bookmark export files in this list will be overwritten."
        answer = self.show_modal_message(
            QMessageBox.Icon.NoIcon, "Export Bookmarks", prompt,
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
            fixed_popup_width=380, center_text_block=True,
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

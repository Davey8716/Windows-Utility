from pathlib import Path
from datetime import datetime, timezone

from PySide6.QtWidgets import QApplication, QMessageBox

from resurface.features.desktop.screenshot_service import (
    ScreenshotCapturePlan,
    ScreenshotCaptureResult,
)
from resurface.features.taskbar.backup_service import BackupResult
from resurface.ui.controllers import organising_actions
from resurface.ui.controllers.organising_actions import OrganisingActionsController


class App:
    def __init__(self, answer=QMessageBox.StandardButton.Cancel):
        self.answer = answer
        self.state = {}
        self.saved_state = {}
        self.modals = []
        self.modal_options = []
        self.timed_messages = []
        self.minimized = 0
        self.settings_saves = 0

    @staticmethod
    def _message_box_icon(name):
        return name

    @staticmethod
    def _message_box_button(name):
        return getattr(QMessageBox.StandardButton, name)

    def _show_modal_message(
        self,
        icon,
        title,
        text,
        buttons,
        default_button,
        *,
        popup_corner_radius=None,
        text_block_width=None,
        fixed_popup_width=None,
        center_text_block=False,
    ):
        kwargs = {"popup_corner_radius": popup_corner_radius}
        if text_block_width is not None:
            kwargs["text_block_width"] = text_block_width
        if fixed_popup_width is not None:
            kwargs["fixed_popup_width"] = fixed_popup_width
        if center_text_block:
            kwargs["center_text_block"] = True
        self.modals.append((icon, title, text, buttons, default_button, popup_corner_radius))
        self.modal_options.append(kwargs)
        return self.answer

    def get_default_desktop_layout_path(self):
        return "layout.json"

    def get_default_taskbar_backup_dir(self):
        return "TaskBarApps"

    def showMinimized(self):
        self.minimized += 1

    def save_all_settings(self):
        self.settings_saves += 1

    def _show_timed_message(
        self,
        *args,
        text_block_width=None,
        fixed_popup_width=None,
        center_text_block=False,
        popup_corner_radius=None,
        **kwargs,
    ):
        if text_block_width is not None:
            kwargs["text_block_width"] = text_block_width
        if fixed_popup_width is not None:
            kwargs["fixed_popup_width"] = fixed_popup_width
        if center_text_block:
            kwargs["center_text_block"] = True
        if popup_corner_radius is not None:
            kwargs["popup_corner_radius"] = popup_corner_radius
        self.timed_messages.append((args, kwargs))


class TaskbarService:
    def __init__(self, result):
        self.result = result
        self.backup_paths = []

    def backup(self, path):
        self.backup_paths.append(path)
        return self.result


class BookmarkExporter:
    export_stem = "TestBrowser"
    output_filename = "TestBrowser_Bookmarks.html"

    def has_bookmarks(self):
        return True

    def bookmark_fingerprint(self):
        return "bookmark-fingerprint"

    def export_to_file(self, path):
        Path(path).write_text("bookmarks", encoding="utf-8")
        return True


def test_capture_layout_requires_rounded_confirmation(monkeypatch):
    app = App()
    captured_paths = []
    monkeypatch.setattr(
        organising_actions,
        "save_desktop_icon_layout",
        lambda path: captured_paths.append(path) or 1,
    )
    controller = OrganisingActionsController(app, None, None, None)
    controller.run_with_optional_minimize = lambda action: action()

    controller.capture_desktop_layout()

    assert captured_paths == []
    assert app.modals == [
        (
            "Question",
            "Capture Desktop Layout",
            "Save the current desktop icon layout?\nThe existing saved layout."
            "will be overwritten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
            controller.POPUP_CORNER_RADIUS,
        )
    ]
    assert app.modal_options == [{"popup_corner_radius": controller.POPUP_CORNER_RADIUS}]


def test_capture_layout_uses_a_360px_text_block(monkeypatch):
    app = App(answer=QMessageBox.StandardButton.Yes)
    app.get_default_desktop_layout_path = (
        lambda: "C:\\Backup\\Desktop Icon Layout\\desktop_icon_layout.json"
    )
    monkeypatch.setattr(organising_actions, "save_desktop_icon_layout", lambda _path: 3)
    controller = OrganisingActionsController(app, None, None, None)
    controller.run_with_optional_minimize = lambda action: action()

    controller.capture_desktop_layout()

    assert app.timed_messages == [
        (
            (
                "Information",
                "Desktop Layout",
                "Captured desktop layout with 3 icon position(s) saved to:\n"
                "C:\\Backup\\\n"
                "Desktop Icon Layout\\desktop_icon_layout.json",
            ),
            {
                "timeout_ms": 10_000,
                "show_close_now_button": True,
                "text_block_width": 360,
                "center_text_block": True,
                "popup_corner_radius": controller.POPUP_CORNER_RADIUS,
            },
        )
    ]


def test_capture_layout_failure_uses_a_360px_text_block(monkeypatch):
    app = App(answer=QMessageBox.StandardButton.Yes)

    def fail_capture(_path):
        raise OSError("disk unavailable")

    monkeypatch.setattr(organising_actions, "save_desktop_icon_layout", fail_capture)
    controller = OrganisingActionsController(app, None, None, None)
    controller.run_with_optional_minimize = lambda action: action()

    controller.capture_desktop_layout()

    assert app.timed_messages == [
        (
            (
                "Warning",
                "Desktop Layout",
                "Could not capture desktop layout to:\nlayout.json",
            ),
            {
                "timeout_ms": 10_000,
                "show_close_now_button": True,
                "text_block_width": 360,
                "popup_corner_radius": controller.POPUP_CORNER_RADIUS,
            },
        )
    ]


def test_restore_layout_success_uses_a_360px_text_block(monkeypatch):
    app = App()
    app.get_default_desktop_layout_path = (
        lambda: "C:\\Backup\\Desktop Icon Layout\\desktop_icon_layout.json"
    )
    monkeypatch.setattr(organising_actions, "restore_desktop_icon_layout", lambda _path: 3)
    controller = OrganisingActionsController(app, None, None, None)
    controller.run_with_optional_minimize = lambda action: action()

    controller.restore_desktop_layout()

    assert app.timed_messages == [
        (
            (
                "Information",
                "Desktop Layout",
                "Desktop icons restored from:\n"
                "C:\\Backup\\\n"
                "Desktop Icon Layout\\desktop_icon_layout.json",
            ),
            {
                "timeout_ms": 10_000,
                "show_close_now_button": True,
                "text_block_width": 360,
                "popup_corner_radius": controller.POPUP_CORNER_RADIUS,
            },
        )
    ]


def test_backup_taskbar_cancelled_before_minimize_or_backup():
    app = App(answer=QMessageBox.StandardButton.Cancel)
    taskbar_service = TaskbarService(BackupResult(count=1, completed=True))
    controller = OrganisingActionsController(app, None, taskbar_service, None)

    controller.backup_taskbar_apps()

    assert app.modals == [
        (
            "Question",
            "Backup Taskbar",
            "Back up the current pinned taskbar shortcuts? Existing shortcuts "
            "with the same names in the backup folder will be overwritten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
            controller.POPUP_CORNER_RADIUS,
        )
    ]
    assert app.modal_options == [
        {
            "popup_corner_radius": controller.POPUP_CORNER_RADIUS,
            "text_block_width": 360,
            "center_text_block": True,
        }
    ]
    assert taskbar_service.backup_paths == []
    assert app.minimized == 0
    assert app.settings_saves == 0
    assert app.timed_messages == []


def test_backup_taskbar_runs_and_notifies_after_confirmation():
    app = App(answer=QMessageBox.StandardButton.Yes)
    taskbar_service = TaskbarService(BackupResult(count=2, completed=True))
    controller = OrganisingActionsController(app, None, taskbar_service, None)
    controller.run_with_optional_minimize = lambda action: action()

    controller.backup_taskbar_apps()

    assert taskbar_service.backup_paths == ["TaskBarApps"]
    assert app.settings_saves == 1
    assert app.timed_messages == [
        (
            (
                "Information",
                "Backup Taskbar",
                "Backed up 2 taskbar shortcut(s) to:\nTaskBarApps",
            ),
            {
                "timeout_ms": 10_000,
                "show_close_now_button": True,
                "popup_corner_radius": controller.POPUP_CORNER_RADIUS,
            },
        )
    ]


class ScreenshotService:
    def __init__(self, result):
        self.result = result
        self.restored_windows = []

    def capture(self, _plan):
        return self.result

    def restore_windows(self, tracked):
        self.restored_windows.append(tracked)


def _screenshot_plan():
    return ScreenshotCapturePlan(
        monitors=(),
        save_dir=Path("C:/Backups/Desktop Screenshots"),
        target_paths=(),
        stale_paths=(),
        existing_paths=(),
    )


def test_successful_screenshot_persists_and_shows_rounded_ten_second_notification(
    monkeypatch,
):
    QApplication.instance() or QApplication([])
    app = App()
    saved_paths = (
        Path("C:/Backups/Desktop Screenshots/DesktopScreenshot_Monitor1.png"),
        Path("C:/Backups/Desktop Screenshots/DesktopScreenshot_Monitor2.png"),
    )
    service = ScreenshotService(ScreenshotCaptureResult(saved_paths))
    saved_states = []
    monkeypatch.setattr(
        organising_actions, "save_state", lambda state: saved_states.append(state)
    )
    controller = OrganisingActionsController(app, service, None, None)

    controller._capture_desktop_screenshot(_screenshot_plan(), (), None)

    assert app.state["desktop_screenshot_last_path"] == str(saved_paths[0])
    assert app.state["desktop_screenshot_last_dir"] == "C:\\Backups\\Desktop Screenshots"
    assert saved_states == [app.state]
    assert app.timed_messages == [
        (
            (
                "Information",
                "Desktop Screenshot",
                "Saved 2 desktop screenshot(s) to:\n"
                + controller._wrap_popup_path(
                    "C:\\Backups\\Desktop Screenshots",
                    controller.TIMED_PATH_TEXT_WIDTH,
                )
                + "\nSaved files:\n"
                + "\n".join(
                    controller._wrap_popup_path(
                        path.name, controller.TIMED_PATH_TEXT_WIDTH
                    )
                    for path in saved_paths
                ),
            ),
            {
                "timeout_ms": 10_000,
                "show_close_now_button": True,
                "fixed_popup_width": 380,
                "center_text_block": True,
                "popup_corner_radius": controller.POPUP_CORNER_RADIUS,
            },
        )
    ]


def test_successful_screenshot_notifies_when_minimize_after_use_keeps_app_minimized(
    monkeypatch,
):
    QApplication.instance() or QApplication([])
    app = App()
    app.state["minimize_after_use_enabled"] = True
    service = ScreenshotService(
        ScreenshotCaptureResult(
            (Path("C:/Backups/Desktop Screenshots/DesktopScreenshot_Monitor1.png"),)
        )
    )
    monkeypatch.setattr(organising_actions, "save_state", lambda _state: None)
    controller = OrganisingActionsController(app, service, None, None)

    controller._capture_desktop_screenshot(_screenshot_plan(), (), None)

    assert app.timed_messages[0][0][0:2] == ("Information", "Desktop Screenshot")
    assert app.timed_messages[0][1]["timeout_ms"] == 10_000


def test_failed_screenshot_notification_remains_five_seconds_and_requires_restoration():
    app = App()
    app.state["minimize_after_use_enabled"] = False
    service = ScreenshotService(ScreenshotCaptureResult((), "disk unavailable"))
    controller = OrganisingActionsController(app, service, None, None)

    controller._capture_desktop_screenshot(_screenshot_plan(), (), None)

    assert app.timed_messages == [
        (
            (
                "Warning",
                "Desktop Screenshot",
                "Could not save desktop screenshot:\ndisk unavailable",
            ),
            {
                "timeout_ms": 5_000,
                "show_close_now_button": True,
                "popup_corner_radius": controller.POPUP_CORNER_RADIUS,
            },
        )
    ]

    app.state["minimize_after_use_enabled"] = True
    controller._capture_desktop_screenshot(_screenshot_plan(), (), None)

    assert len(app.timed_messages) == 1


def test_bookmark_export_confirmation_uses_a_centered_380px_popup(monkeypatch, tmp_path):
    QApplication.instance() or QApplication([])
    app = App()
    app.get_default_bookmarks_export_dir = lambda: str(tmp_path)
    output_filename = "browser_bookmarks_" + "very_long_name_" * 16 + ".html"

    class Exporter:
        @staticmethod
        def has_bookmarks():
            return True

    Exporter.output_filename = output_filename

    monkeypatch.setattr(
        organising_actions.BraveBookmarksExporter,
        "supported_exporters",
        lambda: (Exporter(),),
    )
    controller = OrganisingActionsController(app, None, None, None)

    assert controller.run_bookmarks_export() is None
    target = tmp_path / output_filename
    prompt_lines = app.modals[0][2].splitlines()
    assert prompt_lines[0] == "Export bookmarks to:"
    assert "".join(prompt_lines[1:]) == str(target)
    assert all(
        controller._popup_font_metrics().horizontalAdvance(line)
        <= controller.MODAL_PATH_TEXT_WIDTH
        for line in prompt_lines[1:]
    )
    assert app.modal_options == [
        {
            "popup_corner_radius": controller.POPUP_CORNER_RADIUS,
            "fixed_popup_width": 380,
            "center_text_block": True,
        }
    ]


def test_successful_bookmark_export_uses_a_centered_380px_popup():
    QApplication.instance() or QApplication([])
    app = App()
    controller = OrganisingActionsController(app, None, None, None)
    exported_path = "C:/Backups/Bookmarks/" + "very_long_name_" * 16 + "browser.html"
    controller.run_bookmarks_export = lambda: [exported_path]

    controller.export_bookmarks()

    assert app.timed_messages == [
        (
            (
                "Information",
                "Export Bookmarks",
                "Bookmarks exported to:\n"
                + controller._wrap_popup_path(
                    exported_path, controller.TIMED_PATH_TEXT_WIDTH
                ),
            ),
            {
                "timeout_ms": 10_000,
                "show_close_now_button": True,
                "fixed_popup_width": 380,
                "center_text_block": True,
                "popup_corner_radius": controller.POPUP_CORNER_RADIUS,
            },
        )
    ]

    message_lines = app.timed_messages[0][0][2].splitlines()
    assert "".join(message_lines[1:]) == exported_path
    assert all(
        controller._popup_font_metrics().horizontalAdvance(line)
        <= controller.TIMED_PATH_TEXT_WIDTH
        for line in message_lines[1:]
    )


def test_bookmark_auto_export_due_times_are_calendar_based():
    controller = OrganisingActionsController(App(), None, None, None)
    now = datetime(2026, 2, 28, 12, tzinfo=timezone.utc)
    controller.app.state.update({
        "bookmark_auto_export_interval": "monthly",
        "bookmark_auto_export_last_success_at": "2026-01-31T12:00:00+00:00",
    })
    assert controller._bookmark_auto_export_is_due(now)

    controller.app.state.update({
        "bookmark_auto_export_interval": "daily",
        "bookmark_auto_export_last_success_at": "2026-02-27T12:00:01+00:00",
    })
    assert not controller._bookmark_auto_export_is_due(now)

    controller.app.state.update({
        "bookmark_auto_export_interval": "weekly",
        "bookmark_auto_export_last_success_at": "2026-02-21T12:00:00+00:00",
    })
    assert controller._bookmark_auto_export_is_due(now)


def test_bookmark_auto_export_creates_snapshot_and_prunes_history(monkeypatch, tmp_path):
    app = App()
    app.get_default_bookmarks_export_dir = lambda: str(tmp_path)
    controller = OrganisingActionsController(app, None, None, None)
    controller._now_utc = lambda: datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
    for number in range(10):
        (tmp_path / f"TestBrowser_Bookmarks_Auto_2026-01-{number + 1:02d}_00-00-00.html").write_text("old")
    monkeypatch.setattr(
        organising_actions.BraveBookmarksExporter, "supported_exporters", lambda: [BookmarkExporter()]
    )
    monkeypatch.setattr(organising_actions, "save_state", lambda _state: None)

    exported = controller.run_bookmarks_auto_export()

    assert len(exported) == 1
    snapshots = list(tmp_path.glob("TestBrowser_Bookmarks_Auto_*.html"))
    assert len(snapshots) == 10
    assert Path(exported[0]).exists()
    assert app.state["bookmark_auto_export_last_success_at"] == "2026-10-06T12:00:00+00:00"
    assert not app.modals
    assert app.timed_messages[-1] == (
        (
            "Information",
            "Bookmark Auto-Export",
            f"1 bookmark snapshot saved to:\n{tmp_path}",
        ),
        {
            "timeout_ms": 5_000,
            "show_close_now_button": True,
            "fixed_popup_width": 380,
            "center_text_block": True,
            "popup_corner_radius": controller.POPUP_CORNER_RADIUS,
            "anchor_to_tray": True,
        },
    )


def test_bookmark_auto_export_skips_unchanged_bookmarks(monkeypatch, tmp_path):
    app = App()
    app.get_default_bookmarks_export_dir = lambda: str(tmp_path)
    app.state["bookmark_auto_export_fingerprints"] = {
        "TestBrowser": "bookmark-fingerprint"
    }
    app.state["bookmark_auto_export_last_success_at"] = "2026-10-01T12:00:00+00:00"
    controller = OrganisingActionsController(app, None, None, None)
    controller._now_utc = lambda: datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(
        organising_actions.BraveBookmarksExporter, "supported_exporters", lambda: [BookmarkExporter()]
    )
    monkeypatch.setattr(organising_actions, "save_state", lambda _state: None)

    assert controller.run_bookmarks_auto_export() == []
    assert not list(tmp_path.glob("TestBrowser_Bookmarks_Auto_*.html"))
    assert app.state["bookmark_auto_export_last_success_at"] == "2026-10-01T12:00:00+00:00"
    assert app.state["bookmark_auto_export_last_checked_at"] == "2026-10-06T12:00:00+00:00"


def test_bookmark_auto_export_failure_notifies_once_per_session(monkeypatch, tmp_path):
    app = App()
    app.get_default_bookmarks_export_dir = lambda: str(tmp_path)
    controller = OrganisingActionsController(app, None, None, None)
    monkeypatch.setattr(
        organising_actions.BraveBookmarksExporter, "supported_exporters", lambda: []
    )

    assert controller.run_bookmarks_auto_export() is False
    assert controller.run_bookmarks_auto_export() is False

    assert len(app.timed_messages) == 1
    assert "bookmark_auto_export_last_success_at" not in app.state


def test_selecting_bookmark_auto_export_persists_and_runs_initial_export(monkeypatch):
    app = App()
    controller = OrganisingActionsController(app, None, None, None)
    calls = []
    controller._run_bookmark_auto_export_if_due = lambda: calls.append(True)
    monkeypatch.setattr(organising_actions, "save_state", lambda _state: None)

    controller.set_bookmark_auto_export("weekly")

    assert app.state["bookmark_auto_export_interval"] == "weekly"
    assert calls == [True]


def test_bookmark_auto_export_now_does_not_change_saved_schedule():
    app = App()
    app.state["bookmark_auto_export_interval"] = "weekly"
    controller = OrganisingActionsController(app, None, None, None)
    force_values = []
    controller.run_bookmarks_auto_export = lambda *, force: force_values.append(force) or ["snapshot.html"]

    assert controller.run_bookmarks_auto_export_now() == ["snapshot.html"]
    assert force_values == [True]
    assert app.state["bookmark_auto_export_interval"] == "weekly"


def test_successful_screenshot_wraps_long_directory_and_filename_paths(monkeypatch):
    QApplication.instance() or QApplication([])
    app = App()
    save_dir = Path("C:/Backups/" + "very_long_directory_name_" * 12)
    filename = "DesktopScreenshot_" + "very_long_monitor_name_" * 10 + ".png"
    saved_path = save_dir / filename
    plan = ScreenshotCapturePlan(
        monitors=(),
        save_dir=save_dir,
        target_paths=(),
        stale_paths=(),
        existing_paths=(),
    )
    monkeypatch.setattr(organising_actions, "save_state", lambda _state: None)
    controller = OrganisingActionsController(
        app, ScreenshotService(ScreenshotCaptureResult((saved_path,))), None, None
    )

    controller._capture_desktop_screenshot(plan, (), None)

    message_lines = app.timed_messages[0][0][2].splitlines()
    saved_files_index = message_lines.index("Saved files:")
    assert "".join(message_lines[1:saved_files_index]) == str(save_dir)
    assert "".join(message_lines[saved_files_index + 1:]) == filename
    assert all(
        controller._popup_font_metrics().horizontalAdvance(line)
        <= controller.TIMED_PATH_TEXT_WIDTH
        for line in message_lines[1:saved_files_index]
        + message_lines[saved_files_index + 1:]
    )

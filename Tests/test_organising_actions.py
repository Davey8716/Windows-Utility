from PySide6.QtWidgets import QMessageBox

from resurface.features.taskbar.backup_service import BackupResult
from resurface.ui.controllers import organising_actions
from resurface.ui.controllers.organising_actions import OrganisingActionsController


class App:
    def __init__(self, answer=QMessageBox.StandardButton.Cancel):
        self.answer = answer
        self.state = {}
        self.saved_state = {}
        self.modals = []
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
        self, icon, title, text, buttons, default_button, *, popup_corner_radius=None
    ):
        self.modals.append((icon, title, text, buttons, default_button, popup_corner_radius))
        return self.answer

    def get_default_desktop_layout_path(self):
        return "layout.json"

    def get_default_taskbar_backup_dir(self):
        return "TaskBarApps"

    def showMinimized(self):
        self.minimized += 1

    def save_all_settings(self):
        self.settings_saves += 1

    def _show_timed_message(self, *args, text_block_width=None, **kwargs):
        if text_block_width is not None:
            kwargs["text_block_width"] = text_block_width
        self.timed_messages.append((args, kwargs))


class TaskbarService:
    def __init__(self, result):
        self.result = result
        self.backup_paths = []

    def backup(self, path):
        self.backup_paths.append(path)
        return self.result


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
            "Save the current desktop icon layout?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
            controller.POPUP_CORNER_RADIUS,
        )
    ]


def test_capture_layout_uses_a_360px_text_block(monkeypatch):
    app = App(answer=QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(organising_actions, "save_desktop_icon_layout", lambda _path: 3)
    controller = OrganisingActionsController(app, None, None, None)
    controller.run_with_optional_minimize = lambda action: action()

    controller.capture_desktop_layout()

    assert app.timed_messages == [
        (
            (
                "Information",
                "Desktop Layout",
                "Captured desktop layout with 3 icon position(s) saved to:\nlayout.json",
            ),
            {
                "timeout_ms": 10_000,
                "show_close_now_button": True,
                "text_block_width": 360,
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
            "Back up the current pinned taskbar shortcuts?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
            controller.POPUP_CORNER_RADIUS,
        )
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
            {"timeout_ms": 10_000, "show_close_now_button": True},
        )
    ]

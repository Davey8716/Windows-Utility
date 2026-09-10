from PySide6.QtWidgets import QMessageBox

from resurface.ui.controllers import organising_actions
from resurface.ui.controllers.organising_actions import OrganisingActionsController


class App:
    def __init__(self, answer=QMessageBox.StandardButton.Cancel):
        self.answer = answer
        self.state = {}
        self.saved_state = {}
        self.modals = []

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

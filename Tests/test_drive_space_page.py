import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from resurface.features.drives.drive_service import DriveServiceError
from resurface.ui.external_drive_popups import status_popup_options
from resurface.ui.pages.drive_space_page import DriveSpacePage


class _DriveService:
    def __init__(self, error=None):
        self.error = error
        self.ejected_paths = []

    def eject(self, path):
        if self.error is not None:
            raise self.error
        self.ejected_paths.append(path)


def _bare_page(service, messages):
    page = DriveSpacePage.__new__(DriveSpacePage)
    page.drive_service = service
    page.show_timed_message = lambda *args, **kwargs: messages.append((args, kwargs))
    page.drive_space_list = type("List", (), {"clear": lambda self: None})()
    page.refresh_drives = lambda: None
    return page


def test_output_frame_safe_removal_success_uses_shared_popup_options(monkeypatch):
    messages = []
    page = _bare_page(_DriveService(), messages)
    monkeypatch.setattr(
        "resurface.ui.pages.drive_space_page.QTimer.singleShot",
        lambda *_args: None,
    )

    page._safely_remove_drive("E:\\")

    assert len(messages) == 1
    args, options = messages[0]
    assert args[1:] == ("Drive Removal", "Requested safe removal for E:.")
    assert options == status_popup_options()


def test_output_frame_safe_removal_error_uses_shared_popup_options(monkeypatch):
    messages = []
    page = _bare_page(_DriveService(DriveServiceError("device busy")), messages)
    monkeypatch.setattr(
        "resurface.ui.pages.drive_space_page.QTimer.singleShot",
        lambda *_args: None,
    )

    page._safely_remove_drive("E:\\")

    args, options = messages[0]
    assert args[1] == "Drive Removal"
    assert "Could not safely remove E:." in args[2]
    assert options == status_popup_options()

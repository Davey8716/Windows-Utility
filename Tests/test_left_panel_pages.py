from PySide6.QtWidgets import QApplication, QWidget

from resurface.features.screen_mover.hotkeys import VALID_ACTIONS
from resurface.ui.pages.external_drives_page import ExternalDrivesPage
from resurface.ui.pages.folder_utilities_page import FolderUtilitiesPage
from resurface.ui.pages.organising_utilities_page import OrganisingUtilitiesPage
from resurface.ui.pages.recycle_bin_page import RecycleBinPage
from resurface.ui.pages.screen_mover_settings_page import ScreenMoverSettingsPage
from resurface.ui.pages.user_interface_page import UserInterfacePage


def _app():
    return QApplication.instance() or QApplication([])


def test_split_pages_are_independent_widgets():
    _app()
    tooltip = lambda _widget, _text: None
    pages = [
        UserInterfacePage({}, tooltip, lambda _combo: None),
        ScreenMoverSettingsPage({}, tooltip),
        ExternalDrivesPage({}, tooltip),
        OrganisingUtilitiesPage("C:\\Backups", tooltip),
        FolderUtilitiesPage(tooltip),
        RecycleBinPage({}, tooltip),
    ]
    try:
        assert all(isinstance(page, QWidget) for page in pages)
        assert [page.section_id for page in pages] == [
            "user_interface",
            "screen_mover",
            "drive_reminder_options",
            "organising_utilities",
            "folder_utilities",
            "recycle_bin_actions",
        ]
    finally:
        for page in pages:
            page.deleteLater()


def test_screen_mover_reset_uses_page_settings_signal_and_api():
    _app()
    page = ScreenMoverSettingsPage(
        {
            "title_bar_dock_enabled": False,
            "screen_mover_activation_button": "right",
            "screen_mover_keyboard_hotkeys": {"LEFT": "Ctrl+Left"},
        },
        lambda _widget, _text: None,
    )
    changes = []
    page.settings_changed.connect(changes.append)
    try:
        page.reset_settings()
        settings = page.settings()
        assert changes[-1] == settings
        assert settings["title_bar_dock_enabled"] is True
        assert settings["screen_mover_activation_button"] == "middle"
        assert settings["screen_mover_keyboard_hotkeys"] == {
            action: "" for action in VALID_ACTIONS
        }
    finally:
        page.deleteLater()


def test_external_drives_page_updates_status_through_its_api():
    _app()
    page = ExternalDrivesPage({}, lambda _widget, _text: None)
    try:
        page.set_connected_drives(("E:\\", "F:\\"))
        combo = page.drive_combo()
        assert combo.count() == 2
        assert combo.itemData(0) == "E:\\"
        assert combo.itemData(1) == "F:\\"
    finally:
        page.deleteLater()

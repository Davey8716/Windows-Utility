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

    def tooltip(_widget, _text):
        return None

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


def test_folder_utilities_delete_requests_current_name_and_is_left_aligned():
    app = _app()
    page = FolderUtilitiesPage(lambda _widget, _text: None)
    delete_requests = []
    save_requests = []
    create_requests = []
    page.delete_name_requested.connect(delete_requests.append)
    page.save_name_requested.connect(save_requests.append)
    page.create_folder_requested.connect(create_requests.append)
    try:
        page.show()
        app.processEvents()
        page.refresh_saved_names([])
        assert not page._delete_name.isEnabled()
        assert page._save_name.property("lightModeBlackDisabledText") is True
        page._names.setEditText("   ")
        assert not page._save_name.isEnabled()
        page.refresh_saved_names(["Reports"])
        assert page._delete_name.isEnabled()
        page._names.setEditText("New Folder")
        assert page._save_name.isEnabled()
        page._save_name.click()
        assert save_requests == ["New Folder"]
        page._names.setEditText(" Reports ")
        assert not page._save_name.isEnabled()
        assert page._create_folder.isEnabled()
        page._request_save()
        page._delete_name.click()
        page._request_create()
        save_position = page._save_name.mapTo(page, page._save_name.rect().topLeft())
        delete_position = page._delete_name.mapTo(page, page._delete_name.rect().topLeft())
        assert save_requests == ["New Folder"]
        assert delete_requests == ["Reports"]
        assert create_requests == ["Reports"]
        assert delete_position.x() == save_position.x()
        assert delete_position.y() > save_position.y()
        assert not page._delete_name.isCheckable()
        assert not page._save_name.isCheckable()
        page.folder_name_saved(["Reports", "Invoices"], "Reports")
        assert page._input.text() == "Reports"
        assert not page._save_name.isEnabled()
        assert [page._names.itemText(index) for index in range(page._names.count())] == [
            "Reports",
            "Invoices"
        ]
        page.refresh_saved_names(["poo"])
        page._names.setEditText(" POO ")
        assert not page._save_name.isEnabled()
        assert page._create_folder.isEnabled()
        page.folder_name_deleted(["Invoices"])
        assert page._input.text() == ""
        page.folder_name_deleted([])
        assert not page._delete_name.isEnabled()
    finally:
        page.deleteLater()


def test_screen_mover_reset_uses_page_settings_signal_and_api():
    _app()
    page = ScreenMoverSettingsPage(
        {
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

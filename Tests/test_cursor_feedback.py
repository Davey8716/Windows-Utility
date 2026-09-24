import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QSizePolicy, QWidget

from resurface.features.system.command_runner import CommandRunner
from resurface.features.system.maintenance_actions import MaintenanceActions
from resurface.features.system.windows_tool_catalog import WindowsToolCatalog
from resurface.ui.pages.external_drives_page import ExternalDrivesPage
from resurface.ui.pages.drive_space_page import DriveSpacePage
from resurface.ui.pages.folder_utilities_page import FolderUtilitiesPage
from resurface.ui.pages.hover_window_controls_page import HoverWindowControlsPage
from resurface.ui.pages.maintenance_page import MaintenancePage
from resurface.ui.pages.screen_mover_settings_page import ScreenMoverSettingsPage
from resurface.ui.pages.user_interface_page import UserInterfacePage
from resurface.ui.pages.windows_utilities_page import WindowsUtilitiesPage
from resurface.ui.window_chrome import WindowChrome


def _app():
    return QApplication.instance() or QApplication([])


def _tooltip(*_args):
    return None


class _ChromeHost(QMainWindow):
    SIDEBAR_WIDTH = 220
    TITLE_TEXT_ROW_HEIGHT = 40
    TITLE_TEXT_TOP_PADDING = 10
    TITLE_BAR_HEIGHT = 50

    def __init__(self):
        super().__init__()
        self.root_container = QWidget(self)
        self.setCentralWidget(self.root_container)
        self.resize(1000, 850)

    def register_tooltip(self, *_args):
        return None

    def _title_bar_icon(self, _action):
        return QIcon()


class _DriveService:
    def list_drives(self):
        return []


class _Windows:
    def get_titles_state(self, _titles):
        return "closed"


def test_interactive_controls_use_hand_cursors_and_folder_text_keeps_i_beam():
    _app()
    runner = CommandRunner()
    actions = MaintenanceActions(runner, explorer_windows=None, windows=None)
    pages = [
        UserInterfacePage({}, _tooltip, lambda _combo: None),
        FolderUtilitiesPage(_tooltip),
        ExternalDrivesPage({}, _tooltip),
        HoverWindowControlsPage({}, _tooltip),
        MaintenancePage(actions, runner, _tooltip, lambda action: action(), lambda *_args: None),
        ScreenMoverSettingsPage({}, _tooltip),
        WindowsUtilitiesPage(
            WindowsToolCatalog(), object(), object(), object(), actions, _tooltip,
            lambda action: action(), lambda _label: None,
        ),
    ]

    try:
        user_interface, folder, external, hover, maintenance, screen_mover, windows = pages
        hand = Qt.CursorShape.PointingHandCursor

        assert user_interface.always_on_top_button.cursor().shape() == hand
        assert folder._names.cursor().shape() == hand
        assert folder._input.cursor().shape() == Qt.CursorShape.IBeamCursor
        assert external._drives.cursor().shape() == hand
        assert external._notify_combo.cursor().shape() == hand
        assert hover.dwell_combo.cursor().shape() == hand
        assert maintenance.sidebar_output_clear_btn.cursor().shape() == hand
        assert maintenance.sidebar_output_container.minimumHeight() == 285
        assert maintenance.sidebar_output_container.sizePolicy().verticalPolicy() == (
            QSizePolicy.Policy.Expanding
        )
        assert all(combo.cursor().shape() == hand for combo, _title, _actions in maintenance.quick_action_dropdowns)
        assert screen_mover.reset_button.cursor().shape() == hand
        assert all(button.cursor().shape() == hand for button in screen_mover._clear_hotkey_buttons.values())
        assert all(combo.cursor().shape() == hand for combo, _group, _tools in windows.quick_action_dropdowns)
    finally:
        for page in pages:
            page.deleteLater()
        runner.deleteLater()


def test_title_bar_and_drive_actions_use_hand_cursors():
    _app()
    host = _ChromeHost()
    drive_page = DriveSpacePage(
        _DriveService(), _Windows(), _tooltip, lambda *_args, **_kwargs: None,
        lambda action: action(),
    )

    try:
        WindowChrome(host).build()
        hand = Qt.CursorShape.PointingHandCursor
        assert host.window_minimize_btn.cursor().shape() == hand
        assert host.window_close_btn.cursor().shape() == hand
        assert drive_page.btn_this_pc.cursor().shape() == hand
        assert drive_page.btn_storage_sense.cursor().shape() == hand
        assert drive_page.drive_space_list.minimumHeight() == 120
        assert drive_page.drive_space_list.sizePolicy().verticalPolicy() == (
            QSizePolicy.Policy.Expanding
        )
    finally:
        drive_page.deleteLater()
        host.deleteLater()

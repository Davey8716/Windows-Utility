from PySide6.QtWidgets import QApplication

from resurface.features.system.command_runner import CommandRunner
from resurface.features.system.maintenance_actions import MaintenanceActions
from resurface.features.system.windows_tool_catalog import WindowsToolCatalog
from resurface.ui import styles
from resurface.ui.application_pages import QuickActionsGrid
from resurface.ui.pages.folder_utilities_page import FolderUtilitiesPage
from resurface.ui.pages.hover_window_controls_page import HoverWindowControlsPage
from resurface.ui.pages.maintenance_page import MaintenancePage
from resurface.ui.pages.organising_utilities_page import OrganisingUtilitiesPage
from resurface.ui.pages.recycle_bin_page import RecycleBinPage
from resurface.ui.pages.user_interface_page import UserInterfacePage
from resurface.ui.pages.windows_utilities_page import WindowsUtilitiesPage
from resurface.ui.quick_actions import QuickActionRegistry, QuickActionSpec


def _app():
    return QApplication.instance() or QApplication([])


def _tooltip(*_args):
    return None


def test_named_pages_use_the_shared_control_gap():
    _app()
    runner = CommandRunner()
    actions = MaintenanceActions(runner, explorer_windows=None, windows=None)
    registry = QuickActionRegistry({"quick_action_ids": ["one"]}, lambda _state: None)
    registry.register(QuickActionSpec("one", "One", lambda: None))
    registry.finalize()
    pages = [
        QuickActionsGrid(registry, _tooltip),
        UserInterfacePage({}, _tooltip, lambda _combo: None),
        OrganisingUtilitiesPage("C:\\Backups", _tooltip),
        FolderUtilitiesPage(_tooltip),
        RecycleBinPage({}, _tooltip),
        MaintenancePage(actions, runner, _tooltip, lambda action: action(), lambda *_args: None),
        HoverWindowControlsPage({}, _tooltip),
    ]
    windows_utilities = WindowsUtilitiesPage(
        WindowsToolCatalog(), object(), object(), object(), actions, _tooltip,
        lambda action: action(), lambda _label: None,
    )
    pages.append(windows_utilities)

    try:
        expected = styles.PAGE_CONTROL_ROW_GAP
        assert expected == styles.PAGE_CONTROL_GAP == 12

        quick_actions = pages[0]
        assert quick_actions.layout.horizontalSpacing() == styles.PAGE_CONTROL_GAP
        assert quick_actions.layout.verticalSpacing() == expected

        for page in pages[1:4] + [pages[6]]:
            assert page.content_layout.spacing() == expected

        folder_secondary = pages[3].content_layout.itemAt(1).widget().layout()
        assert folder_secondary.horizontalSpacing() == styles.PAGE_CONTROL_GAP
        assert folder_secondary.verticalSpacing() == expected

        recycle_controls = pages[4].content_layout.itemAt(0).widget().layout()
        assert recycle_controls.horizontalSpacing() == styles.PAGE_CONTROL_GAP
        assert recycle_controls.verticalSpacing() == expected
        assert pages[4]._age_row.layout().horizontalSpacing() == styles.PAGE_CONTROL_GAP

        maintenance_grid = pages[5].page_layout.itemAt(0).widget().layout()
        assert maintenance_grid.horizontalSpacing() == styles.PAGE_CONTROL_GAP
        assert maintenance_grid.verticalSpacing() == expected
        assert pages[5].page_layout.spacing() == 16

        windows_row = windows_utilities.page_layout.itemAt(0).widget().layout()
        assert windows_row.spacing() == styles.PAGE_CONTROL_GAP
        assert all(
            windows_row.itemAt(index).widget().layout().spacing() == expected
            for index in range(windows_row.count())
        )
    finally:
        for page in pages:
            page.deleteLater()
        runner.deleteLater()

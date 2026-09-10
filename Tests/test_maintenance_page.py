from PySide6.QtWidgets import QApplication, QMessageBox

from resurface.features.system.command_runner import CommandRunner
from resurface.features.system.maintenance_actions import MaintenanceActions
from resurface.ui import styles
from resurface.ui.pages.maintenance_page import MaintenancePage


def _application():
    return QApplication.instance() or QApplication([])


def _make_page(show_modal_message):
    _application()
    runner = CommandRunner()
    actions = MaintenanceActions(runner, explorer_windows=None, windows=None)
    return MaintenancePage(
        actions,
        runner,
        lambda *_args: None,
        lambda action: action(),
        show_modal_message,
    ), actions, runner


def test_integrity_elevation_confirmation_is_rounded_and_declining_cancels():
    calls = []
    page, _actions, runner = _make_page(
        lambda *args, **kwargs: calls.append((args, kwargs)) or QMessageBox.StandardButton.No
    )

    page._confirm_integrity_elevation("Check Disk (CHKDSK)", ["chkdsk", "C:"])

    args, kwargs = calls[0]
    assert args[1] == "Check Disk (CHKDSK) Needs Admin Access"
    assert args[3] == QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    assert args[4] == QMessageBox.StandardButton.No
    assert kwargs["popup_corner_radius"] == styles.BUTTON_CORNER_RADIUS
    assert "was cancelled" in page.sidebar_output.toPlainText()
    page.deleteLater()
    runner.deleteLater()


def test_accepting_integrity_elevation_runs_the_requested_command():
    page, actions, runner = _make_page(
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes
    )
    launched = []
    actions.run_admin_command_elevated = lambda command: launched.append(command)

    page._confirm_integrity_elevation("System File Checker (SFC)", ["sfc", "/scannow"])

    assert launched == [["sfc", "/scannow"]]
    page.deleteLater()
    runner.deleteLater()

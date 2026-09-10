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
    actions.run_admin_command_elevated = (
        lambda command, **kwargs: launched.append((command, kwargs.get("finished")))
    )
    finished = lambda *_args: None

    page._confirm_integrity_elevation(
        "System File Checker (SFC)",
        ["sfc", "/scannow"],
        finished,
    )

    assert launched == [(["sfc", "/scannow"], finished)]
    page.deleteLater()
    runner.deleteLater()


def test_cleanup_quick_actions_includes_task_manager():
    page, actions, runner = _make_page(lambda *_args, **_kwargs: None)
    launched = []
    actions.open_task_manager = lambda: launched.append(True)

    combo, _title, action_map = next(
        entry for entry in page.quick_action_dropdowns if entry[1] == "Cleanup / Quick Actions"
    )
    assert "Task Manager" in action_map
    combo.setCurrentText("Task Manager")

    assert launched == [True]
    page.deleteLater()
    runner.deleteLater()


def test_chkdsk_blocker_warnings_are_rounded_and_keep_diagnostics_distinct():
    calls = []
    page, _actions, runner = _make_page(
        lambda *args, **kwargs: calls.append((args, kwargs))
        or QMessageBox.StandardButton.Ok
    )

    page._show_vanguard_chkdsk_warning()
    page._show_generic_chkdsk_warning()

    vanguard_args, vanguard_kwargs = calls[0]
    generic_args, generic_kwargs = calls[1]
    assert vanguard_args[1] == "Vanguard Is Blocking Check Disk"
    assert "sc stop vgk" in vanguard_args[2]
    assert vanguard_kwargs["popup_corner_radius"] == styles.BUTTON_CORNER_RADIUS
    assert generic_args[1] == "Check Disk Access Was Blocked"
    assert "filter driver may be blocking access" in generic_args[2]
    assert generic_kwargs["popup_corner_radius"] == styles.BUTTON_CORNER_RADIUS
    page.deleteLater()
    runner.deleteLater()

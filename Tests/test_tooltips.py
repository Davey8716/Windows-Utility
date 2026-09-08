from PySide6.QtWidgets import QApplication, QPushButton, QToolTip

from resurface.features.system.command_runner import CommandRunner
from resurface.features.system.maintenance_actions import MaintenanceActions
from resurface.ui.pages.hover_window_controls_page import HoverWindowControlsPage
from resurface.ui.pages.maintenance_page import MaintenancePage
from resurface.ui.tooltips import QtTooltipManager, tooltip_text


def _app():
    return QApplication.instance() or QApplication([])


def test_empty_and_whitespace_tooltips_never_schedule_or_show(monkeypatch):
    _app()
    shown = []
    monkeypatch.setattr(QToolTip, "showText", lambda *args: shown.append(args))
    widget = QPushButton("Action")
    manager = QtTooltipManager(widget, "")

    manager._schedule()
    manager._show_tooltip()
    assert not manager._timer.isActive()
    assert shown == []

    manager.set_text("   \n\t")
    manager._schedule()
    manager._show_tooltip()
    assert not manager._timer.isActive()
    assert shown == []
    widget.deleteLater()


def test_clearing_tooltip_text_cancels_timer_and_hides_tooltip(monkeypatch):
    _app()
    hidden = []
    monkeypatch.setattr(QToolTip, "hideText", lambda: hidden.append(True))
    widget = QPushButton("Action")
    manager = QtTooltipManager(widget, "Available action", delay=10_000)

    manager._schedule()
    assert manager._timer.isActive()
    manager.set_text("")

    assert manager.text == ""
    assert not manager._timer.isActive()
    assert hidden
    widget.deleteLater()


def test_dynamic_nonempty_tooltip_still_displays(monkeypatch):
    _app()
    shown = []
    monkeypatch.setattr(QToolTip, "showText", lambda *args: shown.append(args))
    widget = QPushButton("Action")
    manager = QtTooltipManager(widget, "")

    manager.set_text("This action is unavailable on this system.")
    manager._show_tooltip()

    assert len(shown) == 1
    assert "This action is unavailable" in shown[0][1]
    widget.deleteLater()


def test_taskbar_restoration_button_uses_central_tooltip_wording():
    _app()
    registered = {}
    page = HoverWindowControlsPage(
        {},
        lambda widget, text: registered.__setitem__(widget, text),
    )

    assert registered[page.taskbar_restore_button] == tooltip_text(
        "hover_controls_taskbar_restore"
    )
    assert registered[page.taskbar_restore_button] == (
        "Restores a minimized window after the pointer rests over its taskbar "
        "icon. Requires AutoHotkey v2."
    )
    page.deleteLater()


def test_maintenance_clear_log_button_uses_central_tooltip_wording():
    _app()
    registered = {}
    runner = CommandRunner()
    actions = MaintenanceActions(runner, explorer_windows=None, windows=None)
    page = MaintenancePage(
        actions,
        runner,
        lambda widget, text: registered.__setitem__(widget, text),
        lambda action: action(),
        lambda *_args, **_kwargs: None,
    )

    assert registered[page.sidebar_output_clear_btn] == tooltip_text(
        "maintenance_clear_log"
    )
    assert registered[page.sidebar_output_clear_btn] == (
        "Clears the Maintenance page output log without undoing any completed "
        "actions."
    )
    page.deleteLater()

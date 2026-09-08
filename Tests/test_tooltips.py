from PySide6.QtWidgets import QApplication, QPushButton, QToolTip

from resurface.ui.tooltips import QtTooltipManager


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

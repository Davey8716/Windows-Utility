from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QComboBox, QListWidget, QPushButton

from resurface.features.system.command_runner import CommandRunner
from resurface.features.system.maintenance_actions import MaintenanceActions
from resurface.ui.pages.hover_window_controls_page import HoverWindowControlsPage
from resurface.ui.pages.maintenance_page import MaintenancePage
from resurface.ui.style_helpers import fit_page_combo_width
from resurface.ui import styles
from resurface.ui.tooltips import (
    QtTooltipManager,
    format_tooltip_text,
    hide_tooltip,
    install_tooltip_router,
    set_tooltip,
    tooltip_popup,
    tooltip_text,
)


def _app():
    return QApplication.instance() or QApplication([])


def test_empty_and_whitespace_tooltips_never_schedule_or_show():
    _app()
    widget = QPushButton("Action")
    manager = QtTooltipManager(widget, "")

    manager._schedule()
    manager._show_tooltip()
    assert not manager._timer.isActive()
    assert not tooltip_popup().isVisible()

    manager.set_text("   \n\t")
    manager._schedule()
    manager._show_tooltip()
    assert not manager._timer.isActive()
    assert not tooltip_popup().isVisible()
    widget.deleteLater()


def test_clearing_tooltip_text_cancels_timer_and_hides_tooltip():
    _app()
    widget = QPushButton("Action")
    manager = QtTooltipManager(widget, "Available action", delay=10_000)

    manager._schedule()
    assert manager._timer.isActive()
    manager.set_text("")

    assert manager.text == ""
    assert not manager._timer.isActive()
    assert not tooltip_popup().isVisible()
    widget.deleteLater()


def test_dynamic_nonempty_tooltip_still_displays():
    _app()
    widget = QPushButton("Action")
    manager = QtTooltipManager(widget, "")

    manager.set_text("This action is unavailable on this system.")
    manager._show_tooltip()

    assert tooltip_popup().isVisible()
    assert "This action is unavailable" in tooltip_popup().label.text()
    hide_tooltip()
    widget.deleteLater()


def test_application_router_intercepts_direct_widget_tooltips():
    _app()
    install_tooltip_router()
    widget = QPushButton("Action")
    set_tooltip(widget, "Available action")

    handled = QApplication.sendEvent(
        widget,
        QHelpEvent(QEvent.Type.ToolTip, QPoint(1, 1), QPoint(20, 20)),
    )

    assert handled
    assert tooltip_popup().isVisible()
    assert "Available action" in tooltip_popup().label.text()
    hide_tooltip()
    widget.deleteLater()


def test_application_router_intercepts_item_view_tooltips():
    _app()
    install_tooltip_router()
    widget = QListWidget()
    widget.addItem("First")
    widget.item(0).setToolTip(format_tooltip_text("First item"))
    widget.resize(160, 80)
    widget.show()
    QApplication.processEvents()
    index = widget.model().index(0, 0)
    point = widget.visualRect(index).center()

    handled = QApplication.sendEvent(
        widget.viewport(),
        QHelpEvent(
            QEvent.Type.ToolTip,
            point,
            widget.viewport().mapToGlobal(point),
        ),
    )

    assert handled
    assert tooltip_popup().isVisible()
    assert "First item" in tooltip_popup().label.text()
    hide_tooltip()
    widget.deleteLater()


def test_shared_popup_has_a_transparent_window_and_theme_aware_painting():
    _app()
    popup = tooltip_popup()

    assert popup.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert popup.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert popup.label.alignment() & Qt.AlignmentFlag.AlignHCenter
    assert popup.layout().contentsMargins().left() == 10
    assert popup.layout().contentsMargins().top() == 10
    assert popup.layout().contentsMargins().right() == 10
    assert popup.layout().contentsMargins().bottom() == 10


def test_tooltip_html_is_centered_without_inline_padding():
    rendered = format_tooltip_text("First line\nSecond line")

    assert "text-align: center;" in rendered
    assert "padding:" not in rendered
    assert "First line<br>Second line" in rendered


def test_popup_uses_theme_specific_text_color_and_content_sized_frame():
    _app()
    popup = tooltip_popup()
    styles.set_theme(True)
    popup.show_tooltip(QPoint(20, 20), format_tooltip_text("Dark theme"))
    assert styles.tooltip_text_color().name() in popup.label.styleSheet()

    styles.set_theme(False)
    popup.refresh_theme()
    assert styles.tooltip_text_color().name() in popup.label.styleSheet()
    assert popup.width() == popup.label.width() + 20
    assert popup.height() == popup.label.height() + 20
    hide_tooltip()
    styles.set_theme(True)


def test_popup_wraps_long_text_within_the_available_screen_width():
    _app()
    popup = tooltip_popup()
    long_text = " ".join(["tooltip"] * 400)
    popup.show_tooltip(QPoint(20, 20), format_tooltip_text(long_text))
    screen = QApplication.primaryScreen().availableGeometry()

    assert popup.width() <= screen.width() - 16
    assert popup.label.height() > popup.label.fontMetrics().height()
    hide_tooltip()


def test_direct_widget_tooltips_use_the_roomy_formatter():
    _app()
    widget = QPushButton("Action")

    set_tooltip(widget, "Available action")

    assert widget.toolTip() == format_tooltip_text("Available action")
    set_tooltip(widget, "")
    assert widget.toolTip() == ""
    widget.deleteLater()


def test_combo_item_tooltips_use_the_roomy_formatter():
    _app()
    combo = QComboBox()
    combo.addItems(["First", "Second"])

    fit_page_combo_width(combo)

    assert combo.itemData(0, Qt.ItemDataRole.ToolTipRole) == format_tooltip_text("First")
    assert combo.itemData(1, Qt.ItemDataRole.ToolTipRole) == format_tooltip_text("Second")
    combo.deleteLater()


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
    assert not page.sidebar_output_clear_btn.isEnabled()
    assert page.sidebar_output_clear_btn.property("lightModeBlackDisabledText") is True
    page.deleteLater()


def test_maintenance_clear_log_tracks_actionable_output():
    _app()
    runner = CommandRunner()
    actions = MaintenanceActions(runner, explorer_windows=None, windows=None)
    page = MaintenancePage(
        actions,
        runner,
        lambda *_args: None,
        lambda action: action(),
        lambda *_args, **_kwargs: None,
    )

    runner.output_appended.emit("Command output")
    assert page.sidebar_output_clear_btn.isEnabled()

    page.set_output_context("Flush DNS")
    page.sidebar_output_clear_btn.click()
    assert page.sidebar_output.toPlainText() == "Dns output log cleared."
    assert not page.sidebar_output_clear_btn.isEnabled()

    runner.output_appended.emit("More command output")
    assert page.sidebar_output_clear_btn.isEnabled()
    runner.output_reset.emit()
    assert page.sidebar_output.toPlainText() == ""
    assert not page.sidebar_output_clear_btn.isEnabled()
    page.deleteLater()

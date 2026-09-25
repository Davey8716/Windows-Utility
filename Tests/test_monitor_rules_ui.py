import copy
import json
from html import escape
from pathlib import Path
from types import SimpleNamespace

import pytest

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QThread, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QLabel,
    QListView,
    QMessageBox,
    QPushButton,
    QToolButton,
    QWidget,
)

from Shared.app_state_defaults import WINDOWS_RESURFACE_DEFAULTS
from resurface.core.app_paths import (
    MasterBackupDirectoryDialog,
    MasterBackupPathsMixin,
)
from resurface.features.monitor_rules import MonitorRulesRepository, rule_schema
from resurface.ui import application_window as main
from resurface.ui import monitor_rule_editor_dialog
from resurface.ui import monitor_rules_page as monitor_rules_ui
from resurface.ui.navigation_shell import NavigationShell
from resurface.ui.tooltips import format_tooltip_text
from test_screen_mover_settings_ui import _build_offscreen_window


def make_rule(
    rule_id="one",
    name="Discord",
    enabled=True,
    placement_mode="keep_size",
):
    return {
        "id": rule_id,
        "name": name,
        "enabled": enabled,
        "reapply_if_moved": False,
        "executable_name": "discord.exe",
        "executable_path": r"C:\Apps\Discord.exe",
        "match_exact_path": True,
        "target_device": r"\\.\DISPLAY2",
        "target_label": "Monitor 2",
        "placement_mode": placement_mode,
        "saved_geometry": None,
    }


def wait_for_window_choices(dialog, expected_count, timeout_ms=1500):
    """Process queued worker results until the running-window list is ready."""
    elapsed = 0
    while dialog.window_combo.count() != expected_count and elapsed < timeout_ms:
        QTest.qWait(25)
        elapsed += 25
    assert dialog.window_combo.count() == expected_count


def test_monitor_rules_help_button_opens_reviewed_theme_aware_dialog(
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    captured = []

    def capture(dialog):
        captured.append(dialog)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "exec", capture)
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[make_rule()],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
    )
    try:
        for is_dark, expected_surface in ((True, "#222a36"), (False, "#eef2f6")):
            monitor_rules_ui.styles.set_theme(is_dark)
            page.apply_theme()
            assert expected_surface in page.help_button.styleSheet()
            assert "border-radius: 14px" in page.help_button.styleSheet()

            page.help_button.click()
            dialog = captured[-1]
            assert dialog.parent() is page
            assert dialog.windowTitle() == "How Monitor Rules Work"
            assert dialog.text() == monitor_rules_ui.MONITOR_RULES_HELP_TEXT
            assert dialog.standardButtons() == QMessageBox.StandardButton.Ok
            assert dialog.standardButton(dialog.defaultButton()) == (
                QMessageBox.StandardButton.Ok
            )
            assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
            assert (
                dialog._popup_corner_radius
                == monitor_rules_ui.styles.BUTTON_CORNER_RADIUS
            )
            assert dialog.styleSheet() == monitor_rules_ui.styles.message_box_style(
                radius=monitor_rules_ui.styles.BUTTON_CORNER_RADIUS
            )
            app.processEvents()
            assert not dialog.mask().isEmpty()
    finally:
        monitor_rules_ui.styles.set_theme(True)
        page.deleteLater()
        app.processEvents()


def monitors():
    return [
        {
            "handle": 2,
            "device": r"\\.\DISPLAY2",
            "label": "Monitor 2 - 1920 x 1080",
            "rect": (1920, 0, 3840, 1080),
            "work": (1920, 0, 3840, 1040),
            "primary": False,
        }
    ]


def test_monitor_rules_page_enables_reorders_and_reports_unavailable_target(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    commits = []
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[
            make_rule(placement_mode="maximize"),
            make_rule("two", "Discord Work", placement_mode="maximize"),
        ],
        app_hwnd=999,
        on_rules_changed=lambda rules: commits.append(rules),
    )
    try:
        assert isinstance(page, QWidget)
        assert page.objectName() == "MonitorRulesPage"
        assert isinstance(page.rules_frame, QFrame)
        assert page.rules_frame.objectName() == "MonitorRulesEmptyState"
        assert page.help_button.parentWidget() is page.help_row
        assert page.help_row.parentWidget() is page
        assert page.rules_frame.parentWidget() is page
        assert not page.help_button.isAncestorOf(page.rules_frame)
        assert not page.rules_frame.isAncestorOf(page.help_button)
        margins = page.layout().contentsMargins()
        assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
            0,
            0,
            0,
            0,
        )
        assert page.layout().spacing() == 12
        action_grid = page.rules_frame.layout().itemAt(0).layout()
        assert action_grid.horizontalSpacing() == monitor_rules_ui.styles.PAGE_CONTROL_GAP
        assert action_grid.verticalSpacing() == monitor_rules_ui.styles.PAGE_CONTROL_ROW_GAP
        assert page.rule_list_layout.spacing() == monitor_rules_ui.styles.PAGE_CONTROL_ROW_GAP
        panel_margins = page.rules_frame.layout().contentsMargins()
        assert (
            panel_margins.left(),
            panel_margins.top(),
            panel_margins.right(),
            panel_margins.bottom(),
        ) == (11, 11, 11, 11)
        assert isinstance(page.help_button, QToolButton)
        assert page.help_button.text() == "?"
        assert page.help_button.size().width() == page.help_button.size().height() == 28
        assert page.help_button.accessibleName() == "Monitor Rules help"
        assert page.help_button.toolTip() == format_tooltip_text("How Monitor Rules work")
        assert page.add_button.isEnabled()
        assert page.turn_off_all_button.isEnabled()
        assert page.turn_off_all_button.text() == "Turn Off All"
        for button in (
            page.turn_off_all_button,
            page.delete_all_button,
            page.alphabet_sort_button,
        ):
            assert button.property("lightModeBlackText") is True
            assert button.property("lightModeBlackDisabledText") is True
        assert page.delete_all_button.isEnabled()
        assert page.delete_all_button.text() == "Delete All"
        assert page.delete_all_button.property("quickActionSeverity") == "red"
        assert (
            f"background-color: {monitor_rules_ui.styles.power_action_color('red').name()};"
            in page.delete_all_button.styleSheet()
        )
        assert page.alphabet_sort_button.isEnabled()
        assert page.alphabet_sort_button.text() == "A–Z"
        page.resize(760, page.sizeHint().height())
        page.show()
        app.processEvents()
        assert page.rules_frame.width() == 685
        frame_left = page.rules_frame.x()
        frame_right_gap = page.width() - page.rules_frame.geometry().right() - 1
        assert abs(frame_left - frame_right_gap) <= 1
        first_button_position = page.alphabet_sort_button.mapTo(
            page.rules_frame, page.alphabet_sort_button.rect().topLeft()
        )
        delete_button_right = page.delete_all_button.mapTo(
            page.rules_frame, page.delete_all_button.rect().topRight()
        ).x()
        assert first_button_position.x() == 12
        assert first_button_position.y() == 12
        assert page.rules_frame.width() - delete_button_right - 1 == 12
        assert page.export_rules_button.width() == page.turn_off_all_button.width()
        assert page.export_rules_button.x() == page.turn_off_all_button.x()
        assert page.import_rules_button.width() == page.delete_all_button.width()
        assert page.import_rules_button.x() == page.delete_all_button.x()
        help_right = page.help_button.mapTo(
            page, page.help_button.rect().topRight()
        ).x()
        delete_right = page.delete_all_button.mapTo(
            page, page.delete_all_button.rect().topRight()
        ).x()
        assert help_right == delete_right
        assert page.help_button.geometry().bottom() < page.rules_frame.geometry().top()

        page.resize(900, page.height())
        app.processEvents()
        assert page.rules_frame.width() == 685
        frame_left = page.rules_frame.x()
        frame_right_gap = page.width() - page.rules_frame.geometry().right() - 1
        assert abs(frame_left - frame_right_gap) <= 1
        assert page.export_rules_button.geometry().x() == page.turn_off_all_button.geometry().x()
        assert page.export_rules_button.width() == page.turn_off_all_button.width()
        assert page.import_rules_button.geometry().x() == page.delete_all_button.geometry().x()
        assert page.import_rules_button.width() == page.delete_all_button.width()
        help_right = page.help_button.mapTo(
            page, page.help_button.rect().topRight()
        ).x()
        delete_right = page.delete_all_button.mapTo(
            page, page.delete_all_button.rect().topRight()
        ).x()
        assert help_right == delete_right
        initial_cards = [
            page.rule_list_layout.itemAt(index).widget()
            for index in range(page.rule_list_layout.count())
        ]
        assert page.rule_list.objectName() == "MonitorRuleList"
        assert (
            f"background-color: {monitor_rules_ui.styles.qcolor_css(monitor_rules_ui.styles.SURFACE_BG)}"
            in page.rule_list.styleSheet()
        )
        for card in initial_cards:
            assert f"background-color: {monitor_rules_ui.styles.qcolor_css(monitor_rules_ui.styles.WINDOW_BG)}" in card.styleSheet()
            assert "border: 1px solid" in card.styleSheet()
            assert "border-radius: 8px" in card.styleSheet()
            assert card.layout().itemAt(2).layout().spacing() == monitor_rules_ui.styles.PAGE_CONTROL_GAP
        expected_actions = {"Edit", "Move Up", "Move Down"}
        assert all(
            {button.text() for button in card.findChildren(QPushButton)}
            == expected_actions
            for card in initial_cards
        )
        delete_buttons = [
            next(
                button
                for button in card.findChildren(QToolButton)
                if button.accessibleName() == "Delete monitor rule"
            )
            for card in initial_cards
        ]
        assert all(button.text() == "×" for button in delete_buttons)
        assert all(
            button.accessibleName() == "Delete monitor rule"
            and button.toolTip() == format_tooltip_text("Delete this monitor rule")
            and button.size().width() == button.size().height() == 24
            for button in delete_buttons
        )
        assert all(
            card.findChild(monitor_rules_ui.QLabel, "MonitorRuleStatus") is None
            for card in initial_cards
        )
        assert all(
            card.findChild(monitor_rules_ui.StateIndicatorCheckBox).isChecked()
            for card in initial_cards
        )
        move_buttons = [
            {
                button.text(): button
                for button in card.findChildren(QPushButton)
                if button.text() in {"Move Up", "Move Down"}
            }
            for card in initial_cards
        ]
        assert not move_buttons[0]["Move Up"].isEnabled()
        assert move_buttons[0]["Move Down"].isEnabled()
        assert move_buttons[1]["Move Up"].isEnabled()
        assert not move_buttons[1]["Move Down"].isEnabled()
        assert all(
            button.property("lightModeBlackDisabledText") is True
            for card_buttons in move_buttons
            for button in card_buttons.values()
        )

        page.turn_off_all_button.click()
        assert all(rule["enabled"] is False for rule in commits[-1])
        assert page.turn_off_all_button.isEnabled()
        assert page.turn_off_all_button.text() == "Turn On All"
        assert all(
            not page.rule_list_layout.itemAt(index)
            .widget()
            .findChild(monitor_rules_ui.StateIndicatorCheckBox)
            .isChecked()
            for index in range(page.rule_list_layout.count())
        )

        page.turn_off_all_button.click()
        assert all(rule["enabled"] is True for rule in commits[-1])
        assert page.turn_off_all_button.isEnabled()
        assert page.turn_off_all_button.text() == "Turn Off All"
        page._set_enabled(0, False)
        disabled_card = page.rule_list_layout.itemAt(0).widget()
        assert disabled_card.findChild(
            monitor_rules_ui.QLabel, "MonitorRuleStatus"
        ) is None
        assert not disabled_card.findChild(
            monitor_rules_ui.StateIndicatorCheckBox
        ).isChecked()
        page._move_rule(1, -1)
        assert [rule["id"] for rule in commits[-1]] == ["two", "one"]

        current_cards = [
            page.rule_list_layout.itemAt(index).widget()
            for index in range(page.rule_list_layout.count())
        ]
        details = [
            card.findChild(monitor_rules_ui.QLabel, "MonitorRuleDetails").text()
            for card in current_cards
        ]
        assert len(details) == 2
        assert all("<br>Target: Monitor 2<br>Placement: Maximize" in text for text in details)
        assert all("<br>Reapply if moved: Disabled" in text for text in details)

        page.rules[0]["reapply_if_moved"] = True
        page._render_rules()
        enabled_details = (
            page.rule_list_layout.itemAt(0)
            .widget()
            .findChild(monitor_rules_ui.QLabel, "MonitorRuleDetails")
            .text()
        )
        assert "<br>Reapply if moved: Enabled" in enabled_details

        page.rules[0]["target_device"] = r"\\.\MISSING"
        page._render_rules()
        unavailable_card = page.rule_list_layout.itemAt(0).widget()
        assert (
            unavailable_card.findChild(
                monitor_rules_ui.QLabel, "MonitorRuleStatus"
            ).text()
            == "Target unavailable"
        )
    finally:
        page.deleteLater()
        app.processEvents()


def test_monitor_rule_cards_titles_and_details_refresh_for_each_theme(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[make_rule()],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
    )
    try:
        # Exercise the reported light-to-dark transition as well as the initial
        # dark-to-light change.
        for is_dark in (False, True):
            monitor_rules_ui.styles.set_theme(is_dark)
            page.apply_theme()
            card = page.rule_list.findChild(QFrame, "MonitorRuleCard")
            title = page.rule_list.findChild(
                monitor_rules_ui.StateIndicatorCheckBox, "MonitorRuleTitle"
            )
            details = page.rule_list.findChild(QLabel, "MonitorRuleDetails")
            assert card is not None
            assert title is not None
            assert details is not None
            assert (
                f"background-color: {monitor_rules_ui.styles.qcolor_css(monitor_rules_ui.styles.SURFACE_BG)}"
                in page.rule_list.styleSheet()
            )
            assert (
                f"background-color: {monitor_rules_ui.styles.qcolor_css(monitor_rules_ui.styles.WINDOW_BG)}"
                in card.styleSheet()
            )
            assert "background: transparent" in title.styleSheet()
            assert (
                f"color: {monitor_rules_ui.styles.qcolor_css(monitor_rules_ui.styles.theme_text_color())}"
                in title.styleSheet()
            )
            muted_color = monitor_rules_ui.styles.theme_muted_text_color().name()
            assert muted_color in details.styleSheet()
            assert (
                f"color: {muted_color}; text-decoration: underline;"
                in details.text()
            )
    finally:
        monitor_rules_ui.styles.set_theme(True)
        page.deleteLater()
        app.processEvents()


def test_monitor_rules_page_set_rules_rerenders_empty_state(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[make_rule()],
        app_hwnd=0,
        on_rules_changed=lambda _rules: None,
    )
    try:
        page.set_rules([])
        assert page.rules == []
        assert page.rule_list_layout.count() == 1
        assert page.rule_list_layout.itemAt(0).widget().text() == (
            "No application monitor rules have been created or imported."
        )
    finally:
        page.deleteLater()
        app.processEvents()


def test_exact_application_path_is_clickable_escaped_and_uses_existing_color(
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    rule = make_rule()
    rule["executable_path"] = r"C:\Apps & Tools\Discord.exe"
    opened = []
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[rule],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        open_backup_folder=lambda path: opened.append(path) or True,
    )
    try:
        detail_label = (
            page.rule_list_layout.itemAt(0)
            .widget()
            .findChild(QLabel, "MonitorRuleDetails")
        )
        detail_text = detail_label.text()
        muted_color = monitor_rules_ui.styles.theme_muted_text_color().name()
        displayed_path = page.rules[0]["executable_path"]

        assert detail_label.textFormat() == Qt.TextFormat.RichText
        assert (
            detail_label.textInteractionFlags()
            & Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        assert detail_label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
        assert 'href="open-application-directory"' in detail_text
        assert escape(displayed_path) in detail_text
        assert f"color: {muted_color}; text-decoration: underline;" in detail_text
        assert muted_color in detail_label.styleSheet()
        assert "<br>Target: Monitor 2<br>Placement: Keep current size" in detail_text
        assert "<br>Reapply if moved: Disabled" in detail_text

        detail_label.linkActivated.emit("open-application-directory")

        assert opened == [str(Path(displayed_path).parent)]
    finally:
        page.deleteLater()
        app.processEvents()


def test_name_matched_application_remains_plain_and_non_clickable(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    rule = make_rule()
    rule["match_exact_path"] = False
    opened = []
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[rule],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        open_backup_folder=lambda path: opened.append(path) or True,
    )
    try:
        detail_label = (
            page.rule_list_layout.itemAt(0)
            .widget()
            .findChild(QLabel, "MonitorRuleDetails")
        )

        assert detail_label.text().startswith("Application: discord.exe\n")
        assert rule["executable_path"] not in detail_label.text()
        assert "<a " not in detail_label.text()
        assert not (
            detail_label.textInteractionFlags()
            & Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        assert detail_label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
        assert opened == []
    finally:
        page.deleteLater()
        app.processEvents()


def test_application_path_open_failure_does_not_create_folder(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    missing_directory = tmp_path / "Missing application"
    rule = make_rule()
    rule["executable_path"] = str(missing_directory / "Discord.exe")
    messages = []
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[rule],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        open_backup_folder=lambda _path: False,
    )
    monkeypatch.setattr(
        page,
        "_show_modal_message",
        lambda *args, **kwargs: messages.append((args, kwargs)),
    )
    try:
        detail_label = (
            page.rule_list_layout.itemAt(0)
            .widget()
            .findChild(QLabel, "MonitorRuleDetails")
        )
        detail_label.linkActivated.emit("open-application-directory")

        assert not missing_directory.exists()
        assert len(messages) == 1
        opened_directory = Path(page.rules[0]["executable_path"]).parent
        assert messages[0][0] == (
            QMessageBox.Icon.Critical,
            "Open application folder failed",
            f"The application folder could not be opened.\n\n{opened_directory}",
            QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
        )
    finally:
        page.deleteLater()
        app.processEvents()


def test_rule_editor_captures_selected_window_and_builds_saved_geometry(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rule_editor_dialog, "enumerate_monitors", monitors)
    monkeypatch.setattr(
        monitor_rule_editor_dialog,
        "enumerate_eligible_windows",
        lambda **_kwargs: [
            {
                "hwnd": 101,
                "title": "Discord - Friends",
                "class_name": "Chrome_WidgetWin_1",
                "executable_name": "discord.exe",
                "executable_path": r"C:\Apps\Discord.exe",
            }
        ],
    )
    monkeypatch.setattr(
        monitor_rule_editor_dialog,
        "capture_window_geometry",
        lambda _hwnd: {"x_offset": 40, "y_offset": 50, "width": 900, "height": 700},
    )
    dialog = monitor_rule_editor_dialog.MonitorRuleEditorDialog(None, app_hwnd=999)
    try:
        dialog.show()
        wait_for_window_choices(dialog, 2)
        dialog.window_combo.setCurrentIndex(1)
        dialog.placement_combo.setCurrentIndex(
            dialog.placement_combo.findData("saved_geometry")
        )
        dialog._capture_geometry()
        rule = dialog.result_rule()
        assert rule["executable_name"] == "discord.exe"
        assert rule["match_exact_path"]
        assert rule["target_device"] == r"\\.\DISPLAY2"
        assert rule["saved_geometry"]["width"] == 900
        assert not hasattr(dialog, "title_edit")
        assert not hasattr(dialog, "class_edit")
        assert "title_contains" not in rule
        assert "class_name" not in rule
        assert dialog._validation_message() == ""
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("is_dark", (True, False))
def test_rule_editor_is_frameless_fixed_size_and_uses_active_theme(is_dark, monkeypatch):
    app = QApplication.instance() or QApplication([])
    original_theme = monitor_rule_editor_dialog.styles.THEME_IS_DARK
    monkeypatch.setattr(monitor_rule_editor_dialog, "enumerate_monitors", monitors)
    monkeypatch.setattr(
        monitor_rule_editor_dialog,
        "enumerate_eligible_windows",
        lambda **_kwargs: [],
    )
    monitor_rule_editor_dialog.styles.set_theme(is_dark)
    dialog = monitor_rule_editor_dialog.MonitorRuleEditorDialog(None)
    try:
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dialog.minimumSize() == dialog.maximumSize()
        assert dialog.heading_label.text() == "Add Monitor Rule"
        assert (
            monitor_rule_editor_dialog.styles.qcolor_css(
                monitor_rule_editor_dialog.styles.WINDOW_BG
            )
            in dialog.styleSheet()
        )
        assert (
            monitor_rule_editor_dialog.styles.qcolor_css(
                monitor_rule_editor_dialog.styles.theme_text_color()
            )
            in dialog.styleSheet()
        )
        assert (
            monitor_rule_editor_dialog.styles.qcolor_css(
                monitor_rule_editor_dialog.styles.themed_surface_field_border()
            )
            in dialog.styleSheet()
        )
    finally:
        dialog.close()
        dialog.deleteLater()
        monitor_rule_editor_dialog.styles.set_theme(original_theme)
        app.processEvents()


def test_rule_editor_uses_edit_heading_for_existing_rule(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rule_editor_dialog, "enumerate_monitors", monitors)
    window_calls = []
    monkeypatch.setattr(
        monitor_rule_editor_dialog,
        "enumerate_eligible_windows",
        lambda **kwargs: window_calls.append(kwargs) or [],
    )
    rule = make_rule(placement_mode="saved_geometry")
    rule["saved_geometry"] = {
        "x_offset": 10,
        "y_offset": 20,
        "width": 900,
        "height": 700,
    }
    dialog = monitor_rule_editor_dialog.MonitorRuleEditorDialog(
        None,
        rule=rule,
    )
    try:
        assert dialog.heading_label.text() == "Edit Monitor Rule"
        assert window_calls == []
        assert not hasattr(dialog, "window_combo")
        assert not hasattr(dialog, "refresh_windows_button")
        assert not hasattr(dialog, "browse_button")
        assert not hasattr(dialog, "group_button")
        assert not hasattr(dialog, "exact_path_check")
        assert dialog.executable_edit.isReadOnly()
        assert dialog.executable_edit.text() == rule["executable_path"]
        assert not dialog.capture_button.isVisible()

        dialog.monitor_combo.setCurrentIndex(0)
        dialog.enabled_check.setChecked(False)
        edited = dialog.result_rule()

        assert edited["id"] == rule["id"]
        assert edited["executable_name"] == rule["executable_name"]
        assert edited["executable_path"] == rule_schema._normalize_path(
            rule["executable_path"]
        )
        assert edited["match_exact_path"] == rule["match_exact_path"]
        assert edited["saved_geometry"] == rule["saved_geometry"]
        assert not edited["enabled"]
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_rule_editor_matches_import_rules_popup_width(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    (tmp_path / "Monitor Rules").mkdir()
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        get_master_backup_dir=lambda: str(tmp_path),
    )
    import_dialog = monitor_rules_ui.ImportRulesDialog(
        page,
        str(tmp_path / "Monitor Rules"),
    )
    captured = []

    def reject_and_capture(dialog):
        captured.append(dialog)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        monitor_rule_editor_dialog.MonitorRuleEditorDialog,
        "exec",
        reject_and_capture,
    )
    try:
        page._add_rule()
        editor = captured[0]
        editor.show()
        app.processEvents()
        assert editor.width() == import_dialog.width()
        assert editor.minimumSize() == editor.maximumSize()
        assert editor.layout().contentsMargins().left() == 22
        assert editor.layout().spacing() == 14
        assert editor.window_combo.minimumWidth() == 0
        assert not hasattr(editor, "group_button")
        assert not hasattr(editor, "refresh_windows_button")
        assert not hasattr(editor, "browse_button")
    finally:
        import_dialog.deleteLater()
        page.deleteLater()
        app.processEvents()


def test_rule_editor_preserves_filename_only_matching_when_editing(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rule_editor_dialog, "enumerate_monitors", monitors)
    rule = make_rule()
    rule["match_exact_path"] = False
    dialog = monitor_rule_editor_dialog.MonitorRuleEditorDialog(None, rule=rule)
    try:
        assert not hasattr(dialog, "exact_path_check")
        assert not dialog.result_rule()["match_exact_path"]
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_rule_editor_lists_and_selects_windows_resurface(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rule_editor_dialog, "enumerate_monitors", monitors)
    calls = []
    monkeypatch.setattr(
        monitor_rule_editor_dialog,
        "enumerate_eligible_windows",
        lambda **kwargs: calls.append(kwargs) or [
            {
                "hwnd": 999,
                "title": "Windows Resurface",
                "class_name": "QtWindowClass",
                "executable_name": "windows resurface.exe",
                "executable_path": r"C:\Apps\Windows Resurface.exe",
            }
        ],
    )

    dialog = monitor_rule_editor_dialog.MonitorRuleEditorDialog(None, app_hwnd=999)
    try:
        dialog.show()
        wait_for_window_choices(dialog, 2)
        assert calls
        assert all(call == {"app_hwnd": 999} for call in calls)
        assert not dialog.window_combo.isHidden()
        assert not hasattr(dialog, "refresh_windows_button")
        assert not hasattr(dialog, "browse_button")
        assert not hasattr(dialog, "group_button")
        assert not hasattr(dialog, "exact_path_check")
        assert dialog.window_combo.count() == 2
        assert "Windows Resurface" in dialog.window_combo.itemText(1)

        dialog.window_combo.setCurrentIndex(1)

        assert dialog.executable_edit.text() == r"C:\Apps\Windows Resurface.exe"
        assert dialog.name_edit.text() == "windows resurface"
        assert dialog.result_rule()["app_group"] == "windows_resurface"
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_rule_editor_polls_running_windows_and_stops_when_closed(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rule_editor_dialog, "enumerate_monitors", monitors)
    windows = [
        {
            "hwnd": 101,
            "title": "Discord - Friends",
            "class_name": "Chrome_WidgetWin_1",
            "executable_name": "discord.exe",
            "executable_path": r"C:\Apps\Discord.exe",
        }
    ]
    enumeration_threads = []

    def enumerate_windows(**_kwargs):
        enumeration_threads.append(QThread.currentThread())
        return list(windows)

    dialog = monitor_rule_editor_dialog.MonitorRuleEditorDialog(
        None,
        app_hwnd=999,
        window_enumerator=enumerate_windows,
    )
    try:
        dialog.show()
        wait_for_window_choices(dialog, 2)
        assert enumeration_threads
        assert enumeration_threads[0] is not app.thread()

        dialog.window_combo.setCurrentIndex(1)
        assert dialog.executable_edit.text() == r"C:\Apps\Discord.exe"
        windows.clear()
        wait_for_window_choices(dialog, 1, timeout_ms=2000)

        assert dialog.window_combo.currentData() is None
        assert dialog.executable_edit.text() == ""
        assert dialog._validation_message() == "Select a running window."

        thread = dialog._window_poll_thread
        assert thread is not None and thread.isRunning()
        dialog.reject()
        assert not thread.isRunning()
        assert dialog._window_poll_thread is None
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_delete_rule_uses_borderless_confirmation_and_only_commits_yes(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    commits = []
    dialogs = []
    responses = [
        monitor_rules_ui.QMessageBox.StandardButton.Cancel,
        monitor_rules_ui.QMessageBox.StandardButton.Yes,
    ]

    def exec_message_box(message_box):
        dialogs.append(message_box)
        return responses.pop(0)

    monkeypatch.setattr(monitor_rules_ui.QMessageBox, "exec", exec_message_box)
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[make_rule()],
        app_hwnd=999,
        on_rules_changed=lambda rules: commits.append(rules),
    )
    try:
        page._delete_rule(0)
        dialog = dialogs[-1]
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dialog._popup_corner_radius == monitor_rules_ui.MONITOR_RULES_POPUP_CORNER_RADIUS
        assert dialog.styleSheet() == monitor_rules_ui.styles.message_box_style(
            radius=monitor_rules_ui.MONITOR_RULES_POPUP_CORNER_RADIUS
        )
        assert dialog.icon() == monitor_rules_ui.QMessageBox.Icon.NoIcon
        assert dialog.windowTitle() == "Delete Monitor Rule"
        assert dialog.text() == "Delete the rule ‘Discord’?"
        assert dialog.standardButtons() == (
            monitor_rules_ui.QMessageBox.StandardButton.Yes
            | monitor_rules_ui.QMessageBox.StandardButton.Cancel
        )
        assert dialog.standardButton(dialog.defaultButton()) == (
            monitor_rules_ui.QMessageBox.StandardButton.Cancel
        )
        assert len(page.rules) == 1
        assert commits == []

        page._delete_rule(0)
        assert page.rules == []
        assert commits[-1] == []
    finally:
        page.deleteLater()
        app.processEvents()


def test_delete_all_rules_confirms_and_updates_empty_state(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    commits = []
    dialogs = []
    responses = [
        monitor_rules_ui.QMessageBox.StandardButton.No,
        monitor_rules_ui.QMessageBox.StandardButton.Yes,
    ]

    def exec_message_box(message_box):
        dialogs.append(message_box)
        return responses.pop(0)

    monkeypatch.setattr(monitor_rules_ui.QMessageBox, "exec", exec_message_box)
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[make_rule(), make_rule("two", "Discord Work")],
        app_hwnd=999,
        on_rules_changed=lambda rules: commits.append(rules),
    )
    try:
        page.delete_all_button.click()
        assert len(page.rules) == 2
        assert commits == []
        assert dialogs[-1].windowTitle() == "Delete All Monitor Rules"
        assert dialogs[-1].text() == (
            "Delete all 2 monitor rules? This cannot be undone.\n\n"
            "Previously exported monitor rules will not be deleted and can be imported again."
        )

        page.delete_all_button.click()
        assert page.rules == []
        assert commits[-1] == []
        assert not page.delete_all_button.isEnabled()
        assert not page.turn_off_all_button.isEnabled()
        assert (
            page.rule_list_layout.itemAt(0).widget().text()
            == "No application monitor rules have been created or imported."
        )
    finally:
        page.deleteLater()
        app.processEvents()


def test_alphabet_button_sorts_rules_in_both_directions(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    commits = []
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[
            make_rule("zulu", "Zulu"),
            make_rule("alpha", "alpha"),
            make_rule("middle", "Middle"),
        ],
        app_hwnd=999,
        on_rules_changed=lambda rules: commits.append(rules),
    )
    try:
        page.alphabet_sort_button.click()
        assert [rule["name"] for rule in commits[-1]] == ["alpha", "Middle", "Zulu"]
        assert page.alphabet_sort_button.text() == "Z–A"

        page.alphabet_sort_button.click()
        assert [rule["name"] for rule in commits[-1]] == ["Zulu", "Middle", "alpha"]
        assert page.alphabet_sort_button.text() == "A–Z"
    finally:
        page.deleteLater()
        app.processEvents()


def test_export_button_disables_after_sort_round_trip(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    exported_rules = [
        make_rule("zulu", "Zulu"),
        make_rule("middle", "Middle"),
        make_rule("alpha", "alpha"),
    ]
    MonitorRulesRepository(lambda: str(tmp_path)).export_rules(exported_rules)
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=copy.deepcopy(exported_rules),
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        get_master_backup_dir=lambda: str(tmp_path),
    )
    try:
        assert not page.export_rules_button.isEnabled()

        page.alphabet_sort_button.click()
        assert [rule["name"] for rule in page.rules] == ["alpha", "Middle", "Zulu"]
        assert page.export_rules_button.isEnabled()

        page.alphabet_sort_button.click()
        assert page.rules == monitor_rules_ui.normalize_monitor_rules(exported_rules)
        assert not page.export_rules_button.isEnabled()
    finally:
        page.deleteLater()
        app.processEvents()


def test_delete_all_keeps_monitor_rules_page_geometry_stable(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    shell = NavigationShell(
        app_version="test",
        sidebar_width=220,
        page_title_top_inset=43,
    )
    page = monitor_rules_ui.MonitorRulesPage(
        shell.content_parent("monitor_rules"),
        rules=[make_rule(str(index), f"Rule {index}") for index in range(20)],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
    )
    shell.mount_content("monitor_rules", page)

    try:
        shell.resize(1000, 800)
        shell.show()
        shell.navigate_to("monitor_rules")
        app.processEvents()

        scroll = shell.page_scroll_areas["monitor_rules"]
        title = shell.content_parent("monitor_rules").findChild(
            QLabel, "PageTitle"
        )
        assert title is not None
        assert scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        assert scroll.verticalScrollBar().isEnabled()
        before = {
            "title": title.mapTo(shell, QPoint()).x(),
            "help": page.help_button.mapTo(shell, QPoint()).x(),
            "frame": page.rules_frame.mapTo(shell, QPoint()).x(),
        }

        monkeypatch.setattr(
            page,
            "_show_modal_message",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
        )
        page.delete_all_button.click()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        QTest.qWait(25)

        assert page.rules == []
        assert not scroll.verticalScrollBar().isEnabled()
        assert {
            "title": title.mapTo(shell, QPoint()).x(),
            "help": page.help_button.mapTo(shell, QPoint()).x(),
            "frame": page.rules_frame.mapTo(shell, QPoint()).x(),
        } == before
    finally:
        shell.deleteLater()
        app.processEvents()


def test_monitor_rules_export_and_import_use_master_backup_path(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    monkeypatch.setattr(
        monitor_rules_ui.QMessageBox,
        "exec",
        lambda message_box: (
            monitor_rules_ui.QMessageBox.StandardButton.Save
            if message_box.standardButtons()
            & monitor_rules_ui.QMessageBox.StandardButton.Save
            else monitor_rules_ui.QMessageBox.StandardButton.Ok
        ),
    )
    commits = []
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[make_rule()],
        app_hwnd=999,
        on_rules_changed=lambda rules: commits.append(rules),
        get_master_backup_dir=lambda: str(tmp_path),
    )
    try:
        assert page.export_rules_button.isEnabled()
        assert page.import_rules_button.isEnabled()
        exported_path = page._export_rules()
        assert not page.export_rules_button.isEnabled()
        assert exported_path.parent == tmp_path / "Monitor Rules"
        payload = json.loads(exported_path.read_text(encoding="utf-8"))
        assert payload["format"] == "windows-resurface-monitor-rules"
        assert payload["rules"][0]["name"] == "Discord"

        imported_path = tmp_path / "Monitor Rules" / "import.json"
        imported_path.write_text(
            json.dumps({"rules": [make_rule("new", "Imported Rule")]}),
            encoding="utf-8",
        )
        page.rules = []
        monkeypatch.setattr(
            monitor_rules_ui.QFileDialog,
            "exec",
            lambda _dialog: QDialog.DialogCode.Accepted,
        )
        monkeypatch.setattr(
            monitor_rules_ui.QFileDialog,
            "selectedFiles",
            lambda _dialog: [str(imported_path)],
        )
        page._import_rules()
        assert commits[-1][0]["id"] == "new"
        assert commits[-1][0]["name"] == "Imported Rule"
    finally:
        page.deleteLater()
        app.processEvents()


def test_export_rules_dialog_is_frameless_and_tracks_current_theme(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[make_rule()],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        get_master_backup_dir=lambda: str(tmp_path),
    )
    captured = []
    timed_messages = []

    def accept_and_capture(dialog):
        captured.append(dialog)
        if dialog.standardButtons() & QMessageBox.StandardButton.Save:
            return QMessageBox.StandardButton.Save
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(monitor_rules_ui.QMessageBox, "exec", accept_and_capture)
    monkeypatch.setattr(
        page,
        "_show_timed_message",
        lambda *args, **kwargs: timed_messages.append((args, kwargs)),
    )
    try:
        for is_dark in (True, False):
            monitor_rules_ui.styles.set_theme(is_dark)
            page.rules[0]["name"] = f"Discord {is_dark}"
            exported_path = page._export_rules()
            confirmation = captured[-1]
            assert confirmation.parent() is page
            assert confirmation.windowTitle() == "Export Monitor Rules"
            assert str(exported_path.parent) in confirmation.text()
            assert confirmation.icon() == QMessageBox.Icon.NoIcon
            assert (
                confirmation.standardButtons()
                == QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Cancel
            )
            assert confirmation.standardButton(confirmation.defaultButton()) == (
                QMessageBox.StandardButton.Save
            )
            label = confirmation.findChild(QLabel, "qt_msgbox_label")
            assert (
                label.textInteractionFlags()
                & Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
            assert confirmation.windowFlags() & Qt.WindowType.FramelessWindowHint
            assert (
                confirmation._popup_corner_radius
                == monitor_rules_ui.MONITOR_RULES_POPUP_CORNER_RADIUS
            )
            assert (
                confirmation.styleSheet()
                == monitor_rules_ui.styles.message_box_style(
                    radius=monitor_rules_ui.MONITOR_RULES_POPUP_CORNER_RADIUS
                )
            )
            app.processEvents()
            assert not confirmation.mask().isEmpty()
            link_color = "#ffffff" if is_dark else "#000000"
            assert label.palette().color(QPalette.ColorRole.Link).name() == link_color
            assert label.palette().color(QPalette.ColorRole.LinkVisited).name() == link_color
            assert (
                f'style="color: {link_color}; text-decoration: underline;"'
                in confirmation.text()
            )

            timed_args, timed_kwargs = timed_messages[-1]
            assert timed_args == (
                QMessageBox.Icon.Information,
                "Monitor Rules Exported",
                f"Monitor rules were exported to:\n{exported_path}",
            )
            assert timed_kwargs == {
                "show_close_now_button": True,
                "text_block_width": 360,
                "popup_corner_radius": monitor_rules_ui.MONITOR_RULES_POPUP_CORNER_RADIUS,
            }
    finally:
        monitor_rules_ui.styles.set_theme(True)
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("saved_during_confirmation", [False, True])
def test_unchanged_export_silently_disables_button(
    monkeypatch, tmp_path, saved_during_confirmation
):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[make_rule()],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        get_master_backup_dir=lambda: str(tmp_path),
    )
    messages = []
    confirmations = []

    def confirm(*args, **kwargs):
        confirmations.append(args)
        page._repository.export_rules(page.rules)
        return QMessageBox.StandardButton.Save

    monkeypatch.setattr(page, "_show_modal_message", confirm)
    monkeypatch.setattr(page, "_show_timed_message", lambda *args, **kwargs: messages.append(args))
    try:
        if not saved_during_confirmation:
            page._repository.export_rules(page.rules)
        assert page.export_rules_button.isEnabled()
        assert page._export_rules() is None
        assert len(confirmations) == int(saved_during_confirmation)
        assert messages == []
        assert not page.export_rules_button.isEnabled()
        assert len(list((tmp_path / "Monitor Rules").glob("*.json"))) == 1
    finally:
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("change", ["add", "edit", "toggle", "delete", "reorder"])
def test_export_button_tracks_changes_and_reverts(monkeypatch, tmp_path, change):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    rules = [make_rule(), make_rule("two", "Second")]
    MonitorRulesRepository(lambda: str(tmp_path)).export_rules(rules)
    page = monitor_rules_ui.MonitorRulesPage(
        None, rules=rules, app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        get_master_backup_dir=lambda: str(tmp_path),
    )
    try:
        # A fresh page reads the previously saved baseline from disk.
        assert not page.export_rules_button.isEnabled()
        assert page.export_rules_button.property("lightModeBlackDisabledText") is True
        if change == "add":
            page.rules.append(make_rule("three", "Third"))
        elif change == "edit":
            page.rules[0]["name"] = "Edited"
        elif change == "toggle":
            page.rules[0]["enabled"] = False
        elif change == "delete":
            page.rules.pop()
        else:
            page.rules.reverse()
        page._commit()
        assert page.export_rules_button.isEnabled()
        page.rules = copy.deepcopy(rules)
        page._commit()
        assert not page.export_rules_button.isEnabled()
        page.rules = []
        page._commit()
        assert not page.export_rules_button.isEnabled()
    finally:
        page.deleteLater()
        app.processEvents()


def test_export_button_refreshes_for_destination_and_page_display(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    owner = MasterBackupPathsMixin()
    owner.state = {"master_backup_output_path": str(tmp_path / "first")}
    monkeypatch.setattr(owner, "_get_app_module_attr", lambda _name, _default: lambda _state: None)
    page = monitor_rules_ui.MonitorRulesPage(
        None, rules=[make_rule()], app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        get_master_backup_dir=owner._get_master_backup_dir,
    )
    owner.pages = SimpleNamespace(monitor_rules_page=page)
    try:
        path = page._repository.export_rules(page.rules)
        page.show()
        app.processEvents()
        assert not page.export_rules_button.isEnabled()
        owner._set_master_backup_dir(str(tmp_path / "second"))
        # The existing rules backup follows the master path, so no new export
        # is needed immediately after changing its location.
        assert not page.export_rules_button.isEnabled()
        owner._set_master_backup_dir(str(tmp_path / "first"))
        assert not page.export_rules_button.isEnabled()
        page.hide()
        path.unlink()
        page.show()
        app.processEvents()
        assert page.export_rules_button.isEnabled()
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_changing_master_backup_path_moves_all_managed_backups(monkeypatch, tmp_path):
    old_root = tmp_path / "old-backups"
    new_root = tmp_path / "new-backups"
    for name in MasterBackupPathsMixin.MANAGED_BACKUP_ENTRIES:
        if name == "Saved Folder Names":
            continue
        entry = old_root / name
        entry.mkdir(parents=True)
        (entry / "backup.txt").write_text(name, encoding="utf-8")

    old_names = old_root / "Saved Folder Names" / "saved_folder_names.json"
    old_names.parent.mkdir(parents=True)
    old_names.write_text('["Old folder"]', encoding="utf-8")
    new_names = new_root / "Saved Folder Names" / "saved_folder_names.json"
    new_names.parent.mkdir(parents=True)
    new_names.write_text('["New folder"]', encoding="utf-8")

    owner = MasterBackupPathsMixin()
    owner.state = {"master_backup_output_path": str(old_root)}
    monkeypatch.setattr(owner, "_get_app_module_attr", lambda _name, _default: lambda _state: None)

    owner._set_master_backup_dir(str(new_root))

    assert owner.state["master_backup_output_path"] == str(new_root)
    assert not old_root.exists()
    for name in MasterBackupPathsMixin.MANAGED_BACKUP_ENTRIES:
        if name == "Saved Folder Names":
            continue
        assert (new_root / name / "backup.txt").read_text(encoding="utf-8") == name
    assert json.loads(new_names.read_text(encoding="utf-8")) == ["New folder", "Old folder"]


def test_orphaned_backup_root_can_be_adopted_then_fully_moved(monkeypatch, tmp_path):
    abandoned_root = tmp_path / "abandoned-current"
    orphaned_root = tmp_path / "orphaned-backups"
    final_root = tmp_path / "final-backups"
    abandoned_staging = (
        abandoned_root / MasterBackupPathsMixin.HOVER_STAGING_ENTRY
    )
    abandoned_staging.mkdir(parents=True)
    (abandoned_staging / "settings.json").write_text("temporary", encoding="utf-8")

    for name in MasterBackupPathsMixin.MATERIAL_BACKUP_ENTRIES:
        entry = orphaned_root / name
        entry.mkdir(parents=True)
        if name == "Saved Folder Names":
            (entry / "saved_folder_names.json").write_text(
                '["Recovered"]', encoding="utf-8"
            )
        else:
            (entry / "backup.txt").write_text(name, encoding="utf-8")
    orphaned_staging = orphaned_root / MasterBackupPathsMixin.HOVER_STAGING_ENTRY
    orphaned_staging.mkdir()
    (orphaned_staging / "settings.json").write_text("existing", encoding="utf-8")

    owner = MasterBackupPathsMixin()
    owner.state = {"master_backup_output_path": str(abandoned_root)}
    monkeypatch.setattr(owner, "_get_app_module_attr", lambda _name, _default: lambda _state: None)

    owner._set_master_backup_dir(str(orphaned_root))

    assert owner.state["master_backup_output_path"] == str(orphaned_root)
    assert not abandoned_root.exists()
    assert (orphaned_staging / "settings.json").read_text(encoding="utf-8") == "existing"

    owner._set_master_backup_dir(str(final_root))

    assert owner.state["master_backup_output_path"] == str(final_root)
    assert not orphaned_root.exists()
    for name in MasterBackupPathsMixin.MATERIAL_BACKUP_ENTRIES:
        assert (final_root / name).is_dir()
    assert (
        final_root
        / MasterBackupPathsMixin.HOVER_STAGING_ENTRY
        / "settings.json"
    ).read_text(encoding="utf-8") == "existing"


def test_changing_master_backup_path_merges_existing_directories(monkeypatch, tmp_path):
    old_root = tmp_path / "old-backups"
    new_root = tmp_path / "new-backups"
    old_bookmarks = old_root / "Bookmarks"
    new_bookmarks = new_root / "Bookmarks"
    old_bookmarks.mkdir(parents=True)
    new_bookmarks.mkdir(parents=True)
    (old_bookmarks / "old.html").write_text("old", encoding="utf-8")
    (new_bookmarks / "existing.html").write_text("existing", encoding="utf-8")

    owner = MasterBackupPathsMixin()
    owner.state = {"master_backup_output_path": str(old_root)}
    monkeypatch.setattr(owner, "_get_app_module_attr", lambda _name, _default: lambda _state: None)

    owner._set_master_backup_dir(str(new_root))

    assert not old_root.exists()
    assert (new_bookmarks / "old.html").read_text(encoding="utf-8") == "old"
    assert (new_bookmarks / "existing.html").read_text(encoding="utf-8") == "existing"


def test_changing_master_backup_path_preserves_unrelated_old_files(monkeypatch, tmp_path):
    old_root = tmp_path / "old-backups"
    new_root = tmp_path / "new-backups"
    taskbar = old_root / "TaskBarApps"
    taskbar.mkdir(parents=True)
    (taskbar / "app.lnk").write_text("shortcut", encoding="utf-8")
    unrelated = old_root / "personal.txt"
    unrelated.write_text("keep", encoding="utf-8")

    owner = MasterBackupPathsMixin()
    owner.state = {"master_backup_output_path": str(old_root)}
    monkeypatch.setattr(owner, "_get_app_module_attr", lambda _name, _default: lambda _state: None)

    owner._set_master_backup_dir(str(new_root))

    assert owner.state["master_backup_output_path"] == str(new_root)
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert (new_root / "TaskBarApps" / "app.lnk").read_text(encoding="utf-8") == "shortcut"


def test_backup_collision_aborts_before_moving_anything(monkeypatch, tmp_path):
    old_root = tmp_path / "old-backups"
    new_root = tmp_path / "new-backups"
    old_bookmark = old_root / "Bookmarks" / "same.html"
    new_bookmark = new_root / "Bookmarks" / "same.html"
    old_taskbar = old_root / "TaskBarApps" / "app.lnk"
    old_bookmark.parent.mkdir(parents=True)
    new_bookmark.parent.mkdir(parents=True)
    old_taskbar.parent.mkdir(parents=True)
    old_bookmark.write_text("old", encoding="utf-8")
    new_bookmark.write_text("new", encoding="utf-8")
    old_taskbar.write_text("shortcut", encoding="utf-8")

    owner = MasterBackupPathsMixin()
    owner.state = {"master_backup_output_path": str(old_root)}
    messages = []
    monkeypatch.setattr(owner, "_show_modal_message", lambda *args: messages.append(args), raising=False)
    monkeypatch.setattr(owner, "_message_box_icon", lambda name: name, raising=False)
    monkeypatch.setattr(owner, "_message_box_button", lambda name: name, raising=False)

    owner._set_master_backup_dir(str(new_root))

    assert owner.state["master_backup_output_path"] == str(old_root)
    assert old_bookmark.read_text(encoding="utf-8") == "old"
    assert new_bookmark.read_text(encoding="utf-8") == "new"
    assert old_taskbar.read_text(encoding="utf-8") == "shortcut"
    assert len(messages) == 1


def test_export_comparison_error_keeps_button_available(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    page = monitor_rules_ui.MonitorRulesPage(
        None, rules=[make_rule()], app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        get_master_backup_dir=lambda: str(tmp_path),
    )
    warnings = []

    def fail_comparison(_rules):
        raise OSError("Cannot read backups")

    monkeypatch.setattr(page._repository, "has_export_changes", fail_comparison)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    try:
        page.refresh_export_button()
        assert page.export_rules_button.isEnabled()
        assert warnings == []
        page.export_rules_button.click()
        assert len(warnings) == 1
        assert "Cannot read backups" in warnings[0][2]
        assert page.export_rules_button.isEnabled()
    finally:
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("mode", ["empty", "replace", "cancel", "invalid"])
def test_import_updates_saved_baseline_only_after_acceptance(monkeypatch, tmp_path, mode):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    initial = [] if mode == "empty" else [make_rule()]
    imported = [make_rule("imported", "Imported")]
    source = tmp_path / "import.json"
    source.write_text(json.dumps({"rules": imported}), encoding="utf-8")
    state = {"baseline": None}
    commits = []
    page = monitor_rules_ui.MonitorRulesPage(
        None, rules=initial, app_hwnd=999,
        on_rules_changed=lambda rules: commits.append(copy.deepcopy(rules)),
        get_master_backup_dir=lambda: str(tmp_path),
        get_import_baseline=lambda: state["baseline"],
        set_import_baseline=lambda value: state.update(baseline=value),
    )
    monkeypatch.setattr(QFileDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QFileDialog, "selectedFiles", lambda _dialog: [str(source)])
    choice = {"cancel": QMessageBox.StandardButton.Cancel}
    monkeypatch.setattr(
        page,
        "_show_modal_message",
        lambda *_args, **_kwargs: choice.get(mode, QMessageBox.StandardButton.Yes),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: None)
    try:
        if mode in {"cancel", "invalid"}:
            previous = tmp_path / "previous.json"
            previous.write_text(json.dumps({"rules": initial}), encoding="utf-8")
            page._repository.record_import(previous, initial)
        baseline_before = copy.deepcopy(state["baseline"])
        if mode == "invalid":
            source.write_text("broken", encoding="utf-8")
        commits.clear()
        before_files = set(tmp_path.rglob("*.json"))
        page._import_rules()
        if mode in {"cancel", "invalid"}:
            assert commits == []
            assert state["baseline"] == baseline_before
        else:
            assert commits
            assert not page.export_rules_button.isEnabled()
            assert state["baseline"]["source_path"] == str(source.resolve())
            assert page.rules == monitor_rules_ui.normalize_monitor_rules(imported)
            assert page._export_rules() is None
        assert set(tmp_path.rglob("*.json")) == before_files
    finally:
        page.deleteLater()
        app.processEvents()


def test_import_choice_dialog_is_frameless_rounded_and_theme_aware(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    source = tmp_path / "import.json"
    source.write_text(
        json.dumps({"rules": [make_rule("imported", "Imported")]}),
        encoding="utf-8",
    )
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[make_rule()],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        get_master_backup_dir=lambda: str(tmp_path),
    )
    original_rules = copy.deepcopy(page.rules)
    dialogs = []
    monkeypatch.setattr(QFileDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QFileDialog, "selectedFiles", lambda _dialog: [str(source)])
    monkeypatch.setattr(
        QMessageBox,
        "exec",
        lambda dialog: dialogs.append(dialog) or QMessageBox.StandardButton.Cancel,
    )
    try:
        for is_dark in (True, False):
            monitor_rules_ui.styles.set_theme(is_dark)
            page._import_rules()
            dialog = dialogs[-1]
            assert dialog.parent() is page
            assert dialog.windowTitle() == "Import Monitor Rules"
            assert dialog.text() == (
                "Importing will replace all current monitor rules."
            )
            assert dialog.standardButtons() == (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.Cancel
            )
            assert dialog.standardButton(dialog.defaultButton()) == (
                QMessageBox.StandardButton.Cancel
            )
            assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
            assert (
                dialog._popup_corner_radius
                == monitor_rules_ui.MONITOR_RULES_POPUP_CORNER_RADIUS
            )
            assert dialog.styleSheet() == monitor_rules_ui.styles.message_box_style(
                radius=monitor_rules_ui.MONITOR_RULES_POPUP_CORNER_RADIUS
            )
            app.processEvents()
            assert not dialog.mask().isEmpty()
            assert page.rules == original_rules
    finally:
        monitor_rules_ui.styles.set_theme(True)
        page.deleteLater()
        app.processEvents()


def test_export_rules_cancel_does_not_write_file(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    monkeypatch.setattr(
        monitor_rules_ui.QMessageBox,
        "exec",
        lambda _dialog: QMessageBox.StandardButton.Cancel,
    )
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[make_rule()],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        get_master_backup_dir=lambda: str(tmp_path),
    )
    try:
        assert page._export_rules() is None
        assert not (tmp_path / "Monitor Rules").exists()
        assert page._repository.has_export_changes(page.rules)
    finally:
        page.deleteLater()
        app.processEvents()


def test_export_rules_path_link_creates_and_opens_folder(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    captured = []
    opened = []

    def cancel_and_capture(dialog):
        captured.append(dialog)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(monitor_rules_ui.QMessageBox, "exec", cancel_and_capture)
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[make_rule()],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        get_master_backup_dir=lambda: str(tmp_path / "Master & Backup"),
        open_backup_folder=lambda path: opened.append(path) or True,
    )
    try:
        assert page._export_rules() is None
        confirmation = captured[0]
        assert "Master &amp; Backup" in confirmation.text()

        label = confirmation.findChild(QLabel, "qt_msgbox_label")
        label.linkActivated.emit("open-export-destination")

        destination = tmp_path / "Master & Backup" / "Monitor Rules"
        assert destination.is_dir()
        assert opened == [str(destination)]
        assert list(destination.iterdir()) == []
    finally:
        page.deleteLater()
        app.processEvents()


def test_import_rules_dialog_is_non_native_and_tracks_current_theme(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    (tmp_path / "Monitor Rules").mkdir()
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[],
        app_hwnd=999,
        on_rules_changed=lambda _rules: None,
        get_master_backup_dir=lambda: str(tmp_path),
    )
    captured = []

    def reject_and_capture(dialog):
        captured.append(dialog)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(monitor_rules_ui.QFileDialog, "exec", reject_and_capture)
    try:
        for is_dark in (True, False):
            monitor_rules_ui.styles.set_theme(is_dark)
            page._import_rules()
            dialog = captured[-1]
            assert dialog.parent() is page
            assert dialog.windowTitle() == "Import Monitor Rules"
            assert Path(dialog.directory().absolutePath()) == tmp_path / "Monitor Rules"
            assert dialog.nameFilters() == [
                "Monitor rule backups (*.json)",
                "All files (*)",
            ]
            assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
            assert dialog.fileMode() == QFileDialog.FileMode.ExistingFile
            assert dialog.acceptMode() == QFileDialog.AcceptMode.AcceptOpen
            assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
            assert isinstance(dialog, monitor_rules_ui.ImportRulesDialog)
            assert dialog.minimumSize() == dialog.maximumSize()
            assert dialog.contentsMargins().top() == dialog.HEADER_HEIGHT
            heading = dialog.findChild(QLabel, "ImportRulesDialogHeading")
            assert heading is not None
            assert heading.text() == "Import Rules"
            assert heading.alignment() & Qt.AlignmentFlag.AlignHCenter
            assert heading.styleSheet() == monitor_rules_ui.styles.page_title_style()
            sidebar = dialog.findChild(QListView, "sidebar")
            assert sidebar is not None
            assert sidebar.minimumWidth() == dialog.PLACES_SIDEBAR_WIDTH
            assert sidebar.maximumWidth() == dialog.PLACES_SIDEBAR_WIDTH
            stylesheet = dialog.styleSheet()
            assert monitor_rules_ui.styles.qcolor_css(
                monitor_rules_ui.styles.WINDOW_BG
            ) in stylesheet
            assert monitor_rules_ui.styles.qcolor_css(
                monitor_rules_ui.styles.theme_text_color()
            ) in stylesheet
            assert monitor_rules_ui.styles.qcolor_css(
                monitor_rules_ui.styles.SURFACE_BORDER
            ) in stylesheet
    finally:
        monitor_rules_ui.styles.set_theme(True)
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("is_dark", (True, False))
def test_master_backup_directory_dialog_is_themed_and_non_native(is_dark):
    app = QApplication.instance() or QApplication([])
    original_theme = monitor_rules_ui.styles.THEME_IS_DARK
    monitor_rules_ui.styles.set_theme(is_dark)
    dialog = MasterBackupDirectoryDialog(None, "")
    try:
        assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
        assert dialog.testOption(QFileDialog.Option.ShowDirsOnly)
        assert dialog.fileMode() == QFileDialog.FileMode.Directory
        assert dialog.acceptMode() == QFileDialog.AcceptMode.AcceptOpen
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dialog.minimumSize() == dialog.maximumSize()
        assert monitor_rules_ui.styles.qcolor_css(
            monitor_rules_ui.styles.WINDOW_BG
        ) in dialog.styleSheet()
        assert monitor_rules_ui.styles.qcolor_css(
            monitor_rules_ui.styles.theme_text_color()
        ) in dialog.styleSheet()
    finally:
        dialog.close()
        dialog.deleteLater()
        monitor_rules_ui.styles.set_theme(original_theme)
        app.processEvents()


def test_delete_all_does_not_create_a_backup(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    monkeypatch.setattr(
        monitor_rules_ui.QMessageBox,
        "exec",
        lambda _message_box: monitor_rules_ui.QMessageBox.StandardButton.Yes,
    )
    commits = []
    page = monitor_rules_ui.MonitorRulesPage(
        None,
        rules=[make_rule()],
        app_hwnd=999,
        on_rules_changed=lambda rules: commits.append(rules),
        get_master_backup_dir=lambda: str(tmp_path),
    )
    try:
        page._delete_all_rules()
        assert not (tmp_path / "Monitor Rules").exists()
        assert commits[-1] == []
    finally:
        page.deleteLater()
        app.processEvents()


class FakeMonitorRuleWatcher:
    def __init__(self, *args, **kwargs):
        self.updates = []
        self.manual_moves = []
        self.stopped = False

    def update_rules(self, rules, app_hwnd=None, *, apply_existing=False, apply_rule_ids=None):
        self.updates.append((copy.deepcopy(rules), app_hwnd, apply_existing, apply_rule_ids))

    def note_manual_move(self, hwnd):
        self.manual_moves.append(hwnd)

    def stop(self):
        self.stopped = True


def test_application_persists_rules_updates_watcher_and_stops_it(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main, "MonitorRuleWatcher", FakeMonitorRuleWatcher)
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)
    watcher = window.monitor_rule_watcher
    saved_states = []
    monkeypatch.setattr(main, "save_state", lambda value: saved_states.append(copy.deepcopy(value)))
    try:
        assert watcher.updates[0][0] == []
        assert watcher.updates[0][2] is True
        assert window.pages.monitor_rules_page.objectName() == "MonitorRulesPage"
        assert window.pages.monitor_rules_page.rules_frame.objectName() == (
            "MonitorRulesEmptyState"
        )
        assert "border-radius: 8px" in (
            window.pages.monitor_rules_page.rules_frame.styleSheet()
        )
        window.set_monitor_rules([make_rule()])
        assert window.state["monitor_rules"][0]["id"] == "one"
        assert watcher.updates[-1][0][0]["target_device"] == r"\\.\DISPLAY2"
        assert watcher.updates[-1][2] is False
        source = tmp_path / "import.json"
        source.write_text(json.dumps({"rules": [make_rule()]}), encoding="utf-8")
        page = window.pages.monitor_rules_page
        page._repository.record_import(source, [make_rule()])
        assert saved_states[-1]["monitor_rules_import_baseline"]["source_path"] == str(source.resolve())
        restored = json.loads(json.dumps(saved_states[-1]))
        repository = MonitorRulesRepository(
            lambda: window._get_master_backup_dir(),
            get_import_baseline=lambda: restored["monitor_rules_import_baseline"],
        )
        assert not repository.has_export_changes([make_rule()])
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        app.processEvents()
    assert watcher.stopped is True


@pytest.mark.parametrize("save", [True, False])
@pytest.mark.parametrize("rename", [True, False])
def test_editor_save_forwards_rule_id_through_application(monkeypatch, save, rename):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main, "MonitorRuleWatcher", FakeMonitorRuleWatcher)
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    monkeypatch.setattr(rule_schema.os.path, "isfile", lambda _path: True)
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["monitor_rules"] = [make_rule()]
    window = _build_offscreen_window(monkeypatch, state)
    edited = make_rule(name="New name" if rename else "Discord")
    during_dialog = []

    class Editor:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            during_dialog.append(len(watcher.updates))
            return QDialog.DialogCode.Accepted if save else QDialog.DialogCode.Rejected

        def result_rule(self):
            return edited

    monkeypatch.setattr(monitor_rules_ui, "MonitorRuleEditorDialog", Editor)
    try:
        watcher = window.monitor_rule_watcher
        initial_count = len(watcher.updates)
        window.pages.monitor_rules_page._edit_rule(0)
        assert during_dialog == [initial_count]
        if save:
            assert len(watcher.updates) == initial_count + 1
            assert watcher.updates[-1][3] == {"one"}
            assert watcher.updates[-1][0][0]["name"] == edited["name"]
            assert window.state["monitor_rules"][0]["name"] == edited["name"]
            assert "apply_rule_ids" not in window.state["monitor_rules"][0]
        else:
            assert len(watcher.updates) == initial_count
            assert window.state["monitor_rules"][0]["name"] == "Discord"
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("save", [True, False])
def test_add_rule_waits_for_save_before_updating_runtime(monkeypatch, save):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main, "MonitorRuleWatcher", FakeMonitorRuleWatcher)
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)
    added = make_rule("new", "New rule")
    during_dialog = []

    class Editor:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            during_dialog.append(len(watcher.updates))
            return QDialog.DialogCode.Accepted if save else QDialog.DialogCode.Rejected

        def result_rule(self):
            return added

    monkeypatch.setattr(monitor_rules_ui, "MonitorRuleEditorDialog", Editor)
    try:
        watcher = window.monitor_rule_watcher
        initial_count = len(watcher.updates)
        window.pages.monitor_rules_page._add_rule()
        assert during_dialog == [initial_count]
        if save:
            assert len(watcher.updates) == initial_count + 1
            assert watcher.updates[-1][3] == {"new"}
            assert window.state["monitor_rules"][0]["id"] == "new"
            assert window.state["monitor_rules"][0]["name"] == "New rule"
        else:
            assert len(watcher.updates) == initial_count
            assert window.state["monitor_rules"] == []
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        app.processEvents()

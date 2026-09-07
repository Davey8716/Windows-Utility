import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
)

from Shared.app_state_defaults import WINDOWS_RESURFACE_DEFAULTS
from resurface.core.app_paths import MasterBackupPathsMixin
from resurface.features.monitor_rules import MonitorRulesRepository
from resurface.ui import application_window as main
from resurface.ui import monitor_rule_editor_dialog
from resurface.ui import monitor_rules_page as monitor_rules_ui
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
        "title_contains": "",
        "class_name": "",
        "target_device": r"\\.\DISPLAY2",
        "target_label": "Monitor 2",
        "placement_mode": placement_mode,
        "saved_geometry": None,
    }


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
        assert isinstance(page, QFrame)
        assert page.objectName() == "MonitorRulesEmptyState"
        margins = page.layout().contentsMargins()
        assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
            24,
            24,
            24,
            24,
        )
        assert page.layout().spacing() == 12
        assert page.add_button.isEnabled()
        assert page.turn_off_all_button.isEnabled()
        assert page.turn_off_all_button.text() == "Turn Off All"
        assert page.delete_all_button.isEnabled()
        assert page.delete_all_button.text() == "Delete All"
        assert page.alphabet_sort_button.isEnabled()
        assert page.alphabet_sort_button.text() == "A–Z"
        page.resize(760, page.sizeHint().height())
        page.show()
        app.processEvents()
        top_buttons = (
            page.alphabet_sort_button,
            page.add_button,
            page.turn_off_all_button,
            page.delete_all_button,
        )
        assert page.export_rules_button.width() == page.turn_off_all_button.width()
        assert page.export_rules_button.x() == page.turn_off_all_button.x()
        assert page.import_rules_button.width() == page.delete_all_button.width()
        assert page.import_rules_button.x() == page.delete_all_button.x()

        page.resize(900, page.height())
        app.processEvents()
        assert page.export_rules_button.geometry().x() == page.turn_off_all_button.geometry().x()
        assert page.export_rules_button.width() == page.turn_off_all_button.width()
        assert page.import_rules_button.geometry().x() == page.delete_all_button.geometry().x()
        assert page.import_rules_button.width() == page.delete_all_button.width()
        initial_cards = [
            page.rule_list_layout.itemAt(index).widget()
            for index in range(page.rule_list_layout.count())
        ]
        expected_actions = {"Edit", "Delete", "Move Up", "Move Down"}
        assert all(
            {button.text() for button in card.findChildren(QPushButton)}
            == expected_actions
            for card in initial_cards
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
        assert all("\nTarget: Monitor 2\nPlacement: Maximize" in text for text in details)
        assert all("\nReapply if moved: Disabled" in text for text in details)

        page.rules[0]["reapply_if_moved"] = True
        page._render_rules()
        enabled_details = (
            page.rule_list_layout.itemAt(0)
            .widget()
            .findChild(monitor_rules_ui.QLabel, "MonitorRuleDetails")
            .text()
        )
        assert "\nReapply if moved: Enabled" in enabled_details

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
        dialog.window_combo.setCurrentIndex(1)
        dialog.placement_combo.setCurrentIndex(
            dialog.placement_combo.findData("saved_geometry")
        )
        dialog._capture_geometry()
        rule = dialog.result_rule()
        assert rule["executable_name"] == "discord.exe"
        assert rule["target_device"] == r"\\.\DISPLAY2"
        assert rule["saved_geometry"]["width"] == 900
        assert dialog._validation_message() == ""
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
        assert calls == [{"app_hwnd": 999}]
        assert dialog.window_combo.count() == 2
        assert "Windows Resurface" in dialog.window_combo.itemText(1)

        dialog.window_combo.setCurrentIndex(1)

        assert dialog.executable_edit.text() == r"C:\Apps\Windows Resurface.exe"
        assert dialog.name_edit.text() == "windows resurface"
        assert dialog.exact_path_check.isChecked()
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
        monitor_rules_ui.QMessageBox.StandardButton.No,
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
        assert dialog.styleSheet() == monitor_rules_ui.styles.message_box_style()
        assert dialog.icon() == monitor_rules_ui.QMessageBox.Icon.Question
        assert dialog.windowTitle() == "Delete Monitor Rule"
        assert dialog.text() == "Delete the rule ‘Discord’?"
        assert dialog.standardButtons() == (
            monitor_rules_ui.QMessageBox.StandardButton.Yes
            | monitor_rules_ui.QMessageBox.StandardButton.No
        )
        assert dialog.standardButton(dialog.defaultButton()) == (
            monitor_rules_ui.QMessageBox.StandardButton.No
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
            "Delete all 2 monitor rules? This cannot be undone."
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
                confirmation.styleSheet()
                == monitor_rules_ui.styles.message_box_style()
            )
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
            assert timed_kwargs == {"show_close_now_button": True}
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
        assert page.export_rules_button.isEnabled()
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


@pytest.mark.parametrize("mode", ["empty", "replace", "merge", "cancel", "invalid", "safety"])
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
    choice = {"merge": QMessageBox.StandardButton.No, "cancel": QMessageBox.StandardButton.Cancel}
    monkeypatch.setattr(QMessageBox, "question", lambda *args: choice.get(mode, QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: None)
    try:
        if mode in {"cancel", "invalid"}:
            previous = tmp_path / "previous.json"
            previous.write_text(json.dumps({"rules": initial}), encoding="utf-8")
            page._repository.record_import(previous, initial)
        baseline_before = copy.deepcopy(state["baseline"])
        if mode == "invalid":
            source.write_text("broken", encoding="utf-8")
        if mode == "safety":
            monkeypatch.setattr(QMessageBox, "exec", lambda _dialog: QMessageBox.StandardButton.Yes)
            page._delete_all_rules()
            source = next((tmp_path / "Monitor Rules").glob("monitor_rules_before_delete_*.json"))
            imported = initial
            assert page.rules == []
        commits.clear()
        before_files = set(tmp_path.rglob("*.json"))
        page._import_rules()
        if mode in {"cancel", "invalid"}:
            assert commits == []
            assert state["baseline"] == baseline_before
        else:
            assert commits
            assert page.export_rules_button.isEnabled() == (mode == "merge")
            assert state["baseline"]["source_path"] == str(source.resolve())
            if mode != "merge":
                assert page.rules == monitor_rules_ui.normalize_monitor_rules(imported)
                assert page._export_rules() is None
        assert set(tmp_path.rglob("*.json")) == before_files
    finally:
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
            stylesheet = dialog.styleSheet()
            assert monitor_rules_ui.styles.qcolor_css(
                monitor_rules_ui.styles.WINDOW_BG
            ) in stylesheet
            assert monitor_rules_ui.styles.qcolor_css(
                monitor_rules_ui.styles.theme_text_color()
            ) in stylesheet
    finally:
        monitor_rules_ui.styles.set_theme(True)
        page.deleteLater()
        app.processEvents()


def test_delete_all_creates_safety_backup(monkeypatch, tmp_path):
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
        safety_backups = list(
            (tmp_path / "Monitor Rules").glob("monitor_rules_before_delete_*.json")
        )
        assert len(safety_backups) == 1
        assert json.loads(safety_backups[0].read_text(encoding="utf-8"))["rules"]
        assert commits[-1] == []
    finally:
        page.deleteLater()
        app.processEvents()


class FakeMonitorRuleWatcher:
    def __init__(self, *args, **kwargs):
        self.updates = []
        self.stopped = False

    def update_rules(self, rules, app_hwnd=None, *, apply_existing=False, apply_rule_ids=None):
        self.updates.append((copy.deepcopy(rules), app_hwnd, apply_existing, apply_rule_ids))

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
        assert window.pages.monitor_rules_page.objectName() == "MonitorRulesEmptyState"
        assert "border-radius: 8px" in window.pages.monitor_rules_page.styleSheet()
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

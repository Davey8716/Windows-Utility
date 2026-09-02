import copy
import json
from pathlib import Path

from PySide6.QtCore import Qt
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

    def accept_and_capture(dialog):
        captured.append(dialog)
        if dialog.standardButtons() & QMessageBox.StandardButton.Save:
            return QMessageBox.StandardButton.Save
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(monitor_rules_ui.QMessageBox, "exec", accept_and_capture)
    try:
        for is_dark in (True, False):
            monitor_rules_ui.styles.set_theme(is_dark)
            exported_path = page._export_rules()
            confirmation = captured[-2]
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

            acknowledgement = captured[-1]
            assert acknowledgement.parent() is page
            assert acknowledgement.windowTitle() == "Monitor Rules Exported"
            assert acknowledgement.text() == (
                f"Monitor rules were exported to:\n{exported_path}"
            )
            assert acknowledgement.icon() == QMessageBox.Icon.Information
            assert acknowledgement.standardButtons() == QMessageBox.StandardButton.Ok
            assert acknowledgement.windowFlags() & Qt.WindowType.FramelessWindowHint
            assert (
                acknowledgement.styleSheet()
                == monitor_rules_ui.styles.message_box_style()
            )
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

    def update_rules(self, rules, app_hwnd=None, *, apply_existing=False):
        self.updates.append((copy.deepcopy(rules), app_hwnd, apply_existing))

    def stop(self):
        self.stopped = True


def test_application_persists_rules_updates_watcher_and_stops_it(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main, "MonitorRuleWatcher", FakeMonitorRuleWatcher)
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)
    watcher = window.monitor_rule_watcher
    try:
        assert watcher.updates[0][0] == []
        assert watcher.updates[0][2] is True
        assert window.pages.monitor_rules_page.objectName() == "MonitorRulesEmptyState"
        assert "border-radius: 8px" in window.pages.monitor_rules_page.styleSheet()
        window.set_monitor_rules([make_rule()])
        assert window.state["monitor_rules"][0]["id"] == "one"
        assert watcher.updates[-1][0][0]["target_device"] == r"\\.\DISPLAY2"
        assert watcher.updates[-1][2] is False
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        app.processEvents()
    assert watcher.stopped is True

import copy

from PySide6.QtWidgets import QApplication, QFrame

from Shared.app_state_defaults import WINDOWS_RESURFACE_DEFAULTS
from resurface.ui import application_window as main
from resurface.ui import monitor_rules_ui
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
        initial_cards = [
            page.rule_list_layout.itemAt(index).widget()
            for index in range(page.rule_list_layout.count())
        ]
        assert all(
            card.findChild(monitor_rules_ui.QLabel, "MonitorRuleStatus").text() == "on"
            for card in initial_cards
        )

        page._set_enabled(0, False)
        assert commits[-1][0]["enabled"] is False
        disabled_card = page.rule_list_layout.itemAt(0).widget()
        assert (
            disabled_card.findChild(monitor_rules_ui.QLabel, "MonitorRuleStatus").text()
            == "off"
        )
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
    monkeypatch.setattr(monitor_rules_ui, "enumerate_monitors", monitors)
    monkeypatch.setattr(
        monitor_rules_ui,
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
        monitor_rules_ui,
        "capture_window_geometry",
        lambda _hwnd: {"x_offset": 40, "y_offset": 50, "width": 900, "height": 700},
    )
    dialog = monitor_rules_ui.MonitorRuleEditorDialog(None, app_hwnd=999)
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


class FakeMonitorRuleWatcher:
    def __init__(self, *args, **kwargs):
        self.updates = []
        self.stopped = False

    def update_rules(self, rules, app_hwnd=None):
        self.updates.append((copy.deepcopy(rules), app_hwnd))

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
        assert window.monitor_rules_page.objectName() == "MonitorRulesEmptyState"
        assert "border-radius: 8px" in window.monitor_rules_page.styleSheet()
        window.set_monitor_rules([make_rule()])
        assert window.state["monitor_rules"][0]["id"] == "one"
        assert watcher.updates[-1][0][0]["target_device"] == r"\\.\DISPLAY2"
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        app.processEvents()
    assert watcher.stopped is True

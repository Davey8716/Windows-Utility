from resurface.ui.controllers.runtime_settings import (
    MonitorRulesController,
    ScreenMoverSettingsController,
)


class FakeHotkeyManager:
    def __init__(self):
        self.calls = []

    def update_hotkeys(self, hotkeys):
        self.calls.append(hotkeys)


class FakeWatcher:
    def __init__(self):
        self.calls = []

    def update_rules(self, rules, **options):
        self.calls.append((rules, options))


def test_screen_mover_controller_applies_configured_shortcuts_automatically():
    state = {
        "screen_mover_keyboard_hotkeys": {"LEFT": "Ctrl+Left", "RIGHT": ""},
    }
    hotkeys = FakeHotkeyManager()
    controller = ScreenMoverSettingsController(
        state=state,
        hotkey_manager=hotkeys,
        save_state=lambda _state: None,
        settings_page=lambda: None,
        legacy_hotkey_edits=lambda: {},
        refresh_overview=lambda: None,
    )

    controller.apply_settings()

    assert hotkeys.calls == [{"LEFT": "<ctrl>+<left>"}]


def test_monitor_rules_controller_normalizes_persists_and_toggles_rules():
    state = {"monitor_rules": []}
    watcher = FakeWatcher()
    saved = []
    tray_syncs = []
    controller = MonitorRulesController(
        state=state,
        watcher=watcher,
        save_state=lambda current: saved.append([dict(rule) for rule in current["monitor_rules"]]),
        window_handle=lambda: 99,
        rules_page=lambda: None,
        sync_tray=lambda: tray_syncs.append(True),
    )
    rule = {
        "id": "one",
        "name": "Discord",
        "enabled": True,
        "reapply_if_moved": False,
        "executable_name": "Discord.exe",
        "executable_path": r"C:\Apps\Discord.exe",
        "match_exact_path": True,
        "target_device": r"\\.\DISPLAY2",
        "target_label": "Monitor 2",
        "placement_mode": "keep_size",
        "saved_geometry": None,
    }

    controller.set_rules([rule])
    controller.set_enabled(False)

    assert state["monitor_rules"][0]["executable_name"] == "discord.exe"
    assert state["monitor_rules"][0]["enabled"] is False
    assert watcher.calls[0][1] == {"app_hwnd": 99, "apply_existing": False}
    assert watcher.calls[-1][0][0]["enabled"] is False
    assert len(saved) == 2
    assert tray_syncs == [True, True]


def test_monitor_rules_controller_prunes_missing_exact_path_rules_and_refreshes_ui(
    monkeypatch,
):
    from resurface.features.monitor_rules import rule_schema

    missing = {
        "id": "missing",
        "name": "Missing app",
        "enabled": True,
        "reapply_if_moved": False,
        "executable_name": "missing.exe",
        "executable_path": r"C:\\Apps\\missing.exe",
        "match_exact_path": True,
        "target_device": r"\\.\\DISPLAY2",
        "target_label": "Monitor 2",
        "placement_mode": "keep_size",
        "saved_geometry": None,
    }
    name_only = {**missing, "id": "name-only", "match_exact_path": False}
    state = {"monitor_rules": [missing, name_only]}
    watcher = FakeWatcher()
    saved = []
    tray_syncs = []
    overview_refreshes = []

    class Page:
        def __init__(self):
            self.rules = None

        def set_rules(self, rules):
            self.rules = rules

    page = Page()
    monkeypatch.setattr(rule_schema.os.path, "isfile", lambda _path: False)
    controller = MonitorRulesController(
        state=state,
        watcher=watcher,
        save_state=lambda current: saved.append(current["monitor_rules"]),
        window_handle=lambda: 99,
        rules_page=lambda: page,
        sync_tray=lambda: tray_syncs.append(True),
        refresh_overview=lambda: overview_refreshes.append(True),
    )

    assert controller.prune_missing_exact_path_rules() is True
    assert [rule["id"] for rule in state["monitor_rules"]] == ["name-only"]
    assert page.rules == state["monitor_rules"]
    assert len(saved) == 1
    assert tray_syncs == [True]
    assert overview_refreshes == [True]
    assert controller.prune_missing_exact_path_rules() is False
    assert len(saved) == 1


def test_monitor_rules_controller_migrates_retired_filters_once():
    legacy_rule = {
        "id": "one",
        "name": "Discord",
        "enabled": True,
        "reapply_if_moved": False,
        "executable_name": "Discord.exe",
        "executable_path": r"C:\Apps\Discord.exe",
        "match_exact_path": True,
        "title_contains": "Friends",
        "class_name": "LegacyClass",
        "target_device": r"\\.\DISPLAY2",
        "target_label": "Monitor 2",
        "placement_mode": "keep_size",
        "saved_geometry": None,
    }
    state = {"monitor_rules": [legacy_rule]}
    watcher = FakeWatcher()
    saved = []
    tray_syncs = []
    controller = MonitorRulesController(
        state=state,
        watcher=watcher,
        save_state=lambda current: saved.append(current["monitor_rules"]),
        window_handle=lambda: 99,
        rules_page=lambda: None,
        sync_tray=lambda: tray_syncs.append(True),
    )

    assert controller.migrate_retired_filters() is True
    assert "title_contains" not in state["monitor_rules"][0]
    assert "class_name" not in state["monitor_rules"][0]
    assert len(saved) == 1 and tray_syncs == [True]
    assert controller.migrate_retired_filters() is False
    assert len(saved) == 1


def test_monitor_rules_controller_merges_component_rules_using_first_target():
    component = {
        "id": "main",
        "name": "Windows Resurface",
        "enabled": True,
        "reapply_if_moved": True,
        "executable_name": "Windows Resurface.exe",
        "executable_path": r"C:\Apps\Windows Resurface.exe",
        "match_exact_path": True,
        "target_device": r"\\.\DISPLAY2",
        "target_label": "Monitor 2",
        "placement_mode": "maximize",
        "saved_geometry": None,
    }
    later_component = {
        **component,
        "id": "folder",
        "executable_name": "Folder Creator.exe",
        "target_device": r"\\.\DISPLAY3",
        "target_label": "Monitor 3",
    }
    unrelated = {**component, "id": "discord", "executable_name": "Discord.exe"}
    state = {"monitor_rules": [unrelated, component, later_component]}
    saved = []
    controller = MonitorRulesController(
        state=state,
        watcher=FakeWatcher(),
        save_state=lambda current: saved.append(current["monitor_rules"]),
        window_handle=lambda: 99,
        rules_page=lambda: None,
        sync_tray=lambda: None,
    )

    assert controller.migrate_windows_resurface_group_rules() is True
    assert [rule["id"] for rule in state["monitor_rules"]] == ["discord", "main"]
    grouped = state["monitor_rules"][1]
    assert grouped["app_group"] == "windows_resurface"
    assert grouped["target_device"] == r"\\.\DISPLAY2"
    assert grouped["reapply_if_moved"] is True
    assert grouped["placement_mode"] == "keep_size"
    assert len(saved) == 1

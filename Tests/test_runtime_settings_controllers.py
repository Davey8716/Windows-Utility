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
        "title_contains": "",
        "class_name": "",
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

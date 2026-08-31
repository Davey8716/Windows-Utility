from resurface.ui.controllers.runtime_settings import (
    MonitorRulesController,
    ScreenMoverSettingsController,
)


class FakeScreenMover:
    def __init__(self):
        self.calls = []

    def update_settings(self, **settings):
        self.calls.append(settings)


class FakeHotkeyManager:
    def __init__(self):
        self.calls = []

    def update_hotkeys(self, hotkeys, *, enabled):
        self.calls.append((hotkeys, enabled))


class FakeWatcher:
    def __init__(self):
        self.calls = []

    def update_rules(self, rules, **options):
        self.calls.append((rules, options))


def test_screen_mover_controller_applies_runtime_and_dispatches_self_actions():
    state = {
        "title_bar_dock_enabled": True,
        "screen_mover_activation_button": "right",
        "screen_mover_keyboard_hotkeys": {"LEFT": "Ctrl+Left", "RIGHT": ""},
    }
    screen_mover = FakeScreenMover()
    hotkeys = FakeHotkeyManager()
    tray_syncs = []
    actions = []
    controller = ScreenMoverSettingsController(
        state=state,
        screen_mover=screen_mover,
        hotkey_manager=hotkeys,
        save_state=lambda _state: None,
        window_handle=lambda: 42,
        settings_page=lambda: None,
        legacy_toggle=lambda: None,
        legacy_activation_combo=lambda: None,
        legacy_hotkey_edits=lambda: {},
        refresh_overview=lambda: None,
        sync_tray=lambda: tray_syncs.append(True),
        perform_action=lambda hwnd, action: actions.append((hwnd, action)),
    )

    controller.apply_settings()
    controller.handle_self_action("LEFT")
    controller.handle_self_action("MAXIMIZE")

    assert screen_mover.calls == [
        {
            "title_bar_dock_enabled": True,
            "activation_button": "right",
            "force_running": True,
        }
    ]
    assert hotkeys.calls == [({"LEFT": "<ctrl>+<left>"}, True)]
    assert tray_syncs == [True]
    assert actions == [(42, "LEFT")]


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

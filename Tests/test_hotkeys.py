from resurface.features.screen_mover.hotkeys import (
    GlobalHotkeyManager,
    active_hotkeys,
    hotkey_to_display,
    normalize_hotkey,
    normalize_unique_hotkeys,
)


class FakeHotkeyListener:
    def __init__(self, bindings):
        self.bindings = bindings
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def test_normalize_hotkey_orders_modifiers_and_supports_special_keys():
    assert normalize_hotkey("Win + shift + CTRL + F12") == (
        "<ctrl>+<shift>+<cmd>+<f12>"
    )
    assert normalize_hotkey("Alt + Page Down") == "<alt>+<page_down>"
    assert normalize_hotkey("control + z") == "<ctrl>+z"


def test_normalize_hotkey_rejects_missing_or_multiple_primary_keys():
    assert normalize_hotkey("Ctrl + Alt") == ""
    assert normalize_hotkey("Ctrl + A + B") == ""
    assert normalize_hotkey("Ctrl + NotAKey") == ""
    assert normalize_hotkey("Disabled") == ""


def test_hotkey_display_and_active_filtering():
    assert hotkey_to_display("<ctrl>+<cmd>+<page_up>") == "Ctrl+Win+PageUp"
    assert hotkey_to_display("<shift>+<f24>") == "Shift+F24"
    assert active_hotkeys(
        {
            "LEFT": "Ctrl+Left",
            "RIGHT": "off",
            "MINIMIZE": "Win+M",
            "UNKNOWN": "Ctrl+U",
        }
    ) == {
        "LEFT": "<ctrl>+<left>",
        "MINIMIZE": "<cmd>+m",
    }


def test_duplicate_hotkeys_keep_the_first_action_in_screen_order():
    values = {
        "FAR_LEFT": "Shift+Ctrl+A",
        "LEFT": "Ctrl+Shift+A",
        "RIGHT": "control + shift + a",
        "MAXIMIZE": "Win+Up",
    }

    assert normalize_unique_hotkeys(values) == {
        "FAR_LEFT": "<ctrl>+<shift>+a",
        "LEFT": "",
        "RIGHT": "",
        "FAR_RIGHT": "",
        "MINIMIZE": "",
        "MAXIMIZE": "<cmd>+<up>",
    }
    assert active_hotkeys(values) == {
        "FAR_LEFT": "<ctrl>+<shift>+a",
        "MAXIMIZE": "<cmd>+<up>",
    }


def test_global_hotkey_manager_starts_dispatches_reconfigures_and_stops():
    listeners = []
    actions = []

    def factory(bindings):
        listener = FakeHotkeyListener(bindings)
        listeners.append(listener)
        return listener

    manager = GlobalHotkeyManager(actions.append, listener_factory=factory)
    manager.update_hotkeys({"LEFT": "Ctrl+Left"})

    assert len(listeners) == 1
    assert listeners[0].started
    listeners[0].bindings["<ctrl>+<left>"]()
    assert actions == ["LEFT"]

    manager.update_hotkeys({"LEFT": "Ctrl+Left"})
    assert len(listeners) == 1

    manager.update_hotkeys({"RIGHT": "Ctrl+Right"})
    assert listeners[0].stopped
    assert len(listeners) == 2
    assert listeners[1].started

    manager.update_hotkeys({})
    assert listeners[1].stopped
    assert manager.listener is None

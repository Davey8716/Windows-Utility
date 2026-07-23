import copy

import main
from PySide6.QtGui import QIcon, QKeySequence
from PySide6.QtWidgets import QApplication
from Shared.app_state_defaults import WINDOWS_RESURFACE_DEFAULTS


class FakeRuntime:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.configurations = []

    def configure(self, **settings):
        self.configurations.append(settings)

    def update_settings(self, **settings):
        self.calls.append(settings)

    def request_action(self, _action):
        pass

    def stop(self):
        pass


class FakeHotkeyManager:
    def __init__(self, _callback=None):
        self.calls = []

    def update_hotkeys(self, hotkeys, *, enabled):
        self.calls.append((hotkeys, enabled))

    def stop(self):
        pass


class FakeTrayManager:
    def __init__(self, _window=None):
        self.sync_calls = 0
        self.tray = None

    def create_tray_icon(self):
        pass

    def sync_screen_mover_action(self):
        self.sync_calls += 1


class FakeStyle:
    def unpolish(self, _widget):
        pass

    def polish(self, _widget):
        pass


class FakeCombo:
    def __init__(self):
        self.value = "off"
        self.persist_pressed = False

    def findData(self, value):
        return {"off": 0, "middle": 1}[value]

    def blockSignals(self, _blocked):
        pass

    def setCurrentIndex(self, index):
        self.value = {0: "off", 1: "middle"}[index]

    def setProperty(self, name, value):
        if name == "persistPressed":
            self.persist_pressed = value

    def style(self):
        return FakeStyle()


class FakeEdit:
    def __init__(self):
        self.cleared = False

    def blockSignals(self, _blocked):
        pass

    def clear(self):
        self.cleared = True


class FakeToggle:
    def __init__(self, checked=False):
        self.checked = checked
        self.text = ""

    def isChecked(self):
        return self.checked

    def blockSignals(self, _blocked):
        pass

    def setChecked(self, checked):
        self.checked = checked

    def setText(self, text):
        self.text = text


class FakeWindow:
    apply_screen_mover_settings = main.UtilityControlApp.apply_screen_mover_settings
    set_screen_mover_enabled = main.UtilityControlApp.set_screen_mover_enabled
    reset_screen_mover_settings = main.UtilityControlApp.reset_screen_mover_settings

    def __init__(self):
        self.state = {
            "title_bar_dock_enabled": False,
            "screen_mover_activation_button": "right",
            "mmb_activation_enabled": False,
            "screen_mover_keyboard_hotkeys": {
                "LEFT": "Ctrl+Left",
                "RIGHT": "",
            },
            "theme_dark": False,
        }
        self.screen_mover = FakeRuntime()
        self.hotkey_manager = FakeHotkeyManager()
        self.tray_manager = FakeTrayManager()
        self.screen_mover_enabled_btn = FakeToggle(False)
        self.screen_move_button_combo = FakeCombo()
        self.screen_mover_hotkey_edits = {
            "LEFT": FakeEdit(),
            "RIGHT": FakeEdit(),
        }


def test_master_toggle_synchronizes_state_ui_runtime_and_tray(monkeypatch):
    saved_states = []
    monkeypatch.setattr(main, "save_state", lambda state: saved_states.append(dict(state)))
    window = FakeWindow()

    window.set_screen_mover_enabled(True)

    assert window.state["title_bar_dock_enabled"] is True
    assert window.screen_mover_enabled_btn.checked is True
    assert window.screen_mover_enabled_btn.text == "Screen Mover On"
    assert window.screen_mover.calls[-1] == {
        "title_bar_dock_enabled": True,
        "activation_button": "right",
        "force_running": True,
    }
    assert window.hotkey_manager.calls[-1] == (
        {"LEFT": "<ctrl>+<left>"},
        True,
    )
    assert window.tray_manager.sync_calls == 1
    assert saved_states[-1]["title_bar_dock_enabled"] is True


def test_reset_defaults_changes_only_screen_mover_settings(monkeypatch):
    monkeypatch.setattr(main, "save_state", lambda _state: None)
    window = FakeWindow()

    window.reset_screen_mover_settings()

    assert window.state["theme_dark"] is False
    assert window.state["title_bar_dock_enabled"] is True
    assert window.state["screen_mover_activation_button"] == "middle"
    assert window.state["mmb_activation_enabled"] is True
    assert all(
        value == ""
        for value in window.state["screen_mover_keyboard_hotkeys"].values()
    )
    assert window.screen_move_button_combo.value == "middle"
    assert window.screen_move_button_combo.persist_pressed is True
    assert all(edit.cleared for edit in window.screen_mover_hotkey_edits.values())
    assert window.screen_mover.calls[-1]["activation_button"] == "middle"
    assert window.screen_mover.calls[-1]["force_running"] is False


def test_real_screen_mover_section_builds_and_resets_offscreen(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["theme_dark"] = False
    state["screen_mover_activation_button"] = "right"
    state["screen_mover_keyboard_hotkeys"]["LEFT"] = "<ctrl>+<left>"

    monkeypatch.setattr(main, "load_state", lambda: copy.deepcopy(state))
    monkeypatch.setattr(main, "save_state", lambda _state: None)
    monkeypatch.setattr(main, "ScreenMover", FakeRuntime)
    monkeypatch.setattr(main, "GlobalHotkeyManager", FakeHotkeyManager)
    monkeypatch.setattr(main, "TrayIconManager", FakeTrayManager)
    monkeypatch.setattr(main, "resolve_application_icon", lambda _window: QIcon())
    monkeypatch.setattr(
        main.UtilityControlApp,
        "_current_external_drives",
        lambda _self: set(),
    )
    monkeypatch.setattr(
        main.UtilityControlApp,
        "_set_main_window_topmost_state",
        lambda _self, _enabled: None,
    )
    monkeypatch.setattr(
        main.UtilityControlApp,
        "_apply_fixed_window_style",
        lambda _self: None,
    )
    monkeypatch.setattr(
        main.UtilityControlApp,
        "_register_session_notifications",
        lambda _self: None,
    )
    monkeypatch.setattr(
        main.UtilityControlApp,
        "run_recycle_bin_auto_cleanup",
        lambda _self: None,
    )

    window = main.UtilityControlApp()
    try:
        assert window.screen_mover_enabled_btn.isChecked()
        assert window.screen_move_button_combo.currentData() == "right"
        assert set(window.screen_mover_hotkey_edits) == {
            "FAR_LEFT",
            "LEFT",
            "RIGHT",
            "FAR_RIGHT",
            "MINIMIZE",
            "MAXIMIZE",
        }
        assert (
            window.screen_mover_hotkey_edits["LEFT"].keySequence().toString()
            == QKeySequence("Ctrl+Left").toString()
        )

        window.state["desktop_screenshot_last_dir"] = "unchanged"
        window.reset_screen_mover_settings()

        assert window.state["desktop_screenshot_last_dir"] == "unchanged"
        assert window.screen_move_button_combo.currentData() == "middle"
        assert all(
            edit.keySequence().isEmpty()
            for edit in window.screen_mover_hotkey_edits.values()
        )
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()

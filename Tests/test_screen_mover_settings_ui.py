import copy

import main
from PySide6.QtCore import Qt
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


def _build_offscreen_window(monkeypatch, state, *, window_height=None):
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
    if window_height is not None:
        monkeypatch.setattr(
            main.UtilityControlApp,
            "_resolve_window_height",
            lambda _self: window_height,
        )
    return main.UtilityControlApp()


def test_window_height_resolver_uses_preferred_or_available_work_area():
    resolver = main.UtilityControlApp._height_for_available_height

    assert main.UtilityControlApp.PREFERRED_WINDOW_HEIGHT == 1180
    assert resolver(None) == 1180
    assert resolver(1440) == 1180
    assert resolver(1180) == 1180
    assert resolver(900) == 900


def test_window_height_resolver_reads_screen_available_geometry():
    class FakeGeometry:
        def __init__(self, height):
            self._height = height

        def height(self):
            return self._height

    class FakeScreen:
        def __init__(self, height):
            self._geometry = FakeGeometry(height)

        def availableGeometry(self):
            return self._geometry

    class HeightResolverWindow:
        def __init__(self, height):
            self._screen = FakeScreen(height)

        def screen(self):
            return self._screen

        @staticmethod
        def _height_for_available_height(available_height):
            return main.UtilityControlApp._height_for_available_height(available_height)

    assert main.UtilityControlApp._resolve_window_height(HeightResolverWindow(1440)) == 1180
    assert main.UtilityControlApp._resolve_window_height(HeightResolverWindow(900)) == 900


def test_left_panel_scrollbar_policy_tracks_available_height(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    tall_window = _build_offscreen_window(monkeypatch, state, window_height=1180)

    try:
        assert tall_window.main_scroll.verticalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
    finally:
        tall_window._quit_requested = True
        tall_window.close()
        tall_window.deleteLater()
        qt_app.processEvents()

    constrained_window = _build_offscreen_window(monkeypatch, state, window_height=800)
    try:
        assert constrained_window.main_scroll.verticalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
    finally:
        constrained_window._quit_requested = True
        constrained_window.close()
        constrained_window.deleteLater()
        qt_app.processEvents()


def test_borderless_title_bar_controls_preserve_window_lifecycle(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    minimize_calls = []
    monkeypatch.setattr(
        main.UtilityControlApp,
        "showMinimized",
        lambda window: minimize_calls.append(window),
    )
    window = _build_offscreen_window(monkeypatch, state)

    try:
        assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert window.window_title_label.text() == "Windows Resurface"
        assert window.master_collapse_btn_left.parent() is window.window_title_bar
        assert window.window_minimize_btn.parent() is window.window_title_bar
        assert window.window_close_btn.parent() is window.window_title_bar
        assert not window.window_minimize_btn.icon().isNull()
        assert not window.window_close_btn.icon().isNull()

        left_states = copy.deepcopy(window.state["left_section_states"])
        window.window_minimize_btn.click()
        assert minimize_calls == [window]

        window.apply_theme(False)
        assert "font-size: 18px" in window.window_minimize_btn.styleSheet()
        assert "font-size: 18px" in window.window_close_btn.styleSheet()
        assert window.state["left_section_states"] == left_states

        window.show()
        qt_app.processEvents()
        window.window_close_btn.click()
        qt_app.processEvents()
        assert not window.isVisible()

        shutdown_calls = []
        window.prepare_for_shutdown = lambda: shutdown_calls.append(True)
        window._quit_requested = True
        window.show()
        window.window_close_btn.click()
        assert shutdown_calls == [True]
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


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

    window = _build_offscreen_window(monkeypatch, state)
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
        assert not window.screen_mover_shortcuts_container.isHidden()

        window.screen_mover_shortcuts_toggle_btn.click()
        assert window.screen_mover_shortcuts_container.isHidden()
        assert window.state["screen_mover_keyboard_shortcuts_open"] is False
        assert window.screen_mover_shortcuts_toggle_btn.text() == "▲"

        screen_section = next(
            section
            for section in window.left_sections
            if section.section_id == "screen_mover"
        )
        window._set_left_section_open(screen_section, False)
        window._set_left_section_open(screen_section, True)
        assert window.screen_mover_shortcuts_container.isHidden()

        window.screen_mover_shortcuts_toggle_btn.click()
        assert not window.screen_mover_shortcuts_container.isHidden()
        assert window.state["screen_mover_keyboard_shortcuts_open"] is True
        assert window.screen_mover_shortcuts_toggle_btn.text() == "▼"

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


def test_screen_mover_shortcuts_restore_collapsed_state_offscreen(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["screen_mover_keyboard_shortcuts_open"] = False
    window = _build_offscreen_window(monkeypatch, state)

    try:
        assert window.screen_mover_shortcuts_container.isHidden()
        assert window.screen_mover_shortcuts_toggle_btn.text() == "▲"
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()

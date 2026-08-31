"""Controllers for feature settings coordinated by the application window."""

from __future__ import annotations

from collections.abc import Callable

from resurface.features.monitor_rules import normalize_monitor_rules
from resurface.features.screen_mover.hotkeys import VALID_ACTIONS, active_hotkeys
from resurface.features.screen_mover.window_actions import perform_window_action


class ScreenMoverSettingsController:
    def __init__(
        self,
        *,
        state: dict,
        screen_mover,
        hotkey_manager,
        save_state: Callable[[dict], None],
        window_handle: Callable[[], int],
        settings_page: Callable[[], object | None],
        legacy_toggle: Callable[[], object | None],
        legacy_activation_combo: Callable[[], object | None],
        legacy_hotkey_edits: Callable[[], dict],
        refresh_overview: Callable[[], None],
        sync_tray: Callable[[], None],
        perform_action: Callable[[int, str], None] = perform_window_action,
    ) -> None:
        self.state = state
        self.screen_mover = screen_mover
        self.hotkey_manager = hotkey_manager
        self._save_state = save_state
        self._window_handle = window_handle
        self._perform_window_action = perform_action
        self._settings_page = settings_page
        self._legacy_toggle = legacy_toggle
        self._legacy_activation_combo = legacy_activation_combo
        self._legacy_hotkey_edits = legacy_hotkey_edits
        self._refresh_overview = refresh_overview
        self._sync_tray = sync_tray

    def apply_settings(self) -> None:
        enabled = bool(self.state.get("title_bar_dock_enabled", True))
        hotkeys = active_hotkeys(
            self.state.get("screen_mover_keyboard_hotkeys", {})
        )
        activation_button = (
            self.state.get("screen_mover_activation_button", "middle")
            if enabled
            else "off"
        )

        self.screen_mover.update_settings(
            title_bar_dock_enabled=enabled,
            activation_button=activation_button,
            force_running=enabled and bool(hotkeys),
        )
        self.hotkey_manager.update_hotkeys(hotkeys, enabled=enabled)
        self._sync_tray()

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.state["title_bar_dock_enabled"] = enabled
        page = self._settings_page()
        if page is not None:
            page.set_enabled(enabled)
        else:
            toggle = self._legacy_toggle()
            if toggle is not None and toggle.isChecked() != enabled:
                toggle.blockSignals(True)
                toggle.setChecked(enabled)
                toggle.blockSignals(False)
                toggle.setText("Screen Mover On" if enabled else "Screen Mover Off")

        self._save_state(self.state)
        self.apply_settings()
        self._refresh_overview()

    def reset_settings(self) -> None:
        page = self._settings_page()
        if page is not None:
            page.reset_settings()
            return

        self.state["title_bar_dock_enabled"] = True
        self.state["screen_mover_activation_button"] = "middle"
        self.state["mmb_activation_enabled"] = True
        self.state["screen_mover_keyboard_hotkeys"] = {
            action: "" for action in VALID_ACTIONS
        }

        combo = self._legacy_activation_combo()
        if combo is not None:
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData("middle"))
            combo.blockSignals(False)
            combo.setProperty("persistPressed", True)
            combo.style().unpolish(combo)
            combo.style().polish(combo)
        for edit in self._legacy_hotkey_edits().values():
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)

        self.set_enabled(True)

    def handle_self_action(self, action: str) -> None:
        if action == "MAXIMIZE":
            return

        hwnd = int(self._window_handle())
        if not hwnd:
            return

        try:
            self._perform_window_action(hwnd, action)
        except Exception as exc:
            print(f"[SCREEN_MOVER] Failed self-window action {action}: {exc}")


class MonitorRulesController:
    def __init__(
        self,
        *,
        state: dict,
        watcher,
        save_state: Callable[[dict], None],
        window_handle: Callable[[], int],
        rules_page: Callable[[], object | None],
        sync_tray: Callable[[], None],
    ) -> None:
        self.state = state
        self.watcher = watcher
        self._save_state = save_state
        self._window_handle = window_handle
        self._rules_page = rules_page
        self._sync_tray = sync_tray

    def apply_settings(self, *, apply_existing: bool = False) -> None:
        self.watcher.update_rules(
            self.state.get("monitor_rules", []),
            app_hwnd=int(self._window_handle()),
            apply_existing=apply_existing,
        )

    def set_rules(self, rules) -> None:
        self.state["monitor_rules"] = normalize_monitor_rules(rules)
        self._save_state(self.state)
        self.apply_settings()
        self._sync_tray()

    def set_enabled(self, enabled: bool) -> None:
        page = self._rules_page()
        if page is not None:
            page.set_all_enabled(enabled)
            return

        rules = normalize_monitor_rules(self.state.get("monitor_rules", []))
        for rule in rules:
            rule["enabled"] = bool(enabled)
        self.set_rules(rules)

"""Controllers for feature settings coordinated by the application window."""

from __future__ import annotations

from collections.abc import Callable

from resurface.features.monitor_rules import normalize_monitor_rules
from resurface.features.screen_mover.hotkeys import VALID_ACTIONS, active_hotkeys


class ScreenMoverSettingsController:
    def __init__(
        self,
        *,
        state: dict,
        hotkey_manager,
        save_state: Callable[[dict], None],
        settings_page: Callable[[], object | None],
        legacy_hotkey_edits: Callable[[], dict],
        refresh_overview: Callable[[], None],
    ) -> None:
        self.state = state
        self.hotkey_manager = hotkey_manager
        self._save_state = save_state
        self._settings_page = settings_page
        self._legacy_hotkey_edits = legacy_hotkey_edits
        self._refresh_overview = refresh_overview

    def apply_settings(self) -> None:
        hotkeys = active_hotkeys(
            self.state.get("screen_mover_keyboard_hotkeys", {})
        )
        self.hotkey_manager.update_hotkeys(hotkeys)

    def reset_settings(self) -> None:
        page = self._settings_page()
        if page is not None:
            page.reset_settings()
            return

        self.state["screen_mover_keyboard_hotkeys"] = {
            action: "" for action in VALID_ACTIONS
        }

        for edit in self._legacy_hotkey_edits().values():
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)

        self._save_state(self.state)
        self.apply_settings()
        self._refresh_overview()


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

    def apply_settings(self, *, apply_existing: bool = False, apply_rule_ids=None) -> None:
        options = {} if apply_rule_ids is None else {"apply_rule_ids": apply_rule_ids}
        self.watcher.update_rules(
            self.state.get("monitor_rules", []),
            app_hwnd=int(self._window_handle()),
            apply_existing=apply_existing,
            **options,
        )

    def set_rules(self, rules, *, apply_rule_ids=None) -> None:
        self.state["monitor_rules"] = normalize_monitor_rules(rules)
        self._save_state(self.state)
        self.apply_settings(apply_rule_ids=apply_rule_ids)
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

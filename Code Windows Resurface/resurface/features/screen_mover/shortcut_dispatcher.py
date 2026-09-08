"""Event-driven foreground-window actions for Screen Mover shortcuts."""

from __future__ import annotations

from collections.abc import Callable

import win32gui

from resurface.features.screen_mover import window_filter
from resurface.features.screen_mover.window_actions import (
    MONITOR_MOVE_ACTIONS,
    WINDOW_ACTIONS,
    perform_window_action,
    window_is_fullscreen,
)


class ShortcutActionDispatcher:
    """Resolve and act on the foreground window only when a hotkey is pressed."""

    def __init__(
        self,
        *,
        app_hwnd: Callable[[], int],
        manual_move_callback: Callable[[int], None] | None = None,
        perform_action: Callable[[int, str], bool] = perform_window_action,
    ) -> None:
        self._app_hwnd = app_hwnd
        self._manual_move_callback = manual_move_callback
        self._perform_action = perform_action

    def request_action(self, action: str) -> bool:
        action = str(action or "").strip().upper()
        if action not in WINDOW_ACTIONS:
            return False

        hwnd = self._foreground_target()
        if not hwnd:
            return False
        if hwnd == int(self._app_hwnd()) and action == "MAXIMIZE":
            return False

        try:
            succeeded = bool(self._perform_action(hwnd, action))
        except Exception as exc:
            print(f"[SCREEN_MOVER] Failed shortcut action {action}: {exc}")
            return False

        if (
            succeeded
            and action in MONITOR_MOVE_ACTIONS
            and callable(self._manual_move_callback)
        ):
            self._manual_move_callback(hwnd)
        return succeeded

    def _foreground_target(self) -> int | None:
        try:
            hwnd = window_filter.get_root_window(win32gui.GetForegroundWindow())
        except Exception:
            return None
        if not hwnd:
            return None

        app_hwnd = int(self._app_hwnd())
        try:
            rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            rect = None
        if window_is_fullscreen(hwnd, rect):
            return None
        if window_filter.is_self_window_eligible(hwnd, app_hwnd):
            return hwnd
        if window_filter.is_window_eligible(hwnd, app_hwnd=app_hwnd):
            return hwnd
        return None

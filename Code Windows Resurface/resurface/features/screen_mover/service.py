"""Threaded Screen Mover service and command orchestration."""

from __future__ import annotations

import queue
import threading
import time
import traceback
from typing import Callable

from pynput import mouse

import win32api
import win32con
import win32gui

from resurface.core.state_manager import load_state
from resurface.features.screen_mover import window_filter
from resurface.features.screen_mover.dock_icons import DOCK_WIDTH
from resurface.features.screen_mover.dock_overlay import (
    TITLE_BAR_BUTTON_GAP,
    TITLE_BAR_SIDE_MARGIN,
    DockOverlayButton,
    _dock_left_for_target,
)
from resurface.features.screen_mover.window_actions import (
    DOCK_ACTIONS_DICT,
    get_visible_dock_actions,
    perform_window_action,
    window_is_fullscreen,
)


LOOP_SLEEP = 0.03
WINDOW_MOVE_SETTLE_SECONDS = 0.2


class ScreenMover:
    def __init__(
        self,
        *,
        name="ScreenMoverWorker",
        app_hwnd=None,
        self_action_dispatch: Callable[[str], None] | None = None,
    ):
        self.name = str(name).strip() or "ScreenMoverWorker"
        self.dock_overlay = DockOverlayButton(self, overlay_name=self.name)
        self.thread = None
        self.mouse_listener = None
        self.lock = threading.Lock()
        self.command_queue: queue.Queue[tuple[str, tuple]] = queue.Queue()
        self.stop_event = threading.Event()

        self.title_bar_dock_enabled = True
        self.activation_button = "middle"
        self.force_running = False
        self._desired_title_bar_dock_enabled = True
        self._desired_activation_button = "middle"
        self._desired_force_running = False
        self.app_hwnd = app_hwnd
        self.self_action_dispatch = self_action_dispatch
        self._last_title_bar_hwnd = None
        self._last_title_bar_rect = None
        self._suppress_dock_until = 0.0

    def configure(self, *, app_hwnd=None, self_action_dispatch=None, settings=None):
        state = settings or load_state()
        with self.lock:
            if app_hwnd is not None:
                self.app_hwnd = app_hwnd
            if self_action_dispatch is not None:
                self.self_action_dispatch = self_action_dispatch
            self._desired_activation_button = self._load_activation_button(state)
            self._desired_title_bar_dock_enabled = bool(
                state.get("title_bar_dock_enabled", True)
            )

    def refresh_from_state(self):
        state = load_state()
        self.update_settings(
            title_bar_dock_enabled=bool(state.get("title_bar_dock_enabled", True)),
            activation_button=self._load_activation_button(state),
        )

    def update_settings(
        self,
        *,
        title_bar_dock_enabled=None,
        activation_button=None,
        force_running=None,
    ):
        with self.lock:
            if title_bar_dock_enabled is not None:
                self._desired_title_bar_dock_enabled = bool(title_bar_dock_enabled)
            if activation_button is not None:
                self._desired_activation_button = self._normalize_activation_button(
                    activation_button
                )
            if force_running is not None:
                self._desired_force_running = bool(force_running)

            desired_dock = self._desired_title_bar_dock_enabled
            desired_button = self._desired_activation_button
            desired_force = self._desired_force_running
            thread = self.thread
            thread_alive = bool(thread and thread.is_alive())

        should_run = self._service_enabled(desired_dock, desired_button, desired_force)
        if should_run:
            if thread_alive:
                self._queue_command(
                    "settings",
                    desired_dock,
                    desired_button,
                    desired_force,
                )
            else:
                self.start()
            return

        if thread_alive:
            self._queue_command(
                "settings",
                desired_dock,
                desired_button,
                desired_force,
            )
        self.stop()

    def request_click(self, x, y, button):
        with self.lock:
            thread = self.thread
            thread_alive = bool(thread and thread.is_alive())

        if thread_alive:
            self._queue_command("click", x, y, button)

    def request_action(self, action):
        action_value = str(action or "").strip().upper()
        if action_value not in DOCK_ACTIONS_DICT:
            return

        with self.lock:
            thread = self.thread
            thread_alive = bool(thread and thread.is_alive())

        if thread_alive:
            self._queue_command("action", action_value)

    def _normalize_activation_button(self, button) -> str:
        button_value = str(button).strip().lower()
        if button_value in {"left", "middle", "right", "off"}:
            return button_value
        return "middle"

    def _service_enabled(
        self,
        title_bar_dock_enabled,
        activation_button,
        force_running=False,
    ) -> bool:
        return (
            bool(force_running)
            or bool(title_bar_dock_enabled)
            or activation_button != "off"
        )

    def _load_activation_button(self, state):
        button = str(state.get("screen_mover_activation_button", "")).strip().lower()
        if button in {"left", "middle", "right", "off"}:
            return button

        if "mmb_activation_enabled" in state:
            return "middle" if bool(state.get("mmb_activation_enabled", True)) else "off"

        return "middle"

    def _activation_button_matches(self, button) -> bool:
        mapping = {
            "left": mouse.Button.left,
            "middle": mouse.Button.middle,
            "right": mouse.Button.right,
        }
        expected = mapping.get(self.activation_button)
        return expected is not None and button == expected

    def _queue_command(self, command, *payload):
        self.command_queue.put((command, payload))

    def _pump_messages(self):
        try:
            win32gui.PumpWaitingMessages()
        except Exception:
            pass

    def _get_window_exe(self, hwnd):
        return window_filter.get_window_executable_name(hwnd)

    def _is_steam_game_window(self, hwnd):
        return window_filter.is_steam_game_window(hwnd)

    def _is_file_explorer_window(self, hwnd):
        return window_filter.is_file_explorer_window(hwnd)

    def _is_system_window(self, hwnd):
        return window_filter.is_system_window(
            hwnd,
            executable_name_getter=self._get_window_exe,
            file_explorer_check=self._is_file_explorer_window,
        )

    def _is_owned_by_app(self, hwnd):
        return window_filter.is_owned_by_app(hwnd, self.app_hwnd)

    def _is_window_eligible(self, hwnd):
        return window_filter.is_window_eligible(
            hwnd,
            app_hwnd=self.app_hwnd,
            dock_hwnd=self.dock_overlay.hwnd,
            owned_by_app_check=self._is_owned_by_app,
            system_window_check=self._is_system_window,
        )

    def _is_window_fullscreen(self, hwnd, rect=None):
        return window_is_fullscreen(hwnd, rect)

    def _is_self_window_eligible(self, hwnd):
        return window_filter.is_self_window_eligible(hwnd, self.app_hwnd)

    def _get_root_window(self, hwnd):
        return window_filter.get_root_window(hwnd)

    def _get_caption_height(self):
        return (
            win32api.GetSystemMetrics(win32con.SM_CYCAPTION)
            + win32api.GetSystemMetrics(win32con.SM_CYFRAME)
            + 8
        )

    def _is_left_button_pressed(self):
        try:
            return bool(win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000)
        except Exception:
            return False

    def _reset_title_bar_tracking(self):
        self._last_title_bar_hwnd = None
        self._last_title_bar_rect = None
        self._suppress_dock_until = 0.0

    def _track_title_bar_motion(self, hwnd, rect):
        now = time.monotonic()

        if hwnd != self._last_title_bar_hwnd:
            self._last_title_bar_hwnd = hwnd
            self._last_title_bar_rect = rect
            return False

        if rect != self._last_title_bar_rect:
            self._last_title_bar_rect = rect
            self._suppress_dock_until = now + WINDOW_MOVE_SETTLE_SECONDS
            return True

        return now < self._suppress_dock_until

    def _title_bar_candidate(self):
        try:
            cursor_x, cursor_y = win32gui.GetCursorPos()
            if self.dock_overlay.contains_point(cursor_x, cursor_y):
                hwnd = self.dock_overlay.target_hwnd
                rect = win32gui.GetWindowRect(hwnd)
                if self._is_window_fullscreen(hwnd, rect):
                    return None, None
                return hwnd, rect

            raw_hwnd = win32gui.WindowFromPoint((cursor_x, cursor_y))
        except Exception:
            return None, None

        hwnd = self._get_root_window(raw_hwnd)
        try:
            rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            return None, None

        left, top, right, _ = rect
        width = right - left
        if width < (TITLE_BAR_SIDE_MARGIN * 2) + DOCK_WIDTH:
            return None, None

        caption_bottom = top + self._get_caption_height()
        if not (top <= cursor_y <= caption_bottom):
            return None, None

        dock_left = _dock_left_for_target(hwnd, rect, self.app_hwnd)
        if not (dock_left <= cursor_x < dock_left + DOCK_WIDTH):
            return None, None

        if cursor_x > right - TITLE_BAR_BUTTON_GAP:
            return None, None

        if not (self._is_window_eligible(hwnd) or self._is_self_window_eligible(hwnd)):
            return None, None
        if self._is_steam_game_window(hwnd):
            return None, None

        if self._is_window_fullscreen(hwnd, rect):
            return None, None

        if self._is_left_button_pressed():
            self._last_title_bar_hwnd = hwnd
            self._last_title_bar_rect = rect
            self._suppress_dock_until = time.monotonic() + WINDOW_MOVE_SETTLE_SECONDS
            return None, None

        if self._track_title_bar_motion(hwnd, rect):
            return None, None

        return hwnd, rect

    def _update_title_bar_dock(self):
        if not self.title_bar_dock_enabled:
            self.dock_overlay.hide()
            return

        hwnd, rect = self._title_bar_candidate()
        if not hwnd:
            self.dock_overlay.hide()
            return

        self.dock_overlay.show_for_target(
            hwnd,
            rect,
            self._visible_dock_actions(hwnd),
        )

    def _visible_dock_actions(self, hwnd):
        visible_actions = get_visible_dock_actions(hwnd)
        if hwnd == self.app_hwnd:
            return tuple(action for action in visible_actions if action != "MAXIMIZE")
        return visible_actions

    def _apply_settings(
        self,
        title_bar_dock_enabled,
        activation_button,
        force_running=False,
    ):
        self.title_bar_dock_enabled = bool(title_bar_dock_enabled)
        self.activation_button = self._normalize_activation_button(activation_button)
        self.force_running = bool(force_running)
        self._reset_title_bar_tracking()
        if not self.title_bar_dock_enabled:
            self.dock_overlay.hide()

    def _handle_click(self, x, y, button):
        if self.activation_button == "off" or not self._activation_button_matches(button):
            return

        direction = self.dock_overlay.hit_test(x, y)
        target = self.dock_overlay.target_hwnd
        if not direction or not target:
            return

        self.dock_overlay.hide()
        self._dispatch_window_action(target, direction)

    def _handle_action(self, action):
        target = self._foreground_action_target()
        if not target:
            return
        self._dispatch_window_action(target, action)

    def _foreground_action_target(self):
        try:
            hwnd = win32gui.GetForegroundWindow()
        except Exception:
            return None

        hwnd = self._get_root_window(hwnd)
        if not hwnd or hwnd == self.dock_overlay.hwnd:
            return None

        try:
            rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            rect = None

        if self._is_window_fullscreen(hwnd, rect):
            return None

        if self._is_window_eligible(hwnd) or self._is_self_window_eligible(hwnd):
            return hwnd
        return None

    def _dispatch_window_action(self, target_hwnd, action):
        if target_hwnd == self.app_hwnd:
            if action == "MAXIMIZE":
                return
            if callable(self.self_action_dispatch):
                try:
                    self.self_action_dispatch(action)
                except Exception as exc:
                    print(f"[SCREEN_MOVER] Failed to dispatch self action {action}: {exc}")
            else:
                print(
                    f"[SCREEN_MOVER] Missing GUI dispatch for self action {action}; ignoring."
                )
            return

        if not self._is_window_eligible(target_hwnd):
            return

        perform_window_action(target_hwnd, action)

    def _drain_command_queue(self):
        while True:
            try:
                command, payload = self.command_queue.get_nowait()
            except queue.Empty:
                return

            if command == "settings":
                self._apply_settings(*payload)
            elif command == "click":
                self._handle_click(*payload)
            elif command == "action":
                self._handle_action(*payload)
            elif command == "stop":
                self.stop_event.set()

    def worker_loop(self):
        print("[THREAD] Screen mover loop started.")

        with self.lock:
            desired_dock = self._desired_title_bar_dock_enabled
            desired_button = self._desired_activation_button
            desired_force = self._desired_force_running

        self._apply_settings(desired_dock, desired_button, desired_force)
        try:
            self.dock_overlay.preload_icons()
        except Exception as exc:
            print(f"[DOCK] Failed to preload dock icons: {exc}")

        try:
            while not self.stop_event.is_set():
                self._pump_messages()
                self._drain_command_queue()
                if self.stop_event.is_set():
                    break
                self._update_title_bar_dock()
                time.sleep(LOOP_SLEEP)
        except Exception as exc:
            print(f"[THREAD] Screen mover loop crashed: {exc}")
            traceback.print_exc()
        finally:
            try:
                self.dock_overlay.hide()
            except Exception as exc:
                print(f"[DOCK] Failed to hide overlay during shutdown: {exc}")

            try:
                self.dock_overlay.destroy()
            except Exception as exc:
                print(f"[DOCK] Failed to destroy overlay during shutdown: {exc}")

            with self.lock:
                if threading.current_thread() is self.thread:
                    self.thread = None

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return

            if not self._service_enabled(
                self._desired_title_bar_dock_enabled,
                self._desired_activation_button,
                self._desired_force_running,
            ):
                return

            self.stop_event = threading.Event()
            self.command_queue = queue.Queue()
            self.thread = threading.Thread(
                target=self.worker_loop,
                name=self.name,
                daemon=True,
            )
            self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
            thread = self.thread
            listener = self.mouse_listener

        thread.start()
        try:
            listener.start()
        except Exception as exc:
            print(f"[SCREEN_MOVER] Failed to start mouse listener: {exc}")
            self.stop()

    def stop(self):
        with self.lock:
            thread = self.thread
            thread_alive = bool(thread and thread.is_alive())
            listener = self.mouse_listener
            self.mouse_listener = None

            if not thread_alive:
                self.thread = None
            else:
                self.stop_event.set()
                self._queue_command("stop")

        if listener:
            try:
                listener.stop()
            except Exception as exc:
                print(f"[SCREEN_MOVER] Failed to stop mouse listener: {exc}")

        if thread_alive and thread is not None:
            thread.join(timeout=1.0)
            if thread.is_alive():
                print("[SCREEN_MOVER] Worker thread did not exit within 1.0s.")

    def on_mouse_click(self, x, y, button, pressed):
        if not pressed:
            return
        self.request_click(x, y, button)


ScreenMoverWorker = ScreenMover
SCREEN_MOVER = ScreenMover()

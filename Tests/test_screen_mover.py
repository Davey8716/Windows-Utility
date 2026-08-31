import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from resurface.features.screen_mover import (
    service,
    window_filter,
)


def wait_until(predicate, timeout=1.5, interval=0.01):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class FakeListener:
    instances = []

    def __init__(self, on_click):
        self.on_click = on_click
        self.started = False
        self.stopped = False
        type(self).instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FakeOverlay:
    def __init__(self, target_hwnd=None, direction=None):
        self.target_hwnd = target_hwnd
        self.rect = (0, 0, 10, 10)
        self.visible = True
        self.direction = direction
        self.hit_test_threads = []
        self.hide_threads = []
        self.destroy_threads = []

    def hit_test(self, x, y):
        self.hit_test_threads.append(threading.current_thread().name)
        return self.direction

    def contains_point(self, x, y):
        return bool(self.rect)

    def hide(self):
        self.hide_threads.append(threading.current_thread().name)
        self.target_hwnd = None
        self.rect = None
        self.visible = False

    def destroy(self):
        self.destroy_threads.append(threading.current_thread().name)


def test_steam_game_window_is_not_a_title_bar_candidate():
    mover = service.ScreenMover.__new__(service.ScreenMover)
    mover.app_hwnd = None
    mover.dock_overlay = SimpleNamespace(contains_point=lambda _x, _y: False)
    mover._get_root_window = Mock(return_value=123)
    mover._get_caption_height = Mock(return_value=30)
    mover._is_window_eligible = Mock(return_value=True)
    mover._is_self_window_eligible = Mock(return_value=False)
    mover._is_steam_game_window = Mock(return_value=True)
    mover._is_window_fullscreen = Mock()

    with (
        patch.object(service.win32gui, "GetCursorPos", return_value=(350, 5)),
        patch.object(service.win32gui, "WindowFromPoint", return_value=123),
        patch.object(
            service.win32gui,
            "GetWindowRect",
            return_value=(0, 0, 800, 600),
        ),
    ):
        assert mover._title_bar_candidate() == (None, None)

    mover._is_steam_game_window.assert_called_once_with(123)
    mover._is_window_fullscreen.assert_not_called()


def test_hovering_existing_dock_does_not_repeat_process_classification():
    mover = service.ScreenMover.__new__(service.ScreenMover)
    mover.dock_overlay = SimpleNamespace(
        contains_point=lambda _x, _y: True,
        target_hwnd=123,
    )
    mover._is_steam_game_window = Mock()
    mover._is_window_fullscreen = Mock(return_value=False)

    with (
        patch.object(service.win32gui, "GetCursorPos", return_value=(100, 100)),
        patch.object(service.win32gui, "GetWindowRect", return_value=(0, 0, 800, 600)),
        patch.object(service.win32gui, "WindowFromPoint") as window_from_point,
    ):
        assert mover._title_bar_candidate() == (123, (0, 0, 800, 600))

    mover._is_steam_game_window.assert_not_called()
    window_from_point.assert_not_called()


@pytest.mark.parametrize("cursor_x", [309, 490])
def test_cursor_outside_dock_span_skips_expensive_candidate_checks(cursor_x):
    mover = service.ScreenMover.__new__(service.ScreenMover)
    mover.app_hwnd = None
    mover.dock_overlay = SimpleNamespace(contains_point=lambda _x, _y: False)
    mover._get_root_window = Mock(return_value=123)
    mover._get_caption_height = Mock(return_value=30)
    mover._is_window_eligible = Mock()
    mover._is_self_window_eligible = Mock()
    mover._is_steam_game_window = Mock()
    mover._is_window_fullscreen = Mock()

    with (
        patch.object(service.win32gui, "GetCursorPos", return_value=(cursor_x, 5)),
        patch.object(service.win32gui, "WindowFromPoint", return_value=123),
        patch.object(
            service.win32gui,
            "GetWindowRect",
            return_value=(0, 0, 800, 600),
        ),
    ):
        assert mover._title_bar_candidate() == (None, None)

    mover._is_window_eligible.assert_not_called()
    mover._is_self_window_eligible.assert_not_called()
    mover._is_steam_game_window.assert_not_called()
    mover._is_window_fullscreen.assert_not_called()


@pytest.mark.parametrize(
    ("cursor_x", "expected"),
    [(310, True), (489, True), (490, False)],
)
def test_dock_span_uses_left_inclusive_right_exclusive_boundaries(cursor_x, expected):
    mover = service.ScreenMover.__new__(service.ScreenMover)
    mover.app_hwnd = None
    mover.dock_overlay = SimpleNamespace(contains_point=lambda _x, _y: False)
    mover._get_root_window = Mock(return_value=123)
    mover._get_caption_height = Mock(return_value=30)
    mover._is_window_eligible = Mock(return_value=True)
    mover._is_self_window_eligible = Mock(return_value=False)
    mover._is_steam_game_window = Mock(return_value=False)
    mover._is_window_fullscreen = Mock(return_value=False)
    mover._is_left_button_pressed = Mock(return_value=False)
    mover._track_title_bar_motion = Mock(return_value=False)

    with (
        patch.object(service.win32gui, "GetCursorPos", return_value=(cursor_x, 5)),
        patch.object(service.win32gui, "WindowFromPoint", return_value=123),
        patch.object(
            service.win32gui,
            "GetWindowRect",
            return_value=(0, 0, 800, 600),
        ),
    ):
        candidate, _rect = mover._title_bar_candidate()

    assert bool(candidate) is expected


def test_steam_detection_does_not_change_shared_window_eligibility():
    mover = service.ScreenMover.__new__(service.ScreenMover)
    mover.app_hwnd = 999
    mover.dock_overlay = SimpleNamespace(hwnd=998)
    mover._is_owned_by_app = Mock(return_value=False)
    mover._is_system_window = Mock(return_value=False)
    mover._is_steam_game_window = Mock(return_value=True)

    with (
        patch.object(window_filter.win32gui, "IsWindow", return_value=True),
        patch.object(window_filter.win32gui, "IsWindowVisible", return_value=True),
        patch.object(window_filter.win32gui, "GetWindowText", return_value="Steam Game"),
    ):
        assert mover._is_window_eligible(123)

    mover._is_steam_game_window.assert_not_called()


def test_screen_mover_clicks_are_processed_on_worker_thread(monkeypatch):
    FakeListener.instances = []
    monkeypatch.setattr(
        service,
        "load_state",
        lambda: {
            "title_bar_dock_enabled": True,
            "screen_mover_activation_button": "middle",
        },
    )
    monkeypatch.setattr(service.mouse, "Listener", FakeListener)

    external_actions = []
    monkeypatch.setattr(
        service,
        "perform_window_action",
        lambda hwnd, action: external_actions.append((hwnd, action)),
    )

    dispatch_calls = []
    dispatch_event = threading.Event()

    worker = service.ScreenMoverWorker()
    worker.dock_overlay = FakeOverlay(target_hwnd=101, direction="MINIMIZE")
    worker._pump_messages = lambda: None
    worker._update_title_bar_dock = lambda: None
    worker.configure(
        app_hwnd=101,
        self_action_dispatch=lambda action: (
            dispatch_calls.append((action, threading.current_thread().name)),
            dispatch_event.set(),
        ),
    )

    worker.start()
    assert FakeListener.instances and FakeListener.instances[0].started

    worker.on_mouse_click(5, 5, service.mouse.Button.middle, True)

    assert dispatch_event.wait(1.0)
    assert dispatch_calls == [("MINIMIZE", "ScreenMoverWorker")]
    assert worker.dock_overlay.hide_threads
    assert worker.dock_overlay.hide_threads[0] == "ScreenMoverWorker"
    assert external_actions == []

    worker.stop()
    assert wait_until(lambda: worker.thread is None)
    assert worker.dock_overlay.destroy_threads == ["ScreenMoverWorker"]


def test_screen_mover_stop_keeps_thread_reference_until_worker_exits(monkeypatch):
    FakeListener.instances = []
    monkeypatch.setattr(
        service,
        "load_state",
        lambda: {
            "title_bar_dock_enabled": True,
            "screen_mover_activation_button": "middle",
        },
    )
    monkeypatch.setattr(service.mouse, "Listener", FakeListener)

    entered_pump = threading.Event()
    allow_exit = threading.Event()

    worker = service.ScreenMoverWorker()
    worker.dock_overlay = FakeOverlay()

    def blocking_pump():
        entered_pump.set()
        allow_exit.wait(5.0)

    worker._pump_messages = blocking_pump
    worker._update_title_bar_dock = lambda: None
    worker.configure(app_hwnd=101, self_action_dispatch=lambda action: None)

    worker.start()
    assert entered_pump.wait(1.0)
    assert FakeListener.instances and FakeListener.instances[0].started

    thread_obj = worker.thread
    original_join = thread_obj.join
    thread_obj.join = lambda timeout=None: None

    worker.stop()

    assert FakeListener.instances[0].stopped
    assert worker.mouse_listener is None
    assert worker.thread is thread_obj
    assert worker.dock_overlay.destroy_threads == []

    thread_obj.join = original_join
    allow_exit.set()
    original_join(1.0)

    assert wait_until(lambda: worker.thread is None)
    assert worker.dock_overlay.destroy_threads == ["ScreenMoverWorker"]


def test_title_bar_candidate_rejects_fullscreen_window(monkeypatch):
    worker = service.ScreenMoverWorker()
    worker.dock_overlay = FakeOverlay(target_hwnd=None)
    worker.dock_overlay.visible = False

    monkeypatch.setattr(worker.dock_overlay, "contains_point", lambda x, y: False)
    monkeypatch.setattr(service.win32gui, "GetCursorPos", lambda: (900, 5))
    monkeypatch.setattr(service.win32gui, "WindowFromPoint", lambda point: 101)
    monkeypatch.setattr(worker, "_get_root_window", lambda hwnd: hwnd)
    monkeypatch.setattr(worker, "_is_window_eligible", lambda hwnd: True)
    monkeypatch.setattr(worker, "_is_self_window_eligible", lambda hwnd: False)
    monkeypatch.setattr(
        service.win32gui,
        "GetWindowRect",
        lambda hwnd: (0, 0, 1920, 1080),
    )
    monkeypatch.setattr(worker, "_is_window_fullscreen", lambda hwnd, rect=None: True)

    assert worker._title_bar_candidate() == (None, None)


def test_missing_title_bar_candidate_hides_visible_dock_immediately():
    mover = service.ScreenMover.__new__(service.ScreenMover)
    mover.title_bar_dock_enabled = True
    mover.dock_overlay = Mock()
    mover._title_bar_candidate = Mock(return_value=(None, None))

    mover._update_title_bar_dock()

    mover.dock_overlay.hide.assert_called_once_with()
    mover.dock_overlay.show_for_target.assert_not_called()


def test_self_window_maximize_is_suppressed():
    dispatched = []
    worker = service.ScreenMoverWorker(
        app_hwnd=101,
        self_action_dispatch=dispatched.append,
    )

    worker._dispatch_window_action(101, "MAXIMIZE")
    worker._dispatch_window_action(101, "MINIMIZE")

    assert dispatched == ["MINIMIZE"]
    assert "MAXIMIZE" not in worker._visible_dock_actions(101)


def test_hotkey_action_uses_foreground_target_and_worker_dispatch():
    worker = service.ScreenMoverWorker()
    dispatched = []
    worker._foreground_action_target = lambda: 202
    worker._dispatch_window_action = lambda hwnd, action: dispatched.append(
        (hwnd, action)
    )

    worker._handle_action("RIGHT")

    assert dispatched == [(202, "RIGHT")]


def test_force_running_keeps_worker_service_available_for_hotkeys():
    worker = service.ScreenMoverWorker()

    assert not worker._service_enabled(False, "off", False)
    assert worker._service_enabled(False, "off", True)


def test_legacy_middle_mouse_setting_remains_supported():
    worker = service.ScreenMoverWorker()

    assert worker._load_activation_button({"mmb_activation_enabled": True}) == (
        "middle"
    )
    assert worker._load_activation_button({"mmb_activation_enabled": False}) == "off"

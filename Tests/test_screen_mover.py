import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import screen_mover


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


@pytest.mark.parametrize(
    "executable_path",
    [
        r"C:\Program Files (x86)\Steam\steamapps\common\Portal 2\portal2.exe",
        r"D:\STEAMLIBRARY\SteamApps\Common\Game\bin\game.exe",
        "E:/SteamLibrary/steamapps/common/Game/game.exe",
    ],
)
def test_recognizes_steam_game_executable_paths(executable_path):
    assert screen_mover.is_steam_game_executable(executable_path)


@pytest.mark.parametrize(
    "executable_path",
    [
        None,
        "",
        r"C:\Program Files (x86)\Steam\steam.exe",
        r"C:\Games\steamapps\common\game.exe",
        r"C:\Games\notsteamapps\common\Game\game.exe",
        r"C:\Games\steamapps\commonplace\Game\game.exe",
        r"C:\Games\Game\game.exe",
    ],
)
def test_rejects_non_steam_game_executable_paths(executable_path):
    assert not screen_mover.is_steam_game_executable(executable_path)


def test_process_lookup_failure_does_not_classify_window_as_steam_game():
    mover = screen_mover.ScreenMover.__new__(screen_mover.ScreenMover)

    with patch.object(
        screen_mover.win32process,
        "GetWindowThreadProcessId",
        side_effect=OSError,
    ):
        assert not mover._is_steam_game_window(123)


def test_steam_game_window_is_not_a_title_bar_candidate():
    mover = screen_mover.ScreenMover.__new__(screen_mover.ScreenMover)
    mover.app_hwnd = None
    mover.dock_overlay = SimpleNamespace(contains_point=lambda _x, _y: False)
    mover._get_root_window = Mock(return_value=123)
    mover._get_caption_height = Mock(return_value=30)
    mover._is_window_eligible = Mock(return_value=True)
    mover._is_self_window_eligible = Mock(return_value=False)
    mover._is_steam_game_window = Mock(return_value=True)
    mover._is_window_fullscreen = Mock()

    with (
        patch.object(screen_mover.win32gui, "GetCursorPos", return_value=(350, 5)),
        patch.object(screen_mover.win32gui, "WindowFromPoint", return_value=123),
        patch.object(
            screen_mover.win32gui,
            "GetWindowRect",
            return_value=(0, 0, 800, 600),
        ),
    ):
        assert mover._title_bar_candidate() == (None, None)

    mover._is_steam_game_window.assert_called_once_with(123)
    mover._is_window_fullscreen.assert_not_called()


def test_hovering_existing_dock_does_not_repeat_process_classification():
    mover = screen_mover.ScreenMover.__new__(screen_mover.ScreenMover)
    mover.dock_overlay = SimpleNamespace(
        contains_point=lambda _x, _y: True,
        target_hwnd=123,
    )
    mover._is_steam_game_window = Mock()
    mover._is_window_fullscreen = Mock(return_value=False)

    with (
        patch.object(screen_mover.win32gui, "GetCursorPos", return_value=(100, 100)),
        patch.object(screen_mover.win32gui, "GetWindowRect", return_value=(0, 0, 800, 600)),
        patch.object(screen_mover.win32gui, "WindowFromPoint") as window_from_point,
    ):
        assert mover._title_bar_candidate() == (123, (0, 0, 800, 600))

    mover._is_steam_game_window.assert_not_called()
    window_from_point.assert_not_called()


@pytest.mark.parametrize("cursor_x", [309, 490])
def test_cursor_outside_dock_span_skips_expensive_candidate_checks(cursor_x):
    mover = screen_mover.ScreenMover.__new__(screen_mover.ScreenMover)
    mover.app_hwnd = None
    mover.dock_overlay = SimpleNamespace(contains_point=lambda _x, _y: False)
    mover._get_root_window = Mock(return_value=123)
    mover._get_caption_height = Mock(return_value=30)
    mover._is_window_eligible = Mock()
    mover._is_self_window_eligible = Mock()
    mover._is_steam_game_window = Mock()
    mover._is_window_fullscreen = Mock()

    with (
        patch.object(screen_mover.win32gui, "GetCursorPos", return_value=(cursor_x, 5)),
        patch.object(screen_mover.win32gui, "WindowFromPoint", return_value=123),
        patch.object(
            screen_mover.win32gui,
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
    mover = screen_mover.ScreenMover.__new__(screen_mover.ScreenMover)
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
        patch.object(screen_mover.win32gui, "GetCursorPos", return_value=(cursor_x, 5)),
        patch.object(screen_mover.win32gui, "WindowFromPoint", return_value=123),
        patch.object(
            screen_mover.win32gui,
            "GetWindowRect",
            return_value=(0, 0, 800, 600),
        ),
    ):
        candidate, _rect = mover._title_bar_candidate()

    assert bool(candidate) is expected


def test_steam_detection_does_not_change_shared_window_eligibility():
    mover = screen_mover.ScreenMover.__new__(screen_mover.ScreenMover)
    mover.app_hwnd = 999
    mover.dock_overlay = SimpleNamespace(hwnd=998)
    mover._is_owned_by_app = Mock(return_value=False)
    mover._is_system_window = Mock(return_value=False)
    mover._is_steam_game_window = Mock(return_value=True)

    with (
        patch.object(screen_mover.win32gui, "IsWindow", return_value=True),
        patch.object(screen_mover.win32gui, "IsWindowVisible", return_value=True),
        patch.object(screen_mover.win32gui, "GetWindowText", return_value="Steam Game"),
    ):
        assert mover._is_window_eligible(123)

    mover._is_steam_game_window.assert_not_called()


def test_screen_mover_clicks_are_processed_on_worker_thread(monkeypatch):
    FakeListener.instances = []
    monkeypatch.setattr(
        screen_mover,
        "load_state",
        lambda: {
            "title_bar_dock_enabled": True,
            "screen_mover_activation_button": "middle",
        },
    )
    monkeypatch.setattr(screen_mover.mouse, "Listener", FakeListener)

    external_actions = []
    monkeypatch.setattr(
        screen_mover,
        "perform_window_action",
        lambda hwnd, action: external_actions.append((hwnd, action)),
    )

    dispatch_calls = []
    dispatch_event = threading.Event()

    worker = screen_mover.ScreenMoverWorker()
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

    worker.on_mouse_click(5, 5, screen_mover.mouse.Button.middle, True)

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
        screen_mover,
        "load_state",
        lambda: {
            "title_bar_dock_enabled": True,
            "screen_mover_activation_button": "middle",
        },
    )
    monkeypatch.setattr(screen_mover.mouse, "Listener", FakeListener)

    entered_pump = threading.Event()
    allow_exit = threading.Event()

    worker = screen_mover.ScreenMoverWorker()
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


def test_visible_dock_actions_hide_left_actions_on_leftmost_monitor(monkeypatch):
    monkeypatch.setattr(
        screen_mover.win32api,
        "EnumDisplayMonitors",
        lambda: [(10, None, None), (20, None, None), (30, None, None)],
    )
    monkeypatch.setattr(screen_mover.win32api, "MonitorFromWindow", lambda hwnd: 10)

    assert screen_mover.get_visible_dock_actions(101) == (
        "RIGHT",
        "FAR_RIGHT",
        "MINIMIZE",
        "MAXIMIZE",
    )


def test_visible_dock_actions_hide_right_actions_on_rightmost_monitor(monkeypatch):
    monkeypatch.setattr(
        screen_mover.win32api,
        "EnumDisplayMonitors",
        lambda: [(10, None, None), (20, None, None), (30, None, None)],
    )
    monkeypatch.setattr(screen_mover.win32api, "MonitorFromWindow", lambda hwnd: 30)

    assert screen_mover.get_visible_dock_actions(101) == (
        "FAR_LEFT",
        "LEFT",
        "MINIMIZE",
        "MAXIMIZE",
    )


def test_visible_dock_actions_only_show_window_controls_on_single_monitor(monkeypatch):
    monkeypatch.setattr(
        screen_mover.win32api,
        "EnumDisplayMonitors",
        lambda: [(10, None, None)],
    )
    monkeypatch.setattr(screen_mover.win32api, "MonitorFromWindow", lambda hwnd: 10)

    assert screen_mover.get_visible_dock_actions(101) == (
        "MINIMIZE",
        "MAXIMIZE",
    )


def test_visible_dock_actions_hide_maximize_when_window_has_no_maximize_box(
    monkeypatch,
):
    monkeypatch.setattr(
        screen_mover.win32api,
        "EnumDisplayMonitors",
        lambda: [(10, None, None), (20, None, None)],
    )
    monkeypatch.setattr(screen_mover.win32api, "MonitorFromWindow", lambda hwnd: 10)
    monkeypatch.setattr(
        screen_mover.win32gui,
        "GetWindowLong",
        lambda hwnd, index: 0,
    )
    monkeypatch.setattr(screen_mover.win32gui, "IsWindow", lambda hwnd: True)

    assert screen_mover.get_visible_dock_actions(101) == (
        "RIGHT",
        "FAR_RIGHT",
        "MINIMIZE",
    )


def test_window_is_fullscreen_detects_monitor_covering_window(monkeypatch):
    monkeypatch.setattr(
        screen_mover.win32gui,
        "GetWindowPlacement",
        lambda hwnd: (
            0,
            screen_mover.win32con.SW_SHOWNORMAL,
            (0, 0),
            (0, 0),
            (0, 0, 0, 0),
        ),
    )
    monkeypatch.setattr(
        screen_mover.win32api,
        "MonitorFromWindow",
        lambda hwnd, flags=0: 10,
    )
    monkeypatch.setattr(
        screen_mover.win32api,
        "GetMonitorInfo",
        lambda monitor: {"Monitor": (0, 0, 1920, 1080)},
    )

    assert screen_mover.window_is_fullscreen(101, (0, 0, 1920, 1080))


def test_window_is_fullscreen_allows_maximized_windows(monkeypatch):
    monkeypatch.setattr(
        screen_mover.win32gui,
        "GetWindowPlacement",
        lambda hwnd: (
            0,
            screen_mover.win32con.SW_SHOWMAXIMIZED,
            (0, 0),
            (0, 0),
            (0, 0, 0, 0),
        ),
    )
    monkeypatch.setattr(
        screen_mover.win32api,
        "MonitorFromWindow",
        lambda hwnd, flags=0: 10,
    )
    monkeypatch.setattr(
        screen_mover.win32api,
        "GetMonitorInfo",
        lambda monitor: {"Monitor": (0, 0, 1920, 1080)},
    )

    assert not screen_mover.window_is_fullscreen(101, (0, 0, 1920, 1080))


def test_title_bar_candidate_rejects_fullscreen_window(monkeypatch):
    worker = screen_mover.ScreenMoverWorker()
    worker.dock_overlay = FakeOverlay(target_hwnd=None)
    worker.dock_overlay.visible = False

    monkeypatch.setattr(worker.dock_overlay, "contains_point", lambda x, y: False)
    monkeypatch.setattr(screen_mover.win32gui, "GetCursorPos", lambda: (900, 5))
    monkeypatch.setattr(screen_mover.win32gui, "WindowFromPoint", lambda point: 101)
    monkeypatch.setattr(worker, "_get_root_window", lambda hwnd: hwnd)
    monkeypatch.setattr(worker, "_is_window_eligible", lambda hwnd: True)
    monkeypatch.setattr(worker, "_is_self_window_eligible", lambda hwnd: False)
    monkeypatch.setattr(
        screen_mover.win32gui,
        "GetWindowRect",
        lambda hwnd: (0, 0, 1920, 1080),
    )
    monkeypatch.setattr(worker, "_is_window_fullscreen", lambda hwnd, rect=None: True)

    assert worker._title_bar_candidate() == (None, None)


def test_dock_left_uses_same_special_clearance_for_app_window():
    rect = (0, 0, 400, 300)

    assert screen_mover._dock_left_for_target(101, rect, app_hwnd=None) == 110
    assert screen_mover._dock_left_for_target(101, rect, app_hwnd=101) == 166


def test_missing_title_bar_candidate_hides_visible_dock_immediately():
    mover = screen_mover.ScreenMover.__new__(screen_mover.ScreenMover)
    mover.title_bar_dock_enabled = True
    mover.dock_overlay = Mock()
    mover._title_bar_candidate = Mock(return_value=(None, None))

    mover._update_title_bar_dock()

    mover.dock_overlay.hide.assert_called_once_with()
    mover.dock_overlay.show_for_target.assert_not_called()


def test_dock_overlay_hide_only_calls_windows_when_visible(monkeypatch):
    overlay = screen_mover.DockOverlayButton(worker=None, overlay_name="test")
    overlay.hwnd = 123
    overlay.target_hwnd = 101
    overlay.rect = (0, 0, 180, 30)
    overlay.visible = True
    show_window = Mock()
    monkeypatch.setattr(screen_mover.win32gui, "IsWindow", lambda hwnd: True)
    monkeypatch.setattr(screen_mover.win32gui, "ShowWindow", show_window)

    overlay.hide()
    overlay.hide()

    show_window.assert_called_once_with(123, screen_mover.win32con.SW_HIDE)
    assert overlay.visible is False
    assert overlay.target_hwnd is None
    assert overlay.rect is None


def test_dock_overlay_hit_test_only_uses_visible_actions():
    overlay = screen_mover.DockOverlayButton(worker=None, overlay_name="test")
    overlay.target_hwnd = 101
    overlay.rect = (0, 0, 180, 30)
    overlay.visible_actions = ("RIGHT", "FAR_RIGHT", "MINIMIZE", "MAXIMIZE")

    layout = overlay._action_layout(0, 180)
    assert [action for action, *_rest in layout] == list(overlay.visible_actions)

    left_gap_x = int(layout[0][3] - 1)
    assert overlay.hit_test(left_gap_x, 10) is None

    for action, _label, _center_x, seg_left, seg_right in layout:
        midpoint_x = int((seg_left + seg_right) / 2.0)
        assert overlay.hit_test(midpoint_x, 10) == action


def test_dock_overlay_keeps_actions_in_fixed_positions_when_actions_are_hidden():
    overlay = screen_mover.DockOverlayButton(worker=None, overlay_name="test")

    overlay.visible_actions = tuple(
        action for action, _label in screen_mover.DOCK_ACTIONS
    )
    full_layout = {
        action: center for action, _label, center, _left, _right in overlay._action_layout(0, 180)
    }

    overlay.visible_actions = ("RIGHT", "FAR_RIGHT", "MINIMIZE", "MAXIMIZE")
    reduced_layout = {
        action: center for action, _label, center, _left, _right in overlay._action_layout(0, 180)
    }

    assert reduced_layout == {
        action: full_layout[action] for action in overlay.visible_actions
    }


def test_dock_icon_theme_uses_contrast_with_hysteresis():
    assert screen_mover._dock_icon_theme_for_luminance(20) == "White"
    assert screen_mover._dock_icon_theme_for_luminance(240) == "Black"
    assert screen_mover._dock_icon_theme_for_luminance(150, "White") == "White"
    assert screen_mover._dock_icon_theme_for_luminance(150, "Black") == "Black"
    assert screen_mover._dock_icon_theme_for_luminance(None) == "Black"


def test_dock_icon_paths_include_windows_resurface_asset_tree():
    project_root = Path(screen_mover.__file__).resolve().parent.parent
    directories = screen_mover._dock_icon_directories("Black")

    assert project_root / "Icon Pngs" / "Black" in directories
    assert (project_root / "Icon Pngs" / "Black" / "Left.png").is_file()


def test_self_window_maximize_is_suppressed():
    dispatched = []
    worker = screen_mover.ScreenMoverWorker(
        app_hwnd=101,
        self_action_dispatch=dispatched.append,
    )

    worker._dispatch_window_action(101, "MAXIMIZE")
    worker._dispatch_window_action(101, "MINIMIZE")

    assert dispatched == ["MINIMIZE"]
    assert "MAXIMIZE" not in worker._visible_dock_actions(101)


def test_hotkey_action_uses_foreground_target_and_worker_dispatch():
    worker = screen_mover.ScreenMoverWorker()
    dispatched = []
    worker._foreground_action_target = lambda: 202
    worker._dispatch_window_action = lambda hwnd, action: dispatched.append(
        (hwnd, action)
    )

    worker._handle_action("RIGHT")

    assert dispatched == [(202, "RIGHT")]


def test_force_running_keeps_worker_service_available_for_hotkeys():
    worker = screen_mover.ScreenMoverWorker()

    assert not worker._service_enabled(False, "off", False)
    assert worker._service_enabled(False, "off", True)


def test_legacy_middle_mouse_setting_remains_supported():
    worker = screen_mover.ScreenMoverWorker()

    assert worker._load_activation_button({"mmb_activation_enabled": True}) == (
        "middle"
    )
    assert worker._load_activation_button({"mmb_activation_enabled": False}) == "off"

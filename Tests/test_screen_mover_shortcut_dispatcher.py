from unittest.mock import Mock

from resurface.features.screen_mover import shortcut_dispatcher


def _dispatcher(monkeypatch, *, target=101, succeeds=True):
    manual_moves = []
    actions = []
    dispatcher = shortcut_dispatcher.ShortcutActionDispatcher(
        app_hwnd=lambda: 999,
        manual_move_callback=manual_moves.append,
        perform_action=lambda hwnd, action: actions.append((hwnd, action)) or succeeds,
    )
    monkeypatch.setattr(dispatcher, "_foreground_target", lambda: target)
    return dispatcher, actions, manual_moves


def test_successful_monitor_shortcut_notifies_monitor_rules(monkeypatch):
    dispatcher, actions, manual_moves = _dispatcher(monkeypatch)

    assert dispatcher.request_action("left")

    assert actions == [(101, "LEFT")]
    assert manual_moves == [101]


def test_failed_move_and_window_control_actions_do_not_notify_rules(monkeypatch):
    failed, _actions, failed_notifications = _dispatcher(
        monkeypatch,
        succeeds=False,
    )
    assert not failed.request_action("RIGHT")
    assert failed_notifications == []

    dispatcher, actions, manual_moves = _dispatcher(monkeypatch)
    assert dispatcher.request_action("MINIMIZE")
    assert dispatcher.request_action("MAXIMIZE")
    assert actions == [(101, "MINIMIZE"), (101, "MAXIMIZE")]
    assert manual_moves == []


def test_maximize_is_suppressed_for_windows_resurface(monkeypatch):
    dispatcher, actions, manual_moves = _dispatcher(monkeypatch, target=999)

    assert not dispatcher.request_action("MAXIMIZE")
    assert actions == []
    assert manual_moves == []


def test_foreground_target_rejects_fullscreen_and_ineligible_windows(monkeypatch):
    dispatcher = shortcut_dispatcher.ShortcutActionDispatcher(app_hwnd=lambda: 999)
    monkeypatch.setattr(shortcut_dispatcher.win32gui, "GetForegroundWindow", lambda: 101)
    monkeypatch.setattr(
        shortcut_dispatcher.win32gui,
        "GetWindowRect",
        lambda _hwnd: (0, 0, 1920, 1080),
    )
    monkeypatch.setattr(
        shortcut_dispatcher.window_filter,
        "get_root_window",
        lambda hwnd: hwnd,
    )
    monkeypatch.setattr(
        shortcut_dispatcher,
        "window_is_fullscreen",
        lambda _hwnd, _rect: True,
    )
    eligible = Mock(return_value=True)
    monkeypatch.setattr(
        shortcut_dispatcher.window_filter,
        "is_window_eligible",
        eligible,
    )

    assert dispatcher._foreground_target() is None
    eligible.assert_not_called()


def test_invalid_action_does_not_resolve_foreground_window(monkeypatch):
    dispatcher, actions, manual_moves = _dispatcher(monkeypatch)
    target = Mock()
    monkeypatch.setattr(dispatcher, "_foreground_target", target)

    assert not dispatcher.request_action("UNKNOWN")
    target.assert_not_called()
    assert actions == []
    assert manual_moves == []

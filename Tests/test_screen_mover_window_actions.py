from resurface.features.screen_mover import window_actions


def test_visible_dock_actions_hide_left_actions_on_leftmost_monitor(monkeypatch):
    monkeypatch.setattr(
        window_actions.win32api,
        "EnumDisplayMonitors",
        lambda: [(10, None, None), (20, None, None), (30, None, None)],
    )
    monkeypatch.setattr(window_actions.win32api, "MonitorFromWindow", lambda hwnd: 10)

    assert window_actions.get_visible_dock_actions(101) == (
        "RIGHT",
        "FAR_RIGHT",
        "MINIMIZE",
        "MAXIMIZE",
    )


def test_visible_dock_actions_hide_right_actions_on_rightmost_monitor(monkeypatch):
    monkeypatch.setattr(
        window_actions.win32api,
        "EnumDisplayMonitors",
        lambda: [(10, None, None), (20, None, None), (30, None, None)],
    )
    monkeypatch.setattr(window_actions.win32api, "MonitorFromWindow", lambda hwnd: 30)

    assert window_actions.get_visible_dock_actions(101) == (
        "FAR_LEFT",
        "LEFT",
        "MINIMIZE",
        "MAXIMIZE",
    )


def test_visible_dock_actions_only_show_window_controls_on_single_monitor(monkeypatch):
    monkeypatch.setattr(
        window_actions.win32api,
        "EnumDisplayMonitors",
        lambda: [(10, None, None)],
    )
    monkeypatch.setattr(window_actions.win32api, "MonitorFromWindow", lambda hwnd: 10)

    assert window_actions.get_visible_dock_actions(101) == (
        "MINIMIZE",
        "MAXIMIZE",
    )


def test_visible_dock_actions_hide_maximize_when_window_has_no_maximize_box(
    monkeypatch,
):
    monkeypatch.setattr(
        window_actions.win32api,
        "EnumDisplayMonitors",
        lambda: [(10, None, None), (20, None, None)],
    )
    monkeypatch.setattr(window_actions.win32api, "MonitorFromWindow", lambda hwnd: 10)
    monkeypatch.setattr(window_actions.win32gui, "GetWindowLong", lambda hwnd, index: 0)
    monkeypatch.setattr(window_actions.win32gui, "IsWindow", lambda hwnd: True)

    assert window_actions.get_visible_dock_actions(101) == (
        "RIGHT",
        "FAR_RIGHT",
        "MINIMIZE",
    )


def test_window_is_fullscreen_detects_monitor_covering_window(monkeypatch):
    monkeypatch.setattr(
        window_actions.win32gui,
        "GetWindowPlacement",
        lambda hwnd: (
            0,
            window_actions.win32con.SW_SHOWNORMAL,
            (0, 0),
            (0, 0),
            (0, 0, 0, 0),
        ),
    )
    monkeypatch.setattr(
        window_actions.win32api,
        "MonitorFromWindow",
        lambda hwnd, flags=0: 10,
    )
    monkeypatch.setattr(
        window_actions.win32api,
        "GetMonitorInfo",
        lambda monitor: {"Monitor": (0, 0, 1920, 1080)},
    )

    assert window_actions.window_is_fullscreen(101, (0, 0, 1920, 1080))


def test_window_is_fullscreen_allows_maximized_windows(monkeypatch):
    monkeypatch.setattr(
        window_actions.win32gui,
        "GetWindowPlacement",
        lambda hwnd: (
            0,
            window_actions.win32con.SW_SHOWMAXIMIZED,
            (0, 0),
            (0, 0),
            (0, 0, 0, 0),
        ),
    )
    monkeypatch.setattr(
        window_actions.win32api,
        "MonitorFromWindow",
        lambda hwnd, flags=0: 10,
    )
    monkeypatch.setattr(
        window_actions.win32api,
        "GetMonitorInfo",
        lambda monitor: {"Monitor": (0, 0, 1920, 1080)},
    )

    assert not window_actions.window_is_fullscreen(101, (0, 0, 1920, 1080))

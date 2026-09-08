from resurface.features.screen_mover import window_actions


def test_move_window_reports_success_only_when_monitor_changes(monkeypatch):
    monitors = [(10, None, None), (20, None, None)]
    monkeypatch.setattr(window_actions.win32api, "EnumDisplayMonitors", lambda: monitors)
    monkeypatch.setattr(window_actions.win32api, "MonitorFromWindow", lambda _hwnd: 10)
    monkeypatch.setattr(
        window_actions.win32api,
        "GetMonitorInfo",
        lambda handle: {
            "Work": (0, 0, 1920, 1040)
            if handle == 10
            else (1920, 0, 3840, 1040)
        },
    )
    monkeypatch.setattr(
        window_actions.win32gui,
        "GetWindowPlacement",
        lambda _hwnd: (0, window_actions.win32con.SW_SHOWNORMAL, (), (), (0, 0, 0, 0)),
    )
    monkeypatch.setattr(
        window_actions.win32gui,
        "GetWindowRect",
        lambda _hwnd: (100, 100, 900, 700),
    )
    positions = []
    monkeypatch.setattr(
        window_actions.win32gui,
        "SetWindowPos",
        lambda *args: positions.append(args),
    )

    assert window_actions.move_window_to_monitor(101, "RIGHT")
    assert positions[0][2:6] == (2020, 100, 800, 600)
    assert not window_actions.move_window_to_monitor(101, "LEFT")


def test_minimize_and_maximize_report_success(monkeypatch):
    calls = []
    monkeypatch.setattr(
        window_actions.win32gui,
        "ShowWindow",
        lambda hwnd, command: calls.append((hwnd, command)),
    )

    assert window_actions.perform_window_action(101, "MINIMIZE")
    assert window_actions.perform_window_action(101, "MAXIMIZE")
    assert not window_actions.perform_window_action(101, "UNKNOWN")
    assert calls == [
        (101, window_actions.win32con.SW_MINIMIZE),
        (101, window_actions.win32con.SW_MAXIMIZE),
    ]


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

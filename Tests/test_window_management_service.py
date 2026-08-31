import win32con

from resurface.features.windows import window_management
from resurface.features.windows.window_management import WindowManagementService


def test_focus_restores_minimized_window(monkeypatch):
    calls = []
    monkeypatch.setattr(window_management, "_is_window_minimized", lambda _hwnd: True)
    monkeypatch.setattr(window_management.win32gui, "ShowWindow", lambda hwnd, command: calls.append((hwnd, command)))
    monkeypatch.setattr(window_management.win32gui, "SetForegroundWindow", lambda hwnd: calls.append((hwnd, "focus")))
    assert WindowManagementService().focus_handles([12]) is True
    assert calls == [(12, win32con.SW_RESTORE), (12, "focus")]


def test_window_state_distinguishes_closed_minimized_and_open(monkeypatch):
    service = WindowManagementService()
    monkeypatch.setattr(window_management, "_is_trackable_top_level_window", lambda hwnd: hwnd != 0)
    monkeypatch.setattr(window_management, "_is_window_minimized", lambda hwnd: hwnd == 2)
    assert service.state_for_handles([]) == "closed"
    assert service.state_for_handles([0]) == "closed"
    assert service.state_for_handles([2]) == "minimized"
    assert service.state_for_handles([2, 3]) == "open"


def test_open_or_focus_titles_launches_only_when_not_found(monkeypatch):
    service = WindowManagementService()
    monkeypatch.setattr(service, "find_by_titles", lambda _titles: [])
    launched = []
    assert service.open_or_focus_titles(["Settings"], lambda: launched.append(True)) is True
    assert launched == [True]


def test_find_by_titles_skips_cloaked_windows(monkeypatch):
    def enumerate_windows(callback, context):
        callback(1, context)
        callback(2, context)

    monkeypatch.setattr(window_management.win32gui, "EnumWindows", enumerate_windows)
    monkeypatch.setattr(window_management, "_is_trackable_top_level_window", lambda hwnd: hwnd == 2)
    monkeypatch.setattr(window_management.win32gui, "GetWindowText", lambda hwnd: "Advanced display" if hwnd == 2 else "Other")
    assert WindowManagementService().find_by_titles(["display"]) == [2]

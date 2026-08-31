"""Monitor geometry and window actions for Screen Mover."""

from __future__ import annotations

import time

import win32api
import win32con
import win32gui


DOCK_ACTIONS = (
    ("FAR_LEFT", "<<"),
    ("LEFT", "<"),
    ("RIGHT", ">"),
    ("FAR_RIGHT", ">>"),
    ("MINIMIZE", "_"),
    ("MAXIMIZE", "[]"),
)
DOCK_ACTIONS_DICT = dict(DOCK_ACTIONS)
MONITOR_MOVE_ACTIONS = {"FAR_LEFT", "LEFT", "RIGHT", "FAR_RIGHT"}


def _resolve_target_monitor_index(current_idx, monitor_count, direction):
    if direction == "LEFT":
        return max(0, current_idx - 1)
    if direction == "RIGHT":
        return min(monitor_count - 1, current_idx + 1)
    if direction == "FAR_LEFT":
        return 0
    if direction == "FAR_RIGHT":
        return monitor_count - 1
    return current_idx


def _monitor_handles():
    return [monitor[0] for monitor in win32api.EnumDisplayMonitors()]


def get_window_monitor_position(hwnd):
    try:
        monitor_handles = _monitor_handles()
    except Exception:
        return None, 0

    monitor_count = len(monitor_handles)
    if monitor_count == 0:
        return None, 0

    try:
        current_monitor = win32api.MonitorFromWindow(hwnd)
        current_idx = monitor_handles.index(current_monitor)
    except Exception:
        return None, monitor_count

    return current_idx, monitor_count


def window_supports_maximize(hwnd):
    try:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return True
    except Exception:
        return True

    try:
        style = int(win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE))
    except Exception:
        return True

    return bool(style & win32con.WS_MAXIMIZEBOX)


def window_is_fullscreen(hwnd, rect=None):
    if not hwnd:
        return False

    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMAXIMIZED:
            return False
    except Exception:
        pass

    try:
        if rect is None:
            rect = win32gui.GetWindowRect(hwnd)
        monitor = win32api.MonitorFromWindow(
            hwnd,
            getattr(win32con, "MONITOR_DEFAULTTONEAREST", 2),
        )
        monitor_rect = win32api.GetMonitorInfo(monitor)["Monitor"]
    except Exception:
        return False

    left, top, right, bottom = rect
    mon_left, mon_top, mon_right, mon_bottom = monitor_rect
    return (
        left <= mon_left
        and top <= mon_top
        and right >= mon_right
        and bottom >= mon_bottom
    )


def get_visible_dock_actions(hwnd):
    current_idx, monitor_count = get_window_monitor_position(hwnd)
    visible_monitor_actions = set()

    if monitor_count > 1:
        if current_idx is None:
            visible_monitor_actions = set(MONITOR_MOVE_ACTIONS)
        else:
            if current_idx > 0:
                visible_monitor_actions.update({"FAR_LEFT", "LEFT"})
            if current_idx < monitor_count - 1:
                visible_monitor_actions.update({"RIGHT", "FAR_RIGHT"})

    visible_actions = tuple(
        action
        for action, _label in DOCK_ACTIONS
        if action not in MONITOR_MOVE_ACTIONS or action in visible_monitor_actions
    )

    if "MAXIMIZE" in visible_actions and not window_supports_maximize(hwnd):
        visible_actions = tuple(
            action for action in visible_actions if action != "MAXIMIZE"
        )

    return visible_actions


def move_window_to_monitor(hwnd, direction):
    try:
        monitors = win32api.EnumDisplayMonitors()
        if len(monitors) < 2:
            print("[MOVE] Only one monitor detected; skipping move.")
            return

        current_monitor = win32api.MonitorFromWindow(hwnd)
        monitor_handles = [monitor[0] for monitor in monitors]
        try:
            current_idx = monitor_handles.index(current_monitor)
        except ValueError:
            print("[MOVE] Could not resolve current monitor.")
            return

        target_idx = _resolve_target_monitor_index(
            current_idx,
            len(monitors),
            direction,
        )
        if target_idx == current_idx:
            return

        source_info = win32api.GetMonitorInfo(monitor_handles[current_idx])
        target_info = win32api.GetMonitorInfo(monitor_handles[target_idx])
        s_left, s_top, _, _ = source_info["Work"]
        t_left, t_top, t_right, t_bottom = target_info["Work"]

        placement = win32gui.GetWindowPlacement(hwnd)
        show_cmd = placement[1]
        was_maximized = show_cmd == win32con.SW_SHOWMAXIMIZED

        if show_cmd == win32con.SW_SHOWMINIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.02)

        if was_maximized:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.02)

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top

        rel_x = left - s_left
        rel_y = top - s_top
        max_x = max(t_left, t_right - width)
        max_y = max(t_top, t_bottom - height)
        new_x = min(max(t_left + rel_x, t_left), max_x)
        new_y = min(max(t_top + rel_y, t_top), max_y)

        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOP,
            new_x,
            new_y,
            width,
            height,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
        )

        if was_maximized:
            time.sleep(0.02)
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)

        print(f"[MOVE] Window moved {direction} to monitor index {target_idx}.")
    except Exception as exc:
        print(f"[ERROR] move_window_to_monitor: {exc}")


def minimize_window(hwnd):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    except Exception as exc:
        print(f"[ERROR] minimize_window: {exc}")


def maximize_window(hwnd):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    except Exception as exc:
        print(f"[ERROR] maximize_window: {exc}")


def perform_window_action(hwnd, action):
    if action == "MINIMIZE":
        minimize_window(hwnd)
        return
    if action == "MAXIMIZE":
        maximize_window(hwnd)
        return
    move_window_to_monitor(hwnd, action)

from unittest.mock import Mock

from resurface.features.screen_mover import dock_overlay, window_actions


def test_dock_left_uses_same_special_clearance_for_app_window():
    rect = (0, 0, 400, 300)

    assert dock_overlay._dock_left_for_target(101, rect, app_hwnd=None) == 110
    assert dock_overlay._dock_left_for_target(101, rect, app_hwnd=101) == 166


def test_dock_overlay_hide_only_calls_windows_when_visible(monkeypatch):
    overlay = dock_overlay.DockOverlayButton(worker=None, overlay_name="test")
    overlay.hwnd = 123
    overlay.target_hwnd = 101
    overlay.rect = (0, 0, 180, 30)
    overlay.visible = True
    show_window = Mock()
    monkeypatch.setattr(dock_overlay.win32gui, "IsWindow", lambda hwnd: True)
    monkeypatch.setattr(dock_overlay.win32gui, "ShowWindow", show_window)

    overlay.hide()
    overlay.hide()

    show_window.assert_called_once_with(123, dock_overlay.win32con.SW_HIDE)
    assert overlay.visible is False
    assert overlay.target_hwnd is None
    assert overlay.rect is None


def test_dock_overlay_hit_test_only_uses_visible_actions():
    overlay = dock_overlay.DockOverlayButton(worker=None, overlay_name="test")
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
    overlay = dock_overlay.DockOverlayButton(worker=None, overlay_name="test")

    overlay.visible_actions = tuple(
        action for action, _label in window_actions.DOCK_ACTIONS
    )
    full_layout = {
        action: center
        for action, _label, center, _left, _right in overlay._action_layout(0, 180)
    }

    overlay.visible_actions = ("RIGHT", "FAR_RIGHT", "MINIMIZE", "MAXIMIZE")
    reduced_layout = {
        action: center
        for action, _label, center, _left, _right in overlay._action_layout(0, 180)
    }

    assert reduced_layout == {
        action: full_layout[action] for action in overlay.visible_actions
    }

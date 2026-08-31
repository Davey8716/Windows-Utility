"""Native Win32 dock-overlay window used by Screen Mover."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

import win32api
import win32con
import win32gui

from resurface.features.screen_mover.dock_icons import (
    DOCK_HEIGHT,
    DOCK_ICON_DEFAULT_THEME,
    DOCK_ICON_THEME_BLACK,
    DOCK_ICON_THEME_WHITE,
    DOCK_WIDTH,
    DockIconRenderer,
    _dock_icon_theme_for_rect,
)
from resurface.features.screen_mover.window_actions import (
    DOCK_ACTIONS,
    DOCK_ACTIONS_DICT,
)


TITLE_BAR_SIDE_MARGIN = 60
TITLE_BAR_BUTTON_GAP = 180
DOCK_TOP_OFFSET = 14
DOCK_RESTORED_TOP_OFFSET = 2
SELF_WINDOW_DOCK_TITLE_CLEARANCE = 166
DOCK_SIDE_PADDING = 13
DOCK_ICON_SPACING_REDUCTION = 2
DOCK_TRANSPARENT_COLOR = win32api.RGB(255, 255, 255)
DOCK_ARROW_COLOR = win32api.RGB(45, 125, 210)
LRESULT = getattr(wintypes, "LRESULT", ctypes.c_ssize_t)
WNDPROC_TYPE = ctypes.WINFUNCTYPE(
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


def _dock_left_for_target(target_hwnd, rect, app_hwnd=None) -> int:
    left, _top, right, _bottom = rect
    x = left + max(TITLE_BAR_SIDE_MARGIN, ((right - left) - DOCK_WIDTH) // 2)
    if app_hwnd and target_hwnd == app_hwnd:
        min_x = left + SELF_WINDOW_DOCK_TITLE_CLEARANCE
        max_x = right - DOCK_WIDTH
        x = min(max(x, min_x), max_x)
    return x


class DockOverlayButton:
    def __init__(self, worker, *, overlay_name=None):
        self.worker = worker
        self.hwnd = None
        self.target_hwnd = None
        self.rect = None
        self.visible = False
        self.visible_actions = tuple(action for action, _label in DOCK_ACTIONS)
        self.icon_theme = DOCK_ICON_DEFAULT_THEME
        normalized_name = "".join(
            character if str(character).isalnum() else "_"
            for character in str(overlay_name or id(self))
        )
        self._class_name = f"WindowsResurfaceDockOverlay_{normalized_name}_{id(self)}"
        self._wnd_proc = None
        self._icon_renderer = DockIconRenderer()

    def _ensure_window(self):
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            return

        hinstance = win32api.GetModuleHandle(None)
        self._wnd_proc = WNDPROC_TYPE(self._window_proc)

        wndclass = win32gui.WNDCLASS()
        wndclass.hInstance = hinstance
        wndclass.lpszClassName = self._class_name
        wndclass.lpfnWndProc = self._wnd_proc

        try:
            win32gui.RegisterClass(wndclass)
        except win32gui.error:
            pass

        self.hwnd = win32gui.CreateWindowEx(
            win32con.WS_EX_TOPMOST
            | win32con.WS_EX_TOOLWINDOW
            | win32con.WS_EX_LAYERED
            | win32con.WS_EX_TRANSPARENT,
            self._class_name,
            "",
            win32con.WS_POPUP,
            0,
            0,
            DOCK_WIDTH,
            DOCK_HEIGHT,
            0,
            0,
            hinstance,
            None,
        )
        win32gui.SetLayeredWindowAttributes(
            self.hwnd,
            DOCK_TRANSPARENT_COLOR,
            0,
            win32con.LWA_COLORKEY,
        )

    def preload_icons(self) -> None:
        self._icon_renderer.preload_themes(
            (DOCK_ICON_THEME_BLACK, DOCK_ICON_THEME_WHITE),
        )

    def _window_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == win32con.WM_PAINT:
                return self._paint(hwnd)

            if msg == win32con.WM_ERASEBKGND:
                return 1

            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
        except Exception as exc:
            print(f"[DOCK] WNDPROC error: {exc}")
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _icon_centers(self, left, right, icon_count):
        icon_count = max(0, int(icon_count))
        if icon_count == 0:
            return []
        if icon_count <= 1:
            return [left + ((right - left) / 2.0)]

        default_step = (right - left) / icon_count
        icon_step = max(1.0, default_step - DOCK_ICON_SPACING_REDUCTION)
        total_span = icon_step * (icon_count - 1)
        min_start = left + DOCK_SIDE_PADDING
        max_start = right - DOCK_SIDE_PADDING - total_span
        centered_start = left + (((right - left) - total_span) / 2.0)
        start = min(max(centered_start, min_start), max_start)
        return [start + (index * icon_step) for index in range(icon_count)]

    def _action_layout(self, left, right):
        actions = tuple(self.visible_actions)
        all_actions = tuple(action for action, _label in DOCK_ACTIONS)
        centers = self._icon_centers(left, right, len(all_actions))
        if not centers:
            return []

        icon_step = centers[1] - centers[0]
        center_by_action = dict(zip(all_actions, centers))

        return [
            (
                action,
                DOCK_ACTIONS_DICT[action],
                center_by_action[action],
                center_by_action[action] - (icon_step / 2.0),
                center_by_action[action] + (icon_step / 2.0),
            )
            for action in actions
            if action in center_by_action
        ]

    def _paint(self, hwnd):
        hdc, paint_struct = win32gui.BeginPaint(hwnd)

        try:
            left, top, right, bottom = win32gui.GetClientRect(hwnd)
            bg = win32gui.CreateSolidBrush(DOCK_TRANSPARENT_COLOR)
            win32gui.FillRect(hdc, (left, top, right, bottom), bg)
            win32gui.SetBkMode(hdc, win32con.TRANSPARENT)

            logfont = win32gui.LOGFONT()
            logfont.lfHeight = -18
            logfont.lfWeight = 700
            logfont.lfFaceName = "Segoe UI Symbol"
            logfont.lfQuality = getattr(win32con, "NONANTIALIASED_QUALITY", 3)
            font = win32gui.CreateFontIndirect(logfont)
            old_font = win32gui.SelectObject(hdc, font)

            vertical_center = (top + bottom) // 2
            for action, label, _center_x, seg_left, seg_right in self._action_layout(
                left,
                right,
            ):
                if self._icon_renderer.draw_action(hdc, action, self.icon_theme):
                    continue

                _text_width, text_height = win32gui.GetTextExtentPoint32(hdc, label)
                text_rect = (
                    int(seg_left),
                    int(vertical_center - (text_height / 2.0)),
                    int(seg_right),
                    int(vertical_center + (text_height / 2.0)),
                )

                win32gui.SetTextColor(hdc, DOCK_ARROW_COLOR)
                win32gui.DrawText(
                    hdc,
                    label,
                    -1,
                    text_rect,
                    win32con.DT_CENTER | win32con.DT_VCENTER | win32con.DT_SINGLELINE,
                )

            win32gui.SelectObject(hdc, old_font)
            win32gui.DeleteObject(font)
            win32gui.DeleteObject(bg)
        finally:
            win32gui.EndPaint(hwnd, paint_struct)

        return 0

    def show_for_target(self, target_hwnd, rect, actions):
        self._ensure_window()
        visible_actions = tuple(actions)
        if not visible_actions:
            self.hide()
            return

        _left, top, _right, _bottom = rect
        x = _dock_left_for_target(target_hwnd, rect, self.worker.app_hwnd)
        y = top + DOCK_TOP_OFFSET
        try:
            placement = win32gui.GetWindowPlacement(target_hwnd)
            show_cmd = placement[1]
            if show_cmd != win32con.SW_SHOWMAXIMIZED:
                y = top + DOCK_RESTORED_TOP_OFFSET
        except Exception:
            pass
        new_rect = (x, y, x + DOCK_WIDTH, y + DOCK_HEIGHT)
        needs_theme_sample = (
            target_hwnd != self.target_hwnd
            or new_rect != self.rect
            or visible_actions != self.visible_actions
            or not self.visible
        )
        icon_theme = self.icon_theme
        if needs_theme_sample:
            current_theme = (
                self.icon_theme
                if self.visible
                and target_hwnd == self.target_hwnd
                and new_rect == self.rect
                else None
            )
            icon_theme = _dock_icon_theme_for_rect(new_rect, current_theme)
        should_update = (
            target_hwnd != self.target_hwnd
            or new_rect != self.rect
            or visible_actions != self.visible_actions
            or icon_theme != self.icon_theme
            or not self.visible
        )

        self.target_hwnd = target_hwnd
        self.rect = new_rect
        self.visible_actions = visible_actions
        self.icon_theme = icon_theme
        if not should_update:
            return

        win32gui.SetWindowPos(
            self.hwnd,
            win32con.HWND_TOPMOST,
            x,
            y,
            DOCK_WIDTH,
            DOCK_HEIGHT,
            win32con.SWP_SHOWWINDOW,
        )
        self.visible = True
        win32gui.InvalidateRect(self.hwnd, None, True)

    def contains_point(self, x, y):
        if not self.rect or not self.target_hwnd:
            return False

        left, top, right, bottom = self.rect
        return left <= x < right and top <= y < bottom

    def hit_test(self, x, y):
        if not self.contains_point(x, y):
            return None

        left, top, right, bottom = self.rect
        for action, _label, _center_x, seg_left, seg_right in self._action_layout(
            left,
            right,
        ):
            if seg_left <= x < seg_right:
                return action
        return None

    def hide(self):
        was_visible = self.visible
        self.target_hwnd = None
        self.rect = None
        self.visible_actions = tuple(action for action, _label in DOCK_ACTIONS)
        self.icon_theme = DOCK_ICON_DEFAULT_THEME
        if was_visible and self.hwnd and win32gui.IsWindow(self.hwnd):
            win32gui.ShowWindow(self.hwnd, win32con.SW_HIDE)
        self.visible = False

    def destroy(self):
        self.target_hwnd = None
        self.rect = None
        self.visible = False
        self.visible_actions = tuple(action for action, _label in DOCK_ACTIONS)
        self.icon_theme = DOCK_ICON_DEFAULT_THEME
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            try:
                win32gui.DestroyWindow(self.hwnd)
            except win32gui.error:
                pass
        self.hwnd = None
        self._icon_renderer.dispose()

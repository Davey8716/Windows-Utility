import ctypes
import threading
import time
from ctypes import wintypes

from pynput import mouse

import psutil
import win32api
import win32con
import win32gui
import win32process

from state_manager import load_state

TITLE_BAR_SIDE_MARGIN = 80
TITLE_BAR_BUTTON_GAP = 140
DOCK_WIDTH = 92
DOCK_HEIGHT = 28
DOCK_TOP_OFFSET = 14
LOOP_SLEEP = 0.03
LRESULT = getattr(wintypes, "LRESULT", ctypes.c_ssize_t)
WNDPROC_TYPE = ctypes.WINFUNCTYPE(
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class DockOverlayButton:
    def __init__(self, worker):
        self.worker = worker
        self.hwnd = None
        self.target_hwnd = None
        self.rect = None
        self._class_name = "WindowsResurfaceDockOverlay"
        self._wnd_proc = None

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
        win32gui.SetLayeredWindowAttributes(self.hwnd, 0, 240, win32con.LWA_ALPHA)

    def _window_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == win32con.WM_PAINT:
                return self._paint(hwnd)

            if msg == win32con.WM_ERASEBKGND:
                return 1

            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
        except Exception as e:
            print(f"[DOCK] WNDPROC error: {e}")
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _paint(self, hwnd):
        hdc, paint_struct = win32gui.BeginPaint(hwnd)

        try:
            rect = win32gui.GetClientRect(hwnd)
            bg = win32gui.CreateSolidBrush(win32api.RGB(27, 34, 44))
            edge = win32gui.CreateSolidBrush(win32api.RGB(42, 52, 64))
            win32gui.FillRect(hdc, rect, bg)
            win32gui.FrameRect(hdc, rect, edge)
            win32gui.SetBkMode(hdc, win32con.TRANSPARENT)
            win32gui.SetTextColor(hdc, win32api.RGB(90, 200, 255))

            logfont = win32gui.LOGFONT()
            logfont.lfHeight = -18
            logfont.lfWeight = 700
            logfont.lfFaceName = "Segoe UI Symbol"
            font = win32gui.CreateFontIndirect(logfont)
            old_font = win32gui.SelectObject(hdc, font)

            win32gui.DrawText(
                hdc,
                "<   >",
                -1,
                rect,
                win32con.DT_CENTER | win32con.DT_VCENTER | win32con.DT_SINGLELINE,
            )

            win32gui.SelectObject(hdc, old_font)
            win32gui.DeleteObject(font)
            win32gui.DeleteObject(bg)
            win32gui.DeleteObject(edge)
        finally:
            win32gui.EndPaint(hwnd, paint_struct)

        return 0

    def show_for_target(self, target_hwnd, rect):
        self._ensure_window()
        self.target_hwnd = target_hwnd
        left, top, right, _ = rect
        x = left + max(TITLE_BAR_SIDE_MARGIN, ((right - left) - DOCK_WIDTH) // 2)
        y = top + DOCK_TOP_OFFSET
        self.rect = (x, y, x + DOCK_WIDTH, y + DOCK_HEIGHT)
        win32gui.SetWindowPos(
            self.hwnd,
            win32con.HWND_TOPMOST,
            x,
            y,
            DOCK_WIDTH,
            DOCK_HEIGHT,
            win32con.SWP_SHOWWINDOW,
        )
        win32gui.InvalidateRect(self.hwnd, None, True)

    def hit_test(self, x, y):
        if not self.rect or not self.target_hwnd:
            return None

        left, top, right, bottom = self.rect
        if not (left <= x < right and top <= y < bottom):
            return None

        return "LEFT" if x < (left + DOCK_WIDTH // 2) else "RIGHT"

    def hide(self):
        self.target_hwnd = None
        self.rect = None
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            win32gui.ShowWindow(self.hwnd, win32con.SW_HIDE)

    def destroy(self):
        self.target_hwnd = None
        self.rect = None
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            try:
                win32gui.DestroyWindow(self.hwnd)
            except win32gui.error:
                pass
        self.hwnd = None


class ScreenMoverWorker:
    def __init__(self):
        self.dock_overlay = DockOverlayButton(self)
        self.enabled = False
        self.thread = None
        self.mouse_listener = None
        self.lock = threading.Lock()

        self.title_bar_dock_enabled = True
        self.enable_mmb = True
        self.app_hwnd = None

    def configure(self, *, app_hwnd=None):
        if app_hwnd:
            self.app_hwnd = app_hwnd
        self.refresh_from_state()

    def refresh_from_state(self):
        state = load_state()
        self.enable_mmb = bool(state.get("mmb_activation_enabled", True))
        self.title_bar_dock_enabled = bool(state.get("title_bar_dock_enabled", True))

    def _pump_messages(self):
        try:
            win32gui.PumpWaitingMessages()
        except Exception:
            pass

    def _get_window_exe(self, hwnd):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return psutil.Process(pid).name().lower()
        except Exception:
            return ""

    def _is_system_window(self, hwnd):
        exe = self._get_window_exe(hwnd)
        return exe in {
            "explorer.exe",
            "shellexperiencehost.exe",
            "startmenuexperiencehost.exe",
            "searchhost.exe",
            "widgets.exe",
            "dwm.exe",
        }

    def _is_owned_by_app(self, hwnd):
        if not self.app_hwnd or not hwnd or hwnd == self.app_hwnd:
            return False

        try:
            owner_hwnd = win32gui.GetWindow(hwnd, getattr(win32con, "GW_OWNER", 4))
        except Exception:
            return False

        return owner_hwnd == self.app_hwnd

    def _is_window_eligible(self, hwnd):
        if not hwnd or not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False
        if hwnd == self.app_hwnd or hwnd == self.dock_overlay.hwnd:
            return False
        if self._is_owned_by_app(hwnd):
            return False
        if self._is_system_window(hwnd):
            return False
        title = win32gui.GetWindowText(hwnd).strip()
        return bool(title)

    def _is_self_window_eligible(self, hwnd):
        if not self.app_hwnd or hwnd != self.app_hwnd:
            return False
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False
        return True

    def _can_move_window(self, hwnd):
        if self._is_self_window_eligible(hwnd):
            return True
        return self._is_window_eligible(hwnd)

    def _get_root_window(self, hwnd):
        if not hwnd:
            return None
        try:
            return win32gui.GetAncestor(hwnd, getattr(win32con, "GA_ROOT", 2))
        except Exception:
            return hwnd

    def _get_caption_height(self):
        return (
            win32api.GetSystemMetrics(win32con.SM_CYCAPTION)
            + win32api.GetSystemMetrics(win32con.SM_CYFRAME)
            + 8
        )

    def _title_bar_candidate(self):
        try:
            cursor_x, cursor_y = win32gui.GetCursorPos()
            direction = self.dock_overlay.hit_test(cursor_x, cursor_y)
            if direction and self.dock_overlay.target_hwnd:
                hwnd = self.dock_overlay.target_hwnd
                rect = win32gui.GetWindowRect(hwnd)
                return hwnd, rect

            raw_hwnd = win32gui.WindowFromPoint((cursor_x, cursor_y))
        except Exception:
            return None, None

        hwnd = self._get_root_window(raw_hwnd)
        if not (self._is_window_eligible(hwnd) or self._is_self_window_eligible(hwnd)):
            return None, None

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

        if not (left + TITLE_BAR_SIDE_MARGIN <= cursor_x <= right - TITLE_BAR_BUTTON_GAP):
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

        self.dock_overlay.show_for_target(hwnd, rect)

    def move_window_to_monitor(self, hwnd, direction):
        try:
            if not self._can_move_window(hwnd):
                return

            monitors = win32api.EnumDisplayMonitors()
            if len(monitors) < 2:
                print("[MOVE] Only one monitor detected; skipping move.")
                return

            current_monitor = win32api.MonitorFromWindow(hwnd)
            monitor_handles = [m[0] for m in monitors]
            try:
                current_idx = monitor_handles.index(current_monitor)
            except ValueError:
                print("[MOVE] Could not resolve current monitor.")
                return

            target_idx = (current_idx + 1) % len(monitors) if direction == "RIGHT" else (current_idx - 1) % len(monitors)

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
        except Exception as e:
            print(f"[ERROR] move_window_to_monitor: {e}")

    def worker_loop(self):
        print("[THREAD] Screen mover loop started.")

        while self.enabled:
            self._pump_messages()
            self._update_title_bar_dock()
            time.sleep(LOOP_SLEEP)

        self.dock_overlay.hide()
        self.dock_overlay.destroy()

    def start(self):
        with self.lock:
            if self.enabled:
                return

            self.refresh_from_state()
            self.enabled = True
            self.thread = threading.Thread(
                target=self.worker_loop,
                name="ScreenMoverWorker",
                daemon=True,
            )
            self.thread.start()
            self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
            self.mouse_listener.start()

    def stop(self):
        with self.lock:
            if not self.enabled:
                return

            self.enabled = False

            if self.mouse_listener:
                self.mouse_listener.stop()
                self.mouse_listener = None

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.thread = None

    def on_mouse_click(self, x, y, button, pressed):
        if not self.enabled or not self.enable_mmb or button != mouse.Button.middle or not pressed:
            return

        direction = self.dock_overlay.hit_test(x, y)
        target = self.dock_overlay.target_hwnd
        if direction and target:
            self.dock_overlay.hide()
            self.move_window_to_monitor(target, direction)


SCREEN_MOVER = ScreenMoverWorker()

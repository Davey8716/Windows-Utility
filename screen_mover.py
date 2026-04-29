import threading
import time
import ctypes

import psutil
import pygetwindow as gw
from pynput import mouse

import win32api
import win32con
import win32gui
import win32process

from pynput import mouse
from state_manager import load_state

ACTIVATION_Y_MIN = 0
ACTIVATION_Y_MAX = 30

class ScreenMoverWorker:
    def __init__(self):
        self.overlay = FlickOverlay()
        self.enabled = False
        self.thread = None
        self.mouse_listener = None
        self.lock = threading.Lock()

        self.dispatch_ui = None

        self.overlay_enabled = True

        self.mmb_down = False
        self.lmb_down = False
        self.gesture_active = False
        self.activation_method = None

        self.gesture_hwnd = None

        self.flick_start_x = None
        self.flick_start_time = None
        self.flick_threshold_px = 25
        self.flick_max_time = 0.35

        self.auto_align_enabled = False
        self.last_rect = None
        self.last_move_time = 0

        self.enable_mmb = False
        self.mmb_ui_enabled = True
        
    @property
    def hwnd(self):
        return self.overlay.hwnd if self.overlay else None

    def _force_align_all_windows(self):
        if not self.auto_align_enabled:
            return

        try:
            windows = []

            def enum_handler(hwnd, _):
                if not win32gui.IsWindowVisible(hwnd):
                    return
                if win32gui.IsIconic(hwnd):
                    return
                windows.append(hwnd)

            win32gui.EnumWindows(enum_handler, None)

            threshold = ACTIVATION_Y_MAX + 5

            for hwnd in windows:
                try:
                    if self and hwnd == self.hwnd:
                        continue

                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        exe = psutil.Process(pid).name().lower()

                        if exe in (
                            "taskmgr.exe",
                            "mmc.exe",
                            "systemsettings.exe",
                            "dwm.exe",
                            "explorer.exe",
                        ):
                            continue
                    except Exception:
                        continue

                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    width = right - left
                    height = bottom - top

                    if top <= threshold:
                        continue

                    try:
                        win32gui.SetWindowPos(
                            hwnd,
                            win32con.HWND_TOP,
                            left,
                            1,
                            width,
                            height,
                            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
                        )
                    except Exception as e:
                        if "Access is denied" in str(e):
                            continue
                        print("[FORCE-ALIGN] SetWindowPos error:", e)

                except Exception as inner_e:
                    print("[FORCE-ALIGN] Window loop error:", inner_e)

        except Exception as outer_e:
            print("[FORCE-ALIGN] EnumWindows error:", outer_e)

    def _is_system_window(self, hwnd):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            exe = psutil.Process(pid).name().lower()

            return exe in (
                "explorer.exe",                
                "shellexperiencehost.exe",     
                "startmenuexperiencehost.exe",
                "searchhost.exe",
                "widgets.exe",
            )
        except Exception:
            return False

    def show(self, x: int, y: int, paint_callback):
        try:
            import win32api, win32con, win32gui
        except Exception:
            print("[OVERLAY] WinAPI missing")
            return

        if self.hwnd and win32gui.IsWindow(self.hwnd):
            win32gui.SetWindowPos(
                self.hwnd,
                win32con.HWND_TOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )
            return

        width, height = 100, 50
        pos_x = int(x - 50)
        pos_y = int(y - 22)

        hinstance = win32api.GetModuleHandle(None)

        class_name = "FlickOverlayClass"
        wndclass = win32gui.WNDCLASS()
        wndclass.hInstance = hinstance
        wndclass.lpszClassName = class_name
        wndclass.lpfnWndProc = {win32con.WM_PAINT: paint_callback}

        try:
            win32gui.RegisterClass(wndclass)
        except Exception:
            pass 

        self.hwnd = win32gui.CreateWindowEx(
            win32con.WS_EX_TOPMOST
            | win32con.WS_EX_TOOLWINDOW
            | win32con.WS_EX_LAYERED
            | win32con.WS_EX_TRANSPARENT,
            class_name,
            "",
            win32con.WS_POPUP,
            pos_x,
            pos_y,
            width,
            height,
            0,
            0,
            hinstance,
            None
        )

        if not self.hwnd:
            print("[OVERLAY] Failed to create overlay")
            return

        rgn = win32gui.CreateRoundRectRgn(0, 0, width, height, 16, 16)
        win32gui.SetWindowRgn(self.hwnd, rgn, True)

        win32gui.SetLayeredWindowAttributes(
            self.hwnd, 0, 255, win32con.LWA_ALPHA
        )

        win32gui.SetWindowPos(
            self.hwnd,
            win32con.HWND_TOPMOST,
            pos_x, pos_y, width, height,
            win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE
        )

    def hide(self):
        try:
            import win32gui, win32con
            if self.hwnd and win32gui.IsWindow(self.hwnd):
                win32gui.ShowWindow(self.hwnd, win32con.SW_HIDE)
                win32gui.DestroyWindow(self.hwnd)
        except Exception as e:
            if "Access is denied" not in str(e):
                print("[OVERLAY] Destroy failed:", e)
        finally:
            self.hwnd = None
            
    def _soft_auto_align_active_window(self):
        if not self.auto_align_enabled:
            return

        try:
            win = gw.getActiveWindow()
            if not win:
                return

            hwnd = win._hWnd

            if self and hwnd == self.hwnd:
                return

            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                exe = psutil.Process(pid).name().lower()

                if exe in (
                    "taskmgr.exe",
                    "mmc.exe",
                    "systemsettings.exe",
                    "dwm.exe",
                    "explorer.exe",
                ):
                    return
            except Exception:
                return

            placement = win32gui.GetWindowPlacement(hwnd)
            show_cmd = placement[1]
            if show_cmd in (win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED):
                return

            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top

            threshold = ACTIVATION_Y_MAX + 5
            if top <= threshold:
                return

            try:
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_TOP,
                    left,
                    10,
                    width,
                    height,
                    win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
                )
            except Exception as e:
                if "Access is denied" in str(e):
                    return
                print("[AUTO-ALIGN] SetWindowPos error:", e)

        except Exception as outer_error:
            print("[AUTO-ALIGN] Outer error:", outer_error)
        
    def move_active_window(self, direction: str):
        try:
            hwnd = self.gesture_hwnd

            if not hwnd:
                win = gw.getActiveWindow()
                if not win:
                    print("[MOVE] No active window detected.")
                    return
                hwnd = win._hWnd

            if self.overlay and hwnd == self.overlay.hwnd:
                hwnd = win32gui.GetForegroundWindow()

            if not hwnd:
                print("[MOVE] Invalid target window.")
                return

            monitors = win32api.EnumDisplayMonitors()
            if len(monitors) < 2:
                print("[MOVE] Only one monitor detected — skipping move.")
                return

            current_monitor = win32api.MonitorFromWindow(hwnd)
            monitor_handles = [m[0] for m in monitors]

            try:
                idx = monitor_handles.index(current_monitor)
            except ValueError:
                print("[MOVE] Could not resolve current monitor.")
                return

            # Target monitor index
            if direction == "RIGHT":
                target_idx = (idx + 1) % len(monitors)
            else:
                target_idx = (idx - 1) % len(monitors)

            target_info = win32api.GetMonitorInfo(monitor_handles[target_idx])
            t_left, t_top, t_right, t_bottom = target_info["Work"]

            placement = win32gui.GetWindowPlacement(hwnd)
            show_cmd = placement[1]
            was_maximized = (show_cmd == win32con.SW_SHOWMAXIMIZED)

            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            restored_width = right - left
            restored_height = bottom - top

            if show_cmd in (win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.02)

                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                restored_width = right - left
                restored_height = bottom - top

            cur_left, cur_top, _, _ = win32gui.GetWindowRect(hwnd)

            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                t_left + (left - cur_left),
                t_top + (top - cur_top),
                restored_width,
                restored_height,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )

            time.sleep(0.02)

            if was_maximized:
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)

            print(
                f"[MOVE] Window moved to monitor index {target_idx} "
                f"({direction}), maximized={was_maximized}"
            )

        except Exception as e:
            print(f"[ERROR] move_active_window: {e}")
        
    def begin_gesture(self, x, y):
        if not self.enable_mmb:
            return

        self.gesture_active = True

        try:
            self.gesture_hwnd = win32gui.WindowFromPoint((x, y))
        except Exception:
            self.gesture_hwnd = None
        finally:
            self.flick_start_x = x
            self.flick_start_time = time.time()

        print(f"[GESTURE] Begin, x={x}")

        if not self.overlay_enabled:
            return

        def _show():
            self.show(x, y)

        try:
            if callable(self.dispatch_ui):
                self.dispatch_ui(_show)
            else:
                _show()
        except Exception as e:
            print("[OVERLAY] Show dispatch failed:", e)

    def end_gesture(self):
        if not self.gesture_active:
            return

        print("[GESTURE] End")

        self.gesture_active = False
        self.activation_method = None
        self.flick_start_x = None
        self.flick_start_time = None
        self.gesture_hwnd = None

        if not self.overlay_enabled:
            return

        def _hide():
            self.hide()

        try:
            if callable(self.dispatch_ui):
                self.dispatch_ui(_hide)
            else:
                _hide()
        except Exception as e:
            print("[OVERLAY] Hide dispatch failed:", e)
        
    def worker_loop(self):
        print("[THREAD] Screen mover loop started.")

        SLEEP_INTERVAL = 0.01

        while True:
            if not self.enabled:
                break

            now = time.time()

            if self.gesture_active and self.flick_start_x is not None:
                try:
                    x, _ = win32api.GetCursorPos()
                except Exception:
                    x = None

                if x is not None and self._check_flick(x):
                    direction = "RIGHT" if x > self.flick_start_x else "LEFT"
                    print(f"[FLICK] Detected {direction}")

                    self.move_active_window(direction)
                    self.end_gesture()

                    time.sleep(SLEEP_INTERVAL)
                    continue

            if self.auto_align_enabled and not self.gesture_active:
                try:
                    win = gw.getActiveWindow()
                    if win:
                        hwnd = win._hWnd

                        if (
                            self
                            and hwnd == self.hwnd
                        ) or self._is_system_window(hwnd):
                            self.last_rect = None
                        else:
                            rect = win32gui.GetWindowRect(hwnd)

                            if self.last_rect != rect:
                                self.last_rect = rect
                                self.last_move_time = now
                            else:
                                if (now - self.last_move_time) >= 0.20:
                                    self._soft_auto_align_active_window()

                except Exception as e:
                    print("[AUTO-ALIGN] Error:", e)

            time.sleep(SLEEP_INTERVAL)

    def start(self):
        with self.lock:
            if self.enabled:
                return
            
            print("[INFO] Starting Screen-Tab Mover backend…")
            self.enabled = True

            state = load_state()
            self.enable_mmb = state.get("mmb_activation_enabled", False)
            self.auto_align_enabled = state.get("auto_align_enabled", False)

            self.thread = threading.Thread(
                target=self.worker_loop,
                name="ScreenMoverWorker",
                daemon=True
            )
            self.thread.start()

            self.listener = mouse.Listener(
                on_click=self.on_mouse_click
            )
            self.listener.start()

    def stop(self):
        with self.lock:
            if not self.enabled:
                return

            print("[INFO] Stopping Screen-Tab Mover backend…")
            self.enabled = False

            if self.mouse_listener:
                self.mouse_listener.stop()
                self.mouse_listener = None
                

    def on_mouse_click(self, x, y, button, pressed, injected):
        if not self.enabled or not self.enable_mmb:
            return

        if button == mouse.Button.middle:
            self.mmb_down = pressed
        elif button == mouse.Button.left:
            self.lmb_down = pressed

        if self.gesture_active and self.activation_method == "MMB":
            if button == mouse.Button.middle:
                if not pressed:
                    print("[GESTURE] Cancelled → MMB released")
                else:
                    print("[GESTURE] Cancelled → MMB re-press")

                self.end_gesture()
                self.activation_method = None
                return

            return

        if (
            button == mouse.Button.middle
            and pressed
            and ACTIVATION_Y_MIN <= y <= ACTIVATION_Y_MAX
        ):
            print(f"[GESTURE] Activated → MMB at ({x},{y})")
            self.activation_method = "MMB"
            self.begin_gesture(x, y)

class FlickOverlay:
    def __init__(self):
        self.hwnd = self._create_overlay_window()

    def _create_overlay_window(self):
        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_int
        )

        self._wnd_proc = WNDPROC(self._overlay_paint)

        wndclass = win32gui.WNDCLASS()
        wndclass.lpfnWndProc = self._wnd_proc
        wndclass.lpszClassName = "FlickOverlayWindow"
        wndclass.hInstance = win32api.GetModuleHandle(None)

        win32gui.RegisterClass(wndclass)

        hwnd = win32gui.CreateWindowEx(
            win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT,
            wndclass.lpszClassName,
            "",
            win32con.WS_POPUP,
            0, 0, 1, 1,
            0, 0, wndclass.hInstance, None
        )

        return hwnd
    
    def _overlay_paint(self, hwnd, msg, wparam, lparam):
        """
        Win32 WM_PAINT handler for the flick overlay.
        Pure renderer: no worker state, no GUI dependencies.
        """
        hdc, paint_struct = win32gui.BeginPaint(hwnd)

        try:
            win32gui.SetBkMode(hdc, win32con.TRANSPARENT)

            rect = win32gui.GetClientRect(hwnd)
            bg_brush = win32gui.CreateSolidBrush(win32api.RGB(0, 0, 0))
            win32gui.FillRect(hdc, rect, bg_brush)

            logfont = win32gui.LOGFONT()
            logfont.lfHeight = -35
            logfont.lfWeight = 900
            logfont.lfFaceName = "Rubik UI Symbol"
            logfont.lfQuality = win32con.ANTIALIASED_QUALITY

            font = win32gui.CreateFontIndirect(logfont)
            old_font = win32gui.SelectObject(hdc, font)

            win32gui.SetTextColor(hdc, win32api.RGB(0, 178, 255))

            win32gui.DrawText(
                hdc,
                "⮜   ⮞",
                -1,
                (0, 0, 100, 40),
                win32con.DT_CENTER
                | win32con.DT_VCENTER
                | win32con.DT_SINGLELINE
            )

            # Cleanup GDI objects
            win32gui.SelectObject(hdc, old_font)
            win32gui.DeleteObject(font)
            win32gui.DeleteObject(bg_brush)

        finally:
            win32gui.EndPaint(hwnd, paint_struct)

        return 0

    def _check_flick(self, current_x):
        """Detect flick at any time while gesture is active."""
        if self.flick_start_x is None:
            return False

        return abs(current_x - self.flick_start_x) >= self.flick_threshold_px

    def hide_overlay(self):
        """Hide and destroy the Win32 overlay if it exists."""
        if not self.overlay_enabled:
            return

        try:
            if self:
                self.hide()
        except Exception as e:
            print("[OVERLAY] Hide failed:", e)

SCREEN_MOVER = ScreenMoverWorker()













    
    
    

    
    
  
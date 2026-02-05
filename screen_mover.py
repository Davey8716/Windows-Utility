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

from state_manager import load_state

# ==============================================================
# Gesture activation band (top of screen)
# ==============================================================

ACTIVATION_Y_MIN = 0
ACTIVATION_Y_MAX = 30

# ==============================================================
# Screen Mover Background Worker (GUI-agnostic, Qt-safe)
# ==============================================================

class ScreenMoverWorker:
    def __init__(self):
        self.overlay = FlickOverlay()
        self.enabled = False
        self.thread = None
        self.mouse_listener = None
        self.lock = threading.Lock()

        
        # -------------------------
        # GUI / dispatcher hooks (Qt-safe)
        # -------------------------
        # Optional callable: dispatcher(fn) → runs fn on GUI thread
        self.dispatch_ui = None

        # Overlay enable flag (GUI may toggle)
        self.overlay_enabled = True

        # -------------------------
        # Gesture / state
        # -------------------------
        self.mmb_down = False
        self.lmb_down = False
        self.gesture_active = False
        self.activation_method = None

        self.gesture_hwnd = None

        # Flick tracking
        self.flick_start_x = None
        self.flick_start_time = None
        self.flick_threshold_px = 25
        self.flick_max_time = 0.35

        # -------------------------
        # Auto-align tracking
        # -------------------------
        self.auto_align_enabled = False
        self.last_rect = None
        self.last_move_time = 0

        # -------------------------
        # Activation toggles (GUI-controlled)
        # -------------------------
        self.enable_mmb = False
        self.mmb_ui_enabled = True
        
    @property
    def hwnd(self):
        return self.overlay.hwnd if self.overlay else None

        
    # ==============================================================
    # Window nudger (force align)
    # ==============================================================

    def _force_align_all_windows(self):
        """
        When auto-align is enabled, immediately scan all windows and gently move
        any that are below the flick zone threshold back into the activation zone.
        """
        if not self.auto_align_enabled:
            return

        try:
            windows = []

            def enum_handler(hwnd, _):
                # Must be visible and not minimized
                if not win32gui.IsWindowVisible(hwnd):
                    return
                if win32gui.IsIconic(hwnd):
                    return
                windows.append(hwnd)

            win32gui.EnumWindows(enum_handler, None)

            threshold = ACTIVATION_Y_MAX + 5

            for hwnd in windows:
                try:
                    # Skip overlay window
                    if self and hwnd == self.hwnd:
                        continue

                    # Skip protected / system windows
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

                    # Window geometry
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    width = right - left
                    height = bottom - top

                    # Already within activation band
                    if top <= threshold:
                        continue

                    # Nudge window toward top edge
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

        
    
    

    # ==============================================================
    # System window detection
    # ==============================================================

    def _is_system_window(self, hwnd):
        """Return True if the window belongs to Explorer or Windows shell UI."""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            exe = psutil.Process(pid).name().lower()

            return exe in (
                "explorer.exe",                # Taskbar, tray, shell
                "shellexperiencehost.exe",     # Windows 10/11 shell UI
                "startmenuexperiencehost.exe",
                "searchhost.exe",
                "widgets.exe",
            )
        except Exception:
            return False

        
    def show(self, x: int, y: int, paint_callback):
        """Create or raise the overlay at screen position."""
        try:
            import win32api, win32con, win32gui
        except Exception:
            print("[OVERLAY] WinAPI missing")
            return

        # Already exists → raise it
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
            pass  # class may already be registered

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

        # Rounded corners
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
            
    # ==============================================================
    # Soft auto-align (active window)
    # ==============================================================
        
    def _soft_auto_align_active_window(self):
        """
        Gently nudge the active window upward so its title bar stays inside the
        flick activation zone. Runs only after drags and never touches
        minimized or maximized windows.
        """
        if not self.auto_align_enabled:
            return

        try:
            win = gw.getActiveWindow()
            if not win:
                return

            hwnd = win._hWnd

            # Skip overlay window
            if self and hwnd == self.hwnd:
                return

            # ----------------------------------------------------------
            # Skip protected / system windows
            # ----------------------------------------------------------
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

            # Skip minimized or maximized windows
            placement = win32gui.GetWindowPlacement(hwnd)
            show_cmd = placement[1]
            if show_cmd in (win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED):
                return

            # Current geometry
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top

            threshold = ACTIVATION_Y_MAX + 5
            if top <= threshold:
                return

            # Nudge window upward without resizing
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
        
    # ==============================================================
    # Window mover
    # ==============================================================

    def move_active_window(self, direction: str):
        """Move the active window between monitors, preserving size/state."""
        try:
            # ----------------------------------------------------------
            # Resolve target hwnd (gesture-safe)
            # ----------------------------------------------------------
            hwnd = self.gesture_hwnd

            if not hwnd:
                win = gw.getActiveWindow()
                if not win:
                    print("[MOVE] No active window detected.")
                    return
                hwnd = win._hWnd

            # If overlay somehow became foreground, recover real window
            if self.overlay and hwnd == self.overlay.hwnd:
                hwnd = win32gui.GetForegroundWindow()

            if not hwnd:
                print("[MOVE] Invalid target window.")
                return

            # ----------------------------------------------------------
            # Enumerate monitors
            # ----------------------------------------------------------
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

            # ----------------------------------------------------------
            # Window placement state
            # ----------------------------------------------------------
            placement = win32gui.GetWindowPlacement(hwnd)
            show_cmd = placement[1]
            was_maximized = (show_cmd == win32con.SW_SHOWMAXIMIZED)

            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            restored_width = right - left
            restored_height = bottom - top

            # ----------------------------------------------------------
            # Restore if minimized or maximized
            # ----------------------------------------------------------
            if show_cmd in (win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.02)

                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                restored_width = right - left
                restored_height = bottom - top

            # ----------------------------------------------------------
            # Move window (preserve size)
            # ----------------------------------------------------------
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

            # ----------------------------------------------------------
            # Re-maximize if needed
            # ----------------------------------------------------------
            if was_maximized:
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)

            print(
                f"[MOVE] Window moved to monitor index {target_idx} "
                f"({direction}), maximized={was_maximized}"
            )

        except Exception as e:
            print(f"[ERROR] move_active_window: {e}")
        
    # ==============================================================
    # Gesture lifecycle (Qt-safe, GUI-agnostic)
    # ==============================================================

    def begin_gesture(self, x, y):
        """Enter gesture mode and show overlay (GUI-dispatched if provided)."""
        if not self.enable_mmb:
            return

        self.gesture_active = True

        # Resolve window under cursor at gesture start
        try:
            self.gesture_hwnd = win32gui.WindowFromPoint((x, y))
        except Exception:
            self.gesture_hwnd = None
        finally:
            # Flick baseline MUST always be set
            self.flick_start_x = x
            self.flick_start_time = time.time()

        print(f"[GESTURE] Begin, x={x}")

        if not self.overlay_enabled:
            return

        def _show():
            self.show(x, y)

        # GUI-neutral dispatch (Qt can supply dispatcher)
        try:
            if callable(self.dispatch_ui):
                self.dispatch_ui(_show)
            else:
                _show()
        except Exception as e:
            print("[OVERLAY] Show dispatch failed:", e)

    # ==============================================================
    # Gesture end
    # ==============================================================

    def end_gesture(self):
        """Exit gesture mode and hide overlay (GUI-dispatched if provided)."""
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
        """Background loop: handles flick detection and auto-align."""
        print("[THREAD] Screen mover loop started.")

        SLEEP_INTERVAL = 0.01

        while True:
            if not self.enabled:
                break

            now = time.time()

            # --------------------------------------------------
            # 1) Flick detection (gesture active)
            # --------------------------------------------------
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

                    # Skip auto-align this cycle for responsiveness
                    time.sleep(SLEEP_INTERVAL)
                    continue

            # --------------------------------------------------
            # 2) Soft auto-align (idle state)
            # --------------------------------------------------
            if self.auto_align_enabled and not self.gesture_active:
                try:
                    win = gw.getActiveWindow()
                    if win:
                        hwnd = win._hWnd

                        # Ignore overlay or system windows
                        if (
                            self
                            and hwnd == self.hwnd
                        ) or self._is_system_window(hwnd):
                            self.last_rect = None
                        else:
                            rect = win32gui.GetWindowRect(hwnd)

                            # Window moved since last tick
                            if self.last_rect != rect:
                                self.last_rect = rect
                                self.last_move_time = now
                            else:
                                # Window idle long enough → nudge
                                if (now - self.last_move_time) >= 0.20:
                                    self._soft_auto_align_active_window()

                except Exception as e:
                    print("[AUTO-ALIGN] Error:", e)

            time.sleep(SLEEP_INTERVAL)

    # ==============================================================
    # Worker lifecycle
    # ==============================================================

    def start(self):
        with self.lock:
            if self.enabled:
                return
            
            print("[INFO] Starting Screen-Tab Mover backend…")
            self.enabled = True

            # Load persisted state (GUI-independent)
            state = load_state()
            self.enable_mmb = state.get("mmb_activation_enabled", False)
            self.auto_align_enabled = state.get("auto_align_enabled", False)

            # Background worker loop
            self.thread = threading.Thread(
                target=self.worker_loop,
                name="ScreenMoverWorker",
                daemon=True
            )
            self.thread.start()

            # Global mouse hook
            from pynput import mouse

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
                
    # ==============================================================
    # Mouse hook
    # ==============================================================

    def on_mouse_click(self, x, y, button, pressed, injected):
        if not self.enabled or not self.enable_mmb:
            return

        # Track button state
        if button == mouse.Button.middle:
            self.mmb_down = pressed
        elif button == mouse.Button.left:
            self.lmb_down = pressed

        # ---------------------------------------------------------
        # Cancel active gesture
        # ---------------------------------------------------------
        if self.gesture_active and self.activation_method == "MMB":
            if button == mouse.Button.middle:
                if not pressed:
                    print("[GESTURE] Cancelled → MMB released")
                else:
                    print("[GESTURE] Cancelled → MMB re-press")

                self.end_gesture()
                self.activation_method = None
                return

            # Do not allow re-activation while active
            return

        # ---------------------------------------------------------
        # Activate gesture (MMB)
        # ---------------------------------------------------------
        if (
            button == mouse.Button.middle
            and pressed
            and ACTIVATION_Y_MIN <= y <= ACTIVATION_Y_MAX
        ):
            print(f"[GESTURE] Activated → MMB at ({x},{y})")
            self.activation_method = "MMB"
            self.begin_gesture(x, y)


# ==============================================================
# Win32 Flick Overlay (GUI-agnostic)
# ==============================================================

class FlickOverlay:
    def __init__(self):
        self.hwnd = self._create_overlay_window()


    # ==============================================================
    # Overlay paint handler (Win32, stateless)
    # ==============================================================
    
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
            # Transparent background for text
            win32gui.SetBkMode(hdc, win32con.TRANSPARENT)

            # Fill background (black, fully invisible due to layered window)
            rect = win32gui.GetClientRect(hwnd)
            bg_brush = win32gui.CreateSolidBrush(win32api.RGB(0, 0, 0))
            win32gui.FillRect(hdc, rect, bg_brush)

            # Font definition
            logfont = win32gui.LOGFONT()
            logfont.lfHeight = -35
            logfont.lfWeight = 900
            logfont.lfFaceName = "Rubik UI Symbol"
            logfont.lfQuality = win32con.ANTIALIASED_QUALITY

            font = win32gui.CreateFontIndirect(logfont)
            old_font = win32gui.SelectObject(hdc, font)

            # Arrow colour
            win32gui.SetTextColor(hdc, win32api.RGB(0, 178, 255))

            # Draw arrows
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


    # ==============================================================
    # Flick detection
    # ==============================================================

    def _check_flick(self, current_x):
        """Detect flick at any time while gesture is active."""
        if self.flick_start_x is None:
            return False

        return abs(current_x - self.flick_start_x) >= self.flick_threshold_px

    
    
    # ==============================================================
    # Overlay hider (Qt-safe wrapper)
    # ==============================================================

    def hide_overlay(self):
        """Hide and destroy the Win32 overlay if it exists."""
        if not self.overlay_enabled:
            return

        try:
            if self:
                self.hide()
        except Exception as e:
            print("[OVERLAY] Hide failed:", e)

    # ==============================================================
    # Global worker instance
    # ==============================================================

SCREEN_MOVER = ScreenMoverWorker()













    
    
    

    
    
  
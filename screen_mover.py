
import threading
import time
from pynput import mouse
from state_manager import load_state
import win32gui
import win32con
import win32api
import win32process
import pygetwindow as gw

ACTIVATION_Y_MIN = 0
ACTIVATION_Y_MAX = 40

# ===================================================================
#  Background Worker Object
# ===================================================================

class ScreenMoverWorker:
    def __init__(self):
        self.enabled = False
        self.thread = None
        self.mouse_listener = None
        self.auto_align_enabled = False  
        self.last_rect = None
        self.last_move_time = 0

        self.overlay_hwnd = None
        self.gesture_hwnd = None

        self.mmb_down = False
        self.lmb_down = False
        self.gesture_active = False
        self.activation_method = None

        # Flick tracking
        self.flick_start_x = None
        self.flick_start_time = None
        self.flick_threshold_px = 25  
        self.flick_max_time = 0.35  

        # Activation toggles (GUI controls these)
        self.enable_mmb = False
        self.mmb_ui_enabled = True

        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.enabled:
                return  # already running

            print("[INFO] Starting Screen-Tab Mover backend…")
            self.enabled = True

            # Load current toggle settings
            state = load_state()
            self.enable_mmb = state["mmb_activation_enabled"]
            self.auto_align_enabled = state.get("auto_align_enabled", False)  # NEW
            
            # start background worker thread
            self.thread = threading.Thread(target=self.worker_loop, daemon=True)
            self.thread.start()

            # start global mouse hook
            self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
            self.mouse_listener.start()

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
    #  OVERLAY (WINAPI STATIC WINDOW) defines overlay location
    # ==============================================================

    def _safe_show_overlay(self, x, y):
        """Overlay is ALWAYS topmost, independent of GUI always-on-top state."""
        try:
            import win32api, win32con, win32gui
        except Exception:
            print("[OVERLAY] WinAPI missing")
            return

        # Already exists → raise it
        if self.overlay_hwnd and win32gui.IsWindow(self.overlay_hwnd):
            win32gui.SetWindowPos(
                self.overlay_hwnd,
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
        wndclass.lpfnWndProc = {win32con.WM_PAINT: self._overlay_paint}

        try:
            win32gui.RegisterClass(wndclass)
        except:
            pass

        # Independent topmost popup window (NOT tied to GUI)
        self.overlay_hwnd = win32gui.CreateWindowEx(
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
            0,   # no parent (critical)
            0,
            hinstance,
            None
        )
        
        # Apply rounded corners to overlay window
        rgn = win32gui.CreateRoundRectRgn(
            0, 0, width, height,
            16, 16  # corner radius (X, Y)
        )
        win32gui.SetWindowRgn(self.overlay_hwnd, rgn, True)

        if not self.overlay_hwnd:
            print("[OVERLAY] Failed to create overlay")
            return

        win32gui.SetLayeredWindowAttributes(
            self.overlay_hwnd, 0, 255, win32con.LWA_ALPHA
        )

        # FINAL reinforcement
        win32gui.SetWindowPos(
            self.overlay_hwnd,
            win32con.HWND_TOPMOST,
            pos_x, pos_y, width, height,
            win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE
        )


    #===================================================================
    #===================  Paints the mover icon
    #===================================================================
    
    def _overlay_paint(self, hwnd, msg, wparam, lparam):
        """Custom paint handler for transparent arrow-only overlay."""
        hdc, paint = win32gui.BeginPaint(hwnd)

        # Transparent background mode for text
        win32gui.SetBkMode(hdc, win32con.TRANSPARENT)

        # Fill whole window with BLACK so color key makes it invisible
        rect = win32gui.GetClientRect(hwnd)
        brush = win32gui.CreateSolidBrush(win32api.RGB(0, 0, 0))
        win32gui.FillRect(hdc, rect, brush)

        # --- Draw bright cyan arrows ---
        logfont = win32gui.LOGFONT()
        logfont.lfHeight = -35
        logfont.lfWeight = 900
        logfont.lfFaceName = "Rubik UI Symbol"
        logfont.lfQuality = win32con.ANTIALIASED_QUALITY

        font = win32gui.CreateFontIndirect(logfont)
        win32gui.SelectObject(hdc, font)

        win32gui.SetTextColor(hdc, win32api.RGB(0, 178, 255))

        win32gui.DrawText(
            hdc,
            "⮜   ⮞",
            -1,
            (0, 0, 100, 40),
            win32con.DT_CENTER | win32con.DT_VCENTER | win32con.DT_SINGLELINE
        )

        win32gui.EndPaint(hwnd, paint)
        return 0
    

    # =============================================================
    #  Mouse Hook
    # =============================================================
    
    def on_mouse_click(self, x, y, button, pressed):
        if not self.enabled:
            return
        
        if not self.enable_mmb:
            return
        # UX gate (this is the important one)
        # ---------------------------------------------------------
        # Track button state
        # ---------------------------------------------------------
        
        if button == mouse.Button.middle:
            self.mmb_down = pressed
        elif button == mouse.Button.left:
            self.lmb_down = pressed

        # ---------------------------------------------------------
        #  CANCEL gesture (same logic for both activation types)
        # ---------------------------------------------------------
        
        if self.gesture_active:

            # --- MMB mode: MMB release or press toggles off ---
            if self.activation_method == "MMB":

                # Release ends the gesture
                if button == mouse.Button.middle and not pressed:
                    print("[GESTURE] Cancelled → MMB released")
                    self.end_gesture()
                    self.activation_method = None
                    return

                # Press again cancels immediately
                if button == mouse.Button.middle and pressed:
                    print("[GESTURE] Cancelled → MMB re-press")
                    self.end_gesture()
                    self.activation_method = None
                    return

            # No re-activation while active
            return

        # ---------------------------------------------------------
        #  ACTIVATE gesture (MMB)
        # ---------------------------------------------------------
        
        if self.enable_mmb:
            if button == mouse.Button.middle and pressed:
                if ACTIVATION_Y_MIN <= y <= ACTIVATION_Y_MAX:
                    print(f"[GESTURE] Activated → MMB at ({x},{y})")
                    self.activation_method = "MMB"
                    self.begin_gesture(x, y)
                    return

    def begin_gesture(self, x, y):
        """Enter gesture mode and request overlay creation on the main Tk thread."""
        self.gesture_active = True
        if not self.enable_mmb:
            return

        try:
            # window under cursor at the moment gesture starts
            self.gesture_hwnd = win32gui.WindowFromPoint((x, y))
        except Exception:
            self.gesture_hwnd = None   # <-- IMPORTANT
        finally:
            # Flick baseline MUST always be set
            self.flick_start_x = x
            self.flick_start_time = time.time()

        print(f"[GESTURE] Begin, x={x}")

        # Create overlay safely on the Tkinter main thread
        try:
            if hasattr(self, "app_root") and self.app_root:
                self.app_root.after(0, lambda: self._safe_show_overlay(x, y))
            else:
                threading.Thread(
                    target=lambda: self._safe_show_overlay(x, y),
                    daemon=True
                ).start()
        except Exception as e:
            print("[OVERLAY] Failed to schedule overlay:", e)

            
    #===================================================================
    #===================  Gesture ender
    #===================================================================

    def end_gesture(self):
        """Exit gesture mode and hide overlay."""
        print("[GESTURE] End")
        self.gesture_active = False
        self.activation_method = None
        self.flick_start_x = None
        self.flick_start_time = None
        self.gesture_hwnd = None

        self.hide_overlay()
        

    def _check_flick(self, current_x):
        """Detect flick ANY TIME while gesture is active."""
        if self.flick_start_x is None:
            return False

        distance = abs(current_x - self.flick_start_x)

        return distance >= self.flick_threshold_px
    
    def worker_loop(self):
        """Background loop: checks for flicks while a gesture is active."""
        print("[THREAD] Screen mover loop started.")

        while self.enabled:
            now = time.time()

            # -------------------------
            # 1) Flick detection
            # -------------------------
            
            if self.gesture_active and self.flick_start_x is not None:
                try:
                    x, y = win32api.GetCursorPos()
                except Exception:
                    x = None

                if x is not None:
                    if self._check_flick(x):
                        direction = "RIGHT" if x > self.flick_start_x else "LEFT"
                        print(f"[FLICK] Detected {direction}")
                        self.move_active_window(direction)
                        self.end_gesture()
                        # Skip sleep so UI feels snappy right after flick
                        continue
                    
            time.sleep(0.01)

            # -------------------------
            # 2) Soft Auto-Align (NORMAL)
            # -------------------------
            
            if self.auto_align_enabled and not self.gesture_active:
                try:
                    win = gw.getActiveWindow()
                    if win:
                        hwnd = win._hWnd

                        # Ignore overlay
                        if hwnd == self.overlay_hwnd or self._is_system_window(hwnd):
                            self.last_rect = None
                            continue

                        # Get current rect
                        rect = win32gui.GetWindowRect(hwnd)

                        # If rect changed since last loop → window is being dragged
                        if self.last_rect != rect:
                            self.last_rect = rect
                            self.last_move_time = now
                        else:
                            # Window has stopped moving for 0.2s+
                            if (now - self.last_move_time) >= 0.20:
                                self._soft_auto_align_active_window()
                                    
                except Exception as e:
                    print("[AUTO-ALIGN] Error:", e)

    def move_active_window(self, direction: str):
        """Move the active window between monitors, preserving size/state."""
        try:
            # ------------------------------------------------------------------
            # Resolve target hwnd (gesture-safe)
            # ------------------------------------------------------------------
            hwnd = self.gesture_hwnd

            if not hwnd:
                win = gw.getActiveWindow()
                if not win:
                    print("[MOVE] No active window detected.")
                    return
                hwnd = win._hWnd

            if hwnd == self.overlay_hwnd:
                hwnd = win32gui.GetForegroundWindow()

            # ------------------------------------------------------------------
            # Enumerate monitors
            # ------------------------------------------------------------------

            monitors = win32api.EnumDisplayMonitors()
            if len(monitors) < 2:
                print("[MOVE] Only one monitor detected — skipping move.")
                return

            current_monitor = win32api.MonitorFromWindow(hwnd)
            monitor_handles = [m[0] for m in monitors]

            try:
                idx = monitor_handles.index(current_monitor)
            except ValueError:
                print("[MOVE] Could not find current monitor in list.")
                return

            # Determine target monitor
            if direction == "RIGHT":
                target_idx = (idx + 1) % len(monitors)
            else:
                target_idx = (idx - 1) % len(monitors)

            target_info = win32api.GetMonitorInfo(monitor_handles[target_idx])
            t_left, t_top, t_right, t_bottom = target_info["Work"]

            # ------------------------------------------------------------------
            # Current window placement
            # ------------------------------------------------------------------

            placement = win32gui.GetWindowPlacement(hwnd)
            show_cmd = placement[1]
            was_maximized = (show_cmd == win32con.SW_SHOWMAXIMIZED)

            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            restored_width = right - left
            restored_height = bottom - top

            # ------------------------------------------------------------------
            # STEP 0: Restore if minimized OR maximized
            # ------------------------------------------------------------------

            if show_cmd in (win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.02)

                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                restored_width = right - left
                restored_height = bottom - top

            # ------------------------------------------------------------------
            # STEP 1: MOVE ONLY — keep original size
            # ------------------------------------------------------------------

            cur_left, cur_top, _, _ = win32gui.GetWindowRect(hwnd)

            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                t_left + (left - cur_left),
                t_top  + (top  - cur_top),
                restored_width,
                restored_height,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )

            time.sleep(0.02)

            # ------------------------------------------------------------------
            # STEP 2: Re-maximize if needed
            # ------------------------------------------------------------------

            if was_maximized:
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)

            print(f"[MOVE] Window moved to monitor index {target_idx} ({direction}), maximized={was_maximized}")

        except Exception as e:
            print(f"[ERROR] move_active_window: {e}")

    #===================================================================
    #================ Window Nudger
    #===================================================================
    
    def _force_align_all_windows(self):
        """
        When auto-align is enabled, immediately scan all windows and gently move
        any that are below the flick zone threshold back into the activation zone.
        """
        # Only run if auto-align is enabled
        if not self.auto_align_enabled:
            return

        try:
            import win32gui, win32con, win32process, psutil

            windows = []

            def enum_handler(hwnd, ctx):
                # Must be visible & not minimized
                if not win32gui.IsWindowVisible(hwnd):
                    return
                if win32gui.IsIconic(hwnd):  # minimized
                    return
                windows.append(hwnd)

            # Enumerate all top-level windows
            win32gui.EnumWindows(enum_handler, None)

            for hwnd in windows:
                try:
                    # Skip if it's the overlay
                    if hasattr(self, "overlay_hwnd") and hwnd == self.overlay_hwnd:
                        continue

                    # Skip protected/elevated/system windows
                    try:
                        tid, pid = win32process.GetWindowThreadProcessId(hwnd)
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

                    # Get position
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    height = bottom - top
                    width = right - left

                    # If already above the flick zone threshold → skip
                    threshold = ACTIVATION_Y_MAX + 5
                    if top <= threshold:
                        continue

                    # Move window just slightly below the top edge
                    new_top = 10
                    new_left = left

                    try:
                        win32gui.SetWindowPos(
                            hwnd,
                            win32con.HWND_TOP,
                            new_left,
                            new_top,
                            width,
                            height,
                            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
                        )
                    except Exception as e:
                        # Protected or elevated windows may still block SetWindowPos
                        if "Access is denied" in str(e):
                            continue
                        print("[FORCE-ALIGN] Exception:", e)

                except Exception as inner_e:
                    print("[FORCE-ALIGN] Inner Exception:", inner_e)

        except Exception as outer_e:
            print("[FORCE-ALIGN] Outer Exception:", outer_e)

    def _soft_auto_align_active_window(self):
        """
        Gently nudge the active window upward so its title bar stays inside the
        flick activation zone. This only runs after drags (no mouse buttons down),
        and never touches minimized or maximized windows.
        """
        # Only run if auto-align is enabled
        if not self.auto_align_enabled:
            return


        try:
            win = gw.getActiveWindow()
            if not win:
                return

            hwnd = win._hWnd

            # Skip if our own overlay somehow became active (paranoid guard)
            if hwnd == self.overlay_hwnd:
                return

            # -------------------------------------------------------------
            # Skip protected/elevated/system windows (Task Manager, MMC, etc.)
            # -------------------------------------------------------------
            
            try:
                import psutil, win32process
                tid, pid = win32process.GetWindowThreadProcessId(hwnd)
                exe = psutil.Process(pid).name().lower()

                if exe in (
                    "taskmgr.exe",              # Task Manager
                    "mmc.exe",                  # Device Manager / Event Viewer
                    "systemsettings.exe",       # Windows Settings app
                    "dwm.exe",                  # Desktop Window Manager
                    "explorer.exe",             # Explorer shell windows
                ):
                    return
            except Exception:
                return

            # Check window placement (skip minimized/maximized)
            placement = win32gui.GetWindowPlacement(hwnd)
            show_cmd = placement[1]
            if show_cmd in (win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED):
                return

            # Current window rect
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            height = bottom - top
            width = right - left

            # Only care if the top edge is below the flick band
            threshold = ACTIVATION_Y_MAX + 5
            if top <= threshold:
                return

            # Target top
            new_top = 10
            new_left = left

            # Move window without resizing
            try:
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_TOP,
                    new_left,
                    new_top,
                    width,
                    height,
                    win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
                )
            except Exception as e:
                # Windows blocks SetWindowPos on protected windows → safely ignore
                if "Access is denied" in str(e):
                    return
                print("[AUTO-ALIGN] Exception:", e)

        except Exception as outer_error:
            # A final safety net so the worker thread never crashes
            print("[AUTO-ALIGN] Outer Exception:", outer_error)
    
    # ==============================================================
    #  OVERLAY ICON (SAFE TKINTER VERSION)
    # ==============================================================
    
    def _is_system_window(self, hwnd):
        """Return True if window belongs to Explorer or system popups."""
        try:
            import psutil
            tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            exe = psutil.Process(pid).name().lower()
            return exe in (
                "explorer.exe",               # Taskbar, tray popups
                "shellexperiencehost.exe",    # Windows 10/11 UI
                "startmenuexperiencehost.exe",
                "searchhost.exe",
                "widgets.exe"
            )
        except Exception:
            return False
    
    #===================================================================
    #===================  Overlay hider
    #===================================================================
        
    def hide_overlay(self):
        if self.overlay_hwnd and win32gui.IsWindow(self.overlay_hwnd):
            try:
                win32gui.ShowWindow(self.overlay_hwnd, win32con.SW_HIDE)
                win32gui.DestroyWindow(self.overlay_hwnd)
            except Exception as e:
                if "Access is denied" not in str(e):
                    print("[OVERLAY] Destroy failed:", e)

        self.overlay_hwnd = None

# global instance (created after class definition)
SCREEN_MOVER = ScreenMoverWorker()


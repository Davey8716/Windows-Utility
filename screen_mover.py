
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

    # =============================================================
    #  Mouse Hook
    # =============================================================
    
    def on_mouse_click(self, x, y, button, pressed):
        if not self.enabled:
            return

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

    def begin_gesture(self, x, y):
        """Enter gesture mode and request overlay creation on the main Tk thread."""
        self.gesture_active = True
        self.flick_start_x = x
        self.flick_start_time = time.time()
        print(f"[GESTURE] Begin, x={x}")

        # Create overlay safely on the Tkinter main thread
        try:
            if hasattr(self, "app_root") and self.app_root:
                self.app_root.after(0, lambda: self._safe_show_overlay(x, y))
            else:
                # fallback (still safer than direct call inside pynput thread)
                threading.Thread(target=lambda: self._safe_show_overlay(x, y), daemon=True).start()
        except Exception as e:
            print("[OVERLAY] Failed to schedule overlay:", e)

    def _check_flick(self, current_x):
        """Detect flick ANY TIME while gesture is active."""
        if self.flick_start_x is None:
            return False

        distance = abs(current_x - self.flick_start_x)

        return distance >= self.flick_threshold_px

    def move_active_window(self, direction: str):
        """Move the active window between monitors, preserving size/state."""
        try:
            win = gw.getActiveWindow()
            if not win:
                print("[MOVE] No active window detected.")
                return

            hwnd = win._hWnd

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

            # Window is maximized?
            was_maximized = (show_cmd == win32con.SW_SHOWMAXIMIZED)

            # Window rect BEFORE moving (restored bounds)
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)

            # Restored window size
            restored_width = right - left
            restored_height = bottom - top

            # ------------------------------------------------------------------
            # STEP 0: Restore if minimized OR maximized
            # ------------------------------------------------------------------
            
            if show_cmd in (win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.02)

                # Update restored rect AFTER restore
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                restored_width = right - left
                restored_height = bottom - top

            # ------------------------------------------------------------------
            # STEP 1: MOVE ONLY — keep original size
            # ------------------------------------------------------------------
            
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                t_left + (left - win32gui.GetWindowRect(hwnd)[0]),   # keep relative offset
                t_top + (top  - win32gui.GetWindowRect(hwnd)[1]),
                restored_width,
                restored_height,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )

            time.sleep(0.02)

            # ------------------------------------------------------------------
            # STEP 2: If originally maximized → re-maximize on new monitor
            # ------------------------------------------------------------------
            
            if was_maximized:
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)

            print(f"[MOVE] Window moved to monitor index {target_idx} ({direction}), maximized={was_maximized}")

        except Exception as e:
            print(f"[ERROR] move_active_window: {e}")
            
    #===================================================================
    #================ Window Nudger
    #===================================================================
    
    def _soft_auto_align_active_window(self):
        """
        Gently nudge the active window upward so its title bar stays inside the
        flick activation zone. This only runs after drags (no mouse buttons down),
        and never touches minimized or maximized windows.
        """
        try:
            win = gw.getActiveWindow()
            if not win:
                return

            hwnd = win._hWnd

            # Skip if our own overlay somehow became active (paranoid guard)
            if hwnd == self.overlay_hwnd:
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
            # (add a small margin to avoid micro-jitter)
            threshold = ACTIVATION_Y_MAX + 5  # 45px, a little below the band
            if top <= threshold:
                return

            # Target top = slightly below the top of the screen (e.g., 10px)
            new_top = 10
            new_left = left  # keep horizontal position

            # Move window without resizing
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                new_left,
                new_top,
                width,
                height,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )

            print(f"[AUTO-ALIGN] Nudge window up from top={top} to {new_top}")

        except Exception as e:
            print("[AUTO-ALIGN] Exception:", e)

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

        self.hide_overlay()
        
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

    # ==============================================================
    #  OVERLAY (WINAPI STATIC WINDOW)
    # ==============================================================

    def _safe_show_overlay(self, x, y):
        """Create a modern rounded-corner overlay with bright red arrows."""

        if self.overlay_hwnd and win32gui.IsWindow(self.overlay_hwnd):
            return

        width, height = 150, 75
        pos_x = int(x + 20)
        pos_y = int(y + 20)

        hinstance = win32api.GetModuleHandle(None)

        # Register a custom window class for drawing
        class_name = "FlickOverlayClass"
        wndclass = win32gui.WNDCLASS()
        wndclass.hInstance = hinstance
        wndclass.lpszClassName = class_name
        wndclass.lpfnWndProc = {win32con.WM_PAINT: self._overlay_paint}

        try:
            win32gui.RegisterClass(wndclass)
        except Exception:
            pass  # Already registered

        # Create a layered transparent popup window
        self.overlay_hwnd = win32gui.CreateWindowEx(
            win32con.WS_EX_TOPMOST | win32con.WS_EX_LAYERED | win32con.WS_EX_TOOLWINDOW,
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

        if not self.overlay_hwnd:
            print("[OVERLAY] Failed to create overlay window")
            return

        # Set alpha for full transparency
        win32gui.SetLayeredWindowAttributes(
            self.overlay_hwnd,
            0,
            255,
            win32con.LWA_ALPHA
        )

        # Show window
        win32gui.SetWindowPos(
            self.overlay_hwnd,
            win32con.HWND_TOPMOST,
            pos_x,
            pos_y,
            width,
            height,
            win32con.SWP_SHOWWINDOW
        )

    def _overlay_paint(self, hwnd, msg, wparam, lparam):
        """Custom paint handler for transparent arrow-only overlay."""
        hdc, paint = win32gui.BeginPaint(hwnd)

        # Transparent background
        win32gui.SetBkMode(hdc, win32con.TRANSPARENT)

        # --- Draw bright red arrows only (no rectangle) ---
        logfont = win32gui.LOGFONT()
        logfont.lfHeight = -48
        logfont.lfWeight = 900
        logfont.lfFaceName = "Segoe UI Symbol"

        font = win32gui.CreateFontIndirect(logfont)
        win32gui.SelectObject(hdc, font)

        win32gui.SetTextColor(hdc, win32api.RGB(115, 232, 255))

        win32gui.DrawText(
            hdc,
            "⮜   ⮞",
            -1,
            (0, 0, 150, 75),
            win32con.DT_CENTER | win32con.DT_VCENTER | win32con.DT_SINGLELINE
        )

        win32gui.EndPaint(hwnd, paint)
        return 0

# global instance (created after class definition)
SCREEN_MOVER = ScreenMoverWorker()



import threading
import time
from pynput import mouse
from pynput import keyboard
from state_manager import load_state
import win32gui
import win32con
import win32api
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
        self.keyboard_listener = None

        self.overlay_hwnd = None

        self.mmb_down = False
        self.lmb_down = False
        self.shift_down = False
        self.gesture_active = False
        self.activation_method = None

        # Flick tracking
        self.flick_start_x = None
        self.flick_start_time = None
        self.flick_threshold_px = 180   # distance in pixels
        self.flick_max_time = 0.35      # seconds max for a flick

        # Activation toggles (GUI controls these)
        self.enable_mmb = False
        self.enable_shift = True

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
            self.enable_shift = state["shift_activation_enabled"]

            # start background worker thread
            self.thread = threading.Thread(target=self.worker_loop, daemon=True)
            self.thread.start()

            # start global mouse hook
            self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
            self.mouse_listener.start()

            # start global keyboard hook
            self.keyboard_listener = keyboard.Listener(
                on_press=self.on_key_press,
                on_release=self.on_key_release
            )
            self.keyboard_listener.start()

    def stop(self):
        with self.lock:
            if not self.enabled:
                return

            print("[INFO] Stopping Screen-Tab Mover backend…")
            self.enabled = False

            if self.mouse_listener:
                self.mouse_listener.stop()
                self.mouse_listener = None

            if self.keyboard_listener:
                self.keyboard_listener.stop()
                self.keyboard_listener = None

    # --------------------------------------------------------------
    # Keyboard Hook
    # --------------------------------------------------------------
    
    def on_key_press(self, key):
        """Track when Shift is pressed."""
        try:
            if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                self.shift_down = True
        except Exception:
            pass


    def on_key_release(self, key):
        """Track when Shift is released and cancel Shift-based gesture."""
        try:
            if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                self.shift_down = False

                # If we were in a Shift-based gesture, cancel it when Shift is released
                if self.gesture_active and self.activation_method == "SHIFT":
                    print("[GESTURE] Cancelled → Shift released")
                    self.end_gesture()
                    self.activation_method = None
        except Exception:
            pass

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

            # --- SHIFT MODE: LMB release ends gesture ---
            if self.activation_method == "SHIFT":
                if button == mouse.Button.left and not pressed:
                    print("[GESTURE] Cancelled → LMB released (Shift mode)")
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

        # ---------------------------------------------------------
        #  ACTIVATE gesture (Shift + Left Click)
        # ---------------------------------------------------------
        
        if self.enable_shift:
            if button == mouse.Button.left and pressed and self.shift_down:
                if ACTIVATION_Y_MIN <= y <= ACTIVATION_Y_MAX:
                    print(f"[GESTURE] Activated → Shift+LMB at ({x},{y})")
                    self.activation_method = "SHIFT"
                    self.begin_gesture(x, y)
                    return


    # ==============================================================
    #  OVERLAY ICON (SAFE TKINTER VERSION)
    # ==============================================================
    
    def worker_loop(self):
        """Background loop: checks for flicks while a gesture is active."""
        print("[THREAD] Screen mover loop started.")

        while self.enabled:
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

        print("[THREAD] Screen mover loop ended.")
        
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
        """Move the active window to another monitor using a safe two-step move+resize (no snap, no white flash)."""
        try:
            win = gw.getActiveWindow()
            if not win:
                print("[MOVE] No active window detected.")
                return

            hwnd = win._hWnd

            # Enumerate monitors
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

            # Decide target monitor index
            if direction == "RIGHT":
                target_idx = (idx + 1) % len(monitors)
            else:
                target_idx = (idx - 1) % len(monitors)

            target_info = win32api.GetMonitorInfo(monitor_handles[target_idx])
            work_left, work_top, work_right, work_bottom = target_info["Work"]

            # Current window rect (for current width/height)
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            cur_width = right - left
            cur_height = bottom - top

            # Desired full size on target monitor
            full_width = work_right - work_left
            full_height = work_bottom - work_top

            # ------------------------------------------------------------------
            # STEP 0: If minimized, restore first so move/resize works cleanly
            # ------------------------------------------------------------------
            placement = win32gui.GetWindowPlacement(hwnd)
            show_cmd = placement[1]
            if show_cmd == win32con.SW_SHOWMINIMIZED:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

            # ------------------------------------------------------------------
            # STEP 1: Move ONLY (keep current size)
            # ------------------------------------------------------------------
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                work_left,
                work_top,
                cur_width,
                cur_height,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )

            # Small delay to let Windows/GPU settle the move before resizing
            time.sleep(0.02)

            # ------------------------------------------------------------------
            # STEP 2: Resize ONLY (fill the work area on target monitor)
            # ------------------------------------------------------------------
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                work_left,
                work_top,
                full_width,
                full_height,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )

            print(f"[MOVE] Window moved to monitor index {target_idx} ({direction}).")

        except Exception as e:
            print(f"[ERROR] move_active_window: {e}")


    def end_gesture(self):
        """Exit gesture mode and hide overlay."""
        print("[GESTURE] End")
        self.gesture_active = False
        self.activation_method = None
        self.flick_start_x = None
        self.flick_start_time = None

        self.hide_overlay()

    # ==============================================================
    #  OVERLAY (WINAPI STATIC WINDOW)
    # ==============================================================

    def _safe_show_overlay(self, x, y):
        """Create the small topmost WinAPI window near the cursor (bold block ⇐ ⇒ arrows)."""

        # If already visible, do nothing
        if self.overlay_hwnd and win32gui.IsWindow(self.overlay_hwnd):
            return

        width, height = 70, 34
        pos_x = int(x + 12)
        pos_y = int(y + 12)

        hinstance = win32api.GetModuleHandle(None)

        # NEW bold block arrows (thick ⇐ ⇒)
        ARROW_SYMBOL = "⇐ ⇒"

        # Create STATIC window
        self.overlay_hwnd = win32gui.CreateWindowEx(
            win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW,
            "STATIC",
            ARROW_SYMBOL,
            win32con.WS_POPUP | win32con.SS_CENTER,
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

        # Background: dark grey
        win32gui.SetBkColor(self.overlay_hwnd, win32api.RGB(25, 25, 25))

        # Bright green arrow text
        win32gui.SetTextColor(self.overlay_hwnd, win32api.RGB(0, 255, 0))

        # Bold readable font
        LOGFONT = win32gui.LOGFONT()
        LOGFONT.lfHeight = 24
        LOGFONT.lfWeight = 700
        LOGFONT.lfFaceName = "Segoe UI Symbol"
        hfont = win32gui.CreateFontIndirect(LOGFONT)

        try:
            win32gui.SendMessage(self.overlay_hwnd, win32con.WM_SETFONT, hfont, True)
        except Exception as e:
            print("[OVERLAY] WM_SETFONT failed:", e)

        # Show window safely
        if win32gui.IsWindow(self.overlay_hwnd):
            win32gui.SetWindowPos(
                self.overlay_hwnd,
                win32con.HWND_TOPMOST,
                pos_x,
                pos_y,
                width,
                height,
                win32con.SWP_SHOWWINDOW
            )
        else:
            print("[OVERLAY] Window died before SetWindowPos")

    def hide_overlay(self):
        """Destroy the overlay window if it exists (safe)."""
        if self.overlay_hwnd and win32gui.IsWindow(self.overlay_hwnd):
            try:
                win32gui.ShowWindow(self.overlay_hwnd, win32con.SW_HIDE)
                win32gui.DestroyWindow(self.overlay_hwnd)
            except Exception as e:
                # Silently ignore expected destruction errors
                if "Access is denied" not in str(e):
                    print("[OVERLAY] Destroy failed:", e)

        self.overlay_hwnd = None

# global instance (created after class definition)
SCREEN_MOVER = ScreenMoverWorker()


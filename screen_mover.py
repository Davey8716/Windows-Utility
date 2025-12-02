
import threading
import time
import tkinter as tk
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
        self.overlay_root = None
        self.overlay = None
        self.mmb_down = False
        self.lmb_down = False
        self.shift_down = False
        self.gesture_active = False
        self.keyboard_listener = None
        self.activation_method = None
        self.enable_mmb = False
        self.enable_shift = True
        self.app_root = None
        self.flick_start_x = None
        self.flick_start_time = None
        self.flick_threshold = 120      # pixels travelled
        self.flick_speed_min = 0.25     # seconds max for the motion

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
        try:
            if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                self.shift_down = True
        except:
            pass

    def on_key_release(self, key):
        try:
            if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                self.shift_down = False
        except:
            pass

    # =============================================================
    #  Mouse Hook
    # =============================================================
    
    def on_mouse_click(self, x, y, button, pressed):
        if not self.enabled:
            return

        # Track button state
        if button == mouse.Button.middle:
            self.mmb_down = pressed
        if button == mouse.Button.left:
            self.lmb_down = pressed

        # ---------------------------------------------------------
        #  CANCEL gesture (works for both MMB + Shift activations)
        # ---------------------------------------------------------
        
        if self.gesture_active:

            # Cancel via MMB (toggle-off)
            if self.enable_mmb and button == mouse.Button.middle and pressed:
                print("[GESTURE] Cancelled → MMB")
                self.end_gesture()
                
                return

            # Cancel via LMB when SHIFT was the activation method
            if self.activation_method == "SHIFT" and self.enable_shift:
                if button == mouse.Button.left and pressed:  # shift NOT required for cancel
                    print("[GESTURE] Cancelled → Shift+LMB")
                    self.end_gesture()
                    
                    return

            return  # gesture active → do not run activation logic

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
        # Cancel gesture on release (for MMB mode)
        # ---------------------------------------------------------
        
        if not pressed and self.activation_method == "MMB":
            if self.gesture_active:
                print("[GESTURE] Cancel → MMB Release")
                self.end_gesture()
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

    import tkinter as tk

    # ==============================================================
    #  OVERLAY ICON (SAFE TKINTER VERSION)
    # ==============================================================
    
    def worker_loop(self):
        while self.enabled:
            if self.gesture_active:
                # Get current cursor position
                x, y = win32api.GetCursorPos()

                # Detect flick
                if self.check_flick(x):
                    direction = "RIGHT" if x > self.flick_start_x else "LEFT"
                    print(f"[FLICK] Detected {direction}")
                    self.move_active_window(direction)
                    self.end_gesture()
                    continue

        time.sleep(0.01)

    def show_overlay(self, x, y):
        """Create a small arrow overlay window safely on the main thread."""

        if self.overlay_root:   # Already visible
            return

        # Create a borderless Toplevel window
        self.overlay_root = tk.Toplevel()
        self.overlay_root.overrideredirect(True)
        self.overlay_root.attributes("-topmost", True)

        # Position slightly offset from the mouse
        self.overlay_root.geometry(f"+{x+10}+{y+10}")

        # Prevent the window from grabbing focus
        self.overlay_root.attributes("-disabled", True)
        self.overlay_root.lift()

        # Arrow icon (text for now)
        self.overlay = tk.Label(
            self.overlay_root,
            text="⇆",
            font=("Segoe UI", 18, "bold"),
            fg="white",
            bg="#1f6aa5",
            padx=10,
            pady=5
        )
        self.overlay_root.configure(bg="#1f6aa5")
        self.overlay_root.attributes("-alpha", 0.92)    
        self.overlay.pack()

    def hide_overlay(self):
        """Safely destroy the overlay window."""
        if self.overlay_root is not None:
            try:
                self.overlay_root.destroy()
            except:
                pass

        self.overlay_root = None
        self.overlay = None

    def begin_gesture(self, x, y):
        self.gesture_active = True
        self.activation_method = self.activation_method or "UNKNOWN"

        # Save flick starting data
        self.flick_start_x = x
        self.flick_start_time = time.time()

        # schedule overlay creation
        try:
            self.app_root.after(0, lambda: self.show_overlay(x, y))
        except:
            self.show_overlay(x, y)

    def check_flick(self, current_x):
        if self.flick_start_x is None:
            return False

        distance = abs(current_x - self.flick_start_x)
        elapsed = time.time() - self.flick_start_time

        # Must be fast and far
        return distance >= self.flick_threshold and elapsed <= self.flick_speed_min

    def move_active_window(self, direction):
        try:
            win = gw.getActiveWindow()
            if not win:
                print("[MOVE] No active window")
                return

            hwnd = win._hWnd

            # Get monitor info
            monitors = win32api.EnumDisplayMonitors()
            if len(monitors) < 2:
                print("[MOVE] Only one monitor — skipping")
                return

            # Determine current monitor
            current_monitor = win32api.MonitorFromWindow(hwnd)
            monitor_order = [m[0] for m in monitors]
            idx = monitor_order.index(current_monitor)

            # Determine target monitor
            if direction == "RIGHT":
                target_idx = (idx + 1) % len(monitors)
            else:
                target_idx = (idx - 1) % len(monitors)

            target_rect = win32api.GetMonitorInfo(monitor_order[target_idx])["Work"]

            # Move and maximize
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOP,
                target_rect[0], target_rect[1],
                target_rect[2] - target_rect[0],
                target_rect[3] - target_rect[1],
                0
            )

            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            print(f"[MOVE] Window moved to monitor {target_idx}")

        except Exception as e:
            print(f"[ERROR] move_active_window: {e}")

    def end_gesture(self):
        """End the gesture and hide the overlay."""
        self.gesture_active = False
        self.activation_method

        try:
            self.app_root.after(0, self.hide_overlay)
        except:
            self.hide_overlay()

# global instance (created after class definition)
SCREEN_MOVER = ScreenMoverWorker()


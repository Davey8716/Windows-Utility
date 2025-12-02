
import threading
import time
import tkinter as tk
from pynput import mouse
from pynput import keyboard

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
        self.lock = threading.Lock()

    # --------------------------------------------------------------
    def start(self):
        with self.lock:
            if self.enabled:
                return  # already running

            print("[INFO] Starting Screen-Tab Mover backend…")
            self.enabled = True

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

    # --------------------------------------------------------------
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

            # thread ends naturally when enabled becomes False
            
    # --------------------------------------------------------------
    # 🔵 ADD THESE RIGHT HERE
    # -------------------------------------------------------------
    
    def on_key_press(self, key):
        # Detect Shift pressed
        try:
            if key == keyboard.Key.shift or key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                self.shift_down = True
        except:
            pass

    def on_key_release(self, key):
        # Detect Shift released
        try:
            if key == keyboard.Key.shift or key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                self.shift_down = False
        except:
            pass

    # =============================================================
    #  MOUSE HOOK
    # =============================================================

    def on_mouse_click(self, x, y, button, pressed):
        if not self.enabled:
            return

        # -------------------------
        # Track button state
        # -------------------------
        if button == mouse.Button.middle:
            self.mmb_down = pressed

        if button == mouse.Button.left:
            self.lmb_down = pressed

        # ---------------------------------------------------------
        #  CANCEL gesture if already active
        # ---------------------------------------------------------
        if self.gesture_active:

            # Cancel via Middle Mouse Button (always allowed)
            if button == mouse.Button.middle and pressed:
                print("[GESTURE] Cancelled → MMB")
                self.end_gesture()
                self.activation_method = None
                return

            # Cancel via Shift + Left Click (only if SHIFT activation)
            if self.activation_method == "SHIFT":
                if button == mouse.Button.left and pressed and self.shift_down:
                    print("[GESTURE] Cancelled → Shift+LMB")
                    self.end_gesture()
                    self.activation_method = None
                    return

            # While gesture is active, skip activation logic.
            return

        # ---------------------------------------------------------
        #  ACTIVATE gesture (MMB)
        # ---------------------------------------------------------
        
        if button == mouse.Button.middle and pressed:
            if ACTIVATION_Y_MIN <= y <= ACTIVATION_Y_MAX:
                print(f"[GESTURE] Activated → MMB at ({x},{y})")
                self.activation_method = "MMB"
                self.begin_gesture(x, y)
                return

        # ---------------------------------------------------------
        #  ACTIVATE gesture (Shift + Left Click)
        # ---------------------------------------------------------
        
        if button == mouse.Button.left and pressed and self.shift_down:
            if ACTIVATION_Y_MIN <= y <= ACTIVATION_Y_MAX:
                print(f"[GESTURE] Activated → Shift+LMB at ({x},{y})")
                self.activation_method = "SHIFT"
                self.begin_gesture(x, y)
                return

    # ==============================================================
    #  OVERLAY ICON (SMALL ARROW INDICATOR)
    # ==============================================================
    
    def show_overlay(self, x, y):
        if self.overlay_root:
            return  # already visible

        # Make a tiny borderless window
        self.overlay_root = tk.Tk()
        self.overlay_root.overrideredirect(True)
        self.overlay_root.attributes("-topmost", True)
        self.overlay_root.geometry(f"+{x+10}+{y+10}")

        # Simple text-based arrow icon
        # Later you can replace this with an actual PNG
        self.overlay = tk.Label(self.overlay_root, text="↔", font=("Segoe UI", 32), bg="white", fg="black")
        self.overlay.pack()

        # Run on separate thread so it doesn't block
        threading.Thread(target=self._overlay_loop, daemon=True).start()

    def _overlay_loop(self):
        try:
            self.overlay_root.mainloop()
        except:
            pass

    def hide_overlay(self):
        if hasattr(self, "overlay_root") and self.overlay_root:
            try:
                self.overlay_root.destroy()
            except:
                pass
        self.overlay_root = None
        self.overlay = None
        
    def begin_gesture(self, x, y):
        """Enter gesture mode and show overlay."""
        self.gesture_active = True
        self.show_overlay(x, y)

    def end_gesture(self):
        """Exit gesture mode and hide overlay."""
        self.gesture_active = False
        self.hide_overlay()

    def worker_loop(self):
        """Runs continually when enabled."""
        print("[THREAD] Screen mover loop started.")

        while self.enabled:
            # Placeholder for:
            # • detect when mouse is in browser tab region
            # • show overlay icon
            # • detect mouse flick velocity
            # • determine target monitor
            # • move window

            time.sleep(0.01)

        print("[THREAD] Screen mover loop ended.")

# global instance (created after class definition)
SCREEN_MOVER = ScreenMoverWorker()


# ===================================================================
#  Screen Tab Mover + USB Reminder Control Panel
#  Modern 400x400 UI using CustomTkinter
# ===================================================================

import customtkinter as ctk
import threading
import json
import os
import time
from pynput import mouse  # install: pip install pynput

# Configure appearance
ctk.set_appearance_mode("Dark")          # "System", "Dark", "Light"
ctk.set_default_color_theme("blue")      # "blue", "green", "dark-blue"

CONFIG_PATH = "screen_mover_state.json"


def save_state(enabled: bool):
    """Persist ON/OFF toggle across restarts."""
    with open(CONFIG_PATH, "w") as f:
        json.dump({"screen_mover_enabled": enabled}, f)


def load_state() -> bool:
    """Load saved state."""
    if not os.path.exists(CONFIG_PATH):
        return False
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
            return data.get("screen_mover_enabled", False)
    except:
        return False


# ===================================================================
#  Background Worker Object
# ===================================================================
class ScreenMoverWorker:
    def __init__(self):
        self.enabled = False
        self.thread = None
        self.mouse_listener = None
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

            # thread ends naturally when enabled becomes False

    # --------------------------------------------------------------
    def on_mouse_click(self, x, y, button, pressed):
        """This will listen for mouse clicks globally."""
        if not self.enabled:
            return

        # Placeholder — real logic later
        # This is where you will detect left+right, flicks, screen switching.
        if pressed:
            print(f"[HOOK] Mouse press at {x}, {y}, button={button}")

    # --------------------------------------------------------------
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


# ===================================================================
#  Main App
# ===================================================================
class UtilityControlApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Utility Control Panel")
        self.geometry("300x300")
        self.resizable(False, False)

        # ------------------------------------------------------------------
        #  Title Label
        # ------------------------------------------------------------------
        title = ctk.CTkLabel(self, text="Utility Suite", font=("Segoe UI", 24))
        title.pack(pady=10)

        # ------------------------------------------------------------------
        #  Screen Tab Mover toggle
        # ------------------------------------------------------------------
        self.screen_mover_var = ctk.BooleanVar(value=False)
        self.screen_mover_switch = ctk.CTkSwitch(
            self,
            text="Screen-Tab Mover",
            variable=self.screen_mover_var,
            command=self.on_screen_mover_toggle,
            font=("Segoe UI", 16)
        )
        self.screen_mover_switch.pack(pady=10)

        # ------------------------------------------------------------------
        #  USB Reminder Main Switch
        # ------------------------------------------------------------------
        self.usb_reminder_var = ctk.BooleanVar(value=False)
        self.usb_reminder_switch = ctk.CTkSwitch(
            self,
            text="USB Reminder",
            variable=self.usb_reminder_var,
            command=self.on_usb_reminder_toggle,
            font=("Segoe UI", 16)
        )
        self.usb_reminder_switch.pack(pady=10)

        # ------------------------------------------------------------------
        #  USB Reminder Sub-Options Frame
        # ------------------------------------------------------------------
        self.usb_frame = ctk.CTkFrame(self)
        self.usb_frame.pack(pady=10, padx=10, fill="x")

        usb_label = ctk.CTkLabel(self.usb_frame, text="Reminder Options:", font=("Segoe UI", 14))
        usb_label.pack(pady=(5, 5))

        self.opt_idle_var = ctk.BooleanVar(value=False)
        self.opt_idle = ctk.CTkSwitch(
            self.usb_frame,
            text="Idle-plugged Reminder",
            variable=self.opt_idle_var,
            font=("Segoe UI", 13)
        )
        self.opt_idle.pack(anchor="w", padx=10, pady=2)

        self.opt_download_var = ctk.BooleanVar(value=False)
        self.opt_download = ctk.CTkSwitch(
            self.usb_frame,
            text="Download-finished Reminder",
            variable=self.opt_download_var,
            font=("Segoe UI", 13)
        )
        self.opt_download.pack(anchor="w", padx=10, pady=2)

        self.opt_plug_var = ctk.BooleanVar(value=True)
        self.opt_plug = ctk.CTkSwitch(
            self.usb_frame,
            text="Plug / Unplug Notification",
            variable=self.opt_plug_var,
            font=("Segoe UI", 13)
        )
        self.opt_plug.pack(anchor="w", padx=10, pady=2)

        # Start with USB settings disabled
        self.toggle_usb_options(False)

    # ===================================================================
    #  UI Logic Only — attach real backend later
    # ===================================================================
    def toggle_usb_options(self, enable: bool):
        """Enable/disable the sub-toggles under USB Reminder."""
        state = "normal" if enable else "disabled"
        self.opt_idle.configure(state=state)
        self.opt_download.configure(state=state)
        self.opt_plug.configure(state=state)

    # ------------------------------------------------------------------
    def on_usb_reminder_toggle(self):
        enabled = self.usb_reminder_var.get()
        print(f"[INFO] USB Reminder toggled → {enabled}")
        self.toggle_usb_options(enabled)

    # ------------------------------------------------------------------
    def on_screen_mover_toggle(self):
        enabled = self.screen_mover_var.get()
        print(f"[INFO] Screen-Tab Mover toggled → {enabled}")

        # Save state
        save_state(enabled)

        # Activate/deactivate backend
        if enabled:
            SCREEN_MOVER.start()
        else:
            SCREEN_MOVER.stop()


# ===================================================================
# Launch
# ===================================================================
if __name__ == "__main__":
    app = UtilityControlApp()
    app.mainloop()

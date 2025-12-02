# ===================================================================
#  Screen Tab Mover + USB Reminder Control Panel
#  Modern 400x400 UI using CustomTkinter
# ===================================================================

import customtkinter as ctk
from screen_mover import SCREEN_MOVER
from state_manager import load_state, save_state

# Configure appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ===================================================================
#  Main App Gui
# ===================================================================
class UtilityControlApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Load saved state
        state = load_state()

        self.title("Utility Control Panel")
        self.geometry("400x400")
        self.resizable(False, False)

        # ------------------------------------------------------------------
        #  Title Label
        # ------------------------------------------------------------------
        title = ctk.CTkLabel(self, text="Utility Suite", font=("Segoe UI", 24))
        title.pack(pady=10)

        # ------------------------------------------------------------------
        #  Screen Tab Mover toggle
        # ------------------------------------------------------------------
        self.screen_mover_var = ctk.BooleanVar(value=state["screen_mover_enabled"])
        self.screen_mover_switch = ctk.CTkSwitch(
            self,
            text="Screen-Tab Mover",
            variable=self.screen_mover_var,
            command=self.on_screen_mover_toggle,
            font=("Segoe UI", 16)
        )
        self.screen_mover_switch.pack(pady=10)
        
        # ------------------------------------------------------------------
        #  Activation Method Toggles
        # ------------------------------------------------------------------
        self.mmb_var = ctk.BooleanVar(value=state["mmb_activation_enabled"])
        self.mmb_switch = ctk.CTkSwitch(
            self,
            text="Enable Middle Mouse Activation",
            variable=self.mmb_var,
            command=self.save_all_settings
        )
        self.mmb_switch.pack(pady=5)

        self.shift_var = ctk.BooleanVar(value=state["shift_activation_enabled"])
        self.shift_switch = ctk.CTkSwitch(
            self,
            text="Enable Shift + LeftClick Activation",
            variable=self.shift_var,
            command=self.save_all_settings
        )
        self.shift_switch.pack(pady=5)

        # ------------------------------------------------------------------
        #  USB Reminder Main Switch  (UNCHANGED)
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
        #  USB Reminder Sub-Options Frame  (UNCHANGED)
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

        # Start with USB settings disabled (UNCHANGED)
        self.toggle_usb_options(False)

        # Auto-start backend if saved state says it should be ON
        if state["screen_mover_enabled"]:
            SCREEN_MOVER.start()

    # ===================================================================
    #  UI Logic — USB Reminder Options  (UNCHANGED)
    # ===================================================================
    def toggle_usb_options(self, enable: bool):
        state = "normal" if enable else "disabled"
        self.opt_idle.configure(state=state)
        self.opt_download.configure(state=state)
        self.opt_plug.configure(state=state)

    # ------------------------------------------------------------------
    def on_usb_reminder_toggle(self):
        enabled = self.usb_reminder_var.get()
        print(f"[INFO] USB Reminder toggled → {enabled}")
        self.toggle_usb_options(enabled)

    # ===================================================================
    #  Screen Tab Mover Toggle Logic
    # ===================================================================
    def on_screen_mover_toggle(self):
        enabled = self.screen_mover_var.get()
        print(f"[INFO] Screen-Tab Mover toggled → {enabled}")

        # Save new value
        self.save_all_settings()

        # Start or stop backend worker
        if enabled:
            SCREEN_MOVER.start()
        else:
            SCREEN_MOVER.stop()

    # ===================================================================
    #  Save ALL toggle states to JSON
    # ===================================================================
    def save_all_settings(self):
        current = load_state()
        current["screen_mover_enabled"] = self.screen_mover_var.get()
        current["mmb_activation_enabled"] = self.mmb_var.get()
        current["shift_activation_enabled"] = self.shift_var.get()
        save_state(current)
        
        # Update backend live
        SCREEN_MOVER.enable_mmb = self.mmb_var.get()
        SCREEN_MOVER.enable_shift = self.shift_var.get()

# ===================================================================
# Launch App
# ===================================================================
if __name__ == "__main__":
    app = UtilityControlApp()
    app.mainloop()

# ===================================================================
#  Screen Tab Mover + USB Reminder Control Panel
#  Modern 400x400 UI using CustomTkinter
# ===================================================================

import customtkinter as ctk
from screen_mover import SCREEN_MOVER
from state_manager import load_state, save_state
from PIL import Image, ImageDraw

import threading
import pystray

# Configure appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ===================================================================
#  Main App Gui
# ===================================================================

class UtilityControlApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        SCREEN_MOVER.app_root = self   # <-- correct location

        
        # Load saved state
        state = load_state()

        self.title("Utility Control Panel")
        self.geometry("400x400")
        self.resizable(False, False)
        
        # Tray-related attributes
        self.tray_icon = None
        self.tray_thread = None
        
        # When user clicks the window close button → hide to tray
        self.protocol("WM_DELETE_WINDOW", self.on_close_to_tray)
        
        # Auto-start backend if saved state says it should be ON
        if state["screen_mover_enabled"]:
            SCREEN_MOVER.start()

        # Create system tray icon (runs in background thread)
        self.create_tray_icon()

        # ------------------------------------------------------------------
        #  Title Label
        # ------------------------------------------------------------------
        
        title = ctk.CTkLabel(self, text="Utility Suite", font=("Segoe UI", 24))
        title.pack(pady=10)

        # ------------------------------------------------------------------
        #  Screen-Tab Mover Group Box
        # ------------------------------------------------------------------
        
        self.screen_mover_var = ctk.BooleanVar(value=state["screen_mover_enabled"])
        self.screen_mover_switch = ctk.CTkSwitch(
            self,
            text="Enable Screen-Tab Mover",
            variable=self.screen_mover_var,
            command=self.on_screen_mover_toggle,
            font=("Segoe UI", 13)
        )
        self.screen_mover_switch.pack(pady=10)
        
        # ------------------------------------------------------------------
        #  Screen-Tab Mover Group Box(frame)
        # ------------------------------------------------------------------
        
        self.mover_frame = ctk.CTkFrame(self)
        self.mover_frame.pack(pady=10, padx=10, fill="x")

        mover_label = ctk.CTkLabel(self.mover_frame, text="Screen-Tab Mover", font=("Segoe UI", 14))
        mover_label.pack(pady=(5, 5))

        self.mmb_var = ctk.BooleanVar(value=state["mmb_activation_enabled"])
        self.mmb_switch = ctk.CTkSwitch(
            self.mover_frame,
            text="Middle Mouse Activation",
            variable=self.mmb_var,
            command=self.save_all_settings,
            font=("Segoe UI", 13)
        )
        self.mmb_switch.pack(anchor="w", padx=10, pady=2)

        self.shift_var = ctk.BooleanVar(value=state["shift_activation_enabled"])
        self.shift_switch = ctk.CTkSwitch(
            self.mover_frame,
            text="Shift + Left Click Activation",
            variable=self.shift_var,
            command=self.save_all_settings,
            font=("Segoe UI", 13)
        )
        self.shift_switch.pack(anchor="w", padx=10, pady=2)
        # Start Mover sub-options in correct state
        self.toggle_mover_options(self.screen_mover_var.get())

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

        self.opt_plug_var = ctk.BooleanVar(value=False)
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
    #  USB Reminder UI Logic (placeholder for future backend)
    # ===================================================================
    
    def toggle_usb_options(self, enable: bool):
        state = "normal" if enable else "disabled"
        self.opt_idle.configure(state=state)
        self.opt_download.configure(state=state)
        self.opt_plug.configure(state=state)

    def on_usb_reminder_toggle(self):
        enabled = self.usb_reminder_var.get()
        print(f"[INFO] USB Reminder toggled → {enabled}")
        self.toggle_usb_options(enabled)
    
    def toggle_mover_options(self, enable: bool):
        state = "normal" if enable else "disabled"
        self.mmb_switch.configure(state=state)
        self.shift_switch.configure(state=state)

    # ===================================================================
    #  Screen Tab Mover Logic
    # ===================================================================
    
    def on_screen_mover_toggle(self):
        enabled = self.screen_mover_var.get()
        print(f"[INFO] Screen-Tab Mover toggled → {enabled}")
        
        # Grey/enable activation options
        self.toggle_mover_options(enabled)

        # Save new value
        self.save_all_settings()

        # Start or stop backend worker
        if enabled:
            SCREEN_MOVER.start()
        else:
            SCREEN_MOVER.stop()

    def save_all_settings(self):
        old = load_state()   # previous saved values

        new = {}

        # -------------------------
        # Screen Mover settings
        # -------------------------
        
        new["screen_mover_enabled"] = self.screen_mover_var.get()
        new["mmb_activation_enabled"] = self.mmb_var.get()
        new["shift_activation_enabled"] = self.shift_var.get()

        # Live update backend
        SCREEN_MOVER.enable_mmb = new["mmb_activation_enabled"]
        SCREEN_MOVER.enable_shift = new["shift_activation_enabled"]

        # -------------------------
        # USB settings
        # -------------------------
        
        new["usb_enabled"] = self.usb_reminder_var.get()
        new["usb_idle_enabled"] = self.opt_idle_var.get()
        new["usb_download_enabled"] = self.opt_download_var.get()
        new["usb_plug_enabled"] = self.opt_plug_var.get()

        # -------------------------
        # Debug only changed keys
        # -------------------------
        
        for key, value in new.items():
            if key not in old or old[key] != value:
                print(f"[DEBUG] {key} → {value}")

        # -------------------------
        # Save JSON
        # -------------------------
        
        save_state(new)

    # ===================================================================
    #  Tray Icon Logic
    # ===================================================================
    
    def create_tray_icon(self):
        """Create and start the system tray icon in a background thread."""

        # Create a simple blue square icon (matches CTk blue theme)
        def make_icon_image(size=64):
            img = Image.new("RGBA", (size, size), (26, 115, 232, 255))  # blue-ish
            draw = ImageDraw.Draw(img)
            # Optional: draw a slightly lighter inner square
            margin = size // 8
            draw.rectangle(
                [margin, margin, size - margin, size - margin],
                fill=(41, 140, 255, 255)
            )
            return img

        image = make_icon_image()

        # Tray menu
        menu = pystray.Menu(
            pystray.MenuItem("Toggle Window", self.tray_menu_toggle, default=True),
            pystray.MenuItem("Show", self.tray_menu_show),
            pystray.MenuItem("Hide", self.tray_menu_hide),
            pystray.MenuItem("Quit", self.tray_menu_quit)
        )

        self.tray_icon = pystray.Icon(
            "WindowsUtility",
            image,
            "Utility Suite",
            menu
        )

        def run_tray():
            self.tray_icon.run()

        self.tray_thread = threading.Thread(target=run_tray, daemon=True)
        self.tray_thread.start()

    # ---------------- Tray menu callbacks (run in tray thread) ----------
    def tray_menu_show(self, icon, item):
        # Schedule GUI work on Tk main thread
        self.after(0, self._show_window)

    def tray_menu_hide(self, icon, item):
        self.after(0, self.withdraw)
        
    def tray_menu_toggle(self, icon, item):
        """Double-click → toggle window show/hide."""
        self.after(0, self._toggle_window)
        
    def _toggle_window(self):
        if self.state() == "withdrawn":
            self._show_window()
        else:
            self.withdraw()

    def tray_menu_quit(self, icon, item):
        self.after(0, self._quit_from_tray)

    # ---------------- Helpers that run on Tk main thread ----------------
    def _show_window(self):
        self.deiconify()
        self.lift()
        try:
            self.focus_force()
        except:
            pass

    def _quit_from_tray(self):
        print("[INFO] Quitting from tray…")
        try:
            SCREEN_MOVER.stop()
        except:
            pass

        if self.tray_icon:
            # Hide and stop tray icon loop
            self.tray_icon.visible = False
            self.tray_icon.stop()

        self.destroy()

    # ===================================================================
    #  Hide-on-close behaviour
    # ===================================================================
    
    def on_close_to_tray(self):
        """User clicked the X → hide window instead of exiting."""
        print("[INFO] Window hidden to tray")
        self.withdraw()

# ===================================================================
# Launch App
# ===================================================================

if __name__ == "__main__":
    app = UtilityControlApp()
    app.mainloop()

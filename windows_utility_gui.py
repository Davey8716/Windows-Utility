# ===================================================================
#  Screen Tab Mover + USB Reminder Control Panel
#  Modern UI using CustomTkinter
# ===================================================================

import customtkinter as ctk
from screen_mover import SCREEN_MOVER
from state_manager import load_state, save_state
from PIL import Image, ImageDraw
import threading
import pystray
from usb_reminder import toggle_usb_options, toggle_mover_options, on_usb_reminder_toggle
from theme_manager import switch_theme   # add at top with other imports

# Configure appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ===================================================================
#  Main App Gui
# ===================================================================

class UtilityControlApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        SCREEN_MOVER.app_root = self

        # Load saved state
        self.saved_state = load_state()
        
        # Restore theme mode on startup
        self.theme_var = ctk.BooleanVar(value=self.saved_state.get("theme_dark", True))
        switch_theme(self.theme_var.get())


        self.title("Utility Control Panel")
        self.geometry("600x600")
        self.resizable(False, False)

        # Tray
        self.tray_icon = None
        self.tray_thread = None
        self.protocol("WM_DELETE_WINDOW", self.on_close_to_tray)

        # Auto-start backend if saved state says it should be ON
        if self.saved_state["screen_mover_enabled"]:
            SCREEN_MOVER.start()

        # System tray icon
        self.create_tray_icon()

        # --------------------------------------------------------------
        # Title
        # --------------------------------------------------------------
        title = ctk.CTkLabel(self, text="Utility Suite", font=("Segoe UI", 24))
        title.pack(pady=10)

        # --------------------------------------------------------------
        # Dark / Light Mode Toggle  (correctly placed)
        # --------------------------------------------------------------
        self.theme_var = ctk.BooleanVar(value=True)

        self.theme_switch = ctk.CTkSwitch(
            self,
            text="Dark Mode",
            variable=self.theme_var,
            command=self.on_theme_toggle,
            font=("Segoe UI", 16)
        )

        self.theme_switch.pack(
            anchor="w",     # ← aligns to the left edge
            padx=18,        # ← add optional padding so it isn’t touching the border
            pady=(5, 5)
        )
        
        # ------------------------------------------------------------------
        #  Screen-Tab Mover Group Box
        # ------------------------------------------------------------------
        
        self.screen_mover_var = ctk.BooleanVar(value=self.saved_state["screen_mover_enabled"])
        
        self.screen_mover_switch = ctk.CTkSwitch(
            self,
            text="Enable Screen Drag Flick",
            variable=self.screen_mover_var,
            command=self.Enable_Screen_Drag_Flick,
            font=("Segoe UI", 16)
        )
        
        self.screen_mover_switch.pack(
            anchor="w",     # ← aligns to the left edge
            padx=18,        # ← add optional padding so it isn’t touching the border
            pady=(5, 5)
        )
        
        # ------------------------------------------------------------------
        #  Screen-Tab Mover Group Box(frame)
        # ------------------------------------------------------------------
        
        self.mover_frame = ctk.CTkFrame(self)
        self.mover_frame.pack(pady=10, padx=10, fill="x")

        self.mmb_var = ctk.BooleanVar(value=self.saved_state["mmb_activation_enabled"])
        self.mmb_switch = ctk.CTkSwitch(
            self.mover_frame,
            text="Use Middle Mouse To Flick",
            variable=self.mmb_var,
            command=self.save_all_settings,
            font=("Segoe UI", 16)
        )
        self.mmb_switch.pack(anchor="w", padx=10, pady=2)
        
        mover_help = ctk.CTkLabel(
            self.mover_frame,
            text="Click and hold the middle mouse at the top of any program screen\nIn blank space an arrow icon will show indicating its active\nThen flick left or right to move the program to a different screen.",
            font=("Segoe UI", 16),
            justify="left"
        )
        mover_help.pack(anchor="w", padx=10, pady=(0, 4))

        # NEW: Keep Windows in Flick Zone toggle
        self.auto_align_var = ctk.BooleanVar(value=self.saved_state.get("auto_align_enabled", False))
        self.auto_align_switch = ctk.CTkSwitch(
            self.mover_frame,
            text="Keep Windows In Flick Zone",
            variable=self.auto_align_var,
            command=self.save_all_settings,
            font=("Segoe UI", 16)
        )
        self.auto_align_switch.pack(anchor="w", padx=10, pady=(8, 2))

        # NEW: Explanation label under the toggle (Variant B)
        self.auto_align_label = ctk.CTkLabel(
            self.mover_frame,
            text=(
                "Ensures the flick gesture always works by keeping window title bars inside the\n"
                "activation zone. Adjustments only happen after a drag, never during."
            ),
            font=("Segoe UI", 16),
            justify="left"
        )
        self.auto_align_label.pack(anchor="w", padx=10, pady=(0, 4))
        # Start Mover sub-options in correct state
        # Start Mover sub-options in correct state
        toggle_mover_options(self, self.screen_mover_var.get())

        # ------------------------------------------------------------------
        #  USB Reminder Main Switch  (UNCHANGED)
        # ------------------------------------------------------------------
        
        self.usb_reminder_var = ctk.BooleanVar(value=False)
        self.usb_reminder_switch = ctk.CTkSwitch(
            self,
            text="USB Reminder",
            variable=self.usb_reminder_var,
            command=self.usb_reminder_var.get,
            font=("Segoe UI", 24)
        )
        self.usb_reminder_switch.pack(pady=10)
        
        self.usb_reminder_switch.pack(
            anchor="w",     # ← aligns to the left edge
            padx=18,        # ← add optional padding so it isn’t touching the border
            pady=(5, 5)
        )

        # ------------------------------------------------------------------
        #  USB Reminder Sub-Options Frame  (UNCHANGED)
        # ------------------------------------------------------------------
        
        self.usb_frame = ctk.CTkFrame(self)
        self.usb_frame.pack(pady=10, padx=10, fill="x")

        usb_label = ctk.CTkLabel(self.usb_frame, text="Reminder Options:", font=("Segoe UI", 16))
        usb_label.pack(pady=(5, 5))

        self.opt_idle_var = ctk.BooleanVar(value=False)
        self.opt_idle = ctk.CTkSwitch(
            self.usb_frame,
            text="Idle-plugged Reminder",
            variable=self.opt_idle_var,
            font=("Segoe UI", 16)
        )
        self.opt_idle.pack(anchor="w", padx=10, pady=2)

        self.opt_download_var = ctk.BooleanVar(value=False)
        self.opt_download = ctk.CTkSwitch(
            self.usb_frame,
            text="Download-finished Reminder",
            variable=self.opt_download_var,
            font=("Segoe UI", 16)
        )
        self.opt_download.pack(anchor="w", padx=10, pady=2)

        self.opt_plug_var = ctk.BooleanVar(value=False)
        self.opt_plug = ctk.CTkSwitch(
            self.usb_frame,
            text="Plug / Unplug Notification",
            variable=self.opt_plug_var,
            font=("Segoe UI", 16)
        )
        self.opt_plug.pack(anchor="w", padx=10, pady=2)
        # Start with USB settings disabled
        toggle_usb_options(self, False)

    # --------------------------------------------------------------
    # Theme Toggle Handler (correct indentation and import)
    # --------------------------------------------------------------
    def on_theme_toggle(self):
        enabled = self.theme_var.get()
        switch_theme(enabled)
        self.save_all_settings()

    # ===================================================================
    #  Save ALL toggle states to JSON
    # ===================================================================
    
    def save_all_settings(self):
        old = load_state()   # previous saved values

        new = {}

        # -------------------------
        # Screen Mover settings
        # -------------------------
        
        new["screen_mover_enabled"]   = self.screen_mover_var.get()
        new["mmb_activation_enabled"] = self.mmb_var.get()
        new["auto_align_enabled"]     = self.auto_align_var.get()    # NEW

        # Live update backend
        SCREEN_MOVER.enable_mmb        = new["mmb_activation_enabled"]
        SCREEN_MOVER.auto_align_enabled = new["auto_align_enabled"]  # NEW

        # -------------------------
        # USB settings
        # -------------------------
        
        new["usb_enabled"]          = self.usb_reminder_var.get()
        new["usb_idle_enabled"]     = self.opt_idle_var.get()
        new["usb_download_enabled"] = self.opt_download_var.get()
        new["usb_plug_enabled"]     = self.opt_plug_var.get()
        
        #-------------
        # Theme saver
        #-------------
        
        new["theme_dark"] = self.theme_var.get()

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
    #  Screen Tab Mover Logic
    # ===================================================================
    
    def Enable_Screen_Drag_Flick(self):
        enabled = self.screen_mover_var.get()
        print(f"[INFO] Screen-Tab Mover toggled → {enabled}")

        # Grey/enable activation options
        toggle_mover_options(self, enabled)

        # Save new value
        self.save_all_settings()

        # Start or stop backend worker
        if enabled:
            SCREEN_MOVER.start()
        else:
            SCREEN_MOVER.stop()

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
        
    def tray_menu_toggle(self, icon, item):
        """Double-click → toggle window show/hide."""
        self.after(0, self._toggle_window)
        
    def _toggle_window(self):
        if self.saved_state() == "withdrawn":
            self._show_window()
        else:
            self.withdraw()

    def tray_menu_quit(self, icon, item):
        self.after(0, self._quit_from_tray)

    # ---------------- Helpers that run on Tk main thread ----------------
    
    def _show_window(self):
        self.deiconify()
        self.after(10, self.lift)
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

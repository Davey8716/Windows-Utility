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
import tkinter as tk
import os
from usb_reminder import toggle_usb_options, toggle_mover_options
from theme_manager import switch_theme   # add at top with other imports

# Configure appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ===================================================================
# Simple Tooltip for CustomTkinter widgets
# ====================================================================


class CtkTooltip:
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip_window = None
        self.after_id = None

        # Find the actual clickable canvas of CTkSwitch
        target = getattr(widget, "_canvas", widget)

        # Bind ONLY to the switch button component
        target.bind("<Enter>", self.schedule, add="+")
        target.bind("<Leave>", self.hide, add="+")

        
    def schedule(self, event=None):
        self.after_id = self.widget.after(self.delay, self.show)

    def show(self):
        if self.tip_window:
            return

        # Tooltip position
        x = self.widget.winfo_rootx() + 40
        y = self.widget.winfo_rooty() + 25

        # Create tooltip
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        # Make sure tooltip is above CTk window
        tw.lift()
        tw.attributes("-topmost", True)

        # Tooltip look (dark mode compatible)
        label = tk.Label(
            tw,
            text=self.text,
            background="#1E1E1E",
            foreground="white",
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=4,
            font=("Rubik UI", 14)
        )
        label.pack()

    def hide(self, event=None):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

# ===================================================================
#  Main App Gui
# ===================================================================

class UtilityControlApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Always keep GUI on top
        self.attributes("-topmost", True)

        # WinAPI reinforcement
        import ctypes
        ctypes.windll.user32.SetWindowPos(
            self.winfo_id(),
            -1,   # HWND_TOPMOST
            0, 0, 0, 0,
            0x0003  # SWP_NOSIZE | SWP_NOMOVE
        )
        
        SCREEN_MOVER.app_root = self

        # Load saved state
        self.saved_state = load_state()
        
        # Restore theme mode on startup
        self.theme_var = ctk.BooleanVar(value=self.saved_state.get("theme_dark", True))
        switch_theme(self.theme_var.get())
        


        self.title("🦉Problem? Gone!")
        self.geometry("400x700")
        self.resizable(False, False)

        # Tray
        self.tray_icon = None
        self.tray_thread = None
        self.protocol("WM_DELETE_WINDOW", self.on_close_to_tray)

        # Auto-start backend if saved state says it should be ON
        SCREEN_MOVER.start()


        # System tray icon
        self.create_tray_icon()

        # --------------------------------------------------------------
        # Title
        # --------------------------------------------------------------
        
        title = ctk.CTkLabel(self, text="🦉 Problem? Gone!", font=("Rubik UI", 24))
        title.pack(pady=10)

        # --------------------------------------------------------------
        # Dark / Light Mode Toggle  (correctly placed)
        # --------------------------------------------------------------

        self.theme_switch = ctk.CTkSwitch(
            self,
            text="Dark Mode",
            variable=self.theme_var,
            command=self.on_theme_toggle,
            font=("Rubik UI", 16)
        )
        
        # Adjust initial text based on saved theme
        if self.theme_var.get():
            self.theme_switch.configure(text="Dark Mode Enabled")
        else:
            self.theme_switch.configure(text="Light Mode Enabled")


        self.theme_switch.pack(
            anchor="w",     # ← aligns to the left edge
            padx=18,        # ← add optional padding so it isn’t touching the border
            pady=(5, 5)
        )
        
        CtkTooltip(
            self.theme_switch,
            "Light and dark mode. Try them!.\n"
            
        )
        
        # --------------------------------------------------------------
        # Always On Top Toggle (GUI only)
        # --------------------------------------------------------------

        self.always_on_top_var = ctk.BooleanVar(
            value=self.saved_state.get("always_on_top_enabled", True)
        )

        # Apply saved setting on startup
        self.apply_always_on_top(self.always_on_top_var.get())

        self.always_on_top_switch = ctk.CTkSwitch(
            self,
            text="Always On Top",
            variable=self.always_on_top_var,
            command=self.on_always_on_top_toggle,
            font=("Rubik UI", 16)
        )
        self.always_on_top_switch.pack(
            anchor="w",
            padx=18,
            pady=(5, 5)
        )
        
        CtkTooltip(
            self.always_on_top_switch,
            "When off Problem Gone will show below other apps if they are maximized.\n"
            "When on Problem Gone will always show on top of other apps.\n"
            
        )

        # --------------------------------------------------------------
        # Minimize All Windows Toggle (NEW)
        # --------------------------------------------------------------

        self.minimize_all_var = ctk.BooleanVar(
            value=self.saved_state.get("minimize_all_enabled", False)
        )

        self.minimize_all_switch = ctk.CTkSwitch(
            self,
            text="Max/Min All Opened Program Windows",
            variable=self.minimize_all_var,
            command=self.on_minimize_all_toggle,
            font=("Rubik UI", 16)
        )

        self.minimize_all_switch.pack(
            anchor="w",
            padx=18,
            pady=(5, 5)
        )
        
        # Add tooltip
        CtkTooltip(
            self.minimize_all_switch,
            "When off all opened tabs are visible.\n"
            "When toggled on all screens are minimized.\n"
            "The app gui itself stays maximized and in front of all other programs.\n"
        )

        # ------------------------------------------------------------------
        #  Screen-Tab Mover Group Box(frame)
        # ------------------------------------------------------------------
        
        self.mover_frame = ctk.CTkFrame(self)
        self.mover_frame.pack(pady=10, padx=10, fill="x")

        mover_label = ctk.CTkLabel(
            self.mover_frame,
            text="🖱 Quick app/browser screen changer:",
            font=("Rubik UI", 16,),
        )
        mover_label.pack(pady=(0, 0))


        self.mmb_var = ctk.BooleanVar(value=self.saved_state["mmb_activation_enabled"])
        self.mmb_switch = ctk.CTkSwitch(
            self.mover_frame,
            text="Use Middle Mouse To Flick",
            variable=self.mmb_var,
            command=self.save_all_settings,   # <-- correct handler
            font=("Rubik UI", 16)
        )
        self.mmb_switch.pack(anchor="w", padx=10, pady=2)
        
        # Add tooltip
        CtkTooltip(
            self.mmb_switch,
            "Click and hold the middle mouse.\n"
            "At the top of any program window.\n"
            "When the arrow appears, flick left or right\n"
            "To move the window to another screen."
        )


        # NEW: Keep Windows in Flick Zone toggle
        self.auto_align_var = ctk.BooleanVar(value=self.saved_state.get("auto_align_enabled", False))
        self.auto_align_switch = ctk.CTkSwitch(
            self.mover_frame,
            text="Keep Windows In Flick Zone",
            variable=self.auto_align_var,
            command=self.on_auto_align_toggle,     # <-- THIS WAS MISSING
            font=("Rubik UI", 16)
        )
        self.auto_align_switch.pack(anchor="w", padx=10, pady=(8, 2))

        CtkTooltip(
            self.auto_align_switch,
            "Keeps window title bars inside the flick activation zone.\n"
            "Only activates after you finish dragging a window.\n"
            "Never interferes during movement."
        )

        toggle_mover_options(self, True)

        # ------------------------------------------------------------------
        #  USB Reminder Sub-Options Frame  (UNCHANGED)
        # ------------------------------------------------------------------
        
        self.usb_frame = ctk.CTkFrame(self)
        self.usb_frame.pack(pady=10, padx=10, fill="x")

        usb_label = ctk.CTkLabel(self.usb_frame, text="🔌USB Reminder Options:", font=("Rubik UI", 16))
        usb_label.pack(pady=(5, 5))

        
        # USB sub-toggle initializers (load from JSON)
        self.opt_idle_var = ctk.BooleanVar(
            value=self.saved_state.get("usb_idle_enabled", True)
        )
        
        self.opt_idle = ctk.CTkSwitch(
            self.usb_frame,
            text="Idle-plugged Reminder",
            variable=self.opt_idle_var,
            command=self.save_all_settings,
            font=("Rubik UI", 16)
        )
        self.opt_idle.pack(anchor="w", padx=10, pady=2)

        self.opt_download_var = ctk.BooleanVar(
            value=self.saved_state.get("usb_download_enabled", True)
        )
        
        self.opt_download = ctk.CTkSwitch(
            self.usb_frame,
            text="Download-finished Reminder",
            variable=self.opt_download_var,
            command=self.save_all_settings,
            font=("Rubik UI", 16)
        )
        self.opt_download.pack(anchor="w", padx=10, pady=2)

        self.opt_plug_var = ctk.BooleanVar(
            value=self.saved_state.get("usb_plug_enabled", True)
        )
        
        self.opt_plug = ctk.CTkSwitch(
            self.usb_frame,
            text="Plug / Unplug Notification",
            variable=self.opt_plug_var,
            command=self.save_all_settings,
            font=("Rubik UI", 16)
            
        )
        
        self.opt_plug.pack(anchor="w", padx=10, pady=2)
        # Start with USB settings disabled
        toggle_usb_options(self, True)

        # ---------------------------------------------
        # Windows Utilities - Two Column Layout
        # ---------------------------------------------
        
        self.win_utils_frame = ctk.CTkFrame(self)
        self.win_utils_frame.pack(pady=10, padx=10, fill="x")

        # Header
        win_utils_label = ctk.CTkLabel(
            self.win_utils_frame,
            text="⚙️ Windows Utilities:",
            font=("Rubik UI", 16)
        )
        win_utils_label.pack(anchor="w", padx=100, pady=(5, 0))

        # Toggle ABOVE the grid (safe)
        self.power_toggle_var = ctk.BooleanVar(
            value=self.saved_state.get("show_power_buttons", False)
        )


        self.power_toggle = ctk.CTkSwitch(
            self.win_utils_frame,
            text="Show Power Buttons",
            variable=self.power_toggle_var,
            command=self._toggle_power_buttons,
            font=("Rubik UI", 15)
        )
        self.power_toggle.pack(anchor="w", padx=10, pady=(2, 5))
        
        CtkTooltip(
            self.power_toggle,
            "⚠️⚠️ Toggles on off power options ⚠️⚠️.\n"
            "Made for clumsy people who might shutdown by mistake etc.\n"
            "Remembers if its on or off on startup.\n"
            
        )

        # --- NOW define btn_width ---
        btn_width = 120

        # --- NOW define util_grid ---
        util_grid = ctk.CTkFrame(self.win_utils_frame, fg_color="transparent", corner_radius=8)
        util_grid.pack(fill="x", padx=10, pady=5)

        util_grid.columnconfigure(0, weight=1)
        util_grid.columnconfigure(1, weight=1)

        # ==========================
        # LEFT COLUMN
        # ==========================

        self.btn_settings = ctk.CTkButton(
            util_grid,
            text="⚙️ System Settings",
            width=btn_width,
            command=lambda: os.system("start ms-settings:"),
            font=("Rubik UI", 15)
        )
        self.btn_settings.grid(row=0, column=0, sticky="w", pady=3)

        self.btn_device_mgr = ctk.CTkButton(
            util_grid,
            text="🧰 Device Manager",
            width=btn_width,
            command=lambda: os.system("devmgmt.msc"),
            font=("Rubik UI", 15),
        )
        self.btn_device_mgr.grid(row=1, column=0, sticky="w", pady=3)

        self.btn_task_mgr = ctk.CTkButton(
            util_grid,
            text="🧠 Task Manager",
            width=btn_width,
            command=lambda: os.system("taskmgr"),
            font=("Rubik UI", 15),
        )
        self.btn_task_mgr.grid(row=2, column=0, sticky="w", pady=3)

        self.btn_router = ctk.CTkButton(
            util_grid,
            text="📡 Router Login",
            width=btn_width,
            command=self._open_router_page,
            font=("Rubik UI", 15),
        )
        self.btn_router.grid(row=3, column=0, sticky="w", pady=3)

        # ==========================
        # RIGHT COLUMN
        # ==========================
        
        self.btn_sleep = ctk.CTkButton(
            util_grid,
            text="💤 Sleep",
            width=btn_width,
            command=lambda: os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0"),
            font=("Rubik UI", 15),
        )
        self.btn_sleep.grid(row=0, column=1, sticky="e", pady=3)

        self.btn_lock = ctk.CTkButton(
            util_grid,
            text="🔒 Lock PC",
            width=btn_width,
            command=lambda: ctypes.windll.user32.LockWorkStation(),
            font=("Rubik UI", 15),
        )
        self.btn_lock.grid(row=1, column=1, sticky="e", pady=3)
        
        self.btn_restart = ctk.CTkButton(
            util_grid,
            text="🔁 Restart",
            width=btn_width,
            command=lambda: os.system("shutdown /r /t 0"),
            font=("Rubik UI", 15),
        )
        self.btn_restart.grid(row=2, column=1, sticky="e", pady=3)

        self.btn_shutdown = ctk.CTkButton(
            util_grid,
            text="⏻ Shutdown",
            width=btn_width,
            command=lambda: os.system("shutdown /s /t 0"),
            font=("Rubik UI", 15),
        )
        self.btn_shutdown.grid(row=3, column=1, sticky="e", pady=3)
        
        self._toggle_power_buttons()
        
    def _toggle_power_buttons(self):
        """Show or hide the right-side power buttons and save state."""
        enabled = self.power_toggle_var.get()

        # Save state immediately
        self.save_all_settings()

        # If buttons are not ready yet, exit safely
        if not hasattr(self, "btn_shutdown"):
            return

        widgets = [
            self.btn_shutdown,
            self.btn_restart,
            self.btn_sleep,
            self.btn_lock,
        ]

        for w in widgets:
            try:
                if enabled:
                    w.grid()          # Restore to previous grid position
                else:
                    w.grid_remove()   # Hide but preserve grid info
            except Exception:
                pass

    def _open_router_page(self):
        """Auto-detect default gateway and open router page in browser."""
        try:
            import subprocess
            import webbrowser

            # Get routing info
            result = subprocess.check_output("ipconfig", text=True, errors="ignore")

            gateway = None
            for line in result.splitlines():
                if "Default Gateway" in line:
                    parts = line.split(":")
                    if len(parts) > 1:
                        gw = parts[1].strip()
                        if gw and gw != "0.0.0.0":
                            gateway = gw
                            break

            if gateway:
                webbrowser.open(f"http://{gateway}")
                print(f"[ROUTER] Opening router at {gateway}")
            else:
                print("[ROUTER] No default gateway found")

        except Exception as e:
            print("[ROUTER] Failed:", e)

        
    def on_minimize_all_toggle(self):
        from minimize_all import minimize_all_except_gui, restore_all_except_gui
        import ctypes

        enabled = self.minimize_all_var.get()
        print(f"[INFO] Min/Max All toggled → {enabled}")

        # Get real top-level HWND of GUI
        child = self.winfo_id()
        parent = ctypes.windll.user32.GetParent(child)
        real_hwnd = parent if parent else child

        if enabled:
            minimize_all_except_gui(real_hwnd)
        else:
            restore_all_except_gui(real_hwnd)

        self.save_all_settings()

    def on_usb_reminder_toggle(self):
        enabled = self.usb_reminder_var.get()
        toggle_usb_options(self, enabled)
        self.save_all_settings()

    # --------------------------------------------------------------
    # Theme Toggle Handler (correct indentation and import)
    # --------------------------------------------------------------
    
    def on_theme_toggle(self):
        enabled = self.theme_var.get()
        switch_theme(enabled)
        
        # ⬅️ Update label depending on mode
        if enabled:
            self.theme_switch.configure(text="Dark Mode Enabled")
        else:
            self.theme_switch.configure(text="Light Mode Enabled")
    
        self.save_all_settings()
        
    def apply_always_on_top(self, enabled: bool):
        """Apply the topmost flag ONLY to the GUI window, never to overlay."""
        try:
            # Tkinter topmost
            self.attributes("-topmost", enabled)

            # WinAPI reinforcement
            import ctypes
            ctypes.windll.user32.SetWindowPos(
                self.winfo_id(),
                -1 if enabled else -2,  # HWND_TOPMOST or HWND_NOTOPMOST
                0, 0, 0, 0,
                0x0003  # SWP_NOMOVE | SWP_NOSIZE
            )
        except Exception as e:
            print("[AOT] Failed:", e)
            
    def on_always_on_top_toggle(self):
        enabled = self.always_on_top_var.get()
        self.apply_always_on_top(enabled)
        self.save_all_settings()

    def on_auto_align_toggle(self):
        enabled = self.auto_align_var.get()

        # Update runtime state so screen_mover.py knows the toggle changed
        SCREEN_MOVER.auto_align_enabled = enabled

        # Save settings to JSON
        self.save_all_settings()

        # If turning ON → force align all windows immediately
        if enabled:
            try:
                SCREEN_MOVER._force_align_all_windows()
            except Exception as e:
                print("[GUI] Force align failed:", e)


    # ===================================================================
    #  Save ALL toggle states to JSON
    # ===================================================================
    
    def save_all_settings(self):
        old = load_state()   # previous saved values

        new = {}

        # -------------------------
        # Screen Mover settings
        # -------------------------
        
        new["mmb_activation_enabled"] = self.mmb_var.get()
        new["auto_align_enabled"]     = self.auto_align_var.get()
        new["minimize_all_enabled"] = self.minimize_all_var.get()


        # Live update backend
        SCREEN_MOVER.enable_mmb        = new["mmb_activation_enabled"]
        SCREEN_MOVER.auto_align_enabled = new["auto_align_enabled"]  

        # -------------------------
        # USB settings
        # -------------------------

        new["usb_idle_enabled"]     = self.opt_idle_var.get()
        new["usb_download_enabled"] = self.opt_download_var.get()
        new["usb_plug_enabled"]     = self.opt_plug_var.get()
        
        #-------------
        # Theme saver
        #-------------
        
        new["theme_dark"] = self.theme_var.get()
        new["always_on_top_enabled"] = self.always_on_top_var.get()
        new["show_power_buttons"] = self.power_toggle_var.get()

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
        if self.state() == "withdrawn":
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
        self.attributes("-topmost", True)
        try:
            import ctypes
            ctypes.windll.user32.SetWindowPos(
                self.winfo_id(),
                -1,
                0, 0, 0, 0,
                0x0003
            )
        except Exception as e:
            print("[TOPMOST] WinAPI failed:", e)


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

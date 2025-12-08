# ===================================================================
#  Screen Tab Mover + USB Reminder Control Panel
#  Modern UI using CustomTkinter
# ===================================================================

import customtkinter as ctk
from screen_mover import SCREEN_MOVER
from state_manager import load_state, save_state
import tkinter as tk
import os
from windows_utility_toggles import switch_theme   # add at top with other imports
from windows_utility_toggles import UtilityActionsManager

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
        target.bind("<Button-1>", self.hide, add="+")  # hide on click
        
        # ------------------------------------------------------
    # Schedules showing the tooltip
    # ------------------------------------------------------
    def schedule(self, event=None):
        # Cancel previous timer
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

        # Start new timer
        self.after_id = self.widget.after(self.delay, self.show)

    # ------------------------------------------------------
    # Shows the tooltip IF globally enabled
    # ------------------------------------------------------
    def show(self):
        # Global tooltip toggle (check root window)
        root = self.widget.winfo_toplevel()
        if hasattr(root, "tooltips_enabled"):
            if not root.tooltips_enabled:
                return

        if self.tip_window:
            return

        # Position tooltip near cursor
        x = self.widget.winfo_rootx() + 40
        y = self.widget.winfo_rooty() + 25

        # Create popup
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.lift()
        tw.attributes("-topmost", True)

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
#  Collapsible Section with Auto-Theme Arrow Colour
# ===================================================================

class CollapsibleSection:
    def __init__(self, parent, title_text, section_id, initial_open=True):
        self.parent = parent
        self.section_id = section_id   # NEW
        self.open = initial_open

        # A wrapper that keeps header + content together
        self.wrapper = ctk.CTkFrame(parent, fg_color="transparent")
        self.wrapper.pack(fill="x", pady=(10, 0))

        # Header row
        self.header = ctk.CTkFrame(self.wrapper, fg_color="transparent")
        self.header.pack(fill="x")

        self.label = ctk.CTkLabel(
            self.header,
            text=title_text,
            font=("Rubik UI", 16)
        )
        self.label.pack(side="left", padx=10)

        # Toggle button
        self.button = ctk.CTkButton(
            self.header,
            text="▾" if initial_open else "▸",
            width=30,
            height=20,
            command=self.toggle,
            font=("Rubik UI", 18),
            fg_color="transparent",
            hover_color="#202020"
        )
        self.button.pack(side="right", padx=10)

        # Apply correct arrow colour depending on theme
        self.update_arrow_color()

        # Content frame
        self.content = ctk.CTkFrame(self.wrapper)

        if initial_open:
            self.content.pack(fill="x", pady=(0, 10), padx=10)

    # ---------------------------------------------------------
    # NEW: automatic arrow colour based on Dark/Light mode
    # ---------------------------------------------------------
    def update_arrow_color(self):
        mode = ctk.get_appearance_mode()
        if mode == "Dark":
            self.button.configure(text_color="white")
        else:
            self.button.configure(text_color="black")

    def toggle(self):
        if self.open:
            self.content.pack_forget()
            self.button.configure(text="▸")
        else:
            self.content.pack(fill="x", pady=(0, 10), padx=10)
            self.button.configure(text="▾")

        self.open = not self.open

        # Notify app to shrink/expand window
        try:
            app = self.parent.winfo_toplevel()
            if hasattr(app, "resize_to_fit"):
                app.resize_to_fit()
        except Exception:
            pass

        # Save section states
        try:
            app = self.parent.winfo_toplevel()
            if hasattr(app, "save_section_states"):
                app.save_section_states()
        except Exception:
            pass



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
    
        self.actions = UtilityActionsManager(self)
        # Restore theme mode on startup
        self.theme_var = ctk.BooleanVar(value=self.saved_state.get("theme_dark", True))
        switch_theme(self.theme_var.get())
    
        self.title("🦉Problem? Gone!")
        self.geometry("400x900")
        self.resizable(False, False) 
        
        from tray_toggles import TrayIconManager

        self.tray = TrayIconManager(self)
        self.tray.create_tray_icon()
        self.protocol("WM_DELETE_WINDOW", self.tray.on_close_to_tray)

        # Auto-start backend if saved state says it should be ON
        SCREEN_MOVER.start()

        # --------------------------------------------------------------
        # Title
        # --------------------------------------------------------------
        
        title = ctk.CTkLabel(self, text="🦉 Problem? Gone!", font=("Rubik UI", 24))
        title.pack(pady=10)
        
        # --------------------------------------------------------------
        #  Miscellaneous / General Options  (NEW GREY WRAPPER)
        # --------------------------------------------------------------

        # Restore theme mode on startup
        self.theme_var = ctk.BooleanVar(value=self.saved_state.get("theme_dark", True))
        switch_theme(self.theme_var.get())

        # NEW – Always On Top + Minimize All variables must be defined BEFORE UI elements
        self.always_on_top_var = ctk.BooleanVar(
            value=self.saved_state.get("always_on_top_enabled", True)
        )

        self.minimize_all_var = ctk.BooleanVar(
            value=self.saved_state.get("minimize_all_enabled", False)
        )
        
        self.tooltips_enabled_var = ctk.BooleanVar(
            value=self.saved_state.get("tooltips_enabled", True)
        )

        # Local runtime copy for CtkTooltip to read
        self.tooltips_enabled = self.tooltips_enabled_var.get()

        # --------------------------------------------------------------
        #  Collapsible Sections Registry
        # --------------------------------------------------------------
        self.collapsible_sections = []        # <--- ADD THIS FIRST

        # --------------------------------------------------------------
        #  Miscellaneous / General Options
        # --------------------------------------------------------------
        
        misc_section = CollapsibleSection(
            self,
            "🧰 Miscellaneous:",
            section_id="misc",
            initial_open=self.saved_state["section_states"].get("misc", True)
        )
        self.collapsible_sections.append(misc_section)

        # -------------------------
        # Dark Mode Toggle
        # -------------------------

        self.theme_switch = ctk.CTkSwitch(
            misc_section.content,    # FIXED
            text="Dark Mode",
            variable=self.theme_var,
            command=self.actions.theme_toggle,
            font=("Rubik UI", 16)
        )

        if self.theme_var.get():
            self.theme_switch.configure(text="Dark Mode Enabled")
        else:
            self.theme_switch.configure(text="Light Mode Enabled")

        self.theme_switch.pack(anchor="w", padx=12, pady=(2, 4))

        CtkTooltip(self.theme_switch, "Light and Dark mode. Try Them!.")

        # -------------------------
        # Always On Top Toggle
        # -------------------------

        self.always_on_top_switch = ctk.CTkSwitch(
            misc_section.content,
            text="Always On Top",
            variable=self.always_on_top_var,
            command=self.actions.always_on_top_toggle,
            font=("Rubik UI", 16)
        )
        self.always_on_top_switch.pack(anchor="w", padx=12, pady=(4, 4))

        CtkTooltip(
            self.always_on_top_switch,
            "When off Problem Gone will show below other apps if they are maximized.\n"
            "When on Problem Gone will always show on top of other apps.\n"
        )
        
        # -------------------------
        # Turn Off Tooltips Toggle
        # -------------------------

        self.tooltip_switch = ctk.CTkSwitch(
            misc_section.content,  
            text="Enable Tooltips",
            variable=self.tooltips_enabled_var,
            command=self.actions.tooltips_toggle,
            font=("Rubik UI", 16)
        )
        self.tooltip_switch.pack(anchor="w", padx=12, pady=(4, 6))

        CtkTooltip(
            self.tooltip_switch,
            "Enable all hover tooltips across the entire app."
        )

        # -------------------------
        # Max/Min All Windows Toggle
        # -------------------------

        self.minimize_all_switch = ctk.CTkSwitch(
            misc_section.content, 
            text="Max/Min All Opened Program Windows",
            variable=self.minimize_all_var,
            command=self.actions.minimize_all_toggle,
            font=("Rubik UI", 16)
        )

        self.minimize_all_switch.pack(anchor="w", padx=12, pady=(4, 8))

        CtkTooltip(
            self.minimize_all_switch,
            "When off all opened tabs are visible.\n"
            "When toggled on all screens are minimized.\n"
            "The App Gui itself stays maximized and in front of all other programs.\n"
        )

        # ------------------------------------------------------------------
        #  Screen-Tab Mover Group Box(frame)
        # ------------------------------------------------------------------
        
        mover_section = CollapsibleSection(
            self,
            "🖱 Quick app/browser screen changer:",
            section_id="mover",
            initial_open=self.saved_state["section_states"].get("mover", True)
        )
        self.collapsible_sections.append(mover_section)


        self.mmb_var = ctk.BooleanVar(value=self.saved_state["mmb_activation_enabled"])
        self.mmb_switch = ctk.CTkSwitch(
            mover_section.content,   # FIXED
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
            mover_section.content,   # FIXED
            text="Keep Windows In Flick Zone",
            variable=self.auto_align_var,
            command=self.actions.auto_align_toggle,     # <-- THIS WAS MISSING
            font=("Rubik UI", 16)
        )
        self.auto_align_switch.pack(anchor="w", padx=10, pady=(8, 2))

        CtkTooltip(
            self.auto_align_switch,
            "Keeps window title bars inside the flick activation zone.\n"
            "Only activates after you finish dragging a window.\n"
            "Never interferes during movement."
        )

        # ------------------------------------------------------------------
        #  USB Reminder Sub-Options Frame  (UNCHANGED)
        # ------------------------------------------------------------------
        
        usb_section = CollapsibleSection(
            self,
            "🔌 USB Reminder Options:",
            section_id="usb",
            initial_open=self.saved_state["section_states"].get("usb", True)
        )
        self.collapsible_sections.append(usb_section)


        # USB sub-toggle initializers (load from JSON)
        self.opt_idle_var = ctk.BooleanVar(
            value=self.saved_state.get("usb_idle_enabled", True)
        )
        
        self.opt_idle = ctk.CTkSwitch(
            usb_section.content,
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
            usb_section.content,
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
            usb_section.content, 
            text="Plug / Unplug Notification",
            variable=self.opt_plug_var,
            command=self.save_all_settings,
            font=("Rubik UI", 16)
            
        )
        
        self.opt_plug.pack(anchor="w", padx=10, pady=2)
        # Start with USB settings disabled
        
        
        winutil_section = CollapsibleSection(
            self,
            "⚙️ Windows Utilities:",
            section_id="winutils",
            initial_open=self.saved_state.get("section_states", {}).get("winutils", True)
        )
        self.collapsible_sections.append(winutil_section)
        self.win_utils_frame = winutil_section.content

        # Toggle ABOVE the grid (safe)
        self.power_toggle_var = ctk.BooleanVar(
            value=self.saved_state.get("show_power_buttons", False)
        )

        self.power_toggle = ctk.CTkSwitch(
            self.win_utils_frame,
            text="Show Power Buttons",
            variable=self.power_toggle_var,
            command=self.actions.toggle_power_buttons,
            font=("Rubik UI", 15)
        )
        self.power_toggle.pack(anchor="w", padx=10, pady=(2, 5))

        CtkTooltip(
            self.power_toggle,
            "⚠️⚠️ Toggles on/off power options ⚠️⚠️.\n"
            "Made for clumsy people who might shutdown by mistake etc.\n"
            "Remembers if it's on or off on startup.\n"
        )

        # --- NOW define btn_width ---
        btn_width = 120

        # --- NOW define util_grid ---
        util_grid = ctk.CTkFrame(
            self.win_utils_frame,
            fg_color="transparent",
            corner_radius=8
        )
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
            font=("Rubik UI", 15)
        )
        self.btn_device_mgr.grid(row=1, column=0, sticky="w", pady=3)

        self.btn_task_mgr = ctk.CTkButton(
            util_grid,
            text="🧠 Task Manager",
            width=btn_width,
            command=lambda: os.system("taskmgr"),
            font=("Rubik UI", 15)
        )
        self.btn_task_mgr.grid(row=2, column=0, sticky="w", pady=3)

        self.btn_router = ctk.CTkButton(
            util_grid,
            text="📡 Router Login",
            width=btn_width,
            command=self.actions.open_router_page,
            font=("Rubik UI", 15)
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
            font=("Rubik UI", 15)
        )
        self.btn_sleep.grid(row=0, column=1, sticky="e", pady=3)

        self.btn_lock = ctk.CTkButton(
            util_grid,
            text="🔒 Lock PC",
            width=btn_width,
            command=lambda: ctypes.windll.user32.LockWorkStation(),
            font=("Rubik UI", 15)
        )
        self.btn_lock.grid(row=1, column=1, sticky="e", pady=3)

        self.btn_restart = ctk.CTkButton(
            util_grid,
            text="🔁 Restart",
            width=btn_width,
            command=lambda: os.system("shutdown /r /t 0"),
            font=("Rubik UI", 15)
        )
        self.btn_restart.grid(row=2, column=1, sticky="e", pady=3)

        self.btn_shutdown = ctk.CTkButton(
            util_grid,
            text="⏻ Shutdown",
            width=btn_width,
            command=lambda: os.system("shutdown /s /t 0"),
            font=("Rubik UI", 15)
        )
        self.btn_shutdown.grid(row=3, column=1, sticky="e", pady=3)

        self.actions.toggle_power_buttons()
        
        # --------------------------------------------------------------
        #  Organising Utilities  (NEW GREY SECTION)
        # --------------------------------------------------------------

        from screenshot_tool import take_desktop_screenshot

        organising_section = CollapsibleSection(
            self,
            "📁 Organising Utilities:",
            section_id="organising",
            initial_open=self.saved_state.get("section_states", {}).get("organising", True)
        )
        self.collapsible_sections.append(organising_section)

        organising_frame = organising_section.content

        # =============== Desktop Screenshotter Button =================

        self.btn_desktop_screenshot = ctk.CTkButton(
            organising_frame,
            text="🖼 Desktop Screenshot",
            width=200,
            command=lambda: take_desktop_screenshot(self),
            font=("Rubik UI", 15)
        )
        self.btn_desktop_screenshot.pack(anchor="w", padx=10, pady=(5, 5))

        CtkTooltip(
            self.btn_desktop_screenshot,
            "Minimizes the app, takes a full desktop screenshot,\n"
            "lets you choose a save location, then restores the window."
        )

        # =============== Folder Creator Placeholder ===================

        self.btn_folder_creator = ctk.CTkButton(
            organising_frame,
            text="📂 Folder Creator",
            width=200,
            command=lambda: print('[TODO] Folder creator clicked'),
            font=("Rubik UI", 15)
        )
        self.btn_folder_creator.pack(anchor="w", padx=10, pady=(5, 10))

        CtkTooltip(
            self.btn_folder_creator,
            "Simple nested-folder builder will go here.\n"
            "Instant 'Create on Desktop' support coming soon."
        )

    def update_collapsible_arrow_colours(self):
        """Called after theme change to recolour all section arrows."""
        for section in self.collapsible_sections:
            section.update_arrow_color()


    def apply_always_on_top(self, enabled: bool):
        """Apply Always-on-Top state using both Tk and WinAPI."""
        try:
            self.attributes("-topmost", enabled)
        except Exception as e:
            print("[AlwaysOnTop] Tk error:", e)

        try:
            import ctypes
            hwnd = self.winfo_id()
            hWndTopMost = -1 if enabled else -2
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                hWndTopMost,
                0, 0, 0, 0,
                0x0003  # SWP_NOSIZE | SWP_NOMOVE
            )
        except Exception as e:
            print("[AlwaysOnTop] WinAPI error:", e)
            
            
    def resize_to_fit(self):
        """Force the window to resize itself to the natural height of its contents."""
        self.update_idletasks()  # Recalculate layout
        req_width = self.winfo_reqwidth()
        req_height = self.winfo_reqheight()

        # Apply new size
        self.geometry(f"{req_width}x{req_height}")

    # ===================================================================
    #  Save ALL toggle states to JSON
    # ===================================================================
    
    def save_section_states(self):
        """Save expanded/collapsed states of all collapsible sections."""
        if not hasattr(self, "collapsible_sections"):
            return

        states = {}
        for section in self.collapsible_sections:
            states[section.section_id] = section.open

        # Load current JSON
        data = load_state()

        # Update section states
        data["section_states"] = states

        save_state(data)

    
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
        new["tooltips_enabled"] = self.tooltips_enabled_var.get()

        # -------------------------
        # Debug only changed keys
        # -------------------------
        
        for key, value in new.items():
            if key not in old or old[key] != value:
                print(f"[DEBUG] {key} → {value}")
                
        # Retain collapsible section states
        section_states = {}
        for section in self.collapsible_sections:
            section_states[section.section_id] = section.open
        new["section_states"] = section_states

        # -------------------------
        # Save JSON
        # -------------------------
        
        save_state(new)

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

# ===================================================================
# Launch App
# ===================================================================

if __name__ == "__main__":
    app = UtilityControlApp()
    app.mainloop()

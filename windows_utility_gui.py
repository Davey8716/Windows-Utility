# ===================================================================
#  Screen Tab Mover + USB Reminder Control Panel
#  Modern UI using CustomTkinter
# ===================================================================

import customtkinter as ctk
import tkinter as tk
import os
import ctypes
from tkinter import messagebox
from windows_utility_toggles import switch_theme   # add at top with other imports
from windows_utility_toggles import UtilityActionsManager
from pathlib import Path
from screen_mover import SCREEN_MOVER
from state_manager import load_state, save_state
from screenshot_tool import take_desktop_screenshot
from tray_toggles import TrayIconManager

# Configure appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ===================================================================
# Simple Tooltip for CustomTkinter widgets
# ===================================================================

class CtkTooltip:
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip_window = None
        self.after_id = None

        # Gather all actual hoverable child widgets
        targets = [widget]

        for attr in ("_canvas", "_label", "_text_label", "_fg_label", "_border_frame"):
            if hasattr(widget, attr):
                obj = getattr(widget, attr)
                if obj:
                    targets.append(obj)

        if hasattr(widget, "_windows"):
            for win in widget._windows:
                targets.append(win)

        # Apply bindings to all relevant sub-widgets
        for t in targets:
            try:
                t.bind("<Enter>", self.schedule, add="+")
                t.bind("<Leave>", self.hide, add="+")
                t.bind("<Button-1>", self.hide, add="+")
            except:
                pass

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
        self.header.pack(fill="x", pady=(0, 4))


        self.label = ctk.CTkLabel(
            self.header,
            text=title_text,
            font=("Rubik UI", 16, "bold"),
            text_color="#008DFA"    # ← CTk Blue
            
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
            self.content.pack(fill="x", expand=True, pady=(0, 10), padx=10)

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

        # ==============================================================
        # Window / Topmost
        # ==============================================================
        self.attributes("-topmost", True)

        import ctypes
        ctypes.windll.user32.SetWindowPos(
            self.winfo_id(),
            -1,
            0, 0, 0, 0,
            0x0003
        )

        SCREEN_MOVER.app_root = self

        # ==============================================================
        # State / Actions
        # ==============================================================
        self.saved_state = load_state()
        self.actions = UtilityActionsManager(self)

        # ==============================================================
        # Window geometry
        # ==============================================================
        self.COLLAPSED_WIDTH = 500
        self.EXPANDED_WIDTH = 975
        self.WINDOW_HEIGHT = 1150

        self.geometry(f"{self.COLLAPSED_WIDTH}x{self.WINDOW_HEIGHT}")
        self.expanded = False

        self.resizable(False, False)

        # ==============================================================
        # Tray
        # ==============================================================
        self.tray = TrayIconManager(self)
        self.tray.create_tray_icon()
        self.protocol("WM_DELETE_WINDOW", self.tray.on_close_to_tray)

        SCREEN_MOVER.start()

        # ==============================================================
        # Variables (DEFINE ONCE, BEFORE WIDGETS)
        # ==============================================================
        self.theme_var = ctk.BooleanVar(
            value=self.saved_state.get("theme_dark", True)
        )
        switch_theme(self.theme_var.get())

        self.always_on_top_var = ctk.BooleanVar(
            value=self.saved_state.get("always_on_top_enabled", True)
        )

        self.minimize_all_var = ctk.BooleanVar(
            value=self.saved_state.get("minimize_all_enabled", False)
        )

        self.tooltips_enabled_var = ctk.BooleanVar(
            value=self.saved_state.get("tooltips_enabled", True)
        )
        self.tooltips_enabled = self.tooltips_enabled_var.get()

        # ==============================================================
        # Collapsible registry
        # ==============================================================
        self.collapsible_sections = []

        # ==============================================================
        # Root container (2 fixed columns, full height)
        # ==============================================================
        self.root_container = ctk.CTkFrame(self, fg_color="transparent")
        self.root_container.pack(fill="both", expand=True)
        
        self.root_container.grid_propagate(False)
        self.root_container.pack_propagate(False)

        self.root_container.columnconfigure(0, weight=0, minsize=450)
        self.root_container.columnconfigure(1, weight=0, minsize=450)
        self.root_container.rowconfigure(0, weight=1)

        # ==============================================================
        #  MAIN FRAMES LEFT HEADER
        # ==============================================================
        
        self.main_frame = ctk.CTkScrollableFrame(
            self.root_container,
            width=450,
            fg_color="transparent"
        )
        self.main_frame.grid(row=0, column=0, sticky="ns")

        title = ctk.CTkLabel(
            self.main_frame,
            text="🦉 Daily Hassles? Gone!",
            font=("Rubik UI", 24, "bold")
        )
        title.pack(pady=10)

        # ==============================================================
        #  SIDE PANEL RIGHT HEADER
        # ==============================================================


        self.side_frame = ctk.CTkScrollableFrame(
            self.root_container,
            width=450,
            fg_color="transparent"
        )
        self.side_frame.grid(row=0, column=1, sticky="ns")
        self.side_frame.grid_remove()


        # ==============================================================
        # Right Column Header
        # ==============================================================

        self.advanced_title = ctk.CTkLabel(
            self.side_frame,
            text="⚠ Advanced Tools",
            font=("Rubik UI", 22, "bold")
        )
        self.advanced_title.pack(anchor="w", padx=12, pady=(14, 10))
        
        # ==============================================================
        # Collapsible sections
        # ==============================================================
        self.misc_section = CollapsibleSection(
            self.main_frame,
            "User Interface:",
            section_id="misc",
            initial_open=self.saved_state.get("section_states", {}).get("misc", True)
        )
        self.collapsible_sections.append(self.misc_section)

        # ==============================================================
        # Right Column — Advanced Tool Sections (placeholders)
        # ==============================================================

        self.advanced_section_1 = CollapsibleSection(
            self.side_frame,
            "Experimental",
            section_id="advanced_1",
            initial_open=False
        )
        self.collapsible_sections.append(self.advanced_section_1)
        self.advanced_section_1.wrapper.pack(fill="x", padx=12, pady=(0, 6))

        self.advanced_section_2 = CollapsibleSection(
            self.side_frame,
            "Power & System",
            section_id="advanced_2",
            initial_open=False
        )
        self.collapsible_sections.append(self.advanced_section_2)
        self.advanced_section_2.wrapper.pack(fill="x", padx=12, pady=(0, 6))

        self.advanced_section_3 = CollapsibleSection(
            self.side_frame,
            "Debug / Maintenance",
            section_id="advanced_3",
            initial_open=False
        )
        self.collapsible_sections.append(self.advanced_section_3)
        self.advanced_section_3.wrapper.pack(fill="x", padx=12, pady=(0, 6))

        self.advanced_section_4 = CollapsibleSection(
            self.side_frame,
            "Privacy / Security",
            section_id="advanced_4",
            initial_open=False
        )
        self.collapsible_sections.append(self.advanced_section_4)
        self.advanced_section_4.wrapper.pack(fill="x", padx=12, pady=(0, 6))

        self.advanced_section_5 = CollapsibleSection(
            self.side_frame,
            "Miscellaneous",
            section_id="advanced_5",
            initial_open=False
        )
        self.collapsible_sections.append(self.advanced_section_5)
        self.advanced_section_5.wrapper.pack(fill="x", padx=12, pady=(0, 6))

        # ==============================================================
        # Expand / Collapse button
        # ==============================================================
        self.expand_btn = ctk.CTkButton(
            self,
            text="▶",
            width=28,
            height=80,
            corner_radius=8,
            command=self.toggle_side_panel,
            fg_color="#2a2a2a",
            hover_color="#3a3a3a",
            font=("Rubik UI", 18, "bold")
        )
        self.expand_btn.place(relx=1.0, rely=0.5, anchor="e")

        # -------------------------
        # Dark Mode Toggle
        # -------------------------

        self.theme_switch = ctk.CTkSwitch(
            self.misc_section.content,    # FIXED
            text="Dark Mode",
            variable=self.theme_var,
            command=self.actions.theme_toggle,
            font=("Rubik UI", 16, "bold")
        )

        if self.theme_var.get():
            self.theme_switch.configure(text="Dark Mode")
        else:
            self.theme_switch.configure(text="Light Mode")

        self.theme_switch.pack(anchor="w", padx=12, pady=(2, 4))

        CtkTooltip(self.theme_switch, "Light and Dark mode. Try Them!")

        # -------------------------
        # Always On Top Toggle
        # -------------------------

        self.always_on_top_switch = ctk.CTkSwitch(
            self.misc_section.content,
            text="Always On Top",
            variable=self.always_on_top_var,
            command=self.actions.always_on_top_toggle,
            font=("Rubik UI", 16, "bold")
        )
        self.always_on_top_switch.pack(anchor="w", padx=12, pady=(4, 4))

        CtkTooltip(
            self.always_on_top_switch,
            "When off DHG will show below other apps if they are maximized.\n"
            "When on DHG will always show on top of other apps.\n"
        )
        
        # -------------------------
        # Turn Off Tooltips Toggle
        # -------------------------

        self.tooltip_switch = ctk.CTkSwitch(
            self.misc_section.content,  
            text="Enable Tooltips",
            variable=self.tooltips_enabled_var,
            command=self.actions.tooltips_toggle,
            font=("Rubik UI", 16, "bold")
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
            self.misc_section.content, 
            text="Max/Min All Opened Program Windows",
            variable=self.minimize_all_var,
            command=self.actions.minimize_all_toggle,
            font=("Rubik UI", 16, "bold")
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
            self.main_frame,
            "Quick app/browser screen changer:",
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
            font=("Rubik UI", 16, "bold")
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
            font=("Rubik UI", 16, "bold")
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
            self.main_frame,
            "Drive Reminder Options:",
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
            font=("Rubik UI", 16, "bold")
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
            font=("Rubik UI", 16, "bold")
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
            font=("Rubik UI", 16, "bold")
            
        )
        
        self.opt_plug.pack(anchor="w", padx=10, pady=2)
        # Start with USB settings disabled

        winutil_section = CollapsibleSection(
            self.main_frame,
            "Windows Utilities:",
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
            font=("Rubik UI", 16, "bold")
        )
        self.power_toggle.pack(anchor="w", padx=10, pady=(2, 5))

        CtkTooltip(
            self.power_toggle,
            "⚠️⚠️ Toggles on/off power options ⚠️⚠️\n"
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
            text="System Settings",
            width=btn_width,
            command=lambda: os.system("start ms-settings:"),
            font=("Rubik UI", 16,"bold")
        )
        self.btn_settings.grid(row=0, column=0, sticky="w", pady=3)

        self.btn_device_mgr = ctk.CTkButton(
            util_grid,
            text="Device Manager",
            width=btn_width,
            command=lambda: os.system("devmgmt.msc"),
            font=("Rubik UI", 16, "bold")
        )
        self.btn_device_mgr.grid(row=1, column=0, sticky="w", pady=3)

        self.btn_task_mgr = ctk.CTkButton(
            util_grid,
            text="Task Manager",
            width=btn_width,
            command=lambda: os.system("taskmgr"),
            font=("Rubik UI", 16, "bold")
        )
        self.btn_task_mgr.grid(row=2, column=0, sticky="w", pady=3)

        self.btn_router = ctk.CTkButton(
            util_grid,
            text="Router Login",
            width=btn_width,
            command=self.actions.open_router_page,
            font=("Rubik UI", 16, "bold")
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
            font=("Rubik UI", 16, "bold")
        )
        self.btn_sleep.grid(row=0, column=1, sticky="e", pady=3)

        self.btn_lock = ctk.CTkButton(
            util_grid,
            text="🔒 Lock PC",
            width=btn_width,
            command=lambda: ctypes.windll.user32.LockWorkStation(),
            font=("Rubik UI", 16, "bold")
        )
        self.btn_lock.grid(row=1, column=1, sticky="e", pady=3)

        self.btn_restart = ctk.CTkButton(
            util_grid,
            text="🔁 Restart",
            width=btn_width,
            command=lambda: os.system("shutdown /r /t 0"),
            font=("Rubik UI", 16, "bold")
        )
        self.btn_restart.grid(row=2, column=1, sticky="e", pady=3)

        self.btn_shutdown = ctk.CTkButton(
            util_grid,
            text="⏻ Shutdown",
            width=btn_width,
            command=lambda: os.system("shutdown /s /t 0"),
            font=("Rubik UI", 16, "bold")
        )
        self.btn_shutdown.grid(row=3, column=1, sticky="e", pady=3)

        self.actions.toggle_power_buttons()

        # --------------------------------------------------------------
        #  Organising Utilities  (NEW GREY SECTION)
        # --------------------------------------------------------------

        

        organising_section = CollapsibleSection(
            self.main_frame,
            "Organising Utilities:",
            section_id="organising",
            initial_open=self.saved_state.get("section_states", {}).get("organising", True)
        )
        self.collapsible_sections.append(organising_section)
        self.organise_frame = organising_section.content

        # --------------------------------------------------------------
        # Desktop Screenshot Button (top)
        # --------------------------------------------------------------

        self.btn_desktop_screenshot = ctk.CTkButton(
            self.organise_frame,
            text="Desktop Screenshot",
            width=btn_width,
            command=lambda: take_desktop_screenshot(self),
            font=("Rubik UI", 16, "bold")
        )
        self.btn_desktop_screenshot.pack(anchor="w", pady=(5, 6))

        CtkTooltip(
            self.btn_desktop_screenshot,
            "Minimizes the app, takes a full desktop screenshot,\n"
            "lets you choose a save location, then restores the window."
        )

        # --------------------------------------------------------------
        # Folder Creator Row (button left, entry right)
        # --------------------------------------------------------------

        folder_row = ctk.CTkFrame(self.organise_frame, fg_color="transparent")
        folder_row.pack(anchor="w")

        # Left: Create Folder button
        self.btn_create_folder = ctk.CTkButton(
            folder_row,
            text="Folder To Desktop",
            width=btn_width,
            font=("Rubik UI", 16, "bold"),
            command=self._create_desktop_folder
        )
        self.btn_create_folder.pack(side="left", padx=(5, 8))

        CtkTooltip(
            self.btn_create_folder,
            "Type a folder name in the box → Click to create\n"
            "A new folder will appear instantly on your Desktop."
        )

        # Right: Folder name entry
        self.folder_name_var = ctk.StringVar()
        self.folder_name_entry = ctk.CTkEntry(
            folder_row,
            placeholder_text="Folder name…",
            textvariable=self.folder_name_var,
            font=("Rubik UI", 16, "bold"),
            width=220
        )
        self.folder_name_entry.pack(side="left")

        # --------------------------------------------------------------
        #  Desktop Backup  (NEW COLLAPSIBLE SECTION)
        # --------------------------------------------------------------

        desktop_backup_section = CollapsibleSection(
            self.main_frame,
            "Desktop Backup Utilties:",
            section_id="desktop_backup",
            initial_open=self.saved_state.get("section_states", {}).get("desktop_backup", True)
        )
        self.collapsible_sections.append(desktop_backup_section)
        self.desktop_backup_frame = desktop_backup_section.content

        # ===================================================================
        #  Backup Taskbar + Open Backup
        # ===================================================================

        backup_buttons_frame = ctk.CTkFrame(
            self.desktop_backup_frame,
            fg_color="transparent"
        )
        backup_buttons_frame.pack(anchor="w", padx=10, pady=(5, 2))

        # BACKUP BUTTON (top)
        self.btn_backup_pins = ctk.CTkButton(
            backup_buttons_frame,
            text="Backup Taskbar",
            font=("Rubik UI", 15, "bold"),
            width=btn_width,
            command=self.actions.backup_pinned_shortcuts
        )
        self.btn_backup_pins.pack(anchor="w", pady=(0, 5))

        CtkTooltip(
            self.btn_backup_pins,
            "Backs up Taskbar icons to a folder chosen\n"
            "by Change Folder button.\n"
        )

        # OPEN BACKUP BUTTON (underneath)
        self.btn_open_backup = ctk.CTkButton(
            backup_buttons_frame,
            text="Open Backup",
            font=("Rubik UI", 15, "bold"),
            width=btn_width,
            command=self.actions.open_backup_folder
        )
        self.btn_open_backup.pack(anchor="w", pady = (0,5))

        CtkTooltip(
            self.btn_open_backup,
            "Opens backed up Taskbar icons folder location.\n"
        )

        # ===================================================================
        #  Backup Folder Path Display + Change Button
        # ===================================================================


        path_inner = ctk.CTkFrame(
            self.desktop_backup_frame,
            fg_color="transparent"
        )
        path_inner.pack(fill="x", padx=10, pady=(0, 8))

        # Variable must exist BEFORE entry
        self.backup_path_var = ctk.StringVar(
            value=self.saved_state.get("backup_folder_path", str(Path.home()))
        )

        self.btn_change_path = ctk.CTkButton(
            path_inner,
            text=" Change Folder",
            width=btn_width,
            font=("Rubik UI", 16, "bold"),
            command=self.actions.change_backup_folder
        )
        self.btn_change_path.pack(anchor="w", pady = (0,5))

        CtkTooltip(
            self.btn_change_path,
            "Chooses folder path for backing up Taskbar icons.\n"
        )

        self.entry_backup_path = ctk.CTkEntry(
            path_inner,
            textvariable=self.backup_path_var,
            font=("Rubik UI", 16),
            state="readonly"
        )
        self.entry_backup_path.pack(side="left", fill="x", expand=True, padx=(10, 8))
        
    # ==============================================================
    # Side panel toggle (NO UI CREATION HERE)
    # ==============================================================
    
    def toggle_side_panel(self):
        if not self.expanded:
            self.side_frame.grid(row=0, column=1, sticky="ns")
            self.geometry(f"{self.EXPANDED_WIDTH}x{self.WINDOW_HEIGHT}")
            self.expand_btn.configure(text="◀")
            self.expanded = True
        else:
            self.side_frame.grid_remove()
            self.geometry(f"{self.COLLAPSED_WIDTH}x{self.WINDOW_HEIGHT}")
            self.expand_btn.configure(text="▶")
            self.expanded = False

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
        """Keep the window height locked; never auto-resize to content."""
        self.update_idletasks()  # Recalculate layout

        # Lock to the configured size (width depends on expanded state)
        width = self.EXPANDED_WIDTH if self.expanded else self.COLLAPSED_WIDTH
        self.geometry(f"{width}x{self.WINDOW_HEIGHT}")


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
        # Backup folder path (SAFE)
        # -------------------------

        if hasattr(self, "backup_path_var"):
            # Normal case: Organising Utilities section has been built
            new["backup_folder_path"] = self.backup_path_var.get()
        else:
            # Early-startup case: preserve whatever was in the file
            new["backup_folder_path"] = old.get("backup_folder_path", "")

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
        
    # ===================================================================
    #  Create Folder On Desktop
    # ===================================================================
    
    def _create_desktop_folder(self):
        

        folder_name = self.folder_name_var.get().strip()

        # Basic validation
        if not folder_name:
            messagebox.showerror("Error", "Please type a folder name first.")
            return

        # Resolve desktop path
        desktop = os.path.join(os.path.join(os.environ["USERPROFILE"]), "Desktop")
        new_path = os.path.join(desktop, folder_name)

        try:
            if os.path.exists(new_path):
                messagebox.showerror("Error", "A folder with that name already exists on Desktop.")
                return

            os.makedirs(new_path)
            
            self.folder_name_var.set("")     # <-- clears the entry box

        except Exception as e:
            messagebox.showerror("Error", f"Could not create folder:\n{e}")

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

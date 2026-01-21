# ===================================================================
#  Screen Tab Mover + USB Reminder Control Panel
#  Modern UI using CustomTkinter
# ===================================================================

import os
import sys
import ctypes
import win32gui
import win32con
import string
import shutil
import customtkinter as ctk
from tkinter import filedialog
from datetime import datetime
from tkinter import messagebox
from tooltips import CtkTooltip
from pathlib import Path
from screen_mover import SCREEN_MOVER
from state_manager import load_state, save_state
from screenshot_tool import take_desktop_screenshot
from tray_toggles import TrayIconManager
from universal_bookmarks_export import BraveBookmarksExporter
from utility_toggles import switch_theme, UtilityActionsManager 
from collapsible_section import CollapsibleSection


# Configure appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

MUTEX_NAME = "Global\\DailyHasslesGone_SingleInstance"

def get_drive_info():
            drives = []
            for letter in string.ascii_uppercase:
                path = f"{letter}:\\"
                if os.path.exists(path):
                    try:
                        total, used, free = shutil.disk_usage(path)
                        drives.append({
                            "drive": path,
                            "total": total,
                            "free": free
                        })
                    except Exception:
                        pass
            return drives

def bring_existing_instance_to_front():
    def enum_handler(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if "Daily Hassles? Gone!" in title:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

                win32gui.SetForegroundWindow(hwnd)
                return False
        return True

    win32gui.EnumWindows(enum_handler, None)

def ensure_single_instance():
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_error = kernel32.GetLastError()

    ERROR_ALREADY_EXISTS = 183
    if last_error == ERROR_ALREADY_EXISTS:
        bring_existing_instance_to_front()
        sys.exit(0)

    return mutex


# ===================================================================
#  Main App Gui Left Side
# ===================================================================

class UtilityControlApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        from right_utility_gui import AdvancedToolsPanel
        
        mutex = ensure_single_instance()

        # ==============================================================
        # Window / Topmost
        # ==============================================================
        self.attributes("-topmost", True)


        ctypes.windll.user32.SetWindowPos(
            self.winfo_id(),
            -1,
            0, 0, 0, 0,
            0x0003
        )

        # ==============================================================
        # State / Actions
        # ==============================================================
        
        self.saved_state = load_state()
        self.actions = UtilityActionsManager(self)
        
        # ==============================================================
        # MAGNET/ OWNERSHIP
        # ==============================================================
        
        self._ui_ready = False
        self._syncing_windows = False
        self._drag_owner = None

        # ==============================================================
        # Window geometry
        # ==============================================================
        
        self.WINDOW_WIDTH = 510
        self.WINDOW_HEIGHT = 1150
        
        btn_width = 120 # Large buttons
        small_btn_width = 90 # Small buttons

        self.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")
        self.expanded = False

        self.resizable(False, False)

        # ==============================================================
        # Tray
        # ==============================================================
        self.tray = TrayIconManager(self)
        self.tray.create_tray_icon()
        self.protocol("WM_DELETE_WINDOW", self.tray.on_close_to_tray)

        SCREEN_MOVER.start()
        SCREEN_MOVER.app_root = self

        # ==============================================================
        # Variables (DEFINE ONCE, BEFORE WIDGETS) INITIALIZING STATE
        # ==============================================================
        
        self.theme_var = ctk.BooleanVar(
            value=self.saved_state.get("theme_dark", True)
        )
        switch_theme(self.theme_var.get())

        self.main_always_on_top_enabled = ctk.BooleanVar(
            value=self.saved_state.get("main_always_on_top_enabled", True)
            
        )
        
        self.right_always_on_top_enabled = self.saved_state.get(
            "right_always_on_top_enabled", True
        )

        self.minimize_all_var = ctk.BooleanVar(
            value=self.saved_state.get("minimize_all_enabled", False)
        )

        self.tooltips_enabled_var = ctk.BooleanVar(
            value=self.saved_state.get("tooltips_enabled", True)
        )
        self.tooltips_enabled = self.tooltips_enabled_var.get()
        
        self.brave_export_path_var = ctk.StringVar(
            value=self.saved_state.get("brave_export_path", "")
        )
        
        self.power_toggle_var = ctk.BooleanVar(
            value=self.saved_state.get("show_power_buttons", False)
        )
        
        self._folder_status_after_id = None
        
        self.master_toggle_left_var = ctk.BooleanVar(
            value=self.saved_state.get("master_toggle_left", True)
        )


        self.side_panel_open = self.saved_state.get("side_panel_open", False)
        self.expanded = self.side_panel_open
        
        self.bookmarks_exporter_var = ctk.BooleanVar(
            value=self.saved_state.get("bookmarks_exporter", True)
        )


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
        
        self.bind("<Configure>", lambda e: self._sync_windows("main"))
        self.bind("<ButtonPress-1>", lambda e: self._set_drag_owner("main"))
        self.bind("<ButtonRelease-1>", lambda e: self._clear_drag_owner())
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
    
        # ==============================================================
        #  MAIN FRAMES LEFT HEADER
        # ==============================================================
        
        self.main_frame = ctk.CTkScrollableFrame(
            self.root_container,
            width=450,
            fg_color="transparent"
        )
        self.main_frame.grid(row=0, column=0, sticky="ns")

        # --------------------------------------------------------------
        # Title row (label + master collapse button)
        # --------------------------------------------------------------

        title_row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        title_row.pack(fill="x", padx=10, pady=10)

        title = ctk.CTkLabel(
            title_row,
            text="Problems Gone",
            font=("Rubik UI", 20, "bold")
        )
        title.pack(padx = 50, pady = 10)

        self.master_collapse_btn = ctk.CTkButton(
            title_row,
            text="▼",
            width=32,
            height=28,
            font=("Rubik UI", 18, "bold"),
            fg_color="transparent",
            hover_color="#202020",
            command=self.toggle_all_left_sections
        )
        self.master_collapse_btn.pack(side="right")

        # ==============================================================
        # Collapsible sections
        # ==============================================================

        self.misc_section = CollapsibleSection(
            self.main_frame,
            "User Interface:",
            section_id="user_interface",
            app=self,
            initial_open=self.saved_state.get("left_section_states", {}).get("misc", True)
        )
        self.collapsible_sections.append(self.misc_section)

        toggles_row = ctk.CTkFrame(self.misc_section.content, fg_color="transparent")
        toggles_row.pack(fill="x", padx=12, pady=(4, 6))

        left_col = ctk.CTkFrame(toggles_row, fg_color="transparent")
        left_col.pack(side="left", anchor="nw")

        right_col = ctk.CTkFrame(toggles_row, fg_color="transparent")
        right_col.pack(side="right", anchor="ne")
        
        # -------------------------
        # Dark Mode Toggle (LEFT)
        # -------------------------

        self.theme_switch = ctk.CTkSwitch(
            left_col,
            text="Dark Mode",
            variable=self.theme_var,
            command=self.actions.theme_toggle,
            font=("Rubik UI", 15, "bold")
        )
        self.theme_switch.pack(anchor="w", pady=(2, 0))

        if self.theme_var.get():
            self.theme_switch.configure(text="Dark Mode On")
        else:
            self.theme_switch.configure(text="Light Mode On")

        CtkTooltip(self.theme_switch, "Light and Dark mode. Try Them!")


        self.power_toggle = ctk.CTkSwitch(
            left_col,
            text="Show Power Buttons",
            variable=self.power_toggle_var,
            command=self.actions.toggle_power_buttons,
            font=("Rubik UI", 15, "bold")
        )
        self.power_toggle.pack(anchor="w", pady=(0, 0))
        
        if self:
            self.power_toggle.configure(text="Power Options On")
        else:
            self.power_toggle.configure(text="Power Options Off")

        CtkTooltip(
            self.power_toggle,
            "⚠️⚠️ Toggles on/off power options ⚠️⚠️\n"
            "Made for clumsy people who might shutdown by mistake etc.\n"
            "Remembers if it's on or off on startup.\n"
        )

        # -------------------------
        # Always On Top Toggle (LEFT)
        # -------------------------
        
        self.main_always_on_top_var = ctk.BooleanVar(
            value=self.saved_state.get("main_always_on_top_enabled", True)
        )

        self.right_always_on_top_var = ctk.BooleanVar(
            value=self.saved_state.get("right_always_on_top_enabled", True)
        )
        
        self.always_on_top_var = self.main_always_on_top_var

        self.always_on_top_switch = ctk.CTkSwitch(
            left_col,
            text="",
            variable=self.always_on_top_var,
            command=self.actions.always_on_top_toggle,
            font=("Rubik UI", 15, "bold")
        )
        self.always_on_top_switch.pack(anchor="w", pady=(0, 0))
        
        if self.always_on_top_var.get():
            self.always_on_top_switch.configure(text="Always On Top On")
        else:
            self.always_on_top_switch.configure(text="Always On Top Off")

        CtkTooltip(
            self.always_on_top_switch,
            "When off DHG will show below other apps if they are maximized.\n"
            "When on DHG will always show on top of other apps.\n"
        )
        

        # -------------------------
        # Enable Tooltips Toggle (RIGHT)
        # -------------------------

        self.tooltip_switch = ctk.CTkSwitch(
            left_col,   # ✅ FIXED PARENT
            text="",
            variable=self.tooltips_enabled_var,
            command=self.actions.tooltips_toggle,
            font=("Rubik UI", 15, "bold")
        )
        self.tooltip_switch.pack(anchor="w", pady=(2, 0))
        
        if self.tooltips_enabled_var.get():
            self.tooltip_switch.configure(text="Tooltips On")
        else:
            self.tooltip_switch.configure(text="Tooltips Off")

        CtkTooltip(
            self.tooltip_switch,
            "Enable all hover tooltips across the entire app."
        )

        # -------------------------
        # Max/Min All Programs Toggle (RIGHT)
        # -------------------------

        self.minimize_all_switch = ctk.CTkSwitch(
            left_col,
            text="Max/Min All Programs",
            variable=self.minimize_all_var,
            command=self.actions.minimize_all_toggle,
            font=("Rubik UI", 15, "bold")
        )
        self.minimize_all_switch.pack(anchor="w", pady=(0, 0))
        
        if self:
            self.minimize_all_switch.configure(text="Maximize All Off")
        else:
            self.minimize_all_switch.configure(text="Maximize All On")

        CtkTooltip(
            self.minimize_all_switch,
            "When off all opened tabs are visible.\n"
            "When toggled on all screens are minimized.\n"
            "The App Gui itself stays maximized and in front of all other programs.\n"
        )
        
        # ==========================
        # RIGHT COLUMN
        # ==========================

        self.btn_sleep = ctk.CTkButton(
            right_col,
            text="Sleep",
            width=small_btn_width,
            command=lambda: os.system(
                "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"
            ),
            font=("Rubik UI", 15, "bold")
        )
        
        self.btn_lock = ctk.CTkButton(
            right_col,
            text="Lock PC",
            width=small_btn_width,
            command=lambda: ctypes.windll.user32.LockWorkStation(),
            font=("Rubik UI", 15, "bold")
        )
        
        self.btn_restart = ctk.CTkButton(
            right_col,
            text="Restart",
            width=small_btn_width,
            command=lambda: os.system("shutdown /r /t 0"),
            font=("Rubik UI", 15, "bold")
        )
        
        self.btn_shutdown = ctk.CTkButton(
            right_col,
            text="Shutdown",
            width=small_btn_width,
            command=lambda: os.system("shutdown /s /t 0"),
            font=("Rubik UI", 15, "bold")
        )
        
        # ------------------------------------------------------------------
        #  Screen-Tab Mover Group Box(frame)
        # ------------------------------------------------------------------
        
        self.mover_section = CollapsibleSection(
            self.main_frame,
            "Quick app/browser screen changer:",
            section_id="screen_mover",
            app = self,
            initial_open=self.saved_state["left_section_states"].get("mover", True)
        )
        self.collapsible_sections.append(self.mover_section)

        self.mmb_var = ctk.BooleanVar(
            value=self.saved_state.get("mmb_activation_enabled", True)
        )

        self.mmb_switch = ctk.CTkSwitch(
            self.mover_section.content,
            variable=self.mmb_var,
            command=lambda: (
                self._sync_toggle_label(
                    self.mmb_switch,
                    "Middle Mouse To Move",
                    self.mmb_var
                ),
                self.save_all_settings()
            ),
            font=("Rubik UI", 15, "bold")
        )
        self.mmb_switch.pack(anchor="w", padx=10, pady=0)
        
        self._sync_toggle_label(
            self.mmb_switch,
            "Middle Mouse To Move",
            self.mmb_var
        )


        # Add tooltip
        CtkTooltip(
            self.mmb_switch,
            "Click and hold the middle mouse.\n"
            "At the top of any program window.\n"
            "When the arrow appears, Move left or right\n"
            "To move the window to another screen."
        )

        # NEW: Keep Windows in Flick Zone toggle
        self.auto_align_var = ctk.BooleanVar(value=self.saved_state.get("auto_align_enabled", False))
        self.auto_align_switch = ctk.CTkSwitch(
            self.mover_section.content,   # FIXED
            text="Windows In Move Zone",
            variable=self.auto_align_var,
            command=self.actions.auto_align_toggle,     # <-- THIS WAS MISSING
            font=("Rubik UI", 15, "bold")
        )
        self.auto_align_switch.pack(anchor="w", padx=10, pady=2)
        
        self._sync_toggle_label(
            self.auto_align_switch,
            "Windows In Move Zone",
            self.auto_align_var
        )

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
            section_id="drive_reminder_options",
            app = self,
            initial_open=self.saved_state["left_section_states"].get("usb", True)
        )
        self.collapsible_sections.append(usb_section)

        # USB sub-toggle initializers (load from JSON)
        self.opt_idle_var = ctk.BooleanVar(
            value=self.saved_state.get("usb_idle_enabled", True)
        )


        self.opt_download_var = ctk.BooleanVar(
            value=self.saved_state.get("usb_download_enabled", True)
        )

        self.opt_plug_var = ctk.BooleanVar(
            value=self.saved_state.get("usb_plug_enabled", True)
        )
        
        self.opt_idle = ctk.CTkSwitch(
            usb_section.content,
            text="Idle-plugged Reminder",
            variable=self.opt_idle_var,
            command=lambda: (
                self._sync_toggle_label(
                    self.opt_idle,
                    "Idle-plugged Reminder",
                    self.opt_idle_var
                ),
                self.save_all_settings()
            ),
            font=("Rubik UI", 15, "bold")
        )
        self.opt_idle.pack(anchor="w", padx=10, pady=2)

        self.opt_download = ctk.CTkSwitch(
            usb_section.content,
            text="Download-finished Reminder",
            variable=self.opt_download_var,
            command=lambda: (
                self._sync_toggle_label(
                    self.opt_download,
                    "Download-finished Reminder",
                    self.opt_download_var
                ),
                self.save_all_settings()
            ),
            font=("Rubik UI", 15, "bold")
        )
        self.opt_download.pack(anchor="w", padx=10, pady=2)

        self.opt_plug = ctk.CTkSwitch(
            usb_section.content,
            text="Plug / Unplug Notification",
            variable=self.opt_plug_var,
            command=lambda: (
                self._sync_toggle_label(
                    self.opt_plug,
                    "Plug / Unplug Notification",
                    self.opt_plug_var
                ),
                self.save_all_settings()
            ),
            font=("Rubik UI", 15, "bold")
        )
        self.opt_plug.pack(anchor="w", padx=10, pady=2)

        self._sync_toggle_label(self.opt_idle, "Idle-plugged Reminder", self.opt_idle_var)
        self._sync_toggle_label(self.opt_download, "Download-finished Reminder", self.opt_download_var)
        self._sync_toggle_label(self.opt_plug, "Plug / Unplug Notification", self.opt_plug_var)

        # --------------------------------------------------------------
        #  Organising Utilities  (NEW GREY SECTION)
        # --------------------------------------------------------------

        organising_section = CollapsibleSection(
            self.main_frame,
            "Organising Utilities:",
            section_id="organising_utilties",
            app = self,
            initial_open=self.saved_state.get("left_section_states", {}).get("organising", True)
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
            font=("Rubik UI", 15, "bold")
        )
        self.btn_desktop_screenshot.pack(anchor="w", padx=10, pady=(5, 2))

        CtkTooltip(
            self.btn_desktop_screenshot,
            "Minimizes the app, takes a full desktop screenshot,\n"
            "lets you choose a save location, then restores the window."
        )
        
        # --------------------------------------------------------------
        # Folder Creator Row (button left, entry right)
        # --------------------------------------------------------------

        folder_row = ctk.CTkFrame(self.organise_frame, fg_color="transparent")
        folder_row.pack(fill="x", padx=10, pady=(5, 2))

        # left: button (same row)
        self.btn_create_folder = ctk.CTkButton(
            folder_row,
            text="Folder To Desktop",
            width=btn_width,
            font=("Rubik UI", 15, "bold"),
            command=self._create_desktop_folder,
            state="disabled"
        )
        self.btn_create_folder.pack(side="left")

        # right: entry + status (same row)
        entry_group = ctk.CTkFrame(folder_row, fg_color="transparent")
        entry_group.pack(side="right")

        self.folder_name_var = ctk.StringVar()

        self.folder_name_entry = ctk.CTkEntry(
            entry_group,
            placeholder_text="Folder name…",
            textvariable=self.folder_name_var,
            font=("Rubik UI", 15, "bold"),
            width=150
        )
        self.folder_name_entry.pack(side="left", padx = 5)
        
        CtkTooltip(
            self.btn_create_folder,
            "Type a folder name in the box → Click to create\n"
            "A new folder will appear instantly on your Desktop\n"
            "Greyed out if no name entered.\n"
        )
        

        self.folder_status_label = ctk.CTkLabel(
            entry_group,
            text=" ",                  # IMPORTANT: not empty, so it has width
            width=150,
            anchor="w",
            font=("Rubik UI", 16,"bold"),
            text_color="#1f6aa5"
        )
        self.folder_status_label.pack(side="left", padx=(3, 0))

        self.folder_name_var.trace_add("write", self._update_create_folder_button)

        # --------------------------------------------------------------
        #  Desktop Backup  (NEW COLLAPSIBLE SECTION)
        # --------------------------------------------------------------

        desktop_backup_section = CollapsibleSection(
            self.main_frame,
            "Desktop Backup Utilties:",
            section_id="desktop_backup",
            app=self,
            initial_open=self.saved_state.get("left_section_states", {}).get("desktop_backup", True)
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
            font=("Rubik UI", 15, "bold"),
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
            font=("Rubik UI", 15),
            width = 360,
            state="readonly"
        )
        self.entry_backup_path.pack(anchor="w", pady = (0,5))
        
        # -------------------------------------------------
        # Final UI sync (ALL vars now exist)
        # -------------------------------------------------
        
        Desktop_icon_layout = CollapsibleSection(
            self.main_frame,
            "Desktop Icon Organiser:",
            section_id="desktop_icon_organiser",
            app=self
        )
        self.collapsible_sections.append(Desktop_icon_layout)
        
        # --------------------------------------------------
        # Apply master left collapse override (FINAL)
        # --------------------------------------------------

        if not self.master_toggle_left_var.get():
            for section in self.collapsible_sections:
                if isinstance(section, CollapsibleSection) and section.parent == self.main_frame:
                    if section.open:
                        section.toggle()

            self.master_collapse_btn.configure(text="▶")
        else:
            self.master_collapse_btn.configure(text="▼")

        
        self.actions.toggle_power_buttons()
        self.update_idletasks() 
        self.resize_to_fit()
        
        
        # --------------------------------------------------------------
        # Overlay expand button (CORRECT parent + placement)
        # --------------------------------------------------------------

        self.overlay_controls = ctk.CTkFrame(
            self.root_container,
            fg_color="transparent"
        )

        # Place relative to root_container, not the window
        self.overlay_controls.place(
            relx=1.0,
            rely=0.5,
            anchor="e",
            x=-6
        )

        self.expand_btn = ctk.CTkButton(
            self.overlay_controls,
            text="▼",
            width=28,
            height=80,
            corner_radius=8,
            command=self.toggle_side_panel,
            fg_color="#2a2a2a",
            hover_color="#3a3a3a",
            text_color="white",
            font=("Rubik UI", 18, "bold")
        )
        self.expand_btn.pack()

        CtkTooltip(self.expand_btn, "Toggles Advanced Tools panel.")

        # Ensure it stays above scrollable content
        self.overlay_controls.lift()
        self.expand_btn.lift()
        self.after(150, self._mark_ui_ready)
        
        self.advanced_panel = None
        self.advanced_panel = AdvancedToolsPanel(self)
        
        # --------------------------------------------------
        # Restore side panel open/closed state
        # --------------------------------------------------

        if self.saved_state.get("side_panel_open", False):
            self.advanced_panel.show()
            self.expand_btn.configure(text="▶")
        else:
            self.advanced_panel.hide()
            self.expand_btn.configure(text="▼")
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
                
    def _mark_ui_ready(self):
                self._ui_ready = True

    
    # ==================================================
    # Window magnet sync (main <-> advanced)
    # ==================================================

    def _sync_windows(self, source):
        if self._syncing_windows:
            return
        
        if not getattr(self, "_ui_ready", False):
            return
        
        # 🔑 advanced panel may not exist yet
        if not hasattr(self, "advanced_panel"):
            return

        if self._drag_owner and self._drag_owner != source:
            return

        side = self.advanced_panel
        if not side or not side.winfo_exists():
            return

        self._syncing_windows = True
        try:
            if source == "main":
                x = self.winfo_x()
                y = self.winfo_y()

                target_x = x + self.winfo_width()
                target_y = y

                if side.winfo_x() == target_x and side.winfo_y() == target_y:
                    return

                side.geometry(f"+{target_x}+{target_y}")

            elif source == "side":
                x = side.winfo_x()
                y = side.winfo_y()

                target_x = x - self.winfo_width()
                target_y = y

                if self.winfo_x() == target_x and self.winfo_y() == target_y:
                    return

                self.geometry(f"+{target_x}+{target_y}")

        finally:
            self._syncing_windows = False

    def _set_drag_owner(self, who):
        self._drag_owner = who

    def _clear_drag_owner(self):
        self._drag_owner = None

    def _sync_toggle_label(self, switch, base_text, var):
        if var.get():
            switch.configure(text=f"{base_text} On")
        else:
            switch.configure(text=f"{base_text} Off")
        

    def toggle_all_left_sections(self):
        new_state = not self.master_toggle_left_var.get()
        self.master_toggle_left_var.set(new_state)

        for section in self.collapsible_sections:
            if not isinstance(section, CollapsibleSection):
                continue

            if section.parent == self.main_frame:
                if section.open != new_state:
                    section.toggle()

        self.master_collapse_btn.configure(text="▼" if new_state else "▶")
        self.save_all_settings()




    def _choose_brave_export_path(self):
        default_name = f"Brave_Bookmarks_Export_{datetime.now().strftime('%Y-%m-%d')}.html"

        path = filedialog.asksaveasfilename(
            parent=self,  # <- critical: owned by your CTk root
            title="Save Brave Bookmarks As",
            defaultextension=".html",
            initialfile=default_name,
            filetypes=[("HTML files", "*.html")],
        )

        if path:
            self.brave_export_path_var.set(path)

    def _run_brave_export(self):
        default_name = f"Brave_Bookmarks_{datetime.now().strftime('%Y-%m-%d')}.html"

        path = filedialog.asksaveasfilename(
            parent=self,   # ✅ owned by CTk root
            title="Save Brave Bookmarks As",
            defaultextension=".html",
            initialfile=default_name,
            filetypes=[("HTML files", "*.html")]
        )
        
        if not path:
            return
        
        if path:
            self.brave_export_path_var.set(path)
            self.save_all_settings()
            BraveBookmarksExporter().export_to_file(path)

    # ==============================================================
    # Side panel toggle (NO UI CREATION HERE)
    # ==============================================================
    
    def toggle_side_panel(self):
        panel = self.advanced_panel

        if panel.winfo_viewable():
            panel.hide()
            self.expand_btn.configure(text="▼")
        else:
            panel.show()
            self.expand_btn.configure(text="▶")

        self.save_all_settings()


    def update_collapsible_arrow_colours(self):
        for section in self.collapsible_sections:
            if not isinstance(section, CollapsibleSection):
                continue

            section.update_arrow_color()

    def apply_always_on_top(self, enabled: bool):
        """Apply Always-on-Top state using both Tk and WinAPI."""
        try:
            self.attributes("-topmost", enabled)
        except Exception as e:
            print("[AlwaysOnTop] Tk error:", e)

        try:
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

    # ===================================================================
    #  Save ALL toggle states to JSON
    # ===================================================================
    
    def save_all_settings(self):

        left_states = {}
        right_states = {}

        old = load_state()
        new = dict(old)

        new["master_toggle_left"] = self.master_toggle_left_var.get()

        # -------------------------
        # Screen Mover settings
        # -------------------------
        new["mmb_activation_enabled"] = self.mmb_var.get()
        new["auto_align_enabled"] = self.auto_align_var.get()
        new["minimize_all_enabled"] = self.minimize_all_var.get()
        new["brave_export_path"] = self.brave_export_path_var.get()
        new["bookmarks_exporter"] = self.bookmarks_exporter_var.get()

        # ❌ REMOVE THIS
        # new["bookmarks_exporter"] = self.bookmarks_exporter_var.get()

        # -------------------------
        # USB settings
        # -------------------------
        new["usb_idle_enabled"] = self.opt_idle_var.get()
        new["usb_download_enabled"] = self.opt_download_var.get()
        new["usb_plug_enabled"] = self.opt_plug_var.get()

        # -------------------------
        # Theme / window
        # -------------------------
        new["theme_dark"] = self.theme_var.get()
        new["show_power_buttons"] = self.power_toggle_var.get()
        new["tooltips_enabled"] = self.tooltips_enabled_var.get()
        new["main_always_on_top_enabled"] = self.main_always_on_top_var.get()
        new["right_always_on_top_enabled"] = self.right_always_on_top_var.get()

        new["side_panel_open"] = (
            self.advanced_panel.winfo_viewable()
            if hasattr(self, "advanced_panel") and self.advanced_panel.winfo_exists()
            else False
        )

        # -------------------------
        # Collapsible section states
        # -------------------------
        for section in self.collapsible_sections:
            if not isinstance(section, CollapsibleSection):
                continue

            if section.parent == self.main_frame:
                left_states[section.section_id] = section.open

            elif (
                hasattr(self, "advanced_panel")
                and self.advanced_panel
                and self.advanced_panel.winfo_exists()
                and section.parent == self.advanced_panel.side_frame
            ):
                right_states[section.section_id] = section.open

        # ✅ NOW write them
        new["left_section_states"] = left_states
        new["right_section_states"] = right_states

        # ✅ Kill legacy keys
        new.pop("bookmarks_exporter", None)
        new.pop("Bookmarks_exporter", None)

        save_state(new)

    def save_section_states(self):
        """Save expanded/collapsed states of all collapsible sections."""
        if not hasattr(self, "collapsible_sections"):
            return
        
        left_states = {}
        right_states = {}

        for section in self.collapsible_sections:
            if section.parent == self.main_frame:
                left_states[section.section_id] = section.open
            elif section.parent == self.side_frame:
                right_states[section.section_id] = section.open

        # Load current JSON
        data = load_state()

        # Update section states
        
        data["left_section_states"] = left_states
        data["right_section_states"] = right_states
        
        print("collapsible count:", len(self.collapsible_sections))
        print("collapsible count:", len(self.collapsible_sections))
        for s in self.collapsible_sections:
            print("sec:", s.section_id, "parent:", type(s.parent), "toplevel:", s.parent.winfo_toplevel())
            
        save_state(data)
        
    def _set_folder_status_timed(self, text, duration_ms=2000):
        # Cancel any existing timer
        if self._folder_status_after_id:
            self.after_cancel(self._folder_status_after_id)
            self._folder_status_after_id = None

        # Set text immediately
        self.folder_status_label.configure(text=text)

        # Schedule clear
        self._folder_status_after_id = self.after(
            duration_ms,
            lambda: self.folder_status_label.configure(text="")
        )

    # ===================================================================
    #  Create Folder On Desktop
    # ===================================================================
    
    def _create_desktop_folder(self):
        folder_name = self.folder_name_var.get().strip()

        if not folder_name:
            return

        desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
        new_path = os.path.join(desktop, folder_name)

        try:
            if os.path.exists(new_path):
                messagebox.showerror(
                    "Error",
                    "A folder with that name already exists on Desktop."
                )
                return

            os.makedirs(new_path)

            # Clear entry
            self.folder_name_var.set("")

            # Timed success message
            self._set_folder_status_timed("Folder Made", 2000)

        except Exception as e:
            messagebox.showerror(
                "Error",
                f"Could not create folder:\n{e}"
            )
            
    def _update_create_folder_button(self, *_):
        name = self.folder_name_var.get().strip()
        
        if name:
            self.btn_create_folder.configure(state="normal")
            self.folder_status_label.configure(text="")
        else:
            self.btn_create_folder.configure(state="disabled")
            self.folder_status_label.configure(text="")

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

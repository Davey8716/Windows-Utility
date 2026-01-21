import os
import customtkinter as ctk
from tooltips import CtkTooltip
from collapsible_section import CollapsibleSection
from main_utility_gui import get_drive_info


class AdvancedToolsPanel(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app

        # --------------------------------------------------
        # Window config
        # --------------------------------------------------
        self.title("Advanced Tools")
        self.resizable(False, False)
        self.withdraw()  # start hidden
        
        self._desired_topmost = app.right_always_on_top_var.get()

        # Close button behaviour
        self.protocol("WM_DELETE_WINDOW", self.hide)

        # --------------------------------------------------
        # Scrollable content
        # --------------------------------------------------
        self.side_frame = ctk.CTkScrollableFrame(
            self,
            width=450,
            height=1150,
            fg_color="transparent"
        )
        self.side_frame.pack(fill="both", expand=True)

        self.advanced_title = ctk.CTkLabel(
            self.side_frame,
            text="Advanced Tools",
            font=("Rubik UI", 22, "bold")
        )
        self.advanced_title.pack(padx=12, pady=(20, 20))
        
        self.bind("<Configure>", lambda e: self.app._sync_windows("side"))
        self.bind("<ButtonPress-1>", lambda e: self.app._set_drag_owner("side"))
        self.bind("<ButtonRelease-1>", lambda e: self.app._clear_drag_owner())

        # ==================================================
        # Windows Utilities
        # ==================================================

        self.windows_utility_section = CollapsibleSection(
            self.side_frame,
            "Windows Utilities",
            section_id="Windows_utilities",
            app=self.app,
            initial_open=False
        )
        self.windows_utility_section.wrapper.pack(fill="x", padx=12, pady=(5, 6))
        
        CtkTooltip(
            self.windows_utility_section.toggle_btn,
            "Shows windows utilities here instead grouped by type \n"
            "not having to have them all cluttering up your taskbar."
        )
        app.collapsible_sections.append(self.windows_utility_section)

        parent = self.windows_utility_section.content

        self._add_windows_dropdown(parent, "System", self._system_utilities())
        self._add_windows_dropdown(parent, "Hardware", self._hardware_utilities())
        self._add_windows_dropdown(parent, "Network", self._network_utilities())
        self._add_windows_dropdown(parent, "Startup & Power", self._startup_power_utilities())
        self._add_windows_dropdown(parent, "Users", self._user_utilities())
        

        # ==================================================
        # Drive Space Display
        # ==================================================

        self.display_space_section = CollapsibleSection(
            self.side_frame,
            "Drive Space Display",
            section_id="drive_space_display",
            app=self.app,
            initial_open=False
        )
        self.display_space_section.wrapper.pack(fill="x", padx=12, pady=(0, 6))
        
        CtkTooltip(
            self.display_space_section.toggle_btn,
            "Shows disk usage for all detected drives."
        )
        
        app.collapsible_sections.append(self.display_space_section)
        


        drive_parent = self.display_space_section.content
        self.drive_labels = []

        def refresh_drive_display():
            for lbl in self.drive_labels:
                lbl.destroy()
            self.drive_labels.clear()

            for d in get_drive_info():
                used_gb = (d["total"] - d["free"]) / (1024**3)
                total_gb = d["total"] / (1024**3)
                free_gb = d["free"] / (1024**3)

                text = (
                    f"{d['drive']}  "
                    f"used: {used_gb:.1f} GB / "
                    f"Free: {free_gb:.1f} GB / "
                    f"Total: {total_gb:.1f} GB"
                )

                lbl = ctk.CTkLabel(
                    drive_parent,
                    text=text,
                    anchor="w",
                    font=("Rubik UI", 15)
                )
                lbl.pack(anchor="w", padx=12, pady=0)
                self.drive_labels.append(lbl)

        refresh_drive_display()

        def schedule_drive_refresh():
            refresh_drive_display()
            app.after(10_000, schedule_drive_refresh)

        schedule_drive_refresh()

        # ==================================================
        # Universal Bookmarks Exporter
        # ==================================================

        self.advanced_section_3 = CollapsibleSection(
            self.side_frame,
            "Universal Bookmarks Exporter",
            section_id="bookmarks_exporter",
            app=self.app,
            initial_open=False
        )
        self.advanced_section_3.wrapper.pack(fill= "x", padx=12, pady=(5, 6))

        self.btn_brave_export = ctk.CTkButton(
            self.advanced_section_3.content,
            text="Export Brave Bookmarks",
            width=180,
            font=("Rubik UI", 15, "bold"),
            command=app._run_brave_export,
        )
        self.btn_brave_export.pack(anchor="w",padx = 5, pady=(5, 4))
        
        CtkTooltip(
            self.btn_brave_export,
            "Exports brave bookmarks to a file path of your choice,\n"
            "remembers last saved location.\n"
        )

        self.brave_export_entry = ctk.CTkEntry(
            self.advanced_section_3.content,
            textvariable=app.brave_export_path_var,
            font=("Rubik UI", 15),
            width=360,
            state="readonly"
        )
        self.brave_export_entry.pack(anchor="w", padx = 5, pady=(5, 4))
        
        app.collapsible_sections.append(self.advanced_section_3)

    # ==================================================
    # Windows Utilities
    # ==================================================
    
    def _system_utilities(self):
        return {
            "Control Panel": lambda: os.system("control"),
            "System Settings": lambda: os.system("start ms-settings:"),
            "System Information": lambda: os.system("msinfo32"),
            "Task Manager": lambda: os.system("taskmgr"),
        }
        
    def _hardware_utilities(self):
        return {
            "Device Manager": lambda: os.system("devmgmt.msc"),
            "Disk Management": lambda: os.system("diskmgmt.msc"),
            "Services": lambda: os.system("services.msc"),
            "Event Viewer": lambda: os.system("eventvwr.msc"),
        }
        
    def _network_utilities(self):
        return {
            "Network Connections": lambda: os.system("ncpa.cpl"),
            "Firewall": lambda: os.system("wf.msc"),
            "IP Configuration": lambda: os.system("cmd /k ipconfig"),
            "Router Login": self.app.actions.open_router_page,
        }
        
    def _startup_power_utilities(self):
        return {
            "Startup Apps": lambda: os.system("start ms-settings:startupapps"),
            "Power Options": lambda: os.system("powercfg.cpl"),
        }
        
    def _user_utilities(self):
        return {}


    # ==================================================
    # Drop down helper
    # ==================================================
        
    def _add_windows_dropdown(self, parent, label, actions_map):
        placeholder = f"— {label} —"

        def runner(choice):
            if choice == placeholder:
                return
            action = actions_map.get(choice)
            if action:
                action()

        values = [placeholder] + sorted(actions_map.keys())

        dropdown = ctk.CTkOptionMenu(
            parent,
            values=values,
            command=runner,
            width=260,
            font=("Rubik UI", 15, "bold"),
            dropdown_font=("Rubik UI", 14),
        )

        dropdown.set(placeholder)  # ✅ force title display
        dropdown.pack(anchor="w", padx=12, pady=(4, 8))


    # ==================================================
    # Visibility helpers
    # ==================================================

    def show(self):
        self.app._sync_windows("main")
        self.deiconify()
        
        try:
            self.attributes("-topmost", self._desired_topmost)
        except Exception:
            pass
        
        self.lift()

    def hide(self):
        self.withdraw()

        if hasattr(self.app, "expanded"):
            self.app.expanded = False
        if hasattr(self.app, "expand_btn"):
            self.app.expand_btn.configure(text="▼")

    def _position_next_to_main(self):
        self.app.update_idletasks()

        x = self.app.winfo_rootx() + self.app.winfo_width() + 8
        y = self.app.winfo_rooty()

        self.geometry(f"+{x}+{y}")

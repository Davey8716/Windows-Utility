import os
import customtkinter as ctk
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
            height= 1150,
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

        def run_windows_utility(choice):
            actions = {
                "System Settings": lambda: os.system("start ms-settings:"),
                "Device Manager": lambda: os.system("devmgmt.msc"),
                "Task Manager": lambda: os.system("taskmgr"),
                "Router Login": app.actions.open_router_page,
            }
            action = actions.get(choice)
            if action:
                action()

        self.advanced_section_1 = CollapsibleSection(
            self.side_frame,
            "Windows Utilities",
            section_id="Windows_utilities",
            initial_open=False
        )
        self.advanced_section_1.wrapper.pack(fill="x", padx=12, pady=(0, 6))

        parent = self.advanced_section_1.content

        self.windows_util_menu = ctk.CTkOptionMenu(
            parent,
            values=[
                "System Settings",
                "Device Manager",
                "Task Manager",
                "Router Login",
            ],
            command=run_windows_utility,
            width=260,
            font=("Rubik UI", 15, "bold"),
            dropdown_font=("Rubik UI", 14),
        )
        self.windows_util_menu.pack(anchor="w", padx=12, pady=8)

        # ==================================================
        # Drive Space Display
        # ==================================================

        self.advanced_section_2 = CollapsibleSection(
            self.side_frame,
            "Drive Space Display",
            section_id="drive_space_display",
            initial_open=False
        )
        self.advanced_section_2.wrapper.pack(fill="x", padx=12, pady=(0, 6))

        drive_parent = self.advanced_section_2.content
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
            section_id="Bookmarks_exporter",
            initial_open=False
        )
        self.advanced_section_3.wrapper.pack(fill="x", padx=12, pady=(0, 6))

        brave_frame = ctk.CTkFrame(
            self.advanced_section_3.content,
            fg_color="transparent"
        )
        brave_frame.pack(anchor="w", padx=10, pady=(5, 2))

        self.btn_brave_export = ctk.CTkButton(
            brave_frame,
            text="Export Brave Bookmarks",
            width=180,
            font=("Rubik UI", 15, "bold"),
            command=app._run_brave_export,
        )
        self.btn_brave_export.pack(anchor="w", pady=(0, 4))

        self.brave_export_entry = ctk.CTkEntry(
            brave_frame,
            textvariable=app.brave_export_path_var,
            font=("Rubik UI", 15),
            width=360,
            state="readonly"
        )
        self.brave_export_entry.pack(anchor="w")

    # ==================================================
    # Visibility helpers
    # ==================================================

    def show(self):
        self.app._sync_windows("main")
        self.deiconify()
        
        # 🔑 Apply topmost AFTER deiconify
        try:
            self.attributes("-topmost", self._desired_topmost)
        except Exception:
            pass
        
        self.lift()


    def hide(self):
        self.withdraw()

        # tell the app to update its own UI/state
        if hasattr(self.app, "expanded"):
            self.app.expanded = False
        if hasattr(self.app, "expand_btn"):
            self.app.expand_btn.configure(text="▼")


    def _position_next_to_main(self):
        self.app.update_idletasks()

        x = self.app.winfo_rootx() + self.app.winfo_width() + 8
        y = self.app.winfo_rooty()

        self.geometry(f"+{x}+{y}")

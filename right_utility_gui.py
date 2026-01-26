import os
import customtkinter as ctk
import subprocess
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
        self.title("")
        self.resizable(False, False)
        self.withdraw()  # start hidden
        
        self._desired_topmost = app.right_always_on_top_var.get()

        # Close button behaviour
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # --------------------------------------------------
        # Scrollable content
        # --------------------------------------------------
        self.side_frame = ctk.CTkScrollableFrame(
            self,
            width=480,
            height=1150,
            fg_color="transparent"
        )
        self.side_frame.pack(fill="both", expand=True)

        self.advanced_title = ctk.CTkLabel(
            self.side_frame,
            text="Advanced Tools",
            font=("Rubik UI", 20, "bold")
        )
        self.advanced_title.pack(padx=12, pady=(20, 20))
        
        self.bind("<Configure>", lambda e: self.app._sync_windows("side"))
        self.bind("<ButtonPress-1>", lambda e: self.app._set_drag_owner("side"))
        self.bind("<ButtonRelease-1>", lambda e: self.app._clear_drag_owner())
        
        title_row = ctk.CTkFrame(self.side_frame, fg_color="transparent")
        title_row.pack(fill="x", padx=10, pady=10)
        
        self.master_collapse_btn_right = ctk.CTkButton(
            title_row,
            text="▾",
            width=32,
            height=28,
            font=("Rubik UI", 18, "bold"),
            fg_color="transparent",
            hover_color="#202020",
            command=self.toggle_all_right_sections
        )
        self.master_collapse_btn_right.pack(side="right")
        
        CtkTooltip(
            self.master_collapse_btn_right,
            "Master collapse toggle for all of these regions.\n"
            
        )
        
        # ==================================================
        # Windows Utilities
        # ==================================================

        self.windows_utility_section = CollapsibleSection(
            self.side_frame,
            "Windows Utilities",
            section_id="windows_utilities",
            app=self.app,
            initial_open=self.app.saved_state.get("right_section_states", {}).get("windows_utilities", False)
        )
        self.windows_utility_section.wrapper.pack(fill="x", padx=12, pady=(5, 6))
        

        CtkTooltip(
            self.windows_utility_section.toggle_btn,
            "Shows windows utilities here instead grouped by type \n"
            "not having to have them all cluttering up your taskbar."
        )
        app.collapsible_sections.append(self.windows_utility_section)

        parent = self.windows_utility_section.content
        
        self.sidebar_utils_section = CollapsibleSection(
            self.side_frame,
            "Side Bar Utilities",
            section_id="sidebar_utils_section",
            app=self.app,
            initial_open=self.app.saved_state.get("right_section_states", {}).get("sidebar_utils_section", False)
        )
    
        # ✅ REGISTER IT as a right-section state
        self.app.collapsible_sections.append(self.sidebar_utils_section)
        self.sidebar_utils_section.wrapper.pack(fill="x", padx=12, pady=(0, 6))
        
        # 🔴 THIS LINE WAS MISSING
        self.build_sidebar_utilities()
        
        CtkTooltip(
            self.sidebar_utils_section.toggle_btn,
            "Side bar actions menus."
        )
                
        self.sidebar_output = ctk.CTkTextbox(
            self.sidebar_utils_section.content,
            height=120,
            font=("Consolas", 15, "bold"),
        )
        self.sidebar_output.pack(fill="x", padx=8, pady=(8, 6))


        # container row
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(anchor="w", padx=12, pady=(4, 8))

        # left column (System / Hardware)
        left_col = ctk.CTkFrame(row, fg_color="transparent")
        left_col.pack(side="left", padx=(0, 12))

        # right column (Network / Startup & Power)
        right_col = ctk.CTkFrame(row, fg_color="transparent")
        right_col.pack(side="left")

        # add dropdowns
        self._add_windows_dropdown(left_col, "System", self._system_utilities())
        self._add_windows_dropdown(left_col, "Hardware", self._hardware_utilities())

        self._add_windows_dropdown(right_col, "Network", self._network_utilities())
        self._add_windows_dropdown(right_col, "Startup & Power", self._startup_power_utilities())

        # ==================================================
        # Drive Space Display
        # ==================================================

        self.display_space_section = CollapsibleSection(
            self.side_frame,
            "Drive Space Display",
            section_id="drive_space_display",
            app=self.app,
            initial_open=self.app.saved_state.get("right_section_states", {}).get("drive_space_display", False)
        )
        self.display_space_section.wrapper.pack(fill="x", padx=12, pady=(0, 6))

        CtkTooltip(
            self.display_space_section.toggle_btn,
            "Shows disk usage for all detected drives."
        )

        app.collapsible_sections.append(self.display_space_section)

        drive_parent = self.display_space_section.content
        
        def open_this_pc():
            os.system("explorer shell:MyComputerFolder")
            
            # minimize after 5 seconds
            self.after(1000, self.iconify)

        btn_this_pc = ctk.CTkButton(
            drive_parent,
            text="Open This PC",
            font=("Rubik UI", 14, "bold"),
            height=28,
            command=open_this_pc,
        )

        btn_this_pc.pack(anchor= "w",padx= 5, pady=(4, 4))

        # OUTPUT CONSOLE (read-only)
        self.drive_space_output = ctk.CTkTextbox(
            drive_parent,
            height=120,
            font=("Consolas", 12),
            wrap="none",
        )
        self.drive_space_output.pack(fill="x", padx=5, pady=6)
        self.drive_space_output.configure(state="disabled")


        def refresh_drive_display():
            self.drive_space_output.configure(state="normal")
            self.drive_space_output.delete("1.0", "end")

            for d in get_drive_info():
                used_gb = (d["total"] - d["free"]) / (1024**3)
                total_gb = d["total"] / (1024**3)
                free_gb = d["free"] / (1024**3)

                line = (
                    f"{d['drive']:<5} "
                    f"Used: {used_gb:6.1f} GB   "
                    f"Free: {free_gb:6.1f} GB   "
                    f"Total: {total_gb:6.1f} GB\n"
                )

                self.drive_space_output.insert("end", line)

            self.drive_space_output.configure(state="disabled")


        # initial render
        refresh_drive_display()


        def schedule_drive_refresh():
            refresh_drive_display()
            self.app.after(10_000, schedule_drive_refresh)


        schedule_drive_refresh()


        # ==================================================
        # Universal Bookmarks Exporter
        # ==================================================
        
        self.advanced_section_3 = CollapsibleSection(
            self.side_frame,
            "Universal Bookmarks Exporter",
            section_id="bookmarks_exporter",
            app=self.app,
            initial_open=self.app.saved_state.get("right_section_states", {}).get("bookmarks_exporter", False)
        )
        self.advanced_section_3.wrapper.pack(fill="x", padx=12, pady=(5, 6))
        
        CtkTooltip(
            self.advanced_section_3.toggle_btn,
            "Exports bookmarks to a file path of your choosing.\n"
        )
        app.collapsible_sections.append(self.advanced_section_3)

        self.btn_brave_export = ctk.CTkButton(
            self.advanced_section_3.content,
            text="Export Brave Bookmarks",
            width=180,
            font=("Rubik UI", 15, "bold"),
            command=app._run_brave_export,
        )
        self.btn_brave_export.pack(anchor="w", padx=5, pady=(5, 4))

        CtkTooltip(
            self.btn_brave_export,
            "Exports brave bookmarks to a file path of your choice,\n"
            "remembers last saved location.\n"
        )

        self.brave_export_entry = ctk.CTkEntry(
            self.advanced_section_3.content,
            textvariable=app.brave_export_path_var,
            font=("Rubik UI", 15),
            width=400,
            state="readonly"
        )
        self.brave_export_entry.pack(anchor="w", padx=5, pady=(5, 4))
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        

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

    # ==================================================
    # Drop down helper for windows utils
    # ==================================================
        
    def _add_windows_dropdown(self, parent, label, actions_map):
        placeholder = f" {label} "

        def runner(choice):
            if choice == placeholder:
                return

            action = actions_map.get(choice)
            if action:
                # minimize BOTH windows to taskbar
                self.app.iconify()
                self.iconify()

                action()

        values = [placeholder] + sorted(actions_map.keys())

        dropdown = ctk.CTkOptionMenu(
            parent,
            values=values,
            command=runner,
            width=160,
            font=("Rubik UI", 15, "bold"),
            dropdown_font=("Rubik UI", 14),
        )

        dropdown.set(placeholder)
        dropdown.pack(anchor="w", padx=12, pady=(4, 8))
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
    # ==================================================
    # Side Bar Utilities
    # ==================================================

    def _sidebar_network_actions(self):
        return {
            "Flush DNS": self.flush_dns,
            "Renew IP": self.renew_ip,
            "IP Config": self.show_ip_config,
            "Restart Explorer": self.restart_explorer,
            "Restart Bluetooth Service": self.restart_bluetooth,
        }

    def _sidebar_cleanup_actions(self):
        return {
            "Clear Temp Files": self.clear_temp,
            "Clear Clipboard": self.clear_clipboard,
        }

    def _sidebar_quick_open_actions(self):
        return {
            "Open Downloads Folder": self.open_downloads,
            "Open Startup Folder": self.open_startup_folder,
            "Clipboard History": self.open_clipboard_history,
        }
        
        
    def build_sidebar_utilities(self):
        parent = self.sidebar_utils_section.content

        self._add_sidebar_dropdown(
            parent,
            "Network / System Quick Fix",
            self._sidebar_network_actions()
        )

        self._add_sidebar_dropdown(
            parent,
            "Cleanup / Quick Actions",
            self._sidebar_cleanup_actions()
        )

        self._add_sidebar_dropdown(
            parent,
            "Quick Open",
            self._sidebar_quick_open_actions()
        )

    def toggle_side_bar_utilities(self):

        section = self.app.sidebar_utils_section

        new_state = not section.var.get()
        section.var.set(new_state)   # ✅ THIS is the missing line

        if new_state:
            if not section.wrapper.winfo_ismapped():
                section.wrapper.pack(fill="x", padx=12, pady=(0, 6))
        else:
            if section.wrapper.winfo_ismapped():
                section.wrapper.pack_forget()

        self.app.save_all_settings()
        
    def _run_and_output(self, cmd, shell=True):
        self.sidebar_output.delete("1.0", "end")
        try:
            result = subprocess.run(
                cmd,
                shell=shell,
                capture_output=True,
                text=True,
            )
            output = result.stdout or result.stderr or "[no output]"
        except Exception as e:
            output = str(e)

        self.sidebar_output.insert("end", output)

    # ==================================== 
    # Dropdown calls
    # ==================================== 
        
    def flush_dns(self):
        self._run_and_output("ipconfig /flushdns")

    def renew_ip(self):
        self._run_and_output("ipconfig /renew")

    def show_ip_config(self):
        self._run_and_output("ipconfig")

    def restart_explorer(self):
        self._run_and_output("taskkill /f /im explorer.exe && start explorer")

    def restart_bluetooth(self):
        self._run_and_output("powershell Restart-Service bthserv -Force")
        
    def clear_temp(self):
        self._run_and_output("del /q /s %temp%\\*", shell=True)

    def clear_clipboard(self):
        self._run_and_output("cmd /c echo off | clip")
        
    def open_downloads(self):
        self.sidebar_output.delete("1.0", "end")
        os.system("explorer shell:downloads")
        self.sidebar_output.insert("end", "Opened Downloads folder.\n")

    def open_startup_folder(self):
        self.sidebar_output.delete("1.0", "end")
        os.system("explorer shell:startup")
        self.sidebar_output.insert("end", "Opened Startup folder.\n")

    def open_clipboard_history(self):
        self.sidebar_output.delete("1.0", "end")
        os.system("start ms-settings:clipboard")
        self.sidebar_output.insert("end", "Opened Clipboard History.\n")

    def _add_sidebar_dropdown(self, parent, title, actions_map):
        placeholder = f" {title} "

        def runner(choice):
            if choice == placeholder:
                return
            action = actions_map.get(choice)
            if action:
                action()
            dropdown.set(placeholder)  # reset after run

        values = [placeholder] + list(actions_map.keys())

        dropdown = ctk.CTkOptionMenu(
            parent,
            values=values,
            command=runner,
            width=160,
            font=("Rubik UI", 14, "bold"),
            dropdown_font=("Rubik UI", 14),
        )

        dropdown.set(placeholder)
        dropdown.pack(anchor ="w", padx=8, pady=4)
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
    # ==================================================
    # Master Toggle Right
    # ==================================================

    def toggle_all_right_sections(self):
        new_state = not self.app.master_toggle_right_var.get()
        self.app.master_toggle_right_var.set(new_state)

        for section in self.app.collapsible_sections:
            if not isinstance(section, CollapsibleSection):
                continue

            if section.parent == self.side_frame:
                if section.open != new_state:
                    section.toggle()

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
            self.app.expand_btn.configure(text="▾")

    def _position_next_to_main(self):
        self.app.update_idletasks()

        x = self.app.winfo_rootx() + self.app.winfo_width() + 8
        y = self.app.winfo_rooty()

        self.geometry(f"+{x}+{y}")
        
    def _on_close(self):
        # close via the same logic as the toggle
        self.app.advanced_panel_open_var.set(False)
        self.hide()
        self.app.save_all_settings()

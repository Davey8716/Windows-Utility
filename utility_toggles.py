import subprocess
import webbrowser
import ctypes
import win32gui
import win32con
import os 
from screen_mover import SCREEN_MOVER
import customtkinter as ctk

# ===================================================================
#  Utility Actions Manager (Monolithic Class)
# ===================================================================

class UtilityActionsManager:
    def __init__(self, app):
        """
        This class houses all previously-inline logic methods:
        - Power buttons toggling
        - Router opener
        - Minimize/Maximize All
        - USB Reminder toggle
        - Theme toggle
        - Tooltips toggle
        - Always-on-top
        - Auto-align toggle
        """
        self.app = app

    # ===================================================================
    #  Power Buttons Toggle
    # ===================================================================

    def toggle_power_buttons(self):
        enabled = self.app.power_toggle_var.get()

        widgets = [
            self.app.btn_sleep,
            self.app.btn_lock,
            self.app.btn_restart,
            self.app.btn_shutdown,
        ]

        for w in widgets:
            if enabled:
                w.pack(anchor="e", pady=(0, 4))
            else:
                w.pack_forget()
                # Update switch label text
        if enabled:
            self.app.power_toggle.configure(text="Power Options On")
        else:
            self.app.power_toggle.configure(text="Power Options Off")

        self.app.save_all_settings()

    # ===================================================================
    #  Router Auto-Detect & Open
    # ===================================================================

    def open_router_page(self):
        """Auto-detect default gateway and open router page in browser."""
        try:
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

    # ===================================================================
    #  Minimize / Restore All Windows Except GUI
    # ===================================================================

    def minimize_all_toggle(self):
        enabled = self.app.minimize_all_var.get()
        print(f"[INFO] Min/Max All toggled → {enabled}")

        child_hwnd = self.app.winfo_id()
        parent_hwnd = ctypes.windll.user32.GetParent(child_hwnd)
        real_hwnd = parent_hwnd if parent_hwnd else child_hwnd

        if enabled:
            minimize_all_except_gui(real_hwnd)
        else:
            restore_all_except_gui(real_hwnd)
            
        if enabled:
            self.app.minimize_all_switch.configure(text="Maximize All Off")
        else:
            self.app.minimize_all_switch.configure(text="Maximize All On")

        self.app.save_all_settings()

    # ===================================================================
    #  USB Reminder Toggle
    # ===================================================================

    def usb_reminder_toggle(self):
        try:
            enabled = self.app.usb_reminder_var.get()
        except Exception:
            enabled = False

        toggle_usb_options(self.app, enabled)
        self.app.save_all_settings()

    # ===================================================================
    #  Theme Toggle (Dark/Light)
    # ===================================================================

    def theme_toggle(self):
        enabled = self.app.theme_var.get()
        switch_theme(enabled)

        # Update label
        if enabled:
            self.app.theme_switch.configure(text="Dark Mode On")
        else:
            self.app.theme_switch.configure(text="Light Mode On")
            
        # After switching theme, recolour collapse arrows
        self.app.update_collapsible_arrow_colours()

        self.app.save_all_settings()

    # ===================================================================
    #  Tooltips Toggle
    # ===================================================================

    def tooltips_toggle(self):
        enabled = self.app.tooltips_enabled_var.get()
        self.app.save_all_settings()
        
        if enabled:
            self.app.tooltip_switch.configure(text="Tooltips On")
        else:
            self.app.tooltip_switch.configure(text="Tooltips Off")

        self.app.save_all_settings()
            

    # ===================================================================
    #  Always-On-Top Toggle
    # ===================================================================

    def always_on_top_toggle(self):
        enabled = self.app.always_on_top_var.get()

        # Apply behavior
        self.app.apply_always_on_top(enabled)

        # Update switch label
        if enabled:
            self.app.always_on_top_switch.configure(text="Always On Top On")
        else:
            self.app.always_on_top_switch.configure(text="Always On Top Off")

        self.app.save_all_settings()

        
    # ===================================================================
    #  Auto-Align (Screen Mover)
    # ===================================================================

    def auto_align_toggle(self):
        enabled = self.app.auto_align_var.get()

        # Apply backend behaviour
        SCREEN_MOVER.auto_align_enabled = enabled

        # Update switch label text (polish)
        self.app._sync_toggle_label(
            self.app.auto_align_switch,
            "Windows In Move Zone",
            self.app.auto_align_var
        )

        self.app.save_all_settings()


    # ===================================================================
    #  Organising Utilities - Backup Pinned Shortcuts (REAL LOGIC)
    # ===================================================================

    def backup_pinned_shortcuts(self):
        """Backs up Windows taskbar pinned shortcuts into the chosen folder."""
        import shutil
        from tkinter import messagebox

        print("[BACKUP] Starting backup of pinned shortcuts…")

        # 1. Get Windows pinned taskbar folder
        pinned_path = os.path.join(
            os.environ["APPDATA"],
            r"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"
        )

        if not os.path.isdir(pinned_path):
            messagebox.showerror(
                "Backup Error",
                "Windows pinned shortcuts folder was not found.\n"
                "This version of Windows may not be supported."
            )
            print("[BACKUP] ERROR: Pinned folder not found:", pinned_path)
            return

        # 2. Get user's chosen backup folder
        backup_folder = self.app.backup_path_var.get()

        if not os.path.isdir(backup_folder):
            try:
                os.makedirs(backup_folder, exist_ok=True)
            except Exception as e:
                messagebox.showerror(
                    "Backup Error",
                    f"Could not create backup folder:\n{e}"
                )
                print("[BACKUP] ERROR: Cannot create backup folder:", backup_folder)
                return

        # 3. Copy .lnk files
        count = 0
        for file in os.listdir(pinned_path):
            if file.lower().endswith(".lnk"):
                src = os.path.join(pinned_path, file)
                dst = os.path.join(backup_folder, file)

                try:
                    shutil.copy2(src, dst)
                    print(f"[BACKUP] Copied: {file}")
                    count += 1
                except Exception as e:
                    print(f"[BACKUP] Failed to copy {file}: {e}")

        # 4. Finish message
        if count > 0:
            messagebox.showinfo(
                "Backup Complete",
                f"Successfully backed up {count} pinned shortcuts.\n\n"
                f"Saved to:\n{backup_folder}"
            )
        else:
            messagebox.showwarning(
                "No Shortcuts Found",
                "No pinned shortcuts were found to back up."
            )

        print(f"[BACKUP] Completed. {count} shortcuts copied.")

    # ===================================================================
    #  Organising Utilities - Open Backup Folder
    # ===================================================================

    def open_backup_folder(self):
        """Opens the backup folder path stored in the GUI."""
        try:
            path = self.app.backup_path_var.get()
            if os.path.isdir(path):
                os.startfile(path)
            else:
                print("[DEBUG] open_backup_folder: path does not exist")
        except Exception as e:
            print(f"[ERROR] open_backup_folder: {e}")

    # ===================================================================
    #  Organising Utilities - Change Backup Folder Path
    # ===================================================================

    def change_backup_folder(self):
        """Allows the user to select a folder and updates the JSON."""
        import tkinter.filedialog as fd

        try:
            new_path = fd.askdirectory(title="Choose Backup Folder")
            if new_path:
                self.app.backup_path_var.set(new_path)
                self.app.save_all_settings()
                print(f"[DEBUG] Changed backup folder to: {new_path}")
        except Exception as e:
            print(f"[ERROR] change_backup_folder: {e}")


# ===================================================================
#  Minimize / Restore All Windows Except GUI
# ===================================================================

# ------------------------------------------------------------
#  Helper: Should we skip this hwnd?
# ------------------------------------------------------------

def _should_skip(hwnd, skip_hwnd):
    if hwnd == skip_hwnd:
        return True

    if not win32gui.IsWindowVisible(hwnd):
        return True

    # Skip shell windows without title
    title = win32gui.GetWindowText(hwnd)
    if not title.strip():
        return True

    # Only handle top-level windows
    if win32gui.GetParent(hwnd) != 0:
        return True

    return False

# ------------------------------------------------------------
#  Minimize All Except GUI
# ------------------------------------------------------------

def minimize_all_except_gui(skip_hwnd):
    print("[MIN/MAX] Minimizing all windows except GUI…")

    def enum_handler(hwnd, _):
        if _should_skip(hwnd, skip_hwnd):
            return

        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception:
            pass

    win32gui.EnumWindows(enum_handler, None)

# ------------------------------------------------------------
#  Restore All Except GUI
# ------------------------------------------------------------

def restore_all_except_gui(skip_hwnd):
    print("[MIN/MAX] Restoring all minimized windows except GUI…")

    def enum_handler(hwnd, _):

        if _should_skip(hwnd, skip_hwnd):
            return

        # Check if minimized
        placement = win32gui.GetWindowPlacement(hwnd)
        show_cmd = placement[1]

        if show_cmd == win32con.SW_SHOWMINIMIZED:
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            except Exception:
                pass

    win32gui.EnumWindows(enum_handler, None)

# Dark = True, Light = False
def switch_theme(dark_mode: bool):
    if dark_mode:
        ctk.set_appearance_mode("Dark")
        print("[THEME] Switched to Dark Mode On")
    else:
        ctk.set_appearance_mode("Light")
        print("[THEME] Switched to Light Mode Off")

# ===================================================================
#  USB Reminder – UI Helpers (pure GUI logic, safe to import anywhere)
# ===================================================================

def toggle_usb_options(self, enable: bool):
    state = "normal" if enable else "disabled"
    self.opt_idle.configure(state=state)
    self.opt_download.configure(state=state)
    self.opt_plug.configure(state=state)

def on_usb_toggle(app, enabled: bool):
    print(f"[INFO] USB Reminder toggled → {enabled}")
    toggle_usb_options(app, enabled)

def toggle_mover_options(app, enable: bool):
    """
    Enable/disable the Screen Mover sub-switches (MMB + auto-align).
    """
    state = "normal" if enable else "disabled"
    app.mmb_switch.configure(state=state)
    app.auto_align_switch.configure(state=state)   # NEW stays here

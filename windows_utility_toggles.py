import subprocess
import webbrowser
import ctypes

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
        """Show or hide the right-side power buttons and save state."""
        enabled = self.app.power_toggle_var.get()
        self.app.save_all_settings()

        # If GUI not ready yet
        if not hasattr(self.app, "btn_shutdown"):
            return

        widgets = [
            self.app.btn_shutdown,
            self.app.btn_restart,
            self.app.btn_sleep,
            self.app.btn_lock,
        ]

        for w in widgets:
            try:
                if enabled:
                    w.grid()          # Restore previous grid position
                else:
                    w.grid_remove()   # Hide while retaining layout info
            except Exception:
                pass

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
            self.app.theme_switch.configure(text="Dark Mode Enabled")
        else:
            self.app.theme_switch.configure(text="Light Mode Enabled")
            
        # After switching theme, recolour collapse arrows
        self.app.update_collapsible_arrow_colours()

        self.app.save_all_settings()

    # ===================================================================
    #  Tooltips Toggle
    # ===================================================================

    def tooltips_toggle(self):
        self.app.tooltips_enabled = self.app.tooltips_enabled_var.get()
        self.app.save_all_settings()

    # ===================================================================
    #  Always-On-Top Toggle
    # ===================================================================

    def always_on_top_toggle(self):
        enabled = self.app.always_on_top_var.get()
        self.app.apply_always_on_top(enabled)
        self.app.save_all_settings()
        


    # ===================================================================
    #  Auto-Align (Screen Mover)
    # ===================================================================

    def auto_align_toggle(self):
        enabled = self.app.auto_align_var.get()
        SCREEN_MOVER.auto_align_enabled = enabled

        self.app.save_all_settings()

        if enabled:
            try:
                SCREEN_MOVER._force_align_all_windows()
            except Exception as e:
                print("[GUI] Force align failed:", e)



# ===================================================================
#  Minimize / Restore All Windows Except GUI
# ===================================================================

import win32gui
import win32con

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
        print("[THEME] Switched to Dark Mode")
    else:
        ctk.set_appearance_mode("Light")
        print("[THEME] Switched to Light Mode")

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

import json
import os
from pathlib import Path
CONFIG_PATH = "app_state.json"

def save_state(state: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(state, f, indent=4)

def load_state() -> dict:
    
    # ================================================================
    # DEFAULTS (used when file doesn't exist)
    # ================================================================
    
    DEFAULTS = {
        "theme_dark": True,
        "main_always_on_top_enabled": True,
        "right_always_on_top_enabled": True,
        "show_power_buttons": False,
        "tooltips_enabled": True,
        "minimize_all_enabled": False,
        "master_toggle_left": True,
        
        "mmb_activation_enabled": True,
        "auto_align_enabled": False,

        "usb_idle_enabled": True,
        "usb_download_enabled": True,
        "usb_plug_enabled": True,
        
        "master_backup_output_path": str(Path.home()),
        "backup_output_path": str(Path.home()),
        "backup_folder_path": str(Path.home()),
        "brave_export_path": "",
        "advanced_panel_open" : True,


        "left_section_states": {
            "user_interface": True,
            "screen_mover": True,
            "drive_reminder_options": True,
            "organising_utilties": True,
            "desktop_backup_utilities": True,
            "desktop_icon_organiser": True
        },
        "right_section_states": {
            "master_toggle_right": False,
            "sidebar_utils_section": False,
            "windows_utilities": False,
            "drive_space_display": False,
            "bookmarks_exporter": False
        },
    }

    # ================================================================
    # Case 1: File missing → return defaults
    # ================================================================
    
    if not os.path.exists(CONFIG_PATH):
        return DEFAULTS.copy()

    # ================================================================
    # Case 2: File exists → load it
    # ================================================================
    
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)

        # Ensure missing keys never break older configs
        for key, value in DEFAULTS.items():
            data.setdefault(key, value)

        return data

    # ================================================================
    # Case 3: File unreadable / corrupted → return defaults
    # ================================================================
    
    except Exception:
        return DEFAULTS.copy()

import json
import os

CONFIG_PATH = "screen_mover_state.json"

def save_state(state: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(state, f, indent=4)

def load_state() -> dict:
    # ================================================================
    # DEFAULTS (used when file doesn't exist)
    # ================================================================
    DEFAULTS = {
        "mmb_activation_enabled": True,
        "auto_align_enabled": False,                           
        "usb_idle_enabled": True,
        "usb_download_enabled": True,
        "usb_plug_enabled": True,
        "theme_dark": True,
        "minimize_all_enabled": False,
        "always_on_top_enabled": True,
        "show_power_buttons": False,
        "tooltips_enabled": True,

        # NEW: Collapsible section states
        "section_states": {
            "misc": True,
            "mover": True,
            "usb": True,
            "winutils": True
        }
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

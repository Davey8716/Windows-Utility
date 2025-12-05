import json
import os

CONFIG_PATH = "screen_mover_state.json"

def save_state(state: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(state, f, indent=4)

def load_state() -> dict:
    if not os.path.exists(CONFIG_PATH):
        # defaults
        return {
            "mmb_activation_enabled": True,
            "auto_align_enabled": True,                           
            "usb_idle_enabled": True,
            "usb_download_enabled": True,
            "usb_plug_enabled": True,
            "theme_dark": True,    # NEW DEFAULT
            "minimize_all_enabled": False,
            "always_on_top_enabled": True

        }
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)

        # ensure missing keys don't break old configs
        data.setdefault("mmb_activation_enabled", True)
        data.setdefault("auto_align_enabled", True)      
        data.setdefault("usb_idle_enabled", True)
        data.setdefault("usb_download_enabled", True)
        data.setdefault("usb_plug_enabled", True)
        data.setdefault("theme_dark", True)
        data.setdefault("minimize_all_enabled", False)
        data.setdefault("always_on_top_enabled", True)
        
        return data
    except:
        return {
            "mmb_activation_enabled": True,
            "auto_align_enabled": True,           
            "usb_idle_enabled": True,
            "usb_download_enabled": True,
            "usb_plug_enabled": True,
            "theme_dark": True,
            "minimize_all_enabled": False,
            "always_on_top_enabled": True

        }

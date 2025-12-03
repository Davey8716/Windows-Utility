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
            "screen_mover_enabled": True,
            "mmb_activation_enabled": True,
            
        }
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)

        # ensure missing keys don't break old configs
        data.setdefault("screen_mover_enabled", True)
        data.setdefault("mmb_activation_enabled", True)

        return data
    except:
        return {
            "screen_mover_enabled": True,
            "mmb_activation_enabled": True,
            
        }
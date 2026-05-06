import json
import os
from pathlib import Path

APP_DIR_NAME = "Windows Resurface"
CONFIG_FILENAME = "app_state.json"
LEGACY_CONFIG_PATH = Path("app_state.json")

DEFAULTS = {
    "theme_dark": True,
    "main_always_on_top_enabled": True,
    "tooltips_enabled": True,
    "maximize_all_enabled": True,
    "minimize_after_use_enabled": True,
    "power_options_enabled": False,
    "mmb_activation_enabled": True,
    "screen_mover_activation_button": "middle",
    "title_bar_dock_enabled": True,
    "usb_idle_enabled": True,
    "usb_plug_enabled": True,
    "usb_plug_notify_mode": "on",
    "recycle_bin_auto_clean_enabled": False,
    "recycle_bin_age_rule_days": 30,
    "recycle_bin_last_auto_clean_popup_days": None,
    "master_backup_output_path": str(Path.home()),
    "advanced_panel_open": False,
    "master_toggle_left": True,
    "master_toggle_right": False,
    "left_section_states": {
        "user_interface": True,
        "screen_mover": True,
        "drive_reminder_options": True,
        "organising_utilities": True,
        "recycle_bin_actions": True,
    },
    "right_section_states": {
        "windows_utilities": False,
        "sidebar_utils_section": False,
        "drive_space_display": False,
    },
}

LEGACY_KEY_MAP = {
    "maximize_all_enabled": "minimize_all_enabled",
}

LEGACY_VALUE_TRANSFORMS = {
    "maximize_all_enabled": lambda value: not bool(value),
}


def get_config_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIR_NAME / CONFIG_FILENAME
    return Path.home() / "AppData" / "Local" / APP_DIR_NAME / CONFIG_FILENAME


def _build_persisted_state(state: dict) -> dict:
    payload = dict(state)
    persisted = {}

    for key, default in DEFAULTS.items():
        if isinstance(default, dict):
            value = payload.get(key, {})
            merged = default.copy()
            if isinstance(value, dict):
                for nested_key in default:
                    if nested_key in value:
                        merged[nested_key] = bool(value[nested_key])
            persisted[key] = merged
            continue

        legacy_key = LEGACY_KEY_MAP.get(key)
        if key in payload:
            persisted[key] = payload[key]
        elif legacy_key and legacy_key in payload:
            transform = LEGACY_VALUE_TRANSFORMS.get(key, lambda value: value)
            persisted[key] = transform(payload[legacy_key])
        else:
            persisted[key] = default

    return persisted


def save_state(state: dict):
    payload = _build_persisted_state(state)
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)


def load_state() -> dict:
    config_path = get_config_path()
    source_path = config_path
    if not source_path.exists() and LEGACY_CONFIG_PATH.exists():
        source_path = LEGACY_CONFIG_PATH

    if not source_path.exists():
        return DEFAULTS.copy()

    try:
        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data = _build_persisted_state(data)

        if source_path != config_path:
            save_state(data)

        return data
    except Exception:
        return DEFAULTS.copy()

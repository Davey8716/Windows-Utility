import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

from Shared.app_state_defaults import (
    SHARED_APP_STATE_DEFAULTS,
    WINDOWS_RESURFACE_DEFAULTS,
    WINDOWS_RESURFACE_STATE_KEYS,
)
from Shared.shared_state_manager import JsonStateManager

APP_DIR_NAME = "Windows Resurface"
CONFIG_FILENAME = "app_state.json"
LEGACY_CONFIG_PATH = Path("app_state.json")

DEFAULTS = WINDOWS_RESURFACE_DEFAULTS

LEGACY_KEY_MAP = {
    "maximize_all_enabled": "minimize_all_enabled",
}

LEGACY_VALUE_TRANSFORMS = {
    "maximize_all_enabled": lambda value: not bool(value),
}


def _resolve_config_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIR_NAME / CONFIG_FILENAME
    return Path.home() / "AppData" / "Local" / APP_DIR_NAME / CONFIG_FILENAME


def get_config_path() -> Path:
    return _resolve_config_path()


def _create_manager() -> JsonStateManager:
    return JsonStateManager(
        app_dir_name=APP_DIR_NAME,
        config_filename=CONFIG_FILENAME,
        defaults=SHARED_APP_STATE_DEFAULTS,
        legacy_key_map=LEGACY_KEY_MAP,
        legacy_value_transforms=LEGACY_VALUE_TRANSFORMS,
        preserve_unknown_keys=True,
        owned_keys=WINDOWS_RESURFACE_STATE_KEYS,
        config_path_resolver=get_config_path,
        legacy_config_path_resolver=lambda: LEGACY_CONFIG_PATH,
    )


def save_state(state: dict):
    _create_manager().save_state(state)


def load_state() -> dict:
    return _create_manager().load_state()

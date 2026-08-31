import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

from Shared.app_state_defaults import (
    FOLDER_CREATOR_DEFAULTS,
    FOLDER_CREATOR_STATE_KEYS,
    SHARED_APP_STATE_DEFAULTS,
)
from Shared.shared_state_manager import JsonStateManager

APP_DIR_NAME = "Windows Resurface"
CONFIG_FILENAME = "app_state.json"
LEGACY_APP_DIR_NAME = "FolderCreator"
LEGACY_CONFIG_FILENAME = "folder_creator_user_state.json"

DEFAULT_STATE = FOLDER_CREATOR_DEFAULTS


def get_config_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIR_NAME / CONFIG_FILENAME
    return Path.home() / "AppData" / "Local" / APP_DIR_NAME / CONFIG_FILENAME


def get_legacy_config_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / LEGACY_APP_DIR_NAME / LEGACY_CONFIG_FILENAME
    return (
        Path.home()
        / "AppData"
        / "Local"
        / LEGACY_APP_DIR_NAME
        / LEGACY_CONFIG_FILENAME
    )


class StateManager(JsonStateManager):
    def __init__(self):
        super().__init__(
            app_dir_name=APP_DIR_NAME,
            config_filename=CONFIG_FILENAME,
            defaults=SHARED_APP_STATE_DEFAULTS,
            persist_defaults_on_missing=True,
            preserve_unknown_keys=True,
            owned_keys=FOLDER_CREATOR_STATE_KEYS,
            config_path_resolver=get_config_path,
            legacy_config_path_resolver=get_legacy_config_path,
        )

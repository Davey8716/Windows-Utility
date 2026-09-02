"""Stable application identity and user-facing branding."""

import os
from pathlib import Path

DISPLAY_NAME = "Hover Window Controls"
LEGACY_DATA_DIRECTORY = "No Click Min Max Restore"
INTEGRATED_DATA_DIRECTORY = "hover-window-controls"
DEFAULT_DWELL_MS = 750
MIN_DWELL_MS = 500
MAX_DWELL_MS = 2000
DWELL_STEP_MS = 250


def local_app_data_directory(name: str = DISPLAY_NAME) -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / name
    return Path.home() / "AppData" / "Local" / name


def windows_resurface_data_directory() -> Path:
    """Return the feature-owned directory inside Windows Resurface AppData."""
    return local_app_data_directory("Windows Resurface") / INTEGRATED_DATA_DIRECTORY

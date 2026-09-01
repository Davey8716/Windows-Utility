"""One-time, non-destructive import of standalone hover-control data."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from resurface.features.hover_window_controls.app.identity import (
    DISPLAY_NAME,
    LEGACY_DATA_DIRECTORY,
    local_app_data_directory,
    windows_resurface_data_directory,
)


def _valid_profile_directory(directory: Path) -> bool:
    for manifest in directory.glob("manifest_*.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if (
            isinstance(data, dict)
            and isinstance(data.get("schema_version"), int)
            and isinstance(data.get("application"), dict)
            and isinstance(data.get("contexts"), list)
        ):
            return True
    return False


def _copy_profiles(source: Path, destination: Path) -> bool:
    if not source.is_dir():
        return True
    try:
        for application_directory in source.iterdir():
            if application_directory.is_dir() and _valid_profile_directory(application_directory):
                destination.mkdir(parents=True, exist_ok=True)
                shutil.copytree(
                    application_directory,
                    destination / application_directory.name,
                    dirs_exist_ok=True,
                )
    except OSError:
        return False
    return True


def import_standalone_data(
    state: dict,
    *,
    standalone_root: Path | None = None,
    legacy_root: Path | None = None,
    integrated_root: Path | None = None,
) -> bool:
    """Import standalone preferences/profiles once and return whether state changed."""
    if bool(state.get("hover_window_controls_migration_completed", False)):
        return False

    standalone_root = standalone_root or local_app_data_directory(DISPLAY_NAME)
    legacy_root = legacy_root or local_app_data_directory(LEGACY_DATA_DIRECTORY)
    integrated_root = integrated_root or windows_resurface_data_directory()
    settings_path = standalone_root / "settings.json"
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        hover = data["hover"]
        if (
            data.get("schema_version") == 1
            and type(hover.get("paused")) is bool
            and isinstance(hover.get("dwell_ms"), int)
        ):
            state["hover_window_controls_enabled"] = not hover["paused"]
            dwell_ms = min(max(hover["dwell_ms"], 500), 2000)
            state["hover_window_controls_dwell_ms"] = (
                500 + round((dwell_ms - 500) / 250) * 250
            )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass

    destination = integrated_root / "vision-cache"
    # Older data is copied first so the newer standalone cache wins on conflicts.
    legacy_copied = _copy_profiles(legacy_root / "vision-cache", destination)
    standalone_copied = _copy_profiles(standalone_root / "vision-cache", destination)
    if legacy_copied and standalone_copied:
        state["hover_window_controls_migration_completed"] = True
    return True

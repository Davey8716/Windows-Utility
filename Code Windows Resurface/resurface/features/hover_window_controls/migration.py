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
from resurface.features.hover_window_controls.service import normalized_dwell_ms


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
            if (
                application_directory.is_dir()
                and not application_directory.is_symlink()
                and _valid_profile_directory(application_directory)
            ):
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
    previous_integrated_root = windows_resurface_data_directory()

    # The integrated app's settings use the same portable schema. Preserve
    # them when the master location has not already established authority.
    previous_settings = previous_integrated_root / "settings.json"
    destination_settings = integrated_root / "settings.json"
    if previous_settings.is_file() and not destination_settings.exists():
        integrated_root.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(previous_settings, destination_settings)
        except OSError:
            return False

    try:
        data = json.loads(
            (standalone_root / "settings.json").read_text(encoding="utf-8")
        )
        hover = data["hover"]
        if (
            data.get("schema_version") == 1
            and type(hover.get("paused")) is bool
            and isinstance(hover.get("dwell_ms"), int)
        ):
            state["hover_window_controls_enabled"] = not hover["paused"]
            state["hover_window_controls_dwell_ms"] = normalized_dwell_ms(
                hover["dwell_ms"]
            )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass

    destination = integrated_root / "vision-cache"
    legacy_copied = _copy_profiles(legacy_root / "vision-cache", destination)
    standalone_copied = _copy_profiles(
        standalone_root / "vision-cache", destination
    )
    integrated_copied = _copy_profiles(
        previous_integrated_root / "vision-cache", destination
    )
    if legacy_copied and standalone_copied and integrated_copied:
        state["hover_window_controls_migration_completed"] = True
        if previous_integrated_root != integrated_root and previous_integrated_root.exists():
            shutil.rmtree(previous_integrated_root)
    return True

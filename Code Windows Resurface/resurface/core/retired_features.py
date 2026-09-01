"""One-time cleanup for data owned by features removed from the application."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable


RETIRED_FEATURES_CLEANUP_VERSION = 1
RETIRED_HOVER_STATE_KEYS = frozenset(
    {
        "hover_window_controls_enabled",
        "hover_window_controls_dwell_ms",
        "hover_window_controls_migration_completed",
    }
)


def retired_hover_data_directories(local_app_data: Path) -> tuple[Path, ...]:
    root = Path(local_app_data)
    return (
        root / "Windows Resurface" / "hover-window-controls",
        root / "Hover Window Controls",
        root / "No Click Min Max Restore",
    )


def cleanup_retired_features(
    state: dict,
    *,
    local_app_data: Path | None = None,
    remove_tree: Callable[[Path], None] = shutil.rmtree,
) -> bool:
    """Remove retired feature data; failed deletions are retried next launch."""
    changed = False
    for key in RETIRED_HOVER_STATE_KEYS:
        if key in state:
            state.pop(key, None)
            changed = True

    try:
        completed_version = int(
            state.get("retired_features_cleanup_version", 0)
        )
    except (TypeError, ValueError):
        completed_version = 0
    if completed_version >= RETIRED_FEATURES_CLEANUP_VERSION:
        return changed

    if local_app_data is None:
        configured_root = os.environ.get("LOCALAPPDATA")
        local_app_data = (
            Path(configured_root)
            if configured_root
            else Path.home() / "AppData" / "Local"
        )

    cleanup_succeeded = True
    for directory in retired_hover_data_directories(local_app_data):
        try:
            if directory.is_symlink():
                directory.unlink()
            elif directory.exists():
                remove_tree(directory)
            if directory.exists() or directory.is_symlink():
                cleanup_succeeded = False
        except OSError as error:
            cleanup_succeeded = False
            print(f"[CLEANUP] Failed to remove retired data {directory}: {error}")

    if cleanup_succeeded:
        state["retired_features_cleanup_version"] = (
            RETIRED_FEATURES_CLEANUP_VERSION
        )
        changed = True
    return changed

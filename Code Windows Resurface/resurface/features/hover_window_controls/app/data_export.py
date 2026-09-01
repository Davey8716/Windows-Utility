"""Transactional local export of Hover Window Controls application data."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from resurface.features.hover_window_controls.app.identity import DISPLAY_NAME

EXPORT_SCHEMA_VERSION = 1
EXPORT_NAME_FORMAT = "%Y-%m-%d_%H-%M-%S"


class DataExportError(RuntimeError):
    """Raised when application data cannot be exported safely."""


@dataclass(frozen=True)
class DataExportResult:
    directory: Path
    included_roots: tuple[str, ...]


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _is_atomic_temporary(path: Path) -> bool:
    return path.name.startswith(".") and path.name.endswith(".tmp")


def _copy_tree(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise DataExportError(
            f"Cannot export symbolic link: {source.name}"
        )
    destination.mkdir()
    try:
        entries = sorted(source.iterdir(), key=lambda item: item.name)
    except OSError as error:
        raise DataExportError(
            f"Cannot read application-data folder: {source.name}"
        ) from error
    for entry in entries:
        if _is_atomic_temporary(entry):
            continue
        if entry.is_symlink():
            raise DataExportError(
                f"Cannot export symbolic link: {entry.name}"
            )
        target = destination / entry.name
        try:
            if entry.is_dir():
                _copy_tree(entry, target)
            elif entry.is_file():
                shutil.copy2(entry, target)
            else:
                raise DataExportError(
                    f"Unsupported application-data entry: {entry.name}"
                )
        except DataExportError:
            raise
        except OSError as error:
            raise DataExportError(
                f"Cannot copy application-data entry: {entry.name}"
            ) from error
    try:
        shutil.copystat(source, destination)
    except OSError as error:
        raise DataExportError(
            f"Cannot preserve folder metadata: {source.name}"
        ) from error


def _available_destination(
    parent: Path,
    timestamp: datetime,
) -> Path:
    base_name = (
        f"{DISPLAY_NAME} Export - "
        f"{timestamp.astimezone().strftime(EXPORT_NAME_FORMAT)}"
    )
    candidate = parent / base_name
    suffix = 2
    while candidate.exists():
        candidate = parent / f"{base_name} ({suffix})"
        suffix += 1
    return candidate


def export_application_data(
    destination_parent: Path,
    *,
    current_root: Path,
    legacy_root: Optional[Path] = None,
    now: Optional[datetime] = None,
    rename: Callable[[Path, Path], Path] = Path.rename,
) -> DataExportResult:
    """Copy application data to a completed timestamped export folder."""
    if destination_parent.is_symlink():
        raise DataExportError(
            "The selected export destination cannot be a symbolic link."
        )
    destination_parent = destination_parent.resolve()
    if not destination_parent.is_dir():
        raise DataExportError(
            "The selected export destination is not a usable folder."
        )

    source_roots = [current_root]
    if legacy_root is not None and legacy_root.exists():
        source_roots.append(legacy_root)
    roots = []
    for source in source_roots:
        if source.is_symlink():
            raise DataExportError(
                f"Application-data source cannot be a symbolic link: "
                f"{source.name}"
            )
        source = source.resolve()
        if not source.is_dir():
            raise DataExportError(
                f"Application-data source is unavailable: {source.name}"
            )
        if _is_within(destination_parent, source):
            raise DataExportError(
                "Choose an export destination outside the application-data "
                "folders."
            )
        roots.append(source)

    timestamp = now or datetime.now(timezone.utc)
    final_directory = _available_destination(
        destination_parent,
        timestamp,
    )
    staging = destination_parent / (
        f".{final_directory.name}.tmp-{uuid.uuid4().hex}"
    )
    included = []
    try:
        staging.mkdir()
        for source in roots:
            _copy_tree(source, staging / source.name)
            included.append(source.name)
        manifest = {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "application": DISPLAY_NAME,
            "exported_at_utc": timestamp.astimezone(
                timezone.utc
            ).isoformat(),
            "included_roots": included,
        }
        (staging / "export_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        rename(staging, final_directory)
    except DataExportError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except OSError as error:
        shutil.rmtree(staging, ignore_errors=True)
        raise DataExportError(
            "The export could not be completed at the selected location."
        ) from error
    return DataExportResult(final_directory, tuple(included))

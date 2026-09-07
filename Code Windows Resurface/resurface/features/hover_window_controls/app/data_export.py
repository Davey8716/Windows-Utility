"""Transactional local export of Hover Window Controls application data."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from resurface.features.hover_window_controls.app.identity import DISPLAY_NAME

EXPORT_SCHEMA_VERSION = 2
EXPORT_MANIFEST_NAME = "export_manifest.json"


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


def _managed_fingerprint(directory: Path, names: list[str]) -> str:
    """Return a stable fingerprint for managed top-level entries."""
    digest = hashlib.sha256()
    for name in sorted(names):
        root = directory / name
        if root.is_symlink():
            raise DataExportError(
                f"Application-data source cannot be a symbolic link: {root.name}"
            )
        if not root.exists():
            raise DataExportError(
                f"Application-data source is unavailable: {root.name}"
            )
        digest.update(b"entry\0" + name.encode("utf-8") + b"\0")
        if root.is_file():
            entries = [root]
        elif root.is_dir():
            try:
                descendants = sorted(
                    root.rglob("*"), key=lambda item: item.as_posix()
                )
            except OSError as error:
                raise DataExportError(
                    f"Cannot read application-data folder: {root.name}"
                ) from error
            entries = [root, *descendants]
        else:
            raise DataExportError(
                f"Unsupported application-data entry: {root.name}"
            )
        for entry in entries:
            if entry.is_symlink():
                raise DataExportError(
                    f"Cannot export symbolic link: {entry.name}"
                )
            relative = entry.relative_to(directory).as_posix().encode("utf-8")
            if entry.is_dir():
                digest.update(b"dir\0" + relative + b"\0")
                continue
            if not entry.is_file():
                raise DataExportError(
                    f"Unsupported application-data entry: {entry.name}"
                )
            digest.update(b"file\0" + relative + b"\0")
            try:
                with entry.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            except OSError as error:
                raise DataExportError(
                    f"Cannot read application-data entry: {entry.name}"
                ) from error
            digest.update(b"\0")
    return digest.hexdigest()


def _read_direct_manifest(directory: Path) -> dict | None:
    path = directory / EXPORT_MANIFEST_NAME
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as error:
        raise DataExportError(
            "The existing hover-data export manifest is invalid."
        ) from error
    managed = (
        manifest.get("managed_entries") if isinstance(manifest, dict) else None
    )
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != EXPORT_SCHEMA_VERSION
        or manifest.get("application") != DISPLAY_NAME
        or manifest.get("layout") != "direct"
        or not isinstance(managed, list)
        or len(managed) != len(set(managed))
        or any(
            not isinstance(name, str)
            or not name
            or Path(name).name != name
            or name == EXPORT_MANIFEST_NAME
            for name in managed
        )
    ):
        raise DataExportError(
            "The existing hover-data export manifest is invalid."
        )
    return manifest


def _copy_current_contents(source: Path, staging: Path) -> list[str]:
    names = []
    try:
        entries = sorted(source.iterdir(), key=lambda item: item.name)
    except OSError as error:
        raise DataExportError(
            f"Cannot read application-data folder: {source.name}"
        ) from error
    for entry in entries:
        if _is_atomic_temporary(entry):
            continue
        if entry.name == EXPORT_MANIFEST_NAME:
            raise DataExportError(
                "Application data contains the reserved file "
                f"{EXPORT_MANIFEST_NAME}."
            )
        target = staging / entry.name
        if entry.is_symlink():
            raise DataExportError(f"Cannot export symbolic link: {entry.name}")
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
        names.append(entry.name)
    return names


def export_application_data(
    destination_parent: Path,
    *,
    current_root: Path,
    legacy_root: Optional[Path] = None,
    now: Optional[datetime] = None,
    rename: Callable[[Path, Path], Path] = Path.rename,
) -> DataExportResult | None:
    """Copy changed application data directly into the export directory."""
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
    staging = destination_parent / (
        f".{DISPLAY_NAME}.export.tmp-{uuid.uuid4().hex}"
    )
    rollback = destination_parent / (
        f".{DISPLAY_NAME}.export.rollback-{uuid.uuid4().hex}"
    )
    included = [root.name for root in roots]
    installed: list[str] = []
    backed_up: list[str] = []
    try:
        staging.mkdir()
        managed = _copy_current_contents(roots[0], staging)
        if len(roots) > 1:
            legacy_name = roots[1].name
            if legacy_name in managed:
                raise DataExportError(
                    f"Application-data entries conflict at: {legacy_name}"
                )
            _copy_tree(roots[1], staging / legacy_name)
            managed.append(legacy_name)
        managed.sort()

        previous_manifest = _read_direct_manifest(destination_parent)
        previous_managed = (
            list(previous_manifest["managed_entries"])
            if previous_manifest is not None
            else []
        )
        if previous_manifest is None:
            conflicts = [
                name for name in managed if (destination_parent / name).exists()
            ]
            if conflicts:
                raise DataExportError(
                    "The export destination already contains unmanaged data: "
                    + ", ".join(conflicts)
                )
        else:
            unowned_conflicts = [
                name
                for name in managed
                if name not in previous_managed
                and (destination_parent / name).exists()
            ]
            if unowned_conflicts:
                raise DataExportError(
                    "The export destination already contains unmanaged data: "
                    + ", ".join(unowned_conflicts)
                )
            if (
                managed == previous_managed
                and _managed_fingerprint(staging, managed)
                == _managed_fingerprint(destination_parent, previous_managed)
            ):
                shutil.rmtree(staging)
                return None

        manifest = {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "application": DISPLAY_NAME,
            "layout": "direct",
            "exported_at_utc": timestamp.astimezone(
                timezone.utc
            ).isoformat(),
            "included_roots": included,
            "managed_entries": managed,
        }
        (staging / EXPORT_MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        rollback.mkdir()
        for name in [*previous_managed, EXPORT_MANIFEST_NAME]:
            source = destination_parent / name
            if source.exists():
                rename(source, rollback / name)
                backed_up.append(name)
        for name in [*managed, EXPORT_MANIFEST_NAME]:
            rename(staging / name, destination_parent / name)
            installed.append(name)
        staging.rmdir()
        shutil.rmtree(rollback)
    except DataExportError:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(rollback, ignore_errors=True)
        raise
    except OSError as error:
        recovery_failed = False
        for name in reversed(installed):
            target = destination_parent / name
            if target.is_dir():
                try:
                    shutil.rmtree(target)
                except OSError:
                    recovery_failed = True
            else:
                try:
                    target.unlink()
                except OSError:
                    recovery_failed = True
        for name in reversed(backed_up):
            source = rollback / name
            if source.exists():
                try:
                    source.rename(destination_parent / name)
                except OSError:
                    recovery_failed = True
        shutil.rmtree(staging, ignore_errors=True)
        if not recovery_failed:
            shutil.rmtree(rollback, ignore_errors=True)
        raise DataExportError(
            "The export could not be completed at the selected location."
        ) from error
    return DataExportResult(destination_parent, tuple(included))

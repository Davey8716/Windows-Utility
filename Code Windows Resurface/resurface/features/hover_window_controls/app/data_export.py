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

from resurface.features.hover_window_controls.app.identity import (
    DISPLAY_NAME,
    LEGACY_DATA_DIRECTORY,
)

EXPORT_SCHEMA_VERSION = 2
EXPORT_MANIFEST_NAME = "export_manifest.json"


class DataExportError(RuntimeError):
    """Raised when application data cannot be exported safely."""


@dataclass(frozen=True)
class DataExportResult:
    directory: Path
    included_roots: tuple[str, ...]


@dataclass(frozen=True)
class DataImportResult:
    source_directory: Path
    settings: dict


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


def _entries_fingerprint(
    entries_by_name: dict[str, Path | bytes],
) -> str:
    """Return a stable fingerprint for logical top-level entries."""
    digest = hashlib.sha256()
    for name in sorted(entries_by_name):
        root_or_bytes = entries_by_name[name]
        digest.update(b"entry\0" + name.encode("utf-8") + b"\0")
        if isinstance(root_or_bytes, bytes):
            digest.update(b"file\0" + name.encode("utf-8") + b"\0")
            digest.update(root_or_bytes)
            digest.update(b"\0")
            continue
        root = root_or_bytes
        if root.is_symlink():
            raise DataExportError(
                f"Application-data source cannot be a symbolic link: {root.name}"
            )
        if not root.exists():
            raise DataExportError(
                f"Application-data source is unavailable: {root.name}"
            )
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
            relative_path = entry.relative_to(root)
            if entry != root and any(
                _is_atomic_temporary(Path(part))
                for part in relative_path.parts
            ):
                continue
            if entry.is_symlink():
                raise DataExportError(
                    f"Cannot export symbolic link: {entry.name}"
                )
            relative_suffix = (
                "" if entry == root else f"/{relative_path.as_posix()}"
            )
            relative = f"{name}{relative_suffix}".encode("utf-8")
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


def _managed_fingerprint(directory: Path, names: list[str]) -> str:
    return _entries_fingerprint(
        {name: directory / name for name in names}
    )


def _settings_bytes(settings: dict) -> bytes:
    return json.dumps(settings, indent=2, sort_keys=True).encode("utf-8")


def _current_export_entries(
    current_root: Path,
    legacy_root: Optional[Path],
    settings: dict,
) -> dict[str, Path | bytes]:
    entries: dict[str, Path | bytes] = {}
    if current_root.is_symlink():
        raise DataExportError(
            "Application-data source cannot be a symbolic link: "
            f"{current_root.name}"
        )
    if current_root.exists():
        if not current_root.is_dir():
            raise DataExportError(
                f"Application-data source is unavailable: {current_root.name}"
            )
        try:
            children = sorted(
                current_root.iterdir(), key=lambda item: item.name
            )
        except OSError as error:
            raise DataExportError(
                f"Cannot read application-data folder: {current_root.name}"
            ) from error
    else:
        children = []
    for entry in children:
        if _is_atomic_temporary(entry) or entry.name == "settings.json":
            continue
        if entry.name == EXPORT_MANIFEST_NAME:
            raise DataExportError(
                "Application data contains the reserved file "
                f"{EXPORT_MANIFEST_NAME}."
            )
        entries[entry.name] = entry
    entries["settings.json"] = _settings_bytes(settings)
    if legacy_root is not None and legacy_root.exists():
        if legacy_root.name in entries:
            raise DataExportError(
                f"Application-data entries conflict at: {legacy_root.name}"
            )
        entries[legacy_root.name] = legacy_root
    return entries


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


def has_application_data_export_changes(
    destination_directory: Path,
    *,
    current_root: Path,
    settings: dict,
    legacy_root: Optional[Path] = None,
) -> bool:
    """Return whether live hover data differs from the direct export."""
    if destination_directory.is_symlink():
        raise DataExportError(
            "The hover-data export destination cannot be a symbolic link."
        )
    if not destination_directory.exists():
        return True
    destination_directory = destination_directory.resolve()
    if not destination_directory.is_dir():
        raise DataExportError(
            "The hover-data export destination is not a usable folder."
        )
    manifest = _read_direct_manifest(destination_directory)
    if manifest is None:
        return True
    current_entries = _current_export_entries(
        current_root,
        legacy_root,
        settings,
    )
    managed = list(manifest["managed_entries"])
    if managed != sorted(current_entries):
        return True
    return _entries_fingerprint(current_entries) != _managed_fingerprint(
        destination_directory,
        managed,
    )


def _copy_current_contents(
    source: Path,
    staging: Path,
    settings: dict | None = None,
) -> list[str]:
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
        if settings is not None and entry.name == "settings.json":
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
    if settings is not None:
        (staging / "settings.json").write_bytes(_settings_bytes(settings))
        names.append("settings.json")
    return names


def validate_application_data_export(source_directory: Path) -> dict:
    """Validate a direct-layout export and return its hover settings."""
    if source_directory.is_symlink():
        raise DataExportError("The selected hover-data backup cannot be a symbolic link.")
    source_directory = source_directory.resolve()
    if not source_directory.is_dir():
        raise DataExportError("The selected hover-data backup is not a usable folder.")
    manifest = _read_direct_manifest(source_directory)
    if manifest is None:
        raise DataExportError("The selected folder is not a Hover Window Controls backup.")
    managed = list(manifest["managed_entries"])
    _managed_fingerprint(source_directory, managed)
    if "settings.json" not in managed:
        raise DataExportError("The hover-data backup does not contain settings.json.")
    try:
        settings = json.loads(
            (source_directory / "settings.json").read_text(encoding="utf-8")
        )
        hover = settings["hover"]
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise DataExportError("The hover-data backup settings are invalid.") from error
    if (
        not isinstance(settings, dict)
        or settings.get("schema_version") != 1
        or not isinstance(hover, dict)
        or type(hover.get("enabled")) is not bool
        or type(hover.get("taskbar_restore_enabled")) is not bool
        or type(hover.get("dwell_ms")) is not int
    ):
        raise DataExportError("The hover-data backup settings are invalid.")
    return settings


def import_application_data(
    source_directory: Path,
    *,
    current_root: Path,
    rename: Callable[[Path, Path], Path] = Path.rename,
) -> DataImportResult:
    """Replace current hover data with a validated direct-layout export."""
    source_directory = source_directory.resolve()
    if current_root.is_symlink():
        raise DataExportError(
            "The active Hover Window Controls data folder cannot be a "
            "symbolic link."
        )
    current_root = current_root.resolve()
    if (
        source_directory == current_root
        or _is_within(source_directory, current_root)
        or _is_within(current_root, source_directory)
    ):
        raise DataExportError(
            "Choose a hover-data backup outside the active application-data folder."
        )
    settings = validate_application_data_export(source_directory)
    manifest = _read_direct_manifest(source_directory)
    managed = list(manifest["managed_entries"])
    staging = current_root.parent / (
        f".{current_root.name}.import.tmp-{uuid.uuid4().hex}"
    )
    rollback = current_root.parent / (
        f".{current_root.name}.import.rollback-{uuid.uuid4().hex}"
    )
    moved_current = False
    try:
        staging.mkdir(parents=True)
        for name in managed:
            if name == LEGACY_DATA_DIRECTORY:
                continue
            source = source_directory / name
            target = staging / name
            if source.is_dir():
                _copy_tree(source, target)
            elif source.is_file() and not source.is_symlink():
                shutil.copy2(source, target)
            else:
                raise DataExportError(
                    f"Unsupported hover-data backup entry: {name}"
                )
        legacy_cache = (
            source_directory / LEGACY_DATA_DIRECTORY / "vision-cache"
        )
        if legacy_cache.is_dir():
            target_cache = staging / "vision-cache"
            target_cache.mkdir(exist_ok=True)
            for profile in sorted(legacy_cache.iterdir(), key=lambda item: item.name):
                target = target_cache / profile.name
                if target.exists():
                    continue
                if profile.is_dir() and not profile.is_symlink():
                    _copy_tree(profile, target)
        if current_root.exists():
            rename(current_root, rollback)
            moved_current = True
        rename(staging, current_root)
        if moved_current:
            shutil.rmtree(rollback, ignore_errors=True)
    except DataExportError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except OSError as error:
        if moved_current and not current_root.exists() and rollback.exists():
            try:
                rollback.rename(current_root)
            except OSError:
                pass
        shutil.rmtree(staging, ignore_errors=True)
        raise DataExportError(
            "The hover-data backup could not be imported safely."
        ) from error
    return DataImportResult(source_directory, settings)


def export_application_data(
    destination_parent: Path,
    *,
    current_root: Path,
    legacy_root: Optional[Path] = None,
    settings: dict | None = None,
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

    if settings is not None and not has_application_data_export_changes(
        destination_parent,
        current_root=roots[0],
        legacy_root=roots[1] if len(roots) > 1 else None,
        settings=settings,
    ):
        return None

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
        managed = _copy_current_contents(roots[0], staging, settings)
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

import json
import os
import tempfile
from pathlib import Path


APP_DIR_NAME = "Windows Resurface"
FILENAME = "saved_folder_names.json"
MAX_SAVED_NAMES = 20


def get_legacy_saved_folder_names_path() -> Path:
    """Return the pre-master-backup location, for one-time migration only."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIR_NAME / FILENAME
    return Path.home() / "AppData" / "Local" / APP_DIR_NAME / FILENAME


def get_saved_folder_names_path(master_backup_dir: str | Path) -> Path:
    """Return the canonical saved-names file beneath the master backup."""
    root = Path(master_backup_dir)
    if not str(root).strip():
        raise ValueError("A Master Backup Path is required for saved folder names.")
    return root / "Saved Folder Names" / FILENAME


def load_saved_folder_names(path: Path) -> list[str]:
    source = Path(path)
    try:
        with open(source, "r", encoding="utf-8") as file_obj:
            payload = json.load(file_obj)
    except FileNotFoundError:
        return []
    except Exception as exc:
        print(f"[SAVED FOLDERS] Failed to read {source}: {exc}")
        return []

    if not isinstance(payload, list):
        return []

    names: list[str] = []
    seen: set[str] = set()
    for value in payload:
        if not isinstance(value, str):
            continue
        name = value.strip()
        key = name.casefold()
        if not name or key in seen:
            continue
        names.append(name)
        seen.add(key)
        if len(names) == MAX_SAVED_NAMES:
            break
    return names


def save_saved_folder_names(names: list[str], path: Path) -> bool:
    target = Path(path)
    temp_path: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=target.parent,
            prefix=f"{target.stem}-",
            suffix=".tmp",
        ) as file_obj:
            temp_path = Path(file_obj.name)
            json.dump(names[:MAX_SAVED_NAMES], file_obj, indent=4)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.replace(temp_path, target)
        return True
    except Exception as exc:
        print(f"[SAVED FOLDERS] Failed to write {target}: {exc}")
        return False
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass


def add_saved_folder_name(name: str, path: Path) -> list[str]:
    clean_name = name.strip()
    names = load_saved_folder_names(path)
    if not clean_name:
        return names
    key = clean_name.casefold()
    updated = [clean_name, *(value for value in names if value.casefold() != key)]
    updated = updated[:MAX_SAVED_NAMES]
    if save_saved_folder_names(updated, path):
        return updated
    return names


def remove_saved_folder_name(name: str, path: Path) -> list[str]:
    clean_name = name.strip()
    names = load_saved_folder_names(path)
    if not clean_name:
        return names
    key = clean_name.casefold()
    updated = [value for value in names if value.casefold() != key]
    if updated == names:
        return names
    if save_saved_folder_names(updated, path):
        return updated
    return names


def clear_saved_folder_names(path: Path) -> list[str]:
    names = load_saved_folder_names(path)
    if not names:
        return names
    if save_saved_folder_names([], path):
        return []
    return names


def migrate_legacy_saved_folder_names(destination: Path) -> bool:
    """Merge the old AppData list into *destination*, then remove it safely."""
    legacy = get_legacy_saved_folder_names_path()
    if not legacy.exists():
        return False
    legacy_names = load_saved_folder_names(legacy)
    existing = load_saved_folder_names(destination)
    merged = [*existing]
    seen = {name.casefold() for name in merged}
    for name in legacy_names:
        if name.casefold() not in seen:
            merged.append(name)
            seen.add(name.casefold())
    if not save_saved_folder_names(merged[:MAX_SAVED_NAMES], destination):
        raise OSError("Could not write saved folder names to the Master Backup Path.")
    legacy.unlink()
    return True

from __future__ import annotations

import ctypes
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pythoncom
import win32com.client
import win32process

from resurface.features.windows.window_management import WindowManagementService


RECYCLE_BIN_CLSID = "{645FF040-5081-101B-9F08-00AA002F954E}"


class SHQUERYRBINFO(ctypes.Structure):
    """The item-count information returned by ``SHQueryRecycleBinW``."""

    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


def iter_windows_drive_roots():
    try:
        drive_mask = ctypes.windll.kernel32.GetLogicalDrives()
    except Exception:
        drive_mask = 0
    for index in range(26):
        if drive_mask & (1 << index):
            drive_root = Path(f"{chr(ord('A') + index)}:\\")
            if drive_root.exists():
                yield drive_root


def iter_recycle_bin_metadata_files():
    for drive_root in iter_windows_drive_roots():
        recycle_root = drive_root / "$Recycle.Bin"
        if not recycle_root.exists():
            continue
        try:
            for metadata_path in recycle_root.rglob("$I*"):
                if metadata_path.is_file():
                    yield metadata_path
        except (OSError, PermissionError):
            continue


def filetime_to_utc_datetime(filetime: int) -> datetime:
    return datetime.fromtimestamp(
        (filetime - 116444736000000000) / 10_000_000,
        tz=timezone.utc,
    )


def read_recycle_bin_deleted_at(metadata_path: Path) -> datetime | None:
    try:
        with metadata_path.open("rb") as metadata_file:
            header = metadata_file.read(24)
    except OSError:
        return None
    if len(header) < 24:
        return None
    filetime = int.from_bytes(header[16:24], "little", signed=False)
    return filetime_to_utc_datetime(filetime) if filetime > 0 else None


def delete_recycle_bin_entry(metadata_path: Path) -> bool:
    resource_path = metadata_path.with_name("$R" + metadata_path.name[2:])
    deleted_any = False
    for path in (metadata_path, resource_path):
        if not path.exists():
            continue
        try:
            shutil.rmtree(path, ignore_errors=False) if path.is_dir() else path.unlink()
            deleted_any = True
        except OSError as exc:
            print(f"[RECYCLE BIN] Failed to delete {path}: {exc}")
            return False
    return deleted_any


def find_recycle_bin_explorer_windows() -> list[dict[str, int]]:
    windows: list[dict[str, int]] = []
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass
    try:
        shell_windows = win32com.client.Dispatch("Shell.Application").Windows()
    except Exception as exc:
        print(f"[DEBUG] find_recycle_bin_explorer_windows failed: {exc}")
        return windows
    for window in shell_windows:
        try:
            hwnd = int(window.HWND)
            folder_self = window.Document.Folder.Self
        except Exception:
            continue
        try:
            folder_path = str(getattr(folder_self, "Path", "") or "")
        except Exception:
            folder_path = ""
        try:
            folder_name = str(getattr(folder_self, "Name", "") or "")
        except Exception:
            folder_name = ""
        if RECYCLE_BIN_CLSID.casefold() not in folder_path.casefold() and folder_name.casefold() != "recycle bin":
            continue
        try:
            _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            pid = 0
        windows.append({"hwnd": hwnd, "pid": int(pid)})
    return windows


class RecycleBinService:
    def __init__(self, windows: WindowManagementService):
        self.windows = windows

    def open(self) -> bool:
        try:
            subprocess.Popen(
                ["explorer.exe", "shell:RecycleBinFolder"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as exc:
            print("[RECYCLE BIN] Failed to open:", exc)
            return False

    def empty(self) -> bool:
        try:
            result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x1 | 0x2 | 0x4)
            if result != 0:
                print(f"[RECYCLE BIN] SHEmptyRecycleBinW returned {result}")
                return False
            return True
        except Exception as exc:
            print("[RECYCLE BIN] Failed to empty:", exc)
            return False

    def has_items(self) -> bool:
        """Return whether Windows reports anything in the current Recycle Bin."""
        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(info)
        try:
            result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
            if result != 0:
                print(f"[RECYCLE BIN] SHQueryRecycleBinW returned {result}")
                return False
            return info.i64NumItems > 0
        except Exception as exc:
            print("[RECYCLE BIN] Failed to query:", exc)
            return False

    def has_items_older_than(self, days: int) -> bool:
        """Return whether a dated Recycle Bin entry meets an age rule.

        ``SHQueryRecycleBinW`` only provides a total count; the ``$I`` metadata
        files are needed to determine whether a particular cleanup rule can run.
        """
        if days <= 0:
            return False
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        for metadata_path in iter_recycle_bin_metadata_files():
            deleted_at = read_recycle_bin_deleted_at(metadata_path)
            if deleted_at is not None and deleted_at <= cutoff:
                return True
        return False

    def cleanup_age_rule_availability(
        self, days: tuple[int, ...] = (7, 14, 30)
    ) -> dict[int, bool]:
        """Return the currently actionable cleanup ages in one metadata scan."""
        requested_days = tuple(sorted({day for day in days if day > 0}))
        available = {day: False for day in requested_days}
        if not requested_days:
            return available
        now = datetime.now(timezone.utc)
        for metadata_path in iter_recycle_bin_metadata_files():
            deleted_at = read_recycle_bin_deleted_at(metadata_path)
            if deleted_at is None:
                continue
            age = now - deleted_at
            for day in requested_days:
                if age >= timedelta(days=day):
                    available[day] = True
            if all(available.values()):
                break
        return available

    def cleanup_items_older_than(self, days: int) -> int:
        if days <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        deleted_count = 0
        for metadata_path in iter_recycle_bin_metadata_files():
            deleted_at = read_recycle_bin_deleted_at(metadata_path)
            if deleted_at is not None and deleted_at <= cutoff and delete_recycle_bin_entry(metadata_path):
                deleted_count += 1
        return deleted_count

    def is_open(self) -> bool:
        return bool(find_recycle_bin_explorer_windows())

    def close(self) -> bool:
        return self.windows.close_handles(
            [entry["hwnd"] for entry in find_recycle_bin_explorer_windows()]
        )

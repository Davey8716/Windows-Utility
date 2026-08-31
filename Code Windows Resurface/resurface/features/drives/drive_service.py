from __future__ import annotations

import os
import shutil
import string
import subprocess
from dataclasses import dataclass

import win32file


def hidden_startupinfo():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return startupinfo


@dataclass(frozen=True, slots=True)
class DriveInfo:
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    ejectable: bool


class DriveServiceError(RuntimeError):
    pass


class DriveService:
    def usb_drive_letters(self) -> set[str]:
        try:
            result = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "Get-CimInstance Win32_DiskDrive | "
                        "Where-Object { $_.InterfaceType -eq 'USB' } | "
                        "ForEach-Object { "
                        "Get-CimAssociatedInstance -InputObject $_ "
                        "-Association Win32_DiskDriveToDiskPartition | "
                        "ForEach-Object { "
                        "Get-CimAssociatedInstance -InputObject $_ "
                        "-Association Win32_LogicalDiskToPartition | "
                        "ForEach-Object { $_.DeviceID } } }"
                    ),
                ],
                text=True,
                errors="ignore",
                startupinfo=hidden_startupinfo(),
            )
        except Exception:
            return set()

        drive_letters = set()
        for line in result.splitlines():
            entry = line.strip().upper()
            if len(entry) >= 2 and entry[1] == ":":
                drive_letters.add(f"{entry[:2]}\\")
        return drive_letters

    def list_drives(self) -> list[DriveInfo]:
        usb_drives = self.usb_drive_letters()
        drives: list[DriveInfo] = []
        for letter in string.ascii_uppercase:
            path = f"{letter}:\\"
            if not os.path.exists(path):
                continue
            try:
                total, used, free = shutil.disk_usage(path)
            except Exception:
                continue
            try:
                drive_type = win32file.GetDriveType(path)
            except Exception:
                drive_type = None
            drives.append(
                DriveInfo(
                    path=path,
                    total_bytes=total,
                    used_bytes=used,
                    free_bytes=free,
                    ejectable=(
                        drive_type == win32file.DRIVE_REMOVABLE
                        or path.upper() in usb_drives
                    ),
                )
            )
        return drives

    def eject(self, path: str) -> None:
        drive_name = path[:2]
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "(New-Object -ComObject Shell.Application)"
                        f".Namespace(17).ParseName('{drive_name}').InvokeVerb('Eject')"
                    ),
                ],
                check=True,
                startupinfo=hidden_startupinfo(),
            )
        except Exception as exc:
            raise DriveServiceError(str(exc)) from exc

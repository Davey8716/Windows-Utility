import subprocess

import pytest

from resurface.features.drives import drive_service
from resurface.features.drives.drive_service import DriveService, DriveServiceError


def test_usb_drive_letters_normalizes_powershell_output(monkeypatch):
    monkeypatch.setattr(
        drive_service.subprocess,
        "check_output",
        lambda *args, **kwargs: "e:\n F:\\ignored\nnot-a-drive\n",
    )
    assert DriveService().usb_drive_letters() == {"E:\\", "F:\\"}


def test_usb_drive_letters_returns_empty_set_when_detection_fails(monkeypatch):
    monkeypatch.setattr(
        drive_service.subprocess,
        "check_output",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("unavailable")),
    )
    assert DriveService().usb_drive_letters() == set()


def test_list_drives_skips_inaccessible_paths_and_marks_usb(monkeypatch):
    service = DriveService()
    monkeypatch.setattr(service, "usb_drive_letters", lambda: {"E:\\"})
    monkeypatch.setattr(drive_service.os.path, "exists", lambda path: path in {"C:\\", "D:\\", "E:\\"})

    def disk_usage(path):
        if path == "D:\\":
            raise PermissionError(path)
        return (100, 40, 60)

    monkeypatch.setattr(drive_service.shutil, "disk_usage", disk_usage)
    monkeypatch.setattr(drive_service.win32file, "GetDriveType", lambda _path: drive_service.win32file.DRIVE_FIXED)

    drives = service.list_drives()
    assert [(drive.path, drive.used_bytes, drive.ejectable) for drive in drives] == [
        ("C:\\", 40, False),
        ("E:\\", 40, True),
    ]


def test_eject_wraps_process_errors(monkeypatch):
    monkeypatch.setattr(
        drive_service.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "powershell")),
    )
    with pytest.raises(DriveServiceError):
        DriveService().eject("E:\\")

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class BackupResult:
    count: int
    completed: bool


class TaskbarBackupService:
    @staticmethod
    def pinned_shortcuts_path() -> str:
        return os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar",
        )

    def backup(self, backup_folder: str) -> BackupResult:
        print("[BACKUP] Starting backup of pinned shortcuts...")
        pinned_path = self.pinned_shortcuts_path()
        if not os.path.isdir(pinned_path):
            print("[BACKUP] ERROR: Pinned folder not found:", pinned_path)
            return BackupResult(0, False)
        if not backup_folder:
            print("[BACKUP] ERROR: No backup folder provided")
            return BackupResult(0, False)
        try:
            os.makedirs(backup_folder, exist_ok=True)
        except Exception as exc:
            print("[BACKUP] ERROR: Cannot create backup folder:", exc)
            return BackupResult(0, False)
        count = 0
        for name in os.listdir(pinned_path):
            if not name.lower().endswith(".lnk"):
                continue
            try:
                shutil.copy2(os.path.join(pinned_path, name), os.path.join(backup_folder, name))
                count += 1
            except Exception as exc:
                print(f"[BACKUP] Failed to copy {name}: {exc}")
        print(f"[BACKUP] Completed. {count} shortcuts copied.")
        return BackupResult(count, True)

    def backup_pinned_shortcuts(self, backup_folder: str) -> int:
        return self.backup(backup_folder).count

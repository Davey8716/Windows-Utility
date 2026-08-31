from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class FolderCreationStatus(str, Enum):
    CREATED = "created"
    EXISTS = "exists"
    FAILED = "failed"


@dataclass(frozen=True)
class FolderCreationResult:
    status: FolderCreationStatus
    path: Path
    error: str | None = None


class DesktopFolderService:
    def create(self, desktop_path: str | Path, folder_name: str) -> FolderCreationResult:
        target = Path(desktop_path) / folder_name
        if target.exists():
            return FolderCreationResult(FolderCreationStatus.EXISTS, target)
        try:
            target.mkdir(parents=True, exist_ok=False)
        except Exception as exc:
            return FolderCreationResult(FolderCreationStatus.FAILED, target, str(exc))
        return FolderCreationResult(FolderCreationStatus.CREATED, target)

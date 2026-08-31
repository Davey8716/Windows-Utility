"""Persistence for monitor-rule backup files."""

from __future__ import annotations

import copy
from datetime import datetime
import json
from pathlib import Path
from typing import Callable

from .monitor_rules import normalize_monitor_rules


BACKUP_FORMAT = "windows-resurface-monitor-rules"
BACKUP_VERSION = 1


class BackupDirectoryNotConfiguredError(ValueError):
    """Raised when an export has no configured destination."""


class MonitorRulesRepository:
    """Read and write normalized monitor-rule backup files."""

    def __init__(
        self,
        get_master_backup_dir: Callable[[], str] | None = None,
        *,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._get_master_backup_dir = get_master_backup_dir
        self._now = now

    def backup_directory(self) -> Path | None:
        if not callable(self._get_master_backup_dir):
            return None
        raw_path = str(self._get_master_backup_dir() or "").strip()
        return Path(raw_path) if raw_path else None

    def export_rules(self, rules: list[dict], *, safety_backup: bool = False) -> Path:
        backup_dir = self.backup_directory()
        if backup_dir is None:
            raise BackupDirectoryNotConfiguredError(
                "Set a Master Backup Path before exporting monitor rules."
            )

        timestamp = self._now().strftime("%Y%m%d_%H%M%S_%f")
        prefix = "monitor_rules_before_delete" if safety_backup else "monitor_rules"
        path = backup_dir / "Monitor Rules" / f"{prefix}_{timestamp}.json"
        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "rules": normalize_monitor_rules(copy.deepcopy(rules)),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def import_rules(self, path: str | Path) -> list[dict]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        raw_rules = payload.get("rules") if isinstance(payload, dict) else None
        if not isinstance(raw_rules, list):
            raise ValueError("The selected file is not a monitor rules backup.")
        return normalize_monitor_rules(raw_rules)

"""Persistence for monitor-rule backup files."""

from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Callable

from .rule_schema import normalize_monitor_rules


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
        get_import_baseline: Callable[[], dict | None] | None = None,
        set_import_baseline: Callable[[dict | None], None] | None = None,
    ) -> None:
        self._get_master_backup_dir = get_master_backup_dir
        self._now = now
        self._get_import_baseline = get_import_baseline
        self._set_import_baseline = set_import_baseline
        self._import_baseline = None

    @staticmethod
    def _fingerprint(rules: list[dict]) -> str:
        normalized = normalize_monitor_rules(copy.deepcopy(rules))
        encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _destination_key(self) -> str | None:
        directory = self.backup_directory()
        return str(directory.resolve()) if directory is not None else None

    def _store_import_baseline(self, baseline: dict | None) -> None:
        if self._set_import_baseline is not None:
            self._set_import_baseline(copy.deepcopy(baseline))
        self._import_baseline = copy.deepcopy(baseline)

    def record_import(self, path: str | Path, imported_rules: list[dict]) -> None:
        """Record the file contents only after the user accepts the import."""
        self._store_import_baseline({
            "source_path": str(Path(path).resolve()),
            "fingerprint": self._fingerprint(imported_rules),
            "backup_destination": self._destination_key(),
        })

    def _valid_import_fingerprint(self) -> str | None:
        baseline = (
            self._get_import_baseline()
            if self._get_import_baseline is not None
            else self._import_baseline
        )
        if not isinstance(baseline, dict):
            return None
        try:
            if baseline.get("backup_destination") != self._destination_key():
                return None
            source = baseline.get("source_path")
            fingerprint = baseline.get("fingerprint")
            if not isinstance(source, str) or not source or not isinstance(fingerprint, str):
                return None
            if self._fingerprint(self.import_rules(source)) == fingerprint:
                return fingerprint
        except (OSError, TypeError, ValueError):
            pass
        return None

    def backup_directory(self) -> Path | None:
        if not callable(self._get_master_backup_dir):
            return None
        raw_path = str(self._get_master_backup_dir() or "").strip()
        return Path(raw_path) if raw_path else None

    def has_export_changes(self, rules: list[dict]) -> bool:
        """Compare with an accepted import, or the latest compatible export."""
        imported_fingerprint = self._valid_import_fingerprint()
        if imported_fingerprint is not None:
            return self._fingerprint(rules) != imported_fingerprint
        backup_dir = self.backup_directory()
        if backup_dir is None:
            return True
        current = normalize_monitor_rules(copy.deepcopy(rules))
        candidates = sorted(
            (
                path
                for path in (backup_dir / "Monitor Rules").glob("monitor_rules_*.json")
                if re.fullmatch(r"monitor_rules_\d{8}_\d{6}_\d{6}\.json", path.name)
            ),
            reverse=True,
        )
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if (
                    not isinstance(payload, dict)
                    or payload.get("format") != BACKUP_FORMAT
                    or payload.get("version") != BACKUP_VERSION
                    or not isinstance(payload.get("rules"), list)
                ):
                    continue
                previous = normalize_monitor_rules(payload["rules"])
                if len(previous) != len(payload["rules"]):
                    continue
            except (OSError, ValueError, TypeError):
                continue
            return current != previous
        return True

    def export_rules(
        self, rules: list[dict], *, safety_backup: bool = False
    ) -> Path | None:
        backup_dir = self.backup_directory()
        if backup_dir is None:
            raise BackupDirectoryNotConfiguredError(
                "Set a Master Backup Path before exporting monitor rules."
            )

        if not safety_backup and not self.has_export_changes(rules):
            return None

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
        if not safety_backup:
            self._store_import_baseline(None)
        return path

    def import_rules(self, path: str | Path) -> list[dict]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        raw_rules = payload.get("rules") if isinstance(payload, dict) else None
        if not isinstance(raw_rules, list):
            raise ValueError("The selected file is not a monitor rules backup.")
        return normalize_monitor_rules(raw_rules)

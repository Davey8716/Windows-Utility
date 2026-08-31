import json
from datetime import datetime

import pytest

from resurface.features.monitor_rules import MonitorRulesRepository
from test_monitor_rules_ui import make_rule


def test_repository_exports_versioned_normalized_backup(tmp_path):
    repository = MonitorRulesRepository(
        lambda: str(tmp_path),
        now=lambda: datetime(2026, 8, 31, 12, 30, 45, 123456),
    )

    path = repository.export_rules([make_rule()])

    assert path == (
        tmp_path / "Monitor Rules" / "monitor_rules_20260831_123045_123456.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["format"] == "windows-resurface-monitor-rules"
    assert payload["version"] == 1
    assert payload["rules"][0]["name"] == "Discord"


def test_repository_imports_rules_and_rejects_an_invalid_backup(tmp_path):
    repository = MonitorRulesRepository()
    valid_path = tmp_path / "valid.json"
    valid_path.write_text(json.dumps({"rules": [make_rule()]}), encoding="utf-8")

    assert repository.import_rules(valid_path)[0]["id"] == "one"

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps({"items": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a monitor rules backup"):
        repository.import_rules(invalid_path)


def test_repository_requires_a_master_backup_path():
    repository = MonitorRulesRepository()

    with pytest.raises(ValueError, match="Master Backup Path"):
        repository.export_rules([make_rule()])

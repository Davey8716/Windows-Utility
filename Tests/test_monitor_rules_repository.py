import json
import copy
from datetime import datetime
from pathlib import Path

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


def test_unchanged_exports_are_skipped_after_restart(tmp_path):
    repository = MonitorRulesRepository(lambda: str(tmp_path))
    rules = [make_rule()]
    path = repository.export_rules(rules)
    original = path.read_bytes()
    restarted = MonitorRulesRepository(lambda: str(tmp_path))
    rules[0]["name"] = "  Discord  "
    assert not restarted.has_export_changes(rules)
    assert restarted.export_rules(rules) is None
    assert list(path.parent.iterdir()) == [path]
    assert path.read_bytes() == original


@pytest.mark.parametrize("change", ["add", "edit", "toggle", "delete", "reorder"])
def test_rule_changes_create_a_new_export(tmp_path, change):
    repository = MonitorRulesRepository(lambda: str(tmp_path))
    rules = [make_rule(), make_rule("two", "Second")]
    first = repository.export_rules(rules)
    changed = copy.deepcopy(rules)
    if change == "add":
        changed.append(make_rule("three", "Third"))
    elif change == "edit":
        changed[0]["title_contains"] = "New title"
    elif change == "toggle":
        changed[0]["enabled"] = False
    elif change == "delete":
        changed.pop()
    else:
        changed.reverse()
    assert repository.has_export_changes(changed)
    second = repository.export_rules(changed)
    assert second is not None and second != first
    assert repository.export_rules(changed) is None
    # Reverting to an older historical export still constitutes a change.
    assert repository.has_export_changes(rules)
    assert repository.export_rules(rules) is not None


def test_reverting_unsaved_changes_skips_export(tmp_path):
    repository = MonitorRulesRepository(lambda: str(tmp_path))
    rules = [make_rule()]
    repository.export_rules(rules)
    rules[0]["enabled"] = False
    assert repository.has_export_changes(rules)
    rules[0]["enabled"] = True
    assert repository.export_rules(rules) is None


def test_export_baseline_follows_destination_and_existing_files(tmp_path):
    destination = tmp_path / "first"
    repository = MonitorRulesRepository(lambda: str(destination))
    rules = [make_rule()]
    first = repository.export_rules(rules)
    destination = tmp_path / "second"
    assert repository.export_rules(rules) is not None
    destination = tmp_path / "first"
    assert repository.export_rules(rules) is None
    first.unlink()
    assert repository.export_rules(rules) is not None


@pytest.mark.parametrize("invalid", [
    "{broken", "[]", '\u007b"rules": []}',
    json.dumps({"format": "other", "version": 1, "rules": []}),
    json.dumps({"format": "windows-resurface-monitor-rules", "version": 2, "rules": []}),
    json.dumps({"format": "windows-resurface-monitor-rules", "version": 1, "rules": [{}]}),
    json.dumps({"format": "windows-resurface-monitor-rules", "version": 1, "rules": "invalid"}),
])
def test_invalid_newer_backups_are_ignored(tmp_path, invalid):
    repository = MonitorRulesRepository(lambda: str(tmp_path))
    rules = [make_rule()]
    valid = repository.export_rules(rules)
    bad = valid.parent / "monitor_rules_99990101_000000_000000.json"
    bad.write_text(invalid, encoding="utf-8")
    assert repository.export_rules(rules) is None
    valid.unlink()
    assert repository.export_rules(rules) is not None


def test_safety_backups_always_save_and_do_not_set_regular_baseline(tmp_path):
    repository = MonitorRulesRepository(lambda: str(tmp_path))
    rules = [make_rule()]
    assert repository.export_rules(rules, safety_backup=True) is not None
    assert repository.export_rules(rules) is not None
    assert repository.export_rules(rules, safety_backup=True) is not None
    rules[0]["enabled"] = False
    assert repository.export_rules(rules, safety_backup=True) is not None
    assert repository.has_export_changes(rules)
    rules[0]["enabled"] = True
    assert repository.export_rules(rules) is None


def test_failed_export_does_not_advance_baseline(monkeypatch, tmp_path):
    repository = MonitorRulesRepository(lambda: str(tmp_path))
    rules = [make_rule()]
    repository.export_rules(rules)
    rules[0]["name"] = "Changed"
    with monkeypatch.context() as patch:
        def fail_write(*args, **kwargs):
            raise OSError("Write failed")
        patch.setattr(Path, "write_text", fail_write)
        with pytest.raises(OSError, match="Write failed"):
            repository.export_rules(rules)
    assert repository.has_export_changes(rules)
    assert repository.export_rules(rules) is not None

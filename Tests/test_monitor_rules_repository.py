import json
import copy
from pathlib import Path

import pytest

from resurface.features.monitor_rules import MonitorRulesRepository, normalize_monitor_rules
from test_monitor_rules_ui import make_rule


def test_repository_exports_versioned_normalized_backup(tmp_path):
    repository = MonitorRulesRepository(lambda: str(tmp_path))

    legacy_rule = make_rule()
    legacy_rule.update(title_contains="Friends", class_name="LegacyClass")
    path = repository.export_rules([legacy_rule])

    assert path == (
        tmp_path / "Monitor Rules" / "monitor_rules.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["format"] == "windows-resurface-monitor-rules"
    assert payload["version"] == 1
    assert payload["rules"][0]["name"] == "Discord"
    assert "title_contains" not in payload["rules"][0]
    assert "class_name" not in payload["rules"][0]


def test_repository_imports_rules_and_rejects_an_invalid_backup(tmp_path):
    repository = MonitorRulesRepository()
    valid_path = tmp_path / "valid.json"
    valid_path.write_text(json.dumps({"rules": [make_rule()]}), encoding="utf-8")

    assert repository.import_rules(valid_path)[0]["id"] == "one"

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps({"items": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a monitor rules backup"):
        repository.import_rules(invalid_path)


def test_repository_imports_legacy_filters_without_preserving_them(tmp_path):
    repository = MonitorRulesRepository()
    legacy_rule = make_rule()
    legacy_rule.update(title_contains="Friends", class_name="LegacyClass")
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"rules": [legacy_rule]}), encoding="utf-8")

    imported = repository.import_rules(path)

    assert "title_contains" not in imported[0]
    assert "class_name" not in imported[0]


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
def test_rule_changes_overwrite_the_current_export(tmp_path, change):
    repository = MonitorRulesRepository(lambda: str(tmp_path))
    rules = [make_rule(), make_rule("two", "Second")]
    first = repository.export_rules(rules)
    changed = copy.deepcopy(rules)
    if change == "add":
        changed.append(make_rule("three", "Third"))
    elif change == "edit":
        changed[0]["name"] = "New name"
    elif change == "toggle":
        changed[0]["enabled"] = False
    elif change == "delete":
        changed.pop()
    else:
        changed.reverse()
    assert repository.has_export_changes(changed)
    second = repository.export_rules(changed)
    assert second == first
    assert repository.export_rules(changed) is None
    # Reverting the current backup still constitutes a change.
    assert repository.has_export_changes(rules)
    assert repository.export_rules(rules) == first
    assert list(first.parent.glob("*.json")) == [first]


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
def test_invalid_current_backup_is_replaced(tmp_path, invalid):
    repository = MonitorRulesRepository(lambda: str(tmp_path))
    rules = [make_rule()]
    valid = repository.export_rules(rules)
    valid.write_text(invalid, encoding="utf-8")
    assert repository.export_rules(rules) == valid
    assert json.loads(valid.read_text(encoding="utf-8"))["rules"] == normalize_monitor_rules(rules)


def test_export_removes_legacy_app_backups_but_preserves_user_json(tmp_path):
    repository = MonitorRulesRepository(lambda: str(tmp_path))
    rules = [make_rule()]
    directory = tmp_path / "Monitor Rules"
    directory.mkdir()
    legacy = directory / "monitor_rules_20260831_123045_123456.json"
    legacy.write_text(json.dumps({"rules": rules}), encoding="utf-8")
    safety = directory / "monitor_rules_before_delete_20260831_123045_123456.json"
    safety.write_text(json.dumps({"rules": rules}), encoding="utf-8")
    user_file = directory / "import.json"
    user_file.write_text(json.dumps({"rules": rules}), encoding="utf-8")

    current = repository.export_rules(rules)

    assert current == directory / "monitor_rules.json"
    assert list(directory.glob("monitor_rules*.json")) == [current]
    assert user_file.exists()


def test_unchanged_export_cleans_up_legacy_app_backups(tmp_path):
    repository = MonitorRulesRepository(lambda: str(tmp_path))
    rules = [make_rule()]
    current = repository.export_rules(rules)
    legacy = current.parent / "monitor_rules_20260831_123045_123456.json"
    legacy.write_text(json.dumps({"rules": rules}), encoding="utf-8")

    assert repository.has_export_changes(rules)
    assert repository.export_rules(rules) == current
    assert list(current.parent.glob("monitor_rules*.json")) == [current]


def test_failed_export_does_not_advance_baseline(monkeypatch, tmp_path):
    repository = MonitorRulesRepository(lambda: str(tmp_path))
    rules = [make_rule()]
    current = repository.export_rules(rules)
    legacy = current.parent / "monitor_rules_20260831_123045_123456.json"
    legacy.write_text(json.dumps({"rules": rules}), encoding="utf-8")
    original = current.read_bytes()
    rules[0]["name"] = "Changed"
    with monkeypatch.context() as patch:
        def fail_write(*args, **kwargs):
            raise OSError("Write failed")
        patch.setattr(Path, "write_text", fail_write)
        with pytest.raises(OSError, match="Write failed"):
            repository.export_rules(rules)
    assert repository.has_export_changes(rules)
    assert current.read_bytes() == original
    assert legacy.exists()
    assert repository.export_rules(rules) is not None


def test_import_baseline_survives_restart_and_tracks_edits(tmp_path):
    state = {}
    def repository():
        return MonitorRulesRepository(
            lambda: str(tmp_path),
            get_import_baseline=lambda: state.get("baseline"),
            set_import_baseline=lambda value: state.update(baseline=value),
        )
    source = tmp_path / "import.json"
    rules = [make_rule()]
    source.write_text(json.dumps({"rules": rules}), encoding="utf-8")
    repo = repository()
    repo.record_import(source, repo.import_rules(source))
    state = json.loads(json.dumps(state))
    restarted = repository()
    assert not restarted.has_export_changes(rules)
    assert restarted.export_rules(rules) is None
    rules[0]["enabled"] = False
    assert restarted.has_export_changes(rules)
    rules[0]["enabled"] = True
    assert not restarted.has_export_changes(rules)
    assert not (tmp_path / "Monitor Rules").exists()


@pytest.mark.parametrize("invalidate", ["delete", "edit", "malformed", "destination"])
def test_invalid_import_baseline_falls_back_to_regular_export(tmp_path, invalidate):
    destination = tmp_path
    repo = MonitorRulesRepository(lambda: str(destination))
    original = [make_rule()]
    repo.export_rules(original)
    imported = [make_rule("imported", "Imported")]
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"rules": imported}), encoding="utf-8")
    repo.record_import(source, imported)
    assert not repo.has_export_changes(imported)
    if invalidate == "delete":
        source.unlink()
    elif invalidate == "edit":
        source.write_text(json.dumps({"rules": original}), encoding="utf-8")
    elif invalidate == "malformed":
        source.write_text("broken", encoding="utf-8")
    else:
        destination = tmp_path / "new"
    assert repo.has_export_changes(imported)
    assert repo.has_export_changes(original) == (invalidate == "destination")


def test_regular_export_supersedes_import_baseline(tmp_path):
    state = {}
    repo = MonitorRulesRepository(
        lambda: str(tmp_path),
        get_import_baseline=lambda: state.get("baseline"),
        set_import_baseline=lambda value: state.update(baseline=value),
    )
    rules = [make_rule()]
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"rules": rules}), encoding="utf-8")
    repo.record_import(source, rules)
    rules[0]["name"] = "Edited"
    assert repo.export_rules(rules) is not None
    assert state["baseline"] is None
    assert not repo.has_export_changes(rules)
    assert repo.has_export_changes([make_rule()])

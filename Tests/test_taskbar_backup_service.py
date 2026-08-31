from pathlib import Path

from resurface.features.taskbar.backup_service import TaskbarBackupService


def test_backup_copies_only_shortcuts(tmp_path, monkeypatch):
    source = tmp_path / "pinned"
    source.mkdir()
    (source / "One.lnk").write_text("one")
    (source / "Two.LNK").write_text("two")
    (source / "ignore.txt").write_text("ignore")
    destination = tmp_path / "backup"
    service = TaskbarBackupService()
    monkeypatch.setattr(service, "pinned_shortcuts_path", lambda: str(source))
    assert service.backup_pinned_shortcuts(str(destination)) == 2
    assert sorted(path.name for path in destination.iterdir()) == ["One.lnk", "Two.LNK"]


def test_backup_returns_zero_when_source_is_missing(tmp_path, monkeypatch):
    service = TaskbarBackupService()
    monkeypatch.setattr(service, "pinned_shortcuts_path", lambda: str(tmp_path / "missing"))
    assert service.backup_pinned_shortcuts(str(tmp_path / "backup")) == 0

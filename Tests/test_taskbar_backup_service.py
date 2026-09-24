from pathlib import Path

import resurface.features.taskbar.backup_service as backup_service

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


def test_backup_removes_shortcuts_no_longer_pinned(tmp_path, monkeypatch):
    source = tmp_path / "pinned"
    source.mkdir()
    (source / "Current.lnk").write_text("current")
    destination = tmp_path / "backup"
    destination.mkdir()
    (destination / "Current.lnk").write_text("old current")
    (destination / "Removed.LNK").write_text("removed")
    service = TaskbarBackupService()
    monkeypatch.setattr(service, "pinned_shortcuts_path", lambda: str(source))

    assert service.backup_pinned_shortcuts(str(destination)) == 1

    assert (destination / "Current.lnk").read_text() == "current"
    assert not (destination / "Removed.LNK").exists()


def test_backup_removes_all_shortcuts_when_no_apps_are_pinned(tmp_path, monkeypatch):
    source = tmp_path / "pinned"
    source.mkdir()
    destination = tmp_path / "backup"
    destination.mkdir()
    (destination / "Removed.lnk").write_text("removed")
    service = TaskbarBackupService()
    monkeypatch.setattr(service, "pinned_shortcuts_path", lambda: str(source))

    assert service.backup_pinned_shortcuts(str(destination)) == 0

    assert not (destination / "Removed.lnk").exists()


def test_backup_preserves_non_shortcut_backup_contents(tmp_path, monkeypatch):
    source = tmp_path / "pinned"
    source.mkdir()
    destination = tmp_path / "backup"
    destination.mkdir()
    note = destination / "note.txt"
    note.write_text("keep")
    folder = destination / "keep-folder"
    folder.mkdir()
    (folder / "content.txt").write_text("keep")
    service = TaskbarBackupService()
    monkeypatch.setattr(service, "pinned_shortcuts_path", lambda: str(source))

    service.backup_pinned_shortcuts(str(destination))

    assert note.read_text() == "keep"
    assert (folder / "content.txt").read_text() == "keep"


def test_backup_keeps_stale_shortcuts_when_copy_fails(tmp_path, monkeypatch):
    source = tmp_path / "pinned"
    source.mkdir()
    current = source / "Current.lnk"
    current.write_text("current")
    destination = tmp_path / "backup"
    destination.mkdir()
    stale = destination / "Removed.lnk"
    stale.write_text("removed")
    service = TaskbarBackupService()
    monkeypatch.setattr(service, "pinned_shortcuts_path", lambda: str(source))

    def fail_copy(source_path, destination_path):
        if Path(source_path) == current:
            raise OSError("copy failed")
        raise AssertionError("Unexpected shortcut copy")

    monkeypatch.setattr(backup_service.shutil, "copy2", fail_copy)

    assert service.backup_pinned_shortcuts(str(destination)) == 0
    assert stale.read_text() == "removed"

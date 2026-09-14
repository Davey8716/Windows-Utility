from pathlib import Path
from types import SimpleNamespace

from resurface.core.app_paths import MasterBackupPathsMixin


class _Owner(MasterBackupPathsMixin):
    def __init__(self, path: Path):
        self.state = {"master_backup_output_path": str(path)}
        self.pages = SimpleNamespace(
            monitor_rules_page=None,
            organising_utilities_page=None,
        )
        self.messages = []
        self.saved_states = []

    def _get_app_module_attr(self, name, default):
        if name == "save_state":
            return lambda state: self.saved_states.append(dict(state))
        return default

    def _message_box_icon(self, name):
        return name

    def _message_box_button(self, name):
        return name

    def _show_modal_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))


def test_selecting_desktop_creates_dedicated_folder_and_moves_managed_data(
    tmp_path, monkeypatch
):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    managed = desktop / "TaskBarApps"
    managed.mkdir()
    (managed / "shortcut.lnk").write_text("shortcut", encoding="utf-8")
    unrelated = desktop / "notes.txt"
    unrelated.write_text("keep", encoding="utf-8")
    owner = _Owner(desktop)
    monkeypatch.setattr(owner, "_desktop_directory", lambda: desktop)
    watcher_updates = []
    monkeypatch.setattr(
        owner, "_watch_master_backup_path", lambda: watcher_updates.append(True)
    )

    owner._set_master_backup_dir(str(desktop))

    destination = desktop / "Windows Resurface Backup"
    assert destination.is_dir()
    assert owner.state["master_backup_output_path"] == str(destination)
    assert (destination / "TaskBarApps" / "shortcut.lnk").read_text(
        encoding="utf-8"
    ) == "shortcut"
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert watcher_updates == [True]
    assert owner.messages == []


def test_only_the_dedicated_desktop_child_is_allowed_inside_the_old_path(
    tmp_path, monkeypatch
):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    owner = _Owner(desktop)
    monkeypatch.setattr(owner, "_desktop_directory", lambda: desktop)

    owner._validate_backup_relocation(
        desktop,
        desktop / "Windows Resurface Backup",
    )

    nested = desktop / "another-child"
    try:
        owner._validate_backup_relocation(desktop, nested)
    except OSError as error:
        assert "cannot be inside" in str(error)
    else:
        raise AssertionError("Unexpectedly allowed a non-dedicated nested path")


def test_default_home_root_can_migrate_to_the_desktop_backup_child(
    tmp_path, monkeypatch
):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    owner = _Owner(Path.home())
    monkeypatch.setattr(owner, "_desktop_directory", lambda: desktop)

    assert owner._is_allowed_desktop_migration(
        Path.home().resolve(strict=False),
        desktop / "Windows Resurface Backup",
    )


def test_selecting_desktop_moves_the_previous_plural_desktop_folder(
    tmp_path, monkeypatch
):
    desktop = tmp_path / "Desktop"
    legacy = desktop / "Windows Resurface Backups" / "Desktop Icon Layout"
    legacy.mkdir(parents=True)
    (legacy / "desktop_icon_layout.json").write_text("layout", encoding="utf-8")
    owner = _Owner(desktop)
    monkeypatch.setattr(owner, "_desktop_directory", lambda: desktop)

    owner._set_master_backup_dir(str(desktop))

    destination = (
        desktop
        / "Windows Resurface Backup"
        / "Desktop Icon Layout"
        / "desktop_icon_layout.json"
    )
    assert destination.read_text(encoding="utf-8") == "layout"
    assert not (desktop / "Windows Resurface Backups").exists()


def test_legacy_desktop_setting_is_upgraded_without_reselecting_desktop(
    tmp_path, monkeypatch
):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    owner = _Owner(desktop)
    monkeypatch.setattr(owner, "_desktop_directory", lambda: desktop)

    owner._migrate_desktop_master_backup_path()

    assert owner.state["master_backup_output_path"] == str(
        desktop / "Windows Resurface Backup"
    )


def test_master_backup_relocation_error_uses_sized_rounded_theme_popup(tmp_path):
    old_root = tmp_path / "old"
    owner = _Owner(old_root)

    owner._set_master_backup_dir(str(old_root / "nested"))

    args, kwargs = owner.messages[0]
    assert args[:2] == ("Critical", "Master Backup Path")
    assert "cannot be inside" in args[2]
    assert kwargs == {
        "fixed_popup_width": 540,
        "text_block_width": 460,
        "popup_corner_radius": 6,
    }

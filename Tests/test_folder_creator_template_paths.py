import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FOLDER_CREATOR_DIR = PROJECT_ROOT / "Code Folder Creator"
sys.path.insert(0, str(FOLDER_CREATOR_DIR))

from folder_creator.features.templates.template_IO_layer import TemplatePaths  # noqa: E402


def test_template_paths_use_master_backup_location_and_preserve_legacy_files(
    tmp_path, monkeypatch
):
    master_root = tmp_path / "master"
    local_app_data = tmp_path / "local-app-data"
    legacy_default = local_app_data / "FolderCreator" / "default_templates"
    legacy_user = local_app_data / "FolderCreator" / "user_templates"
    legacy_default.mkdir(parents=True)
    legacy_user.mkdir()
    (legacy_default / "legacy-default.txt").write_text("legacy default", encoding="utf-8")
    (legacy_user / "legacy-user.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    paths = TemplatePaths({"master_backup_output_path": str(master_root)})

    assert paths.available
    assert paths.root_dir == master_root / "Folder Creator Templates"
    assert paths.default_dir == paths.root_dir / "default_templates"
    assert paths.user_dir == paths.root_dir / "user_templates"
    assert (paths.default_dir / "legacy-default.txt").read_text(encoding="utf-8") == "legacy default"
    assert (paths.user_dir / "legacy-user.json").read_text(encoding="utf-8") == "{}"
    assert (legacy_user / "legacy-user.json").exists()


def test_legacy_migration_never_overwrites_master_templates(tmp_path, monkeypatch):
    master_root = tmp_path / "master"
    local_app_data = tmp_path / "local-app-data"
    legacy_user = local_app_data / "FolderCreator" / "user_templates"
    legacy_user.mkdir(parents=True)
    (legacy_user / "existing.json").write_text('{"source": "legacy"}', encoding="utf-8")
    destination = master_root / "Folder Creator Templates" / "user_templates"
    destination.mkdir(parents=True)
    (destination / "existing.json").write_text('{"source": "master"}', encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    TemplatePaths({"master_backup_output_path": str(master_root)})

    assert (destination / "existing.json").read_text(encoding="utf-8") == '{"source": "master"}'


def test_bundled_defaults_fill_only_missing_files(tmp_path, monkeypatch):
    master_root = tmp_path / "master"
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "existing.txt").write_text("bundle", encoding="utf-8")
    (bundle_dir / "missing.txt").write_text("new", encoding="utf-8")
    destination = master_root / "Folder Creator Templates" / "default_templates"
    destination.mkdir(parents=True)
    (destination / "existing.txt").write_text("custom", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    paths = TemplatePaths({"master_backup_output_path": str(master_root)})
    paths.bundle_dir = bundle_dir
    TemplatePaths._ensure_templates(paths)

    assert (destination / "existing.txt").read_text(encoding="utf-8") == "custom"
    assert (destination / "missing.txt").read_text(encoding="utf-8") == "new"


def test_unavailable_master_backup_does_not_create_template_fallback(tmp_path, monkeypatch):
    local_app_data = tmp_path / "local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    paths = TemplatePaths(
        {"master_backup_output_path": str(tmp_path / "missing"), "master_backup_path_unavailable": True}
    )

    assert not paths.available
    assert paths.root_dir is None
    assert paths.default_dir is None
    assert paths.user_dir is None
    assert not (local_app_data / "FolderCreator").exists()

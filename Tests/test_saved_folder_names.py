import json
from pathlib import Path

from resurface.core.saved_folder_names import MAX_SAVED_NAMES, add_saved_folder_name, load_saved_folder_names
from resurface.features.desktop import desktop_operations
from resurface.features.desktop.desktop_operations import DesktopOperationsMixin


def test_missing_and_malformed_saved_name_files_are_empty(tmp_path):
    path = tmp_path / "saved_folder_names.json"
    assert load_saved_folder_names(path) == []
    path.write_text("not json", encoding="utf-8")
    assert load_saved_folder_names(path) == []
    path.write_text(json.dumps({"folder_names": ["Reports"]}), encoding="utf-8")
    assert load_saved_folder_names(path) == []


def test_add_saved_name_is_recent_unique_case_insensitive_and_capped(tmp_path):
    path = tmp_path / "saved_folder_names.json"
    for index in range(MAX_SAVED_NAMES + 2):
        add_saved_folder_name(f"Folder {index}", path)
    names = add_saved_folder_name("FOLDER 10", path)
    assert names[0] == "FOLDER 10"
    assert len(names) == MAX_SAVED_NAMES
    assert sum(name.casefold() == "folder 10" for name in names) == 1
    assert load_saved_folder_names(path) == names
    assert not list(tmp_path.glob("*.tmp"))


def test_invalid_entries_are_filtered_when_loaded(tmp_path):
    path = tmp_path / "saved_folder_names.json"
    path.write_text(json.dumps([" Reports ", 7, "", "reports", None, "Invoices"]), encoding="utf-8")
    assert load_saved_folder_names(path) == ["Reports", "Invoices"]


class _Input:
    def __init__(self, text): self.value = text
    def text(self): return self.value
    def clear(self): self.value = ""


class _Toggle:
    def __init__(self, checked): self.checked = checked
    def isChecked(self): return self.checked
    def setChecked(self, checked): self.checked = checked


class _DesktopHarness(DesktopOperationsMixin):
    def __init__(self, save_enabled):
        self.state = {}
        self.save_folder_name_toggle = _Toggle(save_enabled)
        self.refreshed = None
        self.messages = []
    def refresh_saved_folder_names(self, names): self.refreshed = names
    def _run_with_optional_minimize(self, action): action()
    def _show_organizing_timed_message(self, *args, **kwargs): self.messages.append((args, kwargs))
    @staticmethod
    def _message_box_icon(name): return name


def test_successful_creation_saves_when_enabled_and_resets_toggle(monkeypatch, tmp_path):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    harness = _DesktopHarness(True)
    folder_input = _Input(" Reports ")
    saved = []
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(desktop_operations, "add_saved_folder_name", lambda name: saved.append(name) or [name])
    harness._create_desktop_folder(folder_input)
    assert (desktop / "Reports").is_dir()
    assert saved == ["Reports"]
    assert harness.refreshed == ["Reports"]
    assert harness.save_folder_name_toggle.checked is False
    assert folder_input.text() == ""


def test_existing_folder_does_not_save_or_reset_input(monkeypatch, tmp_path):
    desktop = tmp_path / "Desktop"
    (desktop / "Reports").mkdir(parents=True)
    harness = _DesktopHarness(True)
    folder_input = _Input("Reports")
    save_calls = []
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(desktop_operations, "add_saved_folder_name", lambda name: save_calls.append(name))
    harness._create_desktop_folder(folder_input)
    assert save_calls == []
    assert harness.save_folder_name_toggle.checked is True
    assert folder_input.text() == "Reports"

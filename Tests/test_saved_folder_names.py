import json
from pathlib import Path

from resurface.core.saved_folder_names import MAX_SAVED_NAMES, add_saved_folder_name, load_saved_folder_names
from resurface.features.desktop.folder_service import DesktopFolderService
from resurface.ui.controllers import folder_actions
from resurface.ui.controllers.folder_actions import FolderActionsController


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
    assert names[0] == "FOLDER 10" and len(names) == MAX_SAVED_NAMES
    assert sum(name.casefold() == "folder 10" for name in names) == 1
    assert load_saved_folder_names(path) == names


def test_invalid_entries_are_filtered_when_loaded(tmp_path):
    path = tmp_path / "saved_folder_names.json"
    path.write_text(json.dumps([" Reports ", 7, "", "reports", None, "Invoices"]), encoding="utf-8")
    assert load_saved_folder_names(path) == ["Reports", "Invoices"]


class Input:
    def __init__(self, text): self.value = text
    def text(self): return self.value
    def clear(self): self.value = ""


class Toggle:
    def __init__(self, checked): self.checked = checked
    def isChecked(self): return self.checked
    def setChecked(self, checked): self.checked = checked


class OrganisingStub:
    def __init__(self): self.messages = []
    def run_with_optional_minimize(self, action): action()
    def show_timed_message(self, *args, **kwargs): self.messages.append((args, kwargs))


class App:
    def __init__(self, save_enabled):
        self.save_folder_name_toggle = Toggle(save_enabled)
        self.refreshed = None
    def refresh_saved_folder_names(self, names): self.refreshed = names
    @staticmethod
    def _message_box_icon(name): return name


def make_controller(save_enabled):
    app = App(save_enabled)
    return app, FolderActionsController(app, DesktopFolderService(), None, OrganisingStub())


def test_successful_creation_saves_when_enabled_and_resets_toggle(monkeypatch, tmp_path):
    (tmp_path / "Desktop").mkdir()
    app, controller = make_controller(True)
    input_widget = Input(" Reports ")
    saved = []
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(folder_actions, "add_saved_folder_name", lambda name: saved.append(name) or [name])
    controller.create_desktop_folder(input_widget)
    assert (tmp_path / "Desktop" / "Reports").is_dir()
    assert saved == ["Reports"] and app.refreshed == ["Reports"]
    assert app.save_folder_name_toggle.checked is False and input_widget.text() == ""


def test_existing_folder_does_not_save_or_reset_input(monkeypatch, tmp_path):
    (tmp_path / "Desktop" / "Reports").mkdir(parents=True)
    app, controller = make_controller(True)
    input_widget = Input("Reports")
    calls = []
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(folder_actions, "add_saved_folder_name", lambda name: calls.append(name))
    controller.create_desktop_folder(input_widget)
    assert calls == [] and app.save_folder_name_toggle.checked is True
    assert input_widget.text() == "Reports"

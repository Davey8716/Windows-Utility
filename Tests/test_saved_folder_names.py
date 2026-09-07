import json
from pathlib import Path

from resurface.core.saved_folder_names import (
    MAX_SAVED_NAMES,
    add_saved_folder_name,
    load_saved_folder_names,
    remove_saved_folder_name,
)
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


def test_remove_saved_name_is_case_insensitive_and_persisted(tmp_path):
    path = tmp_path / "saved_folder_names.json"
    path.write_text(json.dumps(["Reports", "Invoices"]), encoding="utf-8")
    assert remove_saved_folder_name(" reports ", path) == ["Invoices"]
    assert load_saved_folder_names(path) == ["Invoices"]


def test_remove_blank_or_unknown_saved_name_leaves_storage_unchanged(tmp_path):
    path = tmp_path / "saved_folder_names.json"
    path.write_text(json.dumps(["Reports"]), encoding="utf-8")
    assert remove_saved_folder_name("  ", path) == ["Reports"]
    assert remove_saved_folder_name("Invoices", path) == ["Reports"]
    assert load_saved_folder_names(path) == ["Reports"]


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


class DeletePage:
    def __init__(self):
        self.deleted = None
        self.saved = None
    def folder_name_deleted(self, names): self.deleted = names
    def folder_name_saved(self, names, name): self.saved = (names, name)


class DeleteApp:
    def __init__(self, answer):
        self.answer = answer
        self.modal_args = None
        self.pages = type("Pages", (), {"folder_utilities_page": DeletePage()})()
    @staticmethod
    def _message_box_icon(name): return name
    @staticmethod
    def _message_box_button(name): return {"Yes": 1, "No": 2}[name]
    def _show_modal_message(self, *args):
        self.modal_args = args
        return self.answer


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


def test_delete_saved_name_confirms_with_yes_no_and_refreshes(monkeypatch):
    app = DeleteApp(answer=1)
    controller = FolderActionsController(app, None, None, OrganisingStub())
    monkeypatch.setattr(folder_actions, "load_saved_folder_names", lambda: ["Reports", "Invoices"])
    monkeypatch.setattr(folder_actions, "remove_saved_folder_name", lambda name: ["Invoices"])

    controller.delete_saved_folder_name(" reports ")

    assert app.modal_args[1:3] == (
        "Delete Saved Folder Name",
        'Delete the saved folder name "Reports"?',
    )
    assert app.modal_args[3:] == (1 | 2, 2)
    assert app.pages.folder_utilities_page.deleted == ["Invoices"]


def test_delete_saved_name_no_or_unknown_preserves_entries(monkeypatch):
    app = DeleteApp(answer=2)
    controller = FolderActionsController(app, None, None, OrganisingStub())
    removed = []
    monkeypatch.setattr(folder_actions, "load_saved_folder_names", lambda: ["Reports"])
    monkeypatch.setattr(folder_actions, "remove_saved_folder_name", lambda name: removed.append(name))

    controller.delete_saved_folder_name("Reports")
    controller.delete_saved_folder_name("Unknown")

    assert removed == []
    assert app.pages.folder_utilities_page.deleted is None


def test_save_folder_name_persists_immediately_and_refreshes_page(monkeypatch):
    app = DeleteApp(answer=2)
    controller = FolderActionsController(app, None, None, OrganisingStub())
    saved = []
    monkeypatch.setattr(
        folder_actions,
        "add_saved_folder_name",
        lambda name: saved.append(name) or [name, "Invoices"],
    )

    controller.save_folder_name(" Reports ")

    assert saved == ["Reports"]
    assert app.pages.folder_utilities_page.saved == (
        ["Reports", "Invoices"],
        "Reports",
    )

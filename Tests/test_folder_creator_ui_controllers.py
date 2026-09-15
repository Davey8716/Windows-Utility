import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FOLDER_CREATOR_DIR = PROJECT_ROOT / "Code Folder Creator"
sys.path.insert(0, str(FOLDER_CREATOR_DIR))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from folder_creator.ui.build_controller import BuildController  # noqa: E402
from folder_creator.ui import build_controller as build_module  # noqa: E402
from folder_creator.ui.nested_ui_controller import NestedUIController  # noqa: E402
from folder_creator.ui.output_location_controller import (  # noqa: E402
    OutputLocationController,
)
from folder_creator.ui import output_location_controller as output_module  # noqa: E402
from folder_creator.ui import styles as folder_styles  # noqa: E402
from folder_creator.ui.status_controller import StatusController  # noqa: E402
from folder_creator.ui.template_controller import TemplateController  # noqa: E402
from folder_creator.ui import template_controller as template_controller_module  # noqa: E402
from folder_creator.ui.template_load_dialog import TemplateLoadDialog  # noqa: E402
from folder_creator.ui.template_save_dialog import TemplateSaveDialog  # noqa: E402
from folder_creator.ui.output_directory_dialog import OutputDirectoryDialog  # noqa: E402
from PySide6.QtCore import Qt, Signal  # noqa: E402
from resurface.ui.app_notifications import WindowMessageMixin  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QLineEdit,
    QLabel,
    QDialogButtonBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TreeWidget(QTreeWidget):
    fileDropped = Signal(str)
    loadTemplateShortcut = Signal()
    addFolderShortcut = Signal()
    addSubfolderShortcut = Signal()
    saveTemplateShortcut = Signal()


class CallRecorder:
    def __init__(self):
        self.calls = []
        self.find_calls = []

    def set(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    def show_find_result(self, *args, **kwargs):
        self.find_calls.append((args, kwargs))

    def show_template_loaded(self):
        self.calls.append((("Template loaded",), {"themed": True}))


class UIStateStub:
    def __init__(self):
        self.build_updates = 0
        self.nested_updates = 0

    def update_build_button_state(self):
        self.build_updates += 1

    def update_nested_build_state(self):
        self.nested_updates += 1


class StateManagerStub:
    def __init__(self):
        self.updates = []

    def update(self, key, value):
        self.updates.append((key, value))


class TreeControllerStub:
    def __init__(self):
        self.deserialize_calls = []
        self.remove_calls = 0
        self.auto_number_enabled = False

    def deserialize_tree(self, data, **kwargs):
        self.deserialize_calls.append((data, kwargs))

    def serialize_tree(self):
        return [{"name": "Project", "children": []}]

    def expand_all_animated(self):
        pass

    def remove_all_folders(self):
        self.remove_calls += 1

    def sort_tree(self):
        pass

    def renumber_loaded_tree(self):
        pass

    def add_root_folder(self):
        pass

    def add_subfolder(self):
        pass

    def remove_selected_folders(self):
        pass

    def add_file(self, _filename):
        pass


def make_window(tmp_path):
    user_dir = tmp_path / "user"
    default_dir = tmp_path / "default"
    user_dir.mkdir()
    default_dir.mkdir()

    tree_controller = TreeControllerStub()
    state_manager = StateManagerStub()
    service = SimpleNamespace(
        template_paths=SimpleNamespace(user_dir=user_dir, default_dir=default_dir),
        tree_controller=tree_controller,
        state_manager=state_manager,
        set_state=lambda key, value: state_manager.update(key, value),
    )
    window = SimpleNamespace(
        service=service,
        tree=TreeWidget(),
        status=CallRecorder(),
        ui_state=UIStateStub(),
        load_user_template_dropdown=QComboBox(),
        load_default_template_dropdown=QComboBox(),
        auto_enumerate_folders=QCheckBox(),
        template_path_line=QLineEdit(),
        base_path_line=QLineEdit(),
        find_output_line=QLineEdit(),
        nested_date_toggle=QCheckBox(),
        nested_date_config=QComboBox(),
        open_folder_build_toggle=QCheckBox(),
        minimize_after_build_toggle=QCheckBox(),
        close_app_after_build_toggle=QCheckBox(),
        load_template_btn=QPushButton(),
        save_template_btn=QPushButton(),
        delete_template_btn=QPushButton(),
        add_folder_btn=QPushButton(),
        add_subfolder_btn=QPushButton(),
        remove_btn=QPushButton(),
        sort_btn=QPushButton(),
        find_btn=QPushButton(),
        expand_tree_btn=QPushButton(),
        expand_folders_collapse_btn=QPushButton(),
        remove_all_btn=QPushButton(),
        build_folders_btn=QPushButton(),
        output_location_btn=QPushButton(),
        default_to_desktop_btn=QPushButton(),
        file_dropdown=QComboBox(),
        update_build_button_state=lambda: None,
        update_expand_button_text=lambda: None,
        enforce_tree_name_limit=lambda *_args: None,
        tree_gui_stretch=lambda: None,
        toggle_tree_expand=lambda: None,
    )
    window.load_user_template_dropdown.addItems(["User Templates", "Custom"])
    window.load_default_template_dropdown.addItems(
        ["Default Templates", "Sample"]
    )
    window.nested_date_config.addItems(["ISO", "UK", "US"])
    return window


def test_find_outcomes_use_the_find_specific_timed_popup(qapp, tmp_path):
    window = make_window(tmp_path)
    controller = NestedUIController(window)

    controller.find_folder_in_tree()
    window.find_output_line.setText("Project")
    window.tree.addTopLevelItem(QTreeWidgetItem(["Project"]))
    controller.find_folder_in_tree()
    window.find_output_line.setText("Missing")
    controller.find_folder_in_tree()

    assert window.status.find_calls == [
        (("Enter a folder name to search for.",), {"status_type": "error"}),
        (('Folder "Project" found.',), {"status_type": "success"}),
        (("No matching folder found.",), {"status_type": "error"}),
    ]
    assert window.status.calls == []


def test_find_result_dialog_matches_themed_timed_message_pattern(qapp):
    class Host(WindowMessageMixin, QWidget):
        pass

    host = Host()
    controller = StatusController(host, service=None)
    controller.show_find_result("Folder \"Project\" found.", status_type="success")

    try:
        dialog = host._active_message_boxes[-1]
        text_label = dialog.findChild(QLabel, "qt_msgbox_label")
        button_box = dialog.findChild(QDialogButtonBox)

        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dialog._popup_corner_radius == folder_styles.resurface_styles.BUTTON_CORNER_RADIUS
        assert dialog._close_timer.interval() == 10_000
        assert text_label.alignment() & Qt.AlignmentFlag.AlignHCenter
        assert "This message will disappear in 10 seconds." in text_label.text()
        assert [button.text() for button in button_box.buttons()] == ["Close now"]
        assert button_box.centerButtons()
    finally:
        dialog.close()
        host.deleteLater()


def test_template_loaded_uses_the_shared_timed_popup(qapp, tmp_path, monkeypatch):
    window = make_window(tmp_path)
    (window.service.template_paths.user_dir / "project.json").write_text(
        "[]", encoding="utf-8"
    )
    controller = TemplateController(window)
    monkeypatch.setattr(
        controller,
        "load_template_dialog",
        lambda _parent: ("success", "Template loaded"),
    )

    controller.load_template()

    assert window.status.calls == [(("Template loaded",), {"themed": True})]


def test_selecting_user_templates_clears_tree_without_changing_saved_templates(
    qapp, tmp_path
):
    window = make_window(tmp_path)
    user_template = window.service.template_paths.user_dir / "project.json"
    default_template = window.service.template_paths.default_dir / "sample.txt"
    user_contents = b'{"name": "Project"}'
    default_contents = b"Root\n    Child"
    user_template.write_bytes(user_contents)
    default_template.write_bytes(default_contents)
    window.tree.addTopLevelItem(QTreeWidgetItem(["Project"]))
    window.ui_state.build_updates = 0
    controller = TemplateController(window)
    controller._current_loaded_template = "Project"

    controller.on_user_template_selected(0)

    assert window.tree.topLevelItemCount() == 0
    assert controller._current_loaded_template is None
    assert window.ui_state.build_updates == 1
    assert user_template.read_bytes() == user_contents
    assert default_template.read_bytes() == default_contents


def test_default_template_signal_loads_once_and_resets_user_selection(qapp, tmp_path):
    window = make_window(tmp_path)
    (window.service.template_paths.default_dir / "sample.txt").write_text(
        "Root\n    Child", encoding="utf-8"
    )
    controller = NestedUIController(window)
    controller.connect_signals()

    window.load_user_template_dropdown.setCurrentIndex(1)
    controller.template_controller._loading_template = False
    window.load_default_template_dropdown.setCurrentIndex(1)

    assert window.load_user_template_dropdown.currentIndex() == 0
    assert len(window.service.tree_controller.deserialize_calls) == 1


def test_load_templates_button_invokes_template_loader(qapp, tmp_path):
    window = make_window(tmp_path)
    (window.service.template_paths.user_dir / "project.json").write_text(
        "[]", encoding="utf-8"
    )
    controller = NestedUIController(window)
    calls = []
    controller.template_controller.load_template = lambda: calls.append(True)

    controller.connect_signals()
    window.load_template_btn.click()

    assert calls == [True]


def test_user_template_loading_controls_track_template_files(qapp, tmp_path):
    window = make_window(tmp_path)
    controller = TemplateController(window)

    controller.refresh_user_templates_dropdown()

    assert not window.load_template_btn.isEnabled()
    assert not window.load_user_template_dropdown.isEnabled()

    template = window.service.template_paths.user_dir / "project.json"
    template.write_text("[]", encoding="utf-8")
    controller.refresh_user_templates_dropdown()

    assert window.load_template_btn.isEnabled()
    assert window.load_user_template_dropdown.isEnabled()

    template.unlink()
    controller.refresh_user_templates_dropdown()

    assert not window.load_template_btn.isEnabled()
    assert not window.load_user_template_dropdown.isEnabled()


def test_load_template_shortcut_is_ignored_without_user_templates(
    qapp, tmp_path, monkeypatch
):
    window = make_window(tmp_path)
    controller = TemplateController(window)
    monkeypatch.setattr(
        controller,
        "load_template_dialog",
        lambda _parent: pytest.fail("loader should not open"),
    )

    controller.load_template()


def test_template_load_dialog_is_themed_and_starts_in_user_templates(qapp, tmp_path):
    user_dir = tmp_path / "Folder Creator Templates" / "user_templates"
    user_dir.mkdir(parents=True)
    dialog = TemplateLoadDialog(None, user_dir)

    try:
        assert dialog.windowTitle() == "Load Template"
        assert dialog.directory().absolutePath() == user_dir.as_posix()
        assert dialog.nameFilters() == [
            "Templates (*.json *.txt *.md)",
            "JSON Files (*.json)",
            "Text Outline (*.txt)",
            "Markdown Outline (*.md)",
        ]
        assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
        assert dialog.fileMode() == QFileDialog.FileMode.ExistingFile
        assert dialog.acceptMode() == QFileDialog.AcceptMode.AcceptOpen
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dialog.minimumSize() == dialog.maximumSize()
        assert "QFileDialog" in dialog.styleSheet()
    finally:
        dialog.deleteLater()


def test_template_load_dialog_accepts_selected_file_and_loads_it(qapp, tmp_path, monkeypatch):
    window = make_window(tmp_path)
    selected = tmp_path / "incoming.txt"
    selected.write_text("Project", encoding="utf-8")
    window.service.load_template_data = lambda _path: [{"name": "Project", "children": []}]
    saved = []
    window.service.save_to_user_templates = lambda path: saved.append(path) or True
    monkeypatch.setattr(
        TemplateLoadDialog,
        "exec",
        lambda _dialog: QDialog.DialogCode.Accepted,
    )
    monkeypatch.setattr(
        TemplateLoadDialog,
        "selectedFiles",
        lambda _dialog: [str(selected)],
    )
    monkeypatch.setattr(
        template_controller_module.QTimer,
        "singleShot",
        lambda _delay, callback: callback(),
    )

    status, message = TemplateController(window).load_template_dialog(window)

    assert (status, message) == ("success", "Template loaded")
    assert window.service.tree_controller.deserialize_calls == [
        ([{"name": "Project", "children": []}], {"renumber": False})
    ]
    assert saved == [str(selected)]


def test_template_load_dialog_rejection_does_not_load(qapp, tmp_path, monkeypatch):
    window = make_window(tmp_path)
    window.service.load_template_data = lambda _path: pytest.fail("should not load")
    monkeypatch.setattr(
        TemplateLoadDialog,
        "exec",
        lambda _dialog: QDialog.DialogCode.Rejected,
    )

    assert TemplateController(window).load_template_dialog(window) == ("cancelled", "")


def test_template_load_is_blocked_when_master_backup_path_is_unavailable(
    qapp, tmp_path, monkeypatch
):
    window = make_window(tmp_path)
    window.service.templates_available = lambda: False
    window.service.template_paths = SimpleNamespace(user_dir=None, default_dir=None)
    monkeypatch.setattr(
        TemplateLoadDialog,
        "exec",
        lambda _dialog: pytest.fail("dialog should not open"),
    )

    assert TemplateController(window).load_template_dialog(window) == (
        "unavailable",
        "Set a valid Master Backup Path in Windows Resurface before working with templates.",
    )


def test_remove_all_signal_cleans_all_selection_state_once(
    qapp, tmp_path, monkeypatch
):
    window = make_window(tmp_path)
    controller = NestedUIController(window)
    controller.connect_signals()
    controller.template_controller._current_loaded_template = "Custom"
    window.load_user_template_dropdown.setCurrentIndex(1)
    window.load_default_template_dropdown.setCurrentIndex(1)
    window.ui_state.build_updates = 0
    window.ui_state.nested_updates = 0
    monkeypatch.setattr(
        "folder_creator.ui.nested_ui_controller.QTimer.singleShot",
        lambda _delay, callback: callback(),
    )

    window.remove_all_btn.click()

    assert window.service.tree_controller.remove_calls == 1
    assert controller.template_controller._current_loaded_template is None
    assert window.load_user_template_dropdown.currentIndex() == 0
    assert window.load_default_template_dropdown.currentIndex() == 0
    assert window.ui_state.build_updates == 1
    assert window.ui_state.nested_updates == 1


def test_successful_build_opens_output_and_persists_date_mode(qapp, tmp_path):
    window = make_window(tmp_path)
    window.base_path_line.setText(str(tmp_path))
    window.nested_date_toggle.setChecked(True)
    window.nested_date_config.setCurrentText("UK")
    window.open_folder_build_toggle.setChecked(True)
    window.minimize_after_build_toggle.setChecked(False)
    window.close_app_after_build_toggle.setChecked(False)
    window.service.build_tree = lambda base_path, mode: ("success", "done")
    opened = []
    output = SimpleNamespace(open_output_folder=opened.append)

    BuildController(window, output).build_folders_from_tree()

    assert opened == [str(tmp_path)]
    assert ("nested_date_stamp_mode", "UK") in window.service.state_manager.updates
    assert window.status.calls[-1][1]["status_type"] == "success"


def test_existing_build_does_not_open_output(qapp, tmp_path):
    window = make_window(tmp_path)
    window.base_path_line.setText(str(tmp_path))
    window.open_folder_build_toggle.setChecked(True)
    window.service.build_tree = lambda base_path, mode: ("exists", "already exists")
    opened = []

    BuildController(
        window, SimpleNamespace(open_output_folder=opened.append)
    ).build_folders_from_tree()

    assert opened == []
    assert window.status.calls[-1][1]["status_type"] == "error"


def test_build_toggle_signals_are_mutually_exclusive_and_persisted(qapp, tmp_path):
    window = make_window(tmp_path)
    controller = BuildController(window, SimpleNamespace(open_output_folder=lambda _: None))
    controller.connect_signals()

    window.minimize_after_build_toggle.setChecked(True)

    assert not window.close_app_after_build_toggle.isEnabled()
    assert ("minimize_after_build", True) in window.service.state_manager.updates

    window.minimize_after_build_toggle.setChecked(False)
    window.close_app_after_build_toggle.setChecked(True)

    assert not window.minimize_after_build_toggle.isEnabled()
    assert ("close_after_build", True) in window.service.state_manager.updates


def test_successful_build_schedules_selected_post_build_action(
    qapp, tmp_path, monkeypatch
):
    window = make_window(tmp_path)
    window.base_path_line.setText(str(tmp_path))
    window.minimize_after_build_toggle.setChecked(True)
    window.service.build_tree = lambda base_path, mode: ("success", "done")
    scheduled = []
    monkeypatch.setattr(
        build_module.QTimer,
        "singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )

    BuildController(
        window, SimpleNamespace(open_output_folder=lambda _: None)
    ).build_folders_from_tree()

    assert scheduled[0][0] == 3000


def test_open_output_folder_ignores_missing_path_and_opens_existing(
    qapp, tmp_path, monkeypatch
):
    window = make_window(tmp_path)
    opened = []
    monkeypatch.setattr(output_module.os, "startfile", opened.append, raising=False)
    controller = OutputLocationController(window)

    controller.open_output_folder(str(tmp_path / "missing"))
    controller.open_output_folder(str(tmp_path))

    assert opened == [str(tmp_path)]


def test_output_directory_dialog_is_themed_and_directory_only(qapp, tmp_path):
    dialog = OutputDirectoryDialog(None, tmp_path)

    try:
        assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
        assert dialog.testOption(QFileDialog.Option.ShowDirsOnly)
        assert dialog.fileMode() == QFileDialog.FileMode.Directory
        assert dialog.acceptMode() == QFileDialog.AcceptMode.AcceptOpen
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert "QFileDialog" in dialog.styleSheet()
        assert Path(dialog.directory().absolutePath()).resolve() == tmp_path.resolve()
    finally:
        dialog.close()


def test_output_selection_persists_normalized_directory(qapp, tmp_path, monkeypatch):
    window = make_window(tmp_path)
    selected = tmp_path / "selected"
    selected.mkdir()
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    class AcceptedDialog:
        def __init__(self, parent, directory):
            assert parent is window
            assert directory == desktop

        def exec(self):
            return QDialog.DialogCode.Accepted

        def selectedFiles(self):
            return [str(selected)]

    monkeypatch.setattr(output_module, "OutputDirectoryDialog", AcceptedDialog)
    monkeypatch.setattr(output_module, "get_desktop_path", lambda: desktop)

    OutputLocationController(window).select_base_directory()

    assert window.base_path_line.text() == str(selected.resolve())
    assert ("last_base_dir", str(selected.resolve())) in window.service.state_manager.updates


def test_cancelled_output_selection_reports_error_off_desktop(
    qapp, tmp_path, monkeypatch
):
    window = make_window(tmp_path)
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    window.base_path_line.setText(str(tmp_path))
    class RejectedDialog:
        def __init__(self, *_args):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(output_module, "OutputDirectoryDialog", RejectedDialog)
    monkeypatch.setattr(output_module, "get_desktop_path", lambda: desktop)

    OutputLocationController(window).select_base_directory()

    assert window.status.calls[-1][0] == ("No directory selected.",)
    assert window.status.calls[-1][1]["status_type"] == "error"


def test_output_directory_dialog_starts_at_current_valid_output_path(
    qapp, tmp_path, monkeypatch
):
    window = make_window(tmp_path)
    current = tmp_path / "current"
    current.mkdir()
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    window.base_path_line.setText(str(current))
    initial_directories = []

    class RejectedDialog:
        def __init__(self, _parent, directory):
            initial_directories.append(directory)

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(output_module, "OutputDirectoryDialog", RejectedDialog)
    monkeypatch.setattr(output_module, "get_desktop_path", lambda: desktop)

    OutputLocationController(window).select_base_directory()

    assert initial_directories == [current.resolve()]


def test_auto_number_disable_removes_only_trailing_numeric_suffixes(qapp, tmp_path):
    window = make_window(tmp_path)
    window.tree.addTopLevelItems(
        [QTreeWidgetItem(["Project 1"]), QTreeWidgetItem(["2026 Plan"])]
    )
    controller = NestedUIController(window)

    controller.toggle_auto_number_folders(False)

    assert window.tree.topLevelItem(0).text(0) == "Project"
    assert window.tree.topLevelItem(1).text(0) == "2026 Plan"
    assert ("nested_auto_number_enabled", False) in window.service.state_manager.updates


def test_template_save_writes_to_master_backed_user_folder(qapp, tmp_path, monkeypatch):
    window = make_window(tmp_path)
    user_dir = window.service.template_paths.user_dir
    def save_json(path, data):
        Path(path).write_text(str(data), encoding="utf-8")
        return "success", "saved"

    window.service.template_service = SimpleNamespace(
        save_json=save_json
    )

    def accept_dialog(self):
        self.filename_input.setText("project")
        self._accept_if_valid()
        return self.result()

    monkeypatch.setattr(TemplateSaveDialog, "exec", accept_dialog)

    TemplateController(window).user_template_save()

    assert (user_dir / "project.json").exists()


def test_delete_selected_user_template_removes_its_file_and_resets_ui(
    qapp, tmp_path, monkeypatch
):
    window = make_window(tmp_path)
    template = window.service.template_paths.user_dir / "project.json"
    template.write_text("[]", encoding="utf-8")
    window.tree.addTopLevelItem(QTreeWidgetItem(["Project"]))
    controller = TemplateController(window)
    controller.refresh_user_templates_dropdown()
    window.load_user_template_dropdown.setCurrentIndex(2)
    monkeypatch.setattr(
        TemplateController, "_confirm_template_deletion", lambda *_args: True
    )

    controller.delete_user_template()

    assert not template.exists()
    assert window.load_user_template_dropdown.currentIndex() == 0
    assert window.load_user_template_dropdown.findText("Project") == -1
    assert window.tree.topLevelItemCount() == 0
    assert window.status.calls[-1][0] == ("Template deleted.",)


def test_delete_selected_user_template_keeps_file_when_cancelled(
    qapp, tmp_path, monkeypatch
):
    window = make_window(tmp_path)
    template = window.service.template_paths.user_dir / "project.json"
    template.write_text("[]", encoding="utf-8")
    controller = TemplateController(window)
    controller.refresh_user_templates_dropdown()
    window.load_user_template_dropdown.setCurrentIndex(2)
    monkeypatch.setattr(
        TemplateController, "_confirm_template_deletion", lambda *_args: False
    )

    controller.delete_user_template()

    assert template.exists()
    assert window.load_user_template_dropdown.currentText() == "Project"


def test_delete_template_uses_selected_path_when_display_names_match(
    qapp, tmp_path, monkeypatch
):
    window = make_window(tmp_path)
    json_template = window.service.template_paths.user_dir / "project.json"
    text_template = window.service.template_paths.user_dir / "project.txt"
    json_template.write_text("[]", encoding="utf-8")
    text_template.write_text("Project", encoding="utf-8")
    controller = TemplateController(window)
    controller.refresh_user_templates_dropdown()
    text_index = window.load_user_template_dropdown.findData(
        str(text_template.resolve()), Qt.ItemDataRole.UserRole
    )
    window.load_user_template_dropdown.setCurrentIndex(text_index)
    monkeypatch.setattr(
        TemplateController, "_confirm_template_deletion", lambda *_args: True
    )

    controller.delete_user_template()

    assert json_template.exists()
    assert not text_template.exists()


def test_delete_template_without_selection_reports_an_error(qapp, tmp_path):
    window = make_window(tmp_path)
    controller = TemplateController(window)

    controller.delete_user_template()

    assert window.status.calls[-1][0] == ("Select a user template to delete.",)


def test_delete_template_is_blocked_when_template_storage_is_unavailable(
    qapp, tmp_path
):
    window = make_window(tmp_path)
    window.service.templates_available = lambda: False
    controller = TemplateController(window)

    controller.delete_user_template()

    assert window.status.calls[-1][0] == (
        "Set a valid Master Backup Path in Windows Resurface before working with templates.",
    )


def test_template_save_dialog_rejects_paths_and_keeps_destination_in_user_folder(qapp, tmp_path):
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    dialog = TemplateSaveDialog(None, user_dir)

    dialog.filename_input.setText("../outside")
    dialog._accept_if_valid()

    assert dialog.destination is None
    assert dialog.error_label.text() == "Template names cannot contain folders."

    dialog.filename_input.setText("project")
    dialog._accept_if_valid()

    assert dialog.destination == user_dir.resolve() / "project.json"


def test_template_save_dialog_uses_selected_format(qapp, tmp_path):
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    dialog = TemplateSaveDialog(None, user_dir)
    dialog.filename_input.setText("project")
    dialog.format_selector.setCurrentIndex(2)

    dialog._accept_if_valid()

    assert dialog.destination == user_dir.resolve() / "project.md"


def test_template_save_does_not_overwrite_without_confirmation(qapp, tmp_path, monkeypatch):
    window = make_window(tmp_path)
    destination = window.service.template_paths.user_dir / "project.json"
    destination.write_text("original", encoding="utf-8")
    window.service.template_service = SimpleNamespace(
        save_json=lambda *_args: pytest.fail("save should not run")
    )

    def accept_dialog(self):
        self.filename_input.setText("project")
        self._accept_if_valid()
        return self.result()

    monkeypatch.setattr(TemplateSaveDialog, "exec", accept_dialog)
    monkeypatch.setattr(
        TemplateController, "_confirm_template_replacement", lambda *_args: False
    )

    TemplateController(window).user_template_save()

    assert destination.read_text(encoding="utf-8") == "original"


def test_templates_are_blocked_when_master_backup_path_is_unavailable(
    qapp, tmp_path, monkeypatch
):
    window = make_window(tmp_path)
    window.service.templates_available = lambda: False
    window.service.template_paths = SimpleNamespace(user_dir=None, default_dir=None)
    opened = []
    monkeypatch.setattr(TemplateSaveDialog, "exec", lambda *_args: opened.append(True))

    TemplateController(window).user_template_save()

    assert opened == []
    assert window.status.calls[-1][0] == (
        "Set a valid Master Backup Path in Windows Resurface before working with templates.",
    )
    assert window.status.calls[-1][1]["status_type"] == "error"

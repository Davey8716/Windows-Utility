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
from PySide6.QtCore import Signal  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
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

    def set(self, *args, **kwargs):
        self.calls.append((args, kwargs))


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
        save_template_btn=QPushButton(),
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


def test_output_selection_persists_normalized_directory(qapp, tmp_path, monkeypatch):
    window = make_window(tmp_path)
    selected = tmp_path / "selected"
    selected.mkdir()
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    monkeypatch.setattr(
        output_module.QFileDialog,
        "getExistingDirectory",
        lambda *_args: str(selected),
    )
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
    monkeypatch.setattr(
        output_module.QFileDialog, "getExistingDirectory", lambda *_args: ""
    )
    monkeypatch.setattr(output_module, "get_desktop_path", lambda: desktop)

    OutputLocationController(window).select_base_directory()

    assert window.status.calls[-1][0] == ("No directory selected.",)
    assert window.status.calls[-1][1]["status_type"] == "error"


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

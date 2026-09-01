from pathlib import Path
from shutil import copy

from PySide6.QtCore import QFileSystemWatcher, QTimer
from PySide6.QtWidgets import QFileDialog

from folder_creator.features.tree.outline_parser import parse_indented_text


class TemplateController:
    """Own template loading, saving, selection, and filesystem refreshes."""

    def __init__(self, window):
        self.window = window
        self.service = window.service
        self.tree = window.tree
        self._loading_template = False
        self._current_loaded_template = None
        self.watcher = QFileSystemWatcher()

        user_dir = str(self.service.template_paths.user_dir)
        self.watcher.addPath(user_dir)
        self.watcher.directoryChanged.connect(self.refresh_user_templates_dropdown)

    def reset_loaded_template(self):
        self._current_loaded_template = None

    def load_template_dialog(self, parent):
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            "Load Template",
            "",
            "Templates (*.json *.txt *.md);;JSON Files (*.json);;Text Outline (*.txt)",
        )

        if not file_path:
            return "cancelled", ""

        try:
            self.load_template_from_path(file_path)
            return "success", "Template loaded"
        except Exception:
            return "error", "Error loading template"

    def load_template(self):
        status, message = self.load_template_dialog(self.window)
        if status == "success":
            self.window.status.set(message, target="nested", status_type="success")
        elif status != "cancelled":
            self.window.status.set(message, target="nested", status_type="error")

    def load_template_from_path(self, file_path):
        try:
            self._loading_template = True
            auto_number_was_enabled = self.window.auto_enumerate_folders.isChecked()
            data = self.service.load_template_data(file_path)
            if data is None:
                self._loading_template = False
                return

            self.service.tree_controller.deserialize_tree(
                data,
                renumber=auto_number_was_enabled,
            )
            self.service.save_to_user_templates(file_path)
            self._current_loaded_template = (
                Path(file_path).stem.replace("_", " ").title()
            )
            self.refresh_user_templates_dropdown()

            dropdown = self.window.load_user_template_dropdown
            index = dropdown.findText(self._current_loaded_template)
            if index != -1:
                dropdown.setCurrentIndex(index)

            def finalize():
                if self.tree.topLevelItemCount() > 0:
                    self.tree.setCurrentItem(self.tree.topLevelItem(0))
                self.service.tree_controller.expand_all_animated()
                self.window.load_default_template_dropdown.setCurrentIndex(0)
                self.window.ui_state.update_build_button_state()
                self._loading_template = False

            QTimer.singleShot(0, finalize)
            self.window.status.set(
                "Template loaded",
                target="nested",
                status_type="success",
            )
        except Exception:
            self._loading_template = False
            self.window.status.set(
                "Error loading template",
                target="nested",
                status_type="error",
            )

    def load_user_template_from_dropdown(self):
        if self._loading_template:
            return

        text = self.window.load_user_template_dropdown.currentText()
        if text == "User Templates":
            self.tree.clear()
            self.window.ui_state.update_build_button_state()
            return

        matches = [
            file
            for file in self.service.template_paths.user_dir.glob("*.*")
            if file.stem.replace("_", " ").title() == text
        ]
        if not matches:
            self.tree.clear()
            self.window.ui_state.update_build_button_state()
            return
        self.load_template_from_path(str(matches[0]))

    def refresh_user_templates_dropdown(self):
        dropdown = self.window.load_user_template_dropdown
        dropdown.blockSignals(True)
        dropdown.clear()
        dropdown.addItem("User Templates")
        dropdown.insertSeparator(dropdown.count())
        for file in sorted(self.service.template_paths.user_dir.glob("*.*")):
            dropdown.addItem(file.stem.replace("_", " ").title())
        dropdown.blockSignals(False)

        if self._current_loaded_template:
            index = dropdown.findText(self._current_loaded_template)
            if index != -1:
                dropdown.setCurrentIndex(index)

        current_loaded = self._current_loaded_template
        if current_loaded:
            names = [
                file.stem.replace("_", " ").title()
                for file in self.service.template_paths.user_dir.glob("*.*")
            ]
            if current_loaded not in names:
                self.reset_loaded_template()
                dropdown.setCurrentIndex(0)
                self.tree.clear()
                self.window.ui_state.update_build_button_state()

    def user_template_save(self):
        start_dir = self.window.template_path_line.text().strip()
        file_path, _ = QFileDialog.getSaveFileName(
            self.window,
            "Save Template",
            start_dir,
            "Templates (*.json *.txt *.md);;JSON (*.json);;Text (*.txt);;Markdown (*.md)",
        )
        if not file_path:
            return

        self.window.template_path_line.setText(str(Path(file_path).parent.resolve()))
        data = self.service.tree_controller.serialize_tree()
        if Path(file_path).suffix.lower() == ".json":
            status, message = self.service.template_service.save_json(file_path, data)
        else:
            try:
                Path(file_path).write_text(self.tree_to_outline(data), encoding="utf-8")
                status, message = "success", "Template exported"
            except Exception:
                status, message = "error", "Error saving template"

        if status == "success":
            self.window.status.set(message, target="nested", status_type="success")
            copy(file_path, self.service.template_paths.user_dir / Path(file_path).name)
            self.refresh_user_templates_dropdown()
        else:
            self.window.status.set(message, target="nested", status_type="error")

    def load_default_template(self):
        text = self.window.load_default_template_dropdown.currentText()
        if text == "Default Templates":
            self.tree.clear()
            self.window.ui_state.update_build_button_state()
            return

        template_path = (
            self.service.template_paths.default_dir
            / (text.lower().replace(" ", "_") + ".txt")
        )
        if not template_path.exists():
            return

        data = parse_indented_text(template_path.read_text(encoding="utf-8"))
        self.tree.clear()
        self.service.tree_controller.deserialize_tree(data)
        self.service.tree_controller.expand_all_animated()
        self.window.update_expand_button_text()
        if self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.window.ui_state.update_build_button_state()

    def create_template(self):
        if self.tree.topLevelItemCount() == 0:
            self.window.status.set(
                "Tree is empty.", target="nested", status_type="error"
            )
            return
        self.user_template_save()

    def tree_to_outline(self, data, depth=0):
        lines = []
        for node in data:
            lines.append("    " * depth + node["name"])
            if node["children"]:
                lines.append(self.tree_to_outline(node["children"], depth + 1))
        return "\n".join(lines)

    def on_user_template_selected(self, index):
        if index == 0:
            return
        self.window.ui_state.update_build_button_state()
        self.window.load_default_template_dropdown.setCurrentIndex(0)
        self.load_user_template_from_dropdown()

    def on_default_template_selected(self, index):
        if index == 0:
            return
        self.window.load_user_template_dropdown.setCurrentIndex(0)
        self.load_default_template()

    def connect_signals(self):
        window = self.window
        window.load_user_template_dropdown.currentIndexChanged.connect(
            self.on_user_template_selected
        )
        window.load_default_template_dropdown.currentIndexChanged.connect(
            self.on_default_template_selected
        )
        window.tree.fileDropped.connect(self.load_template_from_path)
        window.tree.loadTemplateShortcut.connect(self.load_template)
        window.save_template_btn.clicked.connect(self.create_template)

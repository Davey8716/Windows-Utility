import os
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QTimer, Qt
from PySide6.QtWidgets import QMessageBox

from folder_creator.features.tree.outline_parser import parse_indented_text
from folder_creator.ui import styles
from folder_creator.ui.template_load_dialog import TemplateLoadDialog
from folder_creator.ui.template_save_dialog import TemplateSaveDialog


class TemplateController:
    """Own template loading, saving, selection, and filesystem refreshes."""

    MASTER_BACKUP_UNAVAILABLE_MESSAGE = (
        "Set a valid Master Backup Path in Windows Resurface before working with templates."
    )

    def __init__(self, window):
        self.window = window
        self.service = window.service
        self.tree = window.tree
        self._loading_template = False
        self._current_loaded_template = None
        self.watcher = QFileSystemWatcher()

        user_dir = self._user_template_dir()
        if user_dir is not None:
            self.watcher.addPath(str(user_dir))
        self.watcher.directoryChanged.connect(self.refresh_user_templates_dropdown)

    def _templates_available(self) -> bool:
        resolver = getattr(self.service, "templates_available", None)
        return bool(resolver()) if callable(resolver) else True

    def _user_template_dir(self) -> Path | None:
        directory = getattr(self.service.template_paths, "user_dir", None)
        return Path(directory) if directory is not None else None

    def _show_master_backup_unavailable(self) -> None:
        self.window.status.set(
            self.MASTER_BACKUP_UNAVAILABLE_MESSAGE,
            target="nested",
            status_type="error",
        )

    def reset_loaded_template(self):
        self._current_loaded_template = None

    def load_template_dialog(self, parent):
        if not self._templates_available():
            return "unavailable", self.MASTER_BACKUP_UNAVAILABLE_MESSAGE

        user_dir = self._user_template_dir()
        if user_dir is None:
            return "unavailable", self.MASTER_BACKUP_UNAVAILABLE_MESSAGE

        dialog = TemplateLoadDialog(parent, user_dir)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return "cancelled", ""

        selected_files = dialog.selectedFiles()
        file_path = selected_files[0] if selected_files else ""

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
            self.window.status.show_template_loaded()
        elif status != "cancelled":
            self.window.status.set(message, target="nested", status_type="error")

    def load_template_from_path(self, file_path):
        if not self._templates_available():
            self._show_master_backup_unavailable()
            return
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
            if not self.service.save_to_user_templates(file_path):
                self._show_master_backup_unavailable()
                return
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
            self.window.status.show_template_loaded()
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

        user_dir = self._user_template_dir()
        if user_dir is None:
            self._show_master_backup_unavailable()
            return
        matches = [
            file
            for file in user_dir.glob("*.*")
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
        user_dir = self._user_template_dir()
        if user_dir is not None:
            for file in sorted(user_dir.glob("*.*")):
                dropdown.addItem(file.stem.replace("_", " ").title())
        dropdown.blockSignals(False)

        if self._current_loaded_template:
            index = dropdown.findText(self._current_loaded_template)
            if index != -1:
                dropdown.setCurrentIndex(index)

        current_loaded = self._current_loaded_template
        if current_loaded and user_dir is not None:
            names = [
                file.stem.replace("_", " ").title()
                for file in user_dir.glob("*.*")
            ]
            if current_loaded not in names:
                self.reset_loaded_template()
                dropdown.setCurrentIndex(0)
                self.tree.clear()
                self.window.ui_state.update_build_button_state()

    def user_template_save(self):
        user_dir = self._user_template_dir()
        if not self._templates_available() or user_dir is None:
            self._show_master_backup_unavailable()
            return

        dialog = TemplateSaveDialog(self.window, user_dir)
        if dialog.exec() != dialog.DialogCode.Accepted or dialog.destination is None:
            return

        destination = dialog.destination
        if destination.exists() and not self._confirm_template_replacement(destination):
            return

        data = self.service.tree_controller.serialize_tree()
        if destination.suffix.lower() == ".json":
            status, message = self.service.template_service.save_json(str(destination), data)
        else:
            try:
                destination.write_text(self.tree_to_outline(data), encoding="utf-8")
                status, message = "success", "Template exported"
            except Exception:
                status, message = "error", "Error saving template"

        if status == "success":
            self.window.status.set(message, target="nested", status_type="success")
            self.refresh_user_templates_dropdown()
        else:
            self.window.status.set(message, target="nested", status_type="error")

    def _confirm_template_replacement(self, destination: Path) -> bool:
        box = QMessageBox(self.window)
        box.setWindowTitle("Replace Template?")
        box.setText(f'"{destination.name}" already exists. Replace it?')
        box.setIcon(QMessageBox.Icon.Warning)
        box.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes
        )
        replace_button = box.button(QMessageBox.StandardButton.Yes)
        replace_button.setText("Replace")
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.setStyleSheet(styles.resurface_styles.message_box_style(radius=12))
        return box.exec() == QMessageBox.StandardButton.Yes

    def load_default_template(self):
        if not self._templates_available():
            self._show_master_backup_unavailable()
            return
        text = self.window.load_default_template_dropdown.currentText()
        if text == "Default Templates":
            self.tree.clear()
            self.window.ui_state.update_build_button_state()
            return

        default_dir = self.service.template_paths.default_dir
        if default_dir is None:
            self._show_master_backup_unavailable()
            return
        template_path = default_dir / (text.lower().replace(" ", "_") + ".txt")
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
        window.load_template_btn.clicked.connect(self.load_template)
        window.save_template_btn.clicked.connect(self.create_template)
        window.load_user_template_dropdown.setContextMenuPolicy(Qt.CustomContextMenu)
        window.load_user_template_dropdown.customContextMenuRequested.connect(
            lambda _position: self.open_user_templates_folder()
        )

    def open_user_templates_folder(self) -> None:
        user_dir = self._user_template_dir()
        if user_dir is None:
            self._show_master_backup_unavailable()
            return
        os.startfile(str(user_dir))

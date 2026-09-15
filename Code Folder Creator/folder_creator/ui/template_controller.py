import os
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QTimer, Qt

from folder_creator.features.tree.outline_parser import parse_indented_text
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

    def _user_template_files(self) -> list[Path]:
        """Return the files represented in the User Templates dropdown."""
        user_dir = self._user_template_dir()
        if user_dir is None:
            return []
        return sorted(file for file in user_dir.glob("*.*") if file.is_file())

    def _user_templates_available(self) -> bool:
        return self._templates_available() and bool(self._user_template_files())

    def _update_user_template_load_controls_state(self) -> None:
        enabled = self._user_templates_available()
        self.window.load_template_btn.setEnabled(enabled)
        self.window.load_user_template_dropdown.setEnabled(enabled)

    def _selected_user_template_path(self) -> Path | None:
        """Return the path stored on the selected dropdown item, if it is safe."""
        user_dir = self._user_template_dir()
        stored_path = self.window.load_user_template_dropdown.currentData(
            Qt.ItemDataRole.UserRole
        )
        if user_dir is None or not stored_path:
            return None
        try:
            path = Path(stored_path).resolve()
            path.relative_to(user_dir.resolve())
        except (OSError, ValueError):
            return None
        return path if path.is_file() else None

    def _update_delete_template_button_state(self) -> None:
        self.window.delete_template_btn.setEnabled(
            self._templates_available()
            and self._selected_user_template_path() is not None
        )
        self.window.delete_all_templates_btn.setEnabled(
            self._user_templates_available()
        )

    def _show_master_backup_unavailable(self, *, action_result: bool = False) -> None:
        if action_result:
            self.window.status.show_action_result(
                self.MASTER_BACKUP_UNAVAILABLE_MESSAGE, status_type="error"
            )
            return
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
        if not self._user_templates_available():
            return
        status, message = self.load_template_dialog(self.window)
        if status != "success" and status != "cancelled":
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

        selected_path = self._selected_user_template_path()
        if selected_path is None:
            self.tree.clear()
            self.window.ui_state.update_build_button_state()
            return
        self.load_template_from_path(str(selected_path))

    def refresh_user_templates_dropdown(self):
        dropdown = self.window.load_user_template_dropdown
        selected_path = self._selected_user_template_path()
        dropdown.blockSignals(True)
        dropdown.clear()
        dropdown.addItem("User Templates")
        dropdown.insertSeparator(dropdown.count())
        user_dir = self._user_template_dir()
        for file in self._user_template_files():
            dropdown.addItem(
                file.stem.replace("_", " ").title(),
                str(file.resolve()),
            )
        dropdown.blockSignals(False)

        if selected_path is not None:
            index = dropdown.findData(str(selected_path), Qt.ItemDataRole.UserRole)
            if index != -1:
                dropdown.setCurrentIndex(index)
        elif self._current_loaded_template:
            index = dropdown.findText(self._current_loaded_template)
            if index != -1:
                dropdown.setCurrentIndex(index)

        current_loaded = self._current_loaded_template
        if current_loaded and user_dir is not None:
            names = [
                file.stem.replace("_", " ").title()
                for file in self._user_template_files()
            ]
            if current_loaded not in names:
                self.reset_loaded_template()
                dropdown.setCurrentIndex(0)
                self.tree.clear()
                self.window.ui_state.update_build_button_state()
        self._update_delete_template_button_state()
        self._update_user_template_load_controls_state()

    def delete_user_template(self):
        if not self._templates_available():
            self._show_master_backup_unavailable(action_result=True)
            return

        template_path = self._selected_user_template_path()
        if template_path is None:
            self.window.status.show_action_result(
                "Select a user template to delete.",
                status_type="error",
            )
            self._update_delete_template_button_state()
            return
        if not self._confirm_template_deletion(template_path):
            self.window.status.show_action_result(
                "Template deletion cancelled.", status_type="info"
            )
            return

        try:
            template_path.unlink()
        except OSError:
            self.window.status.show_action_result(
                "Error deleting template.", status_type="error"
            )
            return

        self.reset_loaded_template()
        self.refresh_user_templates_dropdown()
        self.window.load_user_template_dropdown.setCurrentIndex(0)
        self.tree.clear()
        self.window.ui_state.update_build_button_state()

    def delete_all_user_templates(self):
        if not self._templates_available():
            self._show_master_backup_unavailable(action_result=True)
            return

        template_paths = self._user_template_files()
        if not template_paths:
            self._update_delete_template_button_state()
            self.window.status.show_action_result(
                "No user templates to delete.", status_type="info"
            )
            return
        if not self._confirm_all_template_deletion(len(template_paths)):
            self.window.status.show_action_result(
                "Deleting all templates cancelled.", status_type="info"
            )
            return

        failed = False
        for template_path in template_paths:
            try:
                template_path.unlink()
            except OSError:
                failed = True

        self.reset_loaded_template()
        self.refresh_user_templates_dropdown()
        self.window.load_user_template_dropdown.setCurrentIndex(0)
        self.tree.clear()
        self.window.ui_state.update_build_button_state()
        if failed:
            self.window.status.show_action_result(
                "Error deleting all templates.", status_type="error"
            )
            return

    def _confirm_template_deletion(self, template_path: Path) -> bool:
        return self.window.status.confirm_action(
            "Delete Template?",
            f'Permanently delete "{template_path.name}"?',
            affirmative_label="Delete",
        )

    def _confirm_all_template_deletion(self, template_count: int) -> bool:
        return self.window.status.confirm_action(
            "Delete All Templates?",
            f"Permanently delete all {template_count} user template(s)?",
            affirmative_label="Delete All",
        )

    def user_template_save(self):
        user_dir = self._user_template_dir()
        if not self._templates_available() or user_dir is None:
            self._show_master_backup_unavailable(action_result=True)
            return

        dialog = TemplateSaveDialog(self.window, user_dir)
        if dialog.exec() != dialog.DialogCode.Accepted or dialog.destination is None:
            self.window.status.show_action_result(
                "Template save cancelled.", status_type="info"
            )
            return

        destination = dialog.destination
        replacing_template = destination.exists()
        if replacing_template and not self._confirm_template_replacement(destination):
            self.window.status.show_action_result(
                "Template save cancelled.", status_type="info"
            )
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
            completion_message = (
                f'Template "{destination.name}" replaced successfully.'
                if replacing_template
                else message
            )
            self.window.status.show_action_result(
                completion_message, status_type="success"
            )
            self.refresh_user_templates_dropdown()
            dropdown = self.window.load_user_template_dropdown
            saved_template_index = dropdown.findData(
                str(destination.resolve()), Qt.ItemDataRole.UserRole
            )
            if saved_template_index != -1:
                dropdown.setCurrentIndex(saved_template_index)
        else:
            self.window.status.show_action_result(message, status_type="error")

    def _confirm_template_replacement(self, destination: Path) -> bool:
        return self.window.status.confirm_action(
            "Replace Template?",
            f'"{destination.name}" already exists. Replace it?',
            affirmative_label="Replace",
        )

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
            self.window.status.show_action_result(
                "Tree is empty.", status_type="error"
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
        self._update_delete_template_button_state()
        if index == 0:
            self.reset_loaded_template()
            self.tree.clear()
            self.window.ui_state.update_build_button_state()
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
        window.delete_template_btn.clicked.connect(self.delete_user_template)
        window.delete_all_templates_btn.clicked.connect(self.delete_all_user_templates)
        window.load_user_template_dropdown.setContextMenuPolicy(Qt.CustomContextMenu)
        window.load_user_template_dropdown.customContextMenuRequested.connect(
            lambda _position: self.open_user_templates_folder()
        )
        self._update_delete_template_button_state()
        self._update_user_template_load_controls_state()

    def open_user_templates_folder(self) -> None:
        user_dir = self._user_template_dir()
        if user_dir is None:
            self._show_master_backup_unavailable()
            return
        os.startfile(str(user_dir))

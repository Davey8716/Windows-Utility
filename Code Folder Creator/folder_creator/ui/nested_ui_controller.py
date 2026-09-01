from PySide6.QtWidgets import QFileDialog,QTreeWidgetItemIterator,QAbstractItemView
from PySide6.QtCore import QFileSystemWatcher
from pathlib import Path
from shutil import copy
from PySide6.QtWidgets import QApplication
from folder_creator.core.system_paths import get_desktop_path
from folder_creator.features.tree.outline_parser import parse_indented_text
import os
import re
from PySide6.QtCore import QTimer

class NestedUIController:

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

    def load_template_dialog(self, parent):

        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            "Load Template",
            "",
            "Templates (*.json *.txt *.md);;JSON Files (*.json);;Text Outline (*.txt)"
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
            self.window.status.set(
                message,
                target="nested",
                status_type="success"
            )

        elif status != "cancelled":
            self.window.status.set(
                message,
                target="nested",
                status_type="error"
            )

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
                renumber=auto_number_was_enabled
            )

            self.service.save_to_user_templates(file_path)

            self._current_loaded_template = Path(file_path).stem.replace("_", " ").title()

            self.refresh_user_templates_dropdown()

            dropdown = self.window.load_user_template_dropdown
            index = dropdown.findText(self._current_loaded_template)
            if index != -1:
                dropdown.setCurrentIndex(index)


            def finalize():
                if self.tree.topLevelItemCount() > 0:
                    root = self.tree.topLevelItem(0)
                    self.tree.setCurrentItem(root)

                self.service.tree_controller.expand_all_animated()
                self.window.load_default_template_dropdown.setCurrentIndex(0)
                self.window.ui_state.update_build_button_state()
                self._loading_template = False

            QTimer.singleShot(0, finalize)

            self.window.status.set(
                "Template loaded",
                target="nested",
                status_type="success"
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

        folder = self.service.template_paths.user_dir
        matches = [
            f for f in folder.glob("*.*")
            if f.stem.replace("_", " ").title() == text
        ]
            

        # ---- THIS is the missing guard ----
        if not matches:
            self.tree.clear()
            self.window.ui_state.update_build_button_state()
            return

        path = matches[0]

        self.load_template_from_path(str(path))

    def refresh_user_templates_dropdown(self):
        dropdown = self.window.load_user_template_dropdown

        dropdown.blockSignals(True)
        dropdown.clear()

        dropdown.addItem("User Templates")
        dropdown.insertSeparator(dropdown.count())

        for file in sorted(self.service.template_paths.user_dir.glob("*.*")):
            name = file.stem.replace("_", " ").title()
            dropdown.addItem(name)

        dropdown.blockSignals(False)

        # ---- FORCE dropdown to match current loaded template ----
        active = self._current_loaded_template

        if active:
            index = dropdown.findText(active)
            if index != -1:
                dropdown.setCurrentIndex(index)

        # ---- deletion handling ----
        current_loaded = self._current_loaded_template

        if current_loaded:
            names = [
                f.stem.replace("_", " ").title()
                for f in self.service.template_paths.user_dir.glob("*.*")
            ]

            if current_loaded not in names:
                self._current_loaded_template = None
                dropdown.setCurrentIndex(0)
                self.tree.clear()
                self.window.ui_state.update_build_button_state()
        

    def user_template_save(self):

        start_dir = self.window.template_path_line.text().strip()

        file_path, _ = QFileDialog.getSaveFileName(
            self.window,
            "Save Template",
            start_dir,
            "Templates (*.json *.txt *.md);;JSON (*.json);;Text (*.txt);;Markdown (*.md)"
        )

        if not file_path:
            return

        directory = str(Path(file_path).parent.resolve())
        self.window.template_path_line.setText(directory)

        data = self.service.tree_controller.serialize_tree()

        suffix = Path(file_path).suffix.lower()

        if suffix == ".json":
            status, message = self.service.template_service.save_json(file_path, data)

        else:
            text = self.tree_to_outline(data)

            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(text)

                status = "success"
                message = "Template exported"

            except Exception:
                status = "error"
                message = "Error saving template"

        if status == "success":
            self.window.status.set(message, target="nested", status_type="success")

            appdata_target = self.service.template_paths.user_dir / Path(file_path).name

            copy(file_path, appdata_target)

            print("Copied to:", appdata_target)
            print("Exists:", appdata_target.exists())

            self.refresh_user_templates_dropdown()

        else:
            self.window.status.set(message, target="nested", status_type="error")


    def on_sort_tree(self):

        if self.tree.topLevelItemCount() == 0:
            self.window.status.set(
                "Nothing to sort.",
                target="nested",
                status_type="error"
            )
            return

        self.service.tree_controller.sort_tree()

        if self.tree.topLevelItemCount() > 0:
            root = self.tree.topLevelItem(0)
            self.tree.setCurrentItem(root)

        self.window.status.set(
            "Folder tree sorted alphabetically.",
            target="nested",
            status_type="success"
        )
        
    def find_folder_in_tree(self):

        text = self.window.find_output_line.text().strip().lower()
        if not text:
            self.window.status.set(
                "Enter a folder name to search for.",
                target="nested",
                status_type="error"
            )
            return

        iterator = QTreeWidgetItemIterator(self.tree)

        while iterator.value():

            item = iterator.value()

            if item.text(0).strip().lower() == text:

                self.tree.setCurrentItem(item)

                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()

                self.tree.setCurrentItem(item)

                self.tree.scrollToItem(item, QAbstractItemView.PositionAtCenter)

                rect = self.tree.visualItemRect(item)
                viewport_width = self.tree.viewport().width()
                hbar = self.tree.horizontalScrollBar()

                if rect.left() < 0:
                    hbar.setValue(hbar.value() + rect.left())
                elif rect.right() > viewport_width:
                    hbar.setValue(hbar.value() + (rect.right() - viewport_width))

                self.window.status.set(
                    f'Folder "{item.text(0)}" found.',
                    target="nested",
                    status_type="success"
                )
                return

            iterator += 1

        self.window.status.set(
            "No matching folder found.",
            target="nested",
            status_type="error"
        )
    
    def remove_all_folders(self):
        self.service.tree_controller.remove_all_folders()
        self.window.load_default_template_dropdown.setCurrentIndex(0)
        self.window.ui_state.update_build_button_state()
        
    def toggle_auto_number_folders(self, checked: bool):
        manager = self.service.tree_controller
        manager.auto_number_enabled = checked

        if self.tree.topLevelItemCount() > 0:
            if checked:
                manager.renumber_loaded_tree()
            else:
                # ---- remove numbering ----
              

                it = QTreeWidgetItemIterator(self.tree)
                while it.value():
                    item = it.value()
                    name = item.text(0)

                    # remove trailing " 1", " 2", etc.
                    clean = re.sub(r"\s+\d+$", "", name).strip()
                    item.setText(0, clean)

                    it += 1

        self.service.set_state(
            "nested_auto_number_enabled",
            checked
        )

    def load_default_template(self):
        text = self.window.load_default_template_dropdown.currentText()

        if text == "Default Templates":
            self.tree.clear()
            self.window.ui_state.update_build_button_state()
            return

        filename = text.lower().replace(" ", "_") + ".txt"

        template_path = self.service.template_paths.default_dir / filename

        if not template_path.exists():
            return

        with open(template_path, "r", encoding="utf-8") as f:
            text = f.read()

        self.tree.clear()

        data = parse_indented_text(text)
        self.service.tree_controller.deserialize_tree(data)
        self.service.tree_controller.expand_all_animated()
        self.window.update_expand_button_text()

        if self.tree.topLevelItemCount() > 0:
            root = self.tree.topLevelItem(0)
            self.tree.setCurrentItem(root)

        self.window.ui_state.update_build_button_state()
        
    def create_template(self):

        if self.tree.topLevelItemCount() == 0:
            self.window.status.set(
                "Tree is empty.",
                target="nested",
                status_type="error"
            )
            return

        self.user_template_save()

    def nested_on_date_stamp_toggled(self, checked: bool):
        self.window.nested_date_config.setEnabled(checked)
        self.service.set_state(
            "nested_date_stamp_enabled",
            checked
        )

    def nested_on_date_mode_changed(self, index: int):
        text = self.window.nested_date_config.currentText()

        if "ISO" in text:
            mode = "ISO"
        elif "UK" in text:
            mode = "UK"
        elif "US" in text:
            mode = "US"
        else:
            mode = "ISO"

        self.service.set_state(
            "nested_date_stamp_mode",
            mode
        )

    def tree_to_outline(self, data, depth=0):
        lines = []

        for node in data:
            lines.append("    " * depth + node["name"])

            if node["children"]:
                lines.append(self.tree_to_outline(node["children"], depth + 1))

        return "\n".join(lines)

    def build_folders_from_tree(self):
        base_path = self.window.base_path_line.text().strip()

        if not base_path:
            self.window.status.set(
                "No base directory selected.",
                target="nested",
                status_type="error"
            )
            return

        mode = None

        if self.window.nested_date_toggle.isChecked():

            text = self.window.nested_date_config.currentText()

            if "ISO" in text:
                mode = "ISO"
            elif "UK" in text:
                mode = "UK"
            elif "US" in text:
                mode = "US"

            self.service.state_manager.update(
                "nested_date_stamp_mode",
                mode
            )

        status, message = self.service.build_tree(base_path, mode)

        if status == "success":
            stype = "success"

            if self.window.open_folder_build_toggle.isChecked():
                self.open_output_folder(base_path)

            if self.window.minimize_after_build_toggle.isChecked():
                QTimer.singleShot(3000, self.minimize_after_build)
            
            if self.window.close_app_after_build_toggle.isChecked():
                QTimer.singleShot(5000, self.close_after_build)
            
        elif status == "exists":
            stype = "error"

        self.window.status.set(message, target="nested", status_type=stype)
        
    def minimize_after_build(self):
        self.window.showMinimized()



    def close_after_build(self):
        QApplication.quit()

    def open_output_folder(self, path: str):

        p = Path(path)

        if not p.exists():
            return
        try:
            os.startfile(str(p))
        except Exception:
            pass

    def select_base_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self.window,
            "Select Base Directory"
        )

        if directory:
            desktop_path = get_desktop_path().resolve()
            current_path = Path(self.window.base_path_line.text().strip()).resolve()
            selected_path = Path(directory).resolve()

            if selected_path == desktop_path and current_path == desktop_path:
                self.window.update_build_button_state()

                self.window.status.set(
                    "Desktop is already the active output location.",
                    target="nested",
                    status_type="info"
                )
                return

            normalized = str(selected_path)

            self.window.base_path_line.setText(normalized)
            self.service.set_state("last_base_dir", normalized)
            self.window.ui_state.update_build_button_state()

            self.window.status.set(
                f"Base directory set: {normalized}",
                target="nested",
                status_type="info"
            )
            
        else:
            desktop_path = get_desktop_path().resolve()
            current_path = Path(self.window.base_path_line.text().strip()).resolve()

            if current_path == desktop_path:
                pass
            else:
                self.window.status.set(
                    "No directory selected.",
                    target="nested",
                    status_type="error"
                )

    def default_to_desktop(self):

        desktop_path = get_desktop_path()
        self.window.base_path_line.setText(str(desktop_path))
        self.service.set_state("last_base_dir", str(desktop_path))
        self.window.update_build_button_state()
        self.window.status.set(
            "Base directory set to Desktop.",
            target="nested",
            status_type="info"
        )
        
    def open_output_folder(self, path: str):
        p = Path(path)

        if not p.exists():
            return
        try:
            os.startfile(str(p))
        except Exception:
            pass

    # Mutual exclusion logic for the dropdowns, if a template is chosen on either dropdown and another tempalte is chose on the other dropdown
    # the former reverts to 0 on the index .e.g title.

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
        w = self.window

        # ---- Mutual exclusion ----
        w.minimize_after_build_toggle.toggled.connect(
            lambda checked: w.close_app_after_build_toggle.setEnabled(not checked)
        )

        w.close_app_after_build_toggle.toggled.connect(
            lambda checked: w.minimize_after_build_toggle.setEnabled(not checked)
        )

        w.close_app_after_build_toggle.setEnabled(not w.minimize_after_build_toggle.isChecked())
        w.minimize_after_build_toggle.setEnabled(not w.close_app_after_build_toggle.isChecked())
        w.load_user_template_dropdown.currentIndexChanged.connect(self.on_user_template_selected)
        w.load_default_template_dropdown.currentIndexChanged.connect(self.on_default_template_selected)
        w.load_default_template_dropdown.currentIndexChanged.connect(self.load_default_template)
        w.minimize_after_build_toggle.toggled.connect(lambda v: self.service.state_manager.update("minimize_after_build", v))
        w.close_app_after_build_toggle.toggled.connect(lambda v: self.service.state_manager.update("close_after_build", v))
        w.tree.fileDropped.connect(self.load_template_from_path)
        w.sort_btn.clicked.connect(self.on_sort_tree)
        w.tree.loadTemplateShortcut.connect(self.load_template)
        w.find_btn.clicked.connect(self.find_folder_in_tree)
        w.find_output_line.returnPressed.connect(self.find_folder_in_tree)
        w.auto_enumerate_folders.toggled.connect(self.toggle_auto_number_folders)
        w.save_template_btn.clicked.connect(self.create_template)
        w.remove_all_btn.clicked.connect(self.remove_all_folders)
        w.nested_date_toggle.toggled.connect(self.nested_on_date_stamp_toggled)
        w.build_folders_btn.clicked.connect(self.build_folders_from_tree)
        w.nested_date_config.currentIndexChanged.connect(self.nested_on_date_mode_changed)
        w.output_location_btn.clicked.connect(self.select_base_directory)
        w.default_to_desktop_btn.clicked.connect(self.default_to_desktop)

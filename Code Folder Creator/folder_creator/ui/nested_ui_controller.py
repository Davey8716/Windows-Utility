import re

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QAbstractItemView, QTreeWidgetItemIterator

from folder_creator.ui.build_controller import BuildController
from folder_creator.ui.output_location_controller import OutputLocationController
from folder_creator.ui.template_controller import TemplateController


class NestedUIController:
    """Coordinate tree-specific actions and the focused nested UI controllers."""

    def __init__(self, window):
        self.window = window
        self.service = window.service
        self.tree = window.tree

        self.template_controller = TemplateController(window)
        self.output_location_controller = OutputLocationController(window)
        self.build_controller = BuildController(
            window,
            self.output_location_controller,
        )

    def on_sort_tree(self):
        if self.tree.topLevelItemCount() == 0:
            self.window.status.set(
                "Nothing to sort.", target="nested", status_type="error"
            )
            return

        self.service.tree_controller.sort_tree()
        if self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.window.status.set(
            "Folder tree sorted alphabetically.",
            target="nested",
            status_type="success",
        )

    def find_folder_in_tree(self):
        text = self.window.find_output_line.text().strip().lower()
        if not text:
            self.window.status.show_find_result(
                "Enter a folder name to search for.", status_type="error"
            )
            return

        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.text(0).strip().lower() == text:
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()

                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                rect = self.tree.visualItemRect(item)
                viewport_width = self.tree.viewport().width()
                horizontal_bar = self.tree.horizontalScrollBar()

                if rect.left() < 0:
                    horizontal_bar.setValue(horizontal_bar.value() + rect.left())
                elif rect.right() > viewport_width:
                    horizontal_bar.setValue(
                        horizontal_bar.value() + rect.right() - viewport_width
                    )

                self.window.status.show_find_result(
                    f'Folder "{item.text(0)}" found.', status_type="success"
                )
                return
            iterator += 1

        self.window.status.show_find_result(
            "No matching folder found.", status_type="error"
        )

    def remove_all_folders(self):
        self.service.tree_controller.remove_all_folders()
        self.template_controller.reset_loaded_template()
        self.window.load_user_template_dropdown.setCurrentIndex(0)
        self.window.load_default_template_dropdown.setCurrentIndex(0)
        self.window.ui_state.update_build_button_state()
        QTimer.singleShot(0, self.window.ui_state.update_nested_build_state)

    def toggle_auto_number_folders(self, checked: bool):
        manager = self.service.tree_controller
        manager.auto_number_enabled = checked
        if self.tree.topLevelItemCount() > 0:
            if checked:
                manager.renumber_loaded_tree()
            else:
                iterator = QTreeWidgetItemIterator(self.tree)
                while iterator.value():
                    item = iterator.value()
                    clean = re.sub(r"\s+\d+$", "", item.text(0)).strip()
                    item.setText(0, clean)
                    iterator += 1

        self.service.set_state("nested_auto_number_enabled", checked)

    def add_root_folder(self):
        self.service.tree_controller.add_root_folder()
        self.window.ui_state.update_build_button_state()

    def add_subfolder(self):
        self.service.tree_controller.add_subfolder()
        self.window.ui_state.update_build_button_state()

    def remove_selected_folders(self):
        self.service.tree_controller.remove_selected_folders()
        self.window.ui_state.update_build_button_state()
        QTimer.singleShot(0, self.window.ui_state.update_nested_build_state)

    def add_selected_file_type(self, index):
        filename = {
            2: "main.py",
            3: "script.js",
            4: "index.html",
            5: "styles.css",
            7: "notes.txt",
            8: "README.md",
            9: "README.md",
            11: "data.json",
            12: "config.yaml",
            13: ".env",
            15: "run.bat",
            16: "script.ps1",
        }.get(index)
        if filename is None:
            return
        self.service.tree_controller.add_file(filename)
        self.window.file_dropdown.setCurrentIndex(0)
        self.window.ui_state.update_build_button_state()

    def connect_signals(self):
        self.template_controller.connect_signals()
        self.build_controller.connect_signals()
        self.output_location_controller.connect_signals()

        window = self.window
        window.sort_btn.clicked.connect(self.on_sort_tree)
        window.find_btn.clicked.connect(self.find_folder_in_tree)
        window.find_output_line.returnPressed.connect(self.find_folder_in_tree)
        window.auto_enumerate_folders.toggled.connect(
            self.toggle_auto_number_folders
        )
        window.remove_all_btn.clicked.connect(self.remove_all_folders)
        window.tree.itemExpanded.connect(window.update_expand_button_text)
        window.tree.itemExpanded.connect(window.ui_state.update_build_button_state)
        window.tree.itemCollapsed.connect(window.ui_state.update_build_button_state)
        window.tree.itemCollapsed.connect(window.update_expand_button_text)
        window.tree.addFolderShortcut.connect(window.add_folder_btn.click)
        window.tree.addSubfolderShortcut.connect(window.add_subfolder_btn.click)
        window.tree.saveTemplateShortcut.connect(window.save_template_btn.click)
        window.tree.itemChanged.connect(window.ui_state.update_build_button_state)
        window.tree.itemChanged.connect(window.enforce_tree_name_limit)
        window.tree.itemChanged.connect(window.ui_state.update_nested_build_state)
        window.tree.itemSelectionChanged.connect(
            window.ui_state.update_build_button_state
        )
        window.expand_tree_btn.clicked.connect(window.tree_gui_stretch)
        window.expand_folders_collapse_btn.clicked.connect(window.toggle_tree_expand)
        window.add_folder_btn.clicked.connect(self.add_root_folder)
        window.add_subfolder_btn.clicked.connect(self.add_subfolder)
        window.remove_btn.clicked.connect(self.remove_selected_folders)
        window.file_dropdown.currentIndexChanged.connect(self.add_selected_file_type)

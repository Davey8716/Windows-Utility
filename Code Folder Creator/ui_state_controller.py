from PySide6.QtWidgets import QTreeWidgetItemIterator
from pathlib import Path
from system_paths import get_desktop_path

INVALID_FOLDER_CHARS = '<>:"/\\|?*'
MAX_NESTED_FOLDER_NAME_LENGTH = 64

class UIStateController:
    def __init__(self, window):
        self.w = window
        self.tree = window.tree
        self.service = window.service
        self._build_validation_key = None
        self._selection_validation_key = None

    def update_build_button_state(self):
        has_invalid_chars = self.tree_contains_invalid_chars()
        
        default_template_loaded = (
            self.w.load_default_template_dropdown.currentIndex() != 0
        )

        has_items = self.tree.topLevelItemCount() > 0
        has_selection = self.tree.currentItem() is not None

        default_template_loaded = (
            self.w.load_default_template_dropdown.currentIndex() != 0
        )

        # Detect if nesting exists
        has_children = any(
            self.tree.topLevelItem(i).childCount() > 0
            for i in range(self.tree.topLevelItemCount())
        )
        
        if not has_children:
            self.w.sort_btn.setEnabled(False)

        # Desktop path
  

        desktop_path = get_desktop_path().resolve()
        current_path = Path(self.w.base_path_line.text().strip()).resolve() if self.w.base_path_line.text().strip() else None

        is_desktop = current_path == desktop_path

        self.w.default_to_desktop_btn.setEnabled(not is_desktop)
        
        # ---- Find logic ----
        viewport_height = self.tree.viewport().height()
        row_height = self.tree.sizeHintForRow(0)

        visible_capacity = 0
        if row_height > 0:
            visible_capacity = max(1, viewport_height // row_height)

        total_items = self.get_total_tree_item_count()
        has_collapsed = self.tree_has_collapsed_nodes()

        can_find = (
            total_items > visible_capacity
            or has_collapsed
        )

        self.w.find_btn.setEnabled(can_find)
        self.w.find_output_line.setEnabled(True)
        
        # ---- Duplicate detection ----
        parent_names = [
            self.tree.topLevelItem(i).text(0).strip().lower()
            for i in range(self.tree.topLevelItemCount())
        ]

        has_duplicate_parents = len(parent_names) != len(set(parent_names))

        has_duplicate_children = False
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)

            child_names = [
                parent.child(j).text(0).strip().lower()
                for j in range(parent.childCount())
            ]

            if len(child_names) != len(set(child_names)):
                has_duplicate_children = True
                break

        has_duplicates = has_duplicate_parents or has_duplicate_children

        # ---- Status ----
        validation_message = None
        validation_key = None
        if has_duplicates:
            validation_message = (
                "Duplicate folder names detected under the same parent.Rename folders before building."
                "Or Auto number them."
            )
            validation_key = "duplicate_folders"
                
        if has_invalid_chars:
            validation_message = (
                "Invalid characters detected in folder names.\n "
                "Remove <>:\"/\\|?* before building."
            )
            validation_key = "invalid_folder_chars"

        if validation_message is not None:
            if self._build_validation_key != validation_key:
                self.w.status.set(
                    validation_message,
                    target="nested",
                    status_type="error",
                    dedupe_key=f"build_validation:{validation_key}",
                )
                self._build_validation_key = validation_key
        else:
            self._build_validation_key = None

        # ---- Invalid names ----
        invalid_name_exists = False
        iterator = QTreeWidgetItemIterator(self.tree)

        while iterator.value():
            name = iterator.value().text(0).strip()

            if not name or any(c in name for c in INVALID_FOLDER_CHARS):
                invalid_name_exists = True
                break

            iterator += 1
            
        # ---- Buttons ----
        self.w.build_folders_btn.setEnabled(
            has_items and not has_duplicate_parents and not has_invalid_chars and not invalid_name_exists
        )
        self.w.remove_all_btn.setEnabled(has_items)
        self.w.save_template_btn.setEnabled(has_items and not has_duplicate_parents and not default_template_loaded)
        
        # ---- Sort override ----
        if self.w.auto_enumerate_folders.isChecked():
            self.w.sort_btn.setEnabled(False)
        else:
            can_sort = self.tree.topLevelItemCount() > 1

            if not can_sort:
                for i in range(self.tree.topLevelItemCount()):
                    item = self.tree.topLevelItem(i)
                    if item.childCount() > 1:
                        can_sort = True
                        break

            self.w.sort_btn.setEnabled(can_sort)

        # ---- Sort meaningful ----
        def names_would_change(names):
            normalized = [n.strip().lower() for n in names]
            return normalized != sorted(normalized)

        can_sort = False

        if not has_children:
            can_sort = False
        else:
            root_names = [
                self.tree.topLevelItem(i).text(0)
                for i in range(self.tree.topLevelItemCount())
            ]

            if len(root_names) > 1 and names_would_change(root_names):
                can_sort = True

            if not can_sort:
                for i in range(self.tree.topLevelItemCount()):
                    parent = self.tree.topLevelItem(i)

                    child_names = [
                        parent.child(j).text(0)
                        for j in range(parent.childCount())
                    ]

                    if len(child_names) > 1 and names_would_change(child_names):
                        can_sort = True
                        break

        self.w.sort_btn.setEnabled(can_sort)

        # ---- Other controls ----
        self.w.expand_folders_collapse_btn.setEnabled(has_children)
        self.w.remove_btn.setEnabled(has_selection)
        self.w.add_subfolder_btn.setEnabled(has_selection)

        self.w.file_dropdown.setEnabled(has_items and not default_template_loaded)
        
        if default_template_loaded:
            self.w.auto_enumerate_folders.setChecked(False)
            self.w.auto_enumerate_folders.setEnabled(False)
        else:
            self.w.auto_enumerate_folders.setEnabled(True)


    def update_nested_build_state(self):
        item = self.tree.currentItem()

        if not item:
            self._selection_validation_key = None
            return

        text = item.text(0).strip()
        validation_message = None
        validation_key = None

        if not text:
            validation_message = "Folder name cannot be empty."
            validation_key = "empty_folder_name"

        has_invalid = any(c in text for c in INVALID_FOLDER_CHARS or "")

        if has_invalid:
            validation_message = (
                "Invalid characters detected. Remove <>:\"/\\|?* from folder name."
            )
            validation_key = "selected_invalid_chars"

        elif len(text) >= MAX_NESTED_FOLDER_NAME_LENGTH:
            validation_message = (
                f"Folder name limit is {MAX_NESTED_FOLDER_NAME_LENGTH} characters."
            )
            validation_key = "selected_name_limit"

        if validation_message is not None:
            if self._selection_validation_key != validation_key:
                self.w.status.set(
                    validation_message,
                    target="nested",
                    status_type="error",
                    dedupe_key=f"selection_validation:{validation_key}",
                )
                self._selection_validation_key = validation_key

        else:
            self._selection_validation_key = None


    def tree_contains_invalid_chars(self):
        invalid = '<>:"/\\|?*'
        iterator = QTreeWidgetItemIterator(self.tree)

        while iterator.value():
            name = iterator.value().text(0)

            for c in invalid:
                if c in name:
                    return True

            iterator += 1

        return False

    def get_total_tree_item_count(self):
        count = 0
        iterator = QTreeWidgetItemIterator(self.tree)

        while iterator.value():
            count += 1
            iterator += 1

        return count
    
    def get_visible_tree_item_count(self):
        def count_visible(item):
            total = 1

            if item.isExpanded():
                for i in range(item.childCount()):
                    total += count_visible(item.child(i))

            return total

        total = 0

        for i in range(self.tree.topLevelItemCount()):
            total += count_visible(self.tree.topLevelItem(i))

        return total


    def tree_has_collapsed_nodes(self):
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)

            if not item.isExpanded() and item.childCount() > 0:
                return True

            stack = [item]

            while stack:
                node = stack.pop()

                for j in range(node.childCount()):
                    child = node.child(j)

                    if not child.isExpanded() and child.childCount() > 0:
                        return True

                    stack.append(child)

        return False

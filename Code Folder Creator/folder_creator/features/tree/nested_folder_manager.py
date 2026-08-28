
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtCore import QDir
from PySide6.QtWidgets import QTreeWidgetItem
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTreeWidgetItemIterator
from datetime import datetime
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple

Node = Dict[str, Any]

IGNORED_IMPORT_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".pytest_tmp",
    ".ruff_cache",
    ".tmp",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}

class NestedFolderManager:
    def __init__(self, tree_widget):
        self.tree = tree_widget
        self.auto_number_enabled = False

    def serialize_tree(self):
        data = []
        for i in range(self.tree.topLevelItemCount()):
            data.append(self._serialize_item(self.tree.topLevelItem(i)))
        return data
    
    def deserialize_tree(self, data,renumber = False):
        self.tree.setUpdatesEnabled(False)
        try:
            self.tree.clear()
            nodes = [data] if isinstance(data, dict) else data

            for node in nodes:
                self._deserialize_item(node, None)

            if renumber or self.auto_number_enabled:
                self.renumber_loaded_tree()
        finally:
            self.tree.setUpdatesEnabled(True)

        # ---- Auto expand all nodes after loading ----
        self.expand_all_animated()

    def renumber_loaded_tree(self):
        parents = [None]

        while parents:
            parent = parents.pop()
            child_parents = self._renumber_siblings(parent)
            parents.extend(reversed(child_parents))

    def _renumber_siblings(self, parent):
        if parent is None:
            items = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        else:
            items = [parent.child(i) for i in range(parent.childCount())]

        if not items:
            return []

        used_names = set()

        for item in items:
            original = item.text(0).strip()

            # remove existing numbering
            base_name = re.sub(r"\s+\d+$", "", original).strip()

            name = base_name
            n = 1

            while name in used_names:
                name = f"{base_name} {n}"
                n += 1

            item.setText(0, name)
            used_names.add(name)

        return [item for item in items if item.childCount() > 0]

    def _serialize_item(self, item):
        return {
            "name": item.text(0),
            "children": [
                self._serialize_item(item.child(i))
                for i in range(item.childCount())
            ]
        }

    def _deserialize_item(self, data, parent):
        item = self._make_tree_item(data.get("name", "Unnamed"))

        if parent:
            parent.addChild(item)
        else:
            self.tree.addTopLevelItem(item)

        stack = [
            (child, item)
            for child in reversed(data.get("children", []))
        ]

        while stack:
            child_data, child_parent = stack.pop()
            child_item = self._make_tree_item(child_data.get("name", "Unnamed"))
            child_parent.addChild(child_item)

            for grandchild in reversed(child_data.get("children", [])):
                stack.append((grandchild, child_item))

    def _make_tree_item(self, name: str):
        item = QTreeWidgetItem([name])
        item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
        return item

    def expand_all_animated(self, step_ms: int = 25, max_items: int = 2000):
        """
        Expands the tree progressively so Qt's animation is actually visible.
        step_ms: delay between expanding each item
        max_items: safety cap for huge trees
        """
        it = QTreeWidgetItemIterator(self.tree)
        items = []
        n = 0
        while it.value() and n < max_items:
            items.append(it.value())
            it += 1
            n += 1

        # Expand roots first for best visual effect
        items.sort(key=lambda i: 0 if i.parent() is None else 1)

        def tick():
            if not items:
                return

            item = items.pop(0)

            try:
                if item and item.treeWidget():
                    item.setExpanded(True)
            except RuntimeError:
                pass

            QTimer.singleShot(step_ms, tick)

        QTimer.singleShot(0, tick)

    def _count_leading_ws(self,line: str) -> Tuple[int, str]:
        """
        Returns (indent_count, stripped_line) where indent_count is the number of
        leading whitespace chars (tabs count as 1 here; we normalize later).
        """
        m = re.match(r"^([ \t]*)(.*)$", line)
        ws = m.group(1)
        text = m.group(2)
        return len(ws), text

    def parse_indented_text(self,text: str) -> List[Node]:
        """
        Parses an indented outline into a tree structure:
        - Each non-empty line is a folder name.
        - Indentation defines parent/child.
        - Supports tabs or spaces (or even mixed, but prefer consistent).
        Returns a list of root nodes (same format as your JSON templates).
        """
        # Preprocess lines: keep original indentation; drop empty/comment lines
        raw_lines = []
        for raw in text.splitlines():
            if not raw.strip():
                continue
            # optional: allow comments
            if raw.lstrip().startswith("#"):
                continue
            raw_lines.append(raw.rstrip("\n\r"))

        if not raw_lines:
            return []

        # Determine indentation unit (best-effort):
        # Find the smallest positive indent across lines (after normalization).
        # We'll treat a tab as 4 spaces for indent-unit detection only.
        indents = []
        for line in raw_lines:
            ws_len, stripped = self._count_leading_ws(line)
            if not stripped.strip():
                continue
            # normalize tabs for indent detection
            ws = line[:ws_len].replace("\t", " " * 4)
            n = len(ws)
            if n > 0:
                indents.append(n)

        indent_unit = min(indents) if indents else 4  # if everything is root-level

        roots: List[Node] = []
        stack: List[Tuple[int, Node]] = []  # (depth, node)

        for line in raw_lines:
            ws_len, name = self._count_leading_ws(line)
            name = name.strip()

            # normalize indent: tabs -> 4 spaces for depth computation
            ws_norm = line[:ws_len].replace("\t", " " * 4)
            indent_len = len(ws_norm)

            # Depth as "indent steps"
            depth = indent_len // indent_unit if indent_unit > 0 else 0

            node: Node = {"name": name, "children": []}

            if not stack:
                roots.append(node)
                stack.append((depth, node))
                continue

            # If depth is greater than last, it's a child of last
            last_depth, last_node = stack[-1]
            if depth > last_depth:
                last_node["children"].append(node)
                stack.append((depth, node))
                continue

            # Otherwise pop until we find parent depth < current depth
            while stack and stack[-1][0] >= depth:
                stack.pop()

            if not stack:
                roots.append(node)
                stack.append((depth, node))
            else:
                stack[-1][1]["children"].append(node)
                stack.append((depth, node))

        return roots
    
    def build_folders(self, base_path, timestamp_mode=None):
        base_dir = QDir(base_path)

        if self.tree.topLevelItemCount() == 0:
            return "empty", "Tree is empty."

        try:
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)

                name = item.text(0).strip()

                if timestamp_mode:
                    stamp = self._build_timestamp(timestamp_mode)
                    name = f"{name}_{stamp}"

                full_path = base_dir.filePath(name)

                if QDir(full_path).exists():
                    return "exists", "Folder structure already exists."

                base_dir.mkpath(name)

                child_dir = QDir(full_path)

                for j in range(item.childCount()):
                    self._mk_dirs(child_dir, item.child(j))

            return "success", "Folder structure created successfully."

        except Exception:
            return "error", "Error creating folder structure."

    def _build_timestamp(self, mode):
        now = datetime.now()

        if mode == "ISO":
            return now.strftime("%Y-%m-%d")

        if mode == "UK":
            return now.strftime("%d-%m-%Y")

        if mode == "US":
            return now.strftime("%m-%d-%Y")

        return ""
                        
    def _mk_dirs(self, parent_dir, item):
        name = item.text(0).strip()
        if not name:
            return

        is_file = item.data(0, Qt.UserRole) == "file"

        if is_file:
            file_path = Path(parent_dir.filePath(name))
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.touch(exist_ok=True)
            except Exception:
                pass
            return

        # folder
        parent_dir.mkpath(name)
        child_dir = QDir(parent_dir.filePath(name))

        for i in range(item.childCount()):
            self._mk_dirs(child_dir, item.child(i))
                
    def add_root_folder(self):
        default_base = "New Folder"
        
        # ---- If auto numbering OFF → just create base name ----
        if not self.auto_number_enabled:
            item = QTreeWidgetItem([default_base])
            item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)

            self.tree.addTopLevelItem(item)
            self.tree.setCurrentItem(item)   
            self.tree.editItem(item, 0)
            return

        count = self.tree.topLevelItemCount()

        if count == 0:
            base_name = default_base
        else:
            first_name = self.tree.topLevelItem(0).text(0).strip()
            base_name = first_name if first_name else default_base

        existing_names = [
            self.tree.topLevelItem(i).text(0)
            for i in range(count)
        ]

        n = 0
        name = base_name
        while name in existing_names:
            n += 1
            name = f"{base_name} {n}"

        item = QTreeWidgetItem([name])
        item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)

        self.tree.addTopLevelItem(item)
        self.tree.setCurrentItem(item)
        self.tree.editItem(item, 0)

    def add_subfolder(self):
        selected = self.tree.currentItem()
        if not selected:
            return

        # ---- force folder target ----
        if selected.data(0, Qt.UserRole) == "file":
            selected = selected.parent()

        if not selected:
            return

        default_base = "New Subfolder"
        
        # ---- If auto numbering OFF ----
        if not self.auto_number_enabled:
            child = QTreeWidgetItem([default_base])
            child.setFlags(child.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)

            selected.addChild(child)
            selected.setExpanded(True)
            self.tree.setCurrentItem(child)
            self.tree.editItem(child, 0)
            return

        count = selected.childCount()

        if count == 0:
            base_name = default_base
        else:
            first_name = selected.child(0).text(0).strip()
            base_name = first_name if first_name else default_base

        existing_names = [
            selected.child(i).text(0)
            for i in range(count)
        ]

        n = 0
        name = base_name
        while name in existing_names:
            n += 1
            name = f"{base_name} {n}"

        child = QTreeWidgetItem([name])
        child.setFlags(child.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)

        selected.addChild(child)
        selected.setExpanded(True)
        self.tree.setCurrentItem(child)
        self.tree.editItem(child, 0)
            
    def remove_all_folders(self):
        self.tree.clear()

    def remove_selected_folders(self):
        selected = self.tree.currentItem()
        if not selected:
            return

        parent = selected.parent()
        if parent:
            parent.removeChild(selected)
        else:
            index = self.tree.indexOfTopLevelItem(selected)
            self.tree.takeTopLevelItem(index)
            

    # ---------------------------------------------------------
    # Import folder tree from filesystem
    # ---------------------------------------------------------
    def import_folder_tree(self, folder_path: str):
        """
        Reads a real folder structure from disk and recreates it in the tree.
        Files are ignored.
        Generated/cache folders and unreadable folders are skipped so a
        protected pytest temp directory cannot block the import.
        """

        root = Path(folder_path)

        if not root.exists() or not root.is_dir():
            return {"imported": False, "skipped": []}

        root_item = self._make_tree_item(root.name)
        skipped_dirs = []

        self.tree.setUpdatesEnabled(False)
        try:
            self.tree.clear()
            self.tree.addTopLevelItem(root_item)

            stack = [(root, root_item, None)]

            while stack:
                current_path, current_item, parent_item = stack.pop()

                try:
                    entries = []
                    with os.scandir(current_path) as scanner:
                        for entry in scanner:
                            try:
                                if entry.name.lower() in IGNORED_IMPORT_DIRS:
                                    skipped_dirs.append(str(Path(entry.path)))
                                    continue

                                if (
                                    entry.is_dir(follow_symlinks=False)
                                ):
                                    entries.append(entry)
                            except OSError:
                                skipped_dirs.append(str(Path(entry.path)))
                                continue
                except OSError:
                    skipped_dirs.append(str(current_path))
                    if parent_item is not None:
                        parent_item.removeChild(current_item)
                    continue

                entries.sort(key=lambda entry: entry.name.lower())

                for entry in entries:
                    child_item = self._make_tree_item(entry.name)
                    current_item.addChild(child_item)
                    stack.append((Path(entry.path), child_item, current_item))

            if self.auto_number_enabled:
                self.renumber_loaded_tree()
        finally:
            self.tree.setUpdatesEnabled(True)

        self.expand_all_animated()
        return {"imported": True, "skipped": skipped_dirs}
        
    def sort_tree(self):
        """
        Alphabetically sorts the entire tree recursively.
        """

        def sort_item(parent):
            children = []
            for i in range(parent.childCount()):
                children.append(parent.takeChild(0))

            children.sort(key=lambda x: x.text(0).lower())

            for child in children:
                parent.addChild(child)
                sort_item(child)
                
        

        # ---- Sort top level items ----
        roots = []
        for i in range(self.tree.topLevelItemCount()):
            roots.append(self.tree.takeTopLevelItem(0))

        roots.sort(key=lambda x: x.text(0).lower())

        for root in roots:
            self.tree.addTopLevelItem(root)
            sort_item(root)
            
        self.expand_all_animated()
        
        # ensure something is selected
        if self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

        # refresh UI state
        window = self.tree.window()
        if hasattr(window, "update_build_button_state"):
            window.update_build_button_state()

    def add_file(self, filename="new_file.txt"):
        selected = self.tree.currentItem()
        if not selected:
            return
        
        # ---- force target to be a folder ----
        if selected.data(0, Qt.UserRole) == "file":
            parent = selected.parent()
            if parent:
                selected = parent
            else:
                return  # root-level file → do nothing

        file_item = QTreeWidgetItem([filename])
        file_item.setFlags(file_item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled)

        # mark as file (lightweight, no structural change needed)
        file_item.setData(0, Qt.UserRole, "file")

        selected.addChild(file_item)
        selected.setExpanded(True)

        self.tree.setCurrentItem(file_item)
        self.tree.editItem(file_item, 0)

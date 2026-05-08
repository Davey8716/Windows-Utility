import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent, QKeySequence, QPainter
from PySide6.QtWidgets import QApplication, QAbstractItemView, QTreeWidget

import styles


class SmartTreeWidget(QTreeWidget):

    fileDropped = Signal(str)
    addFolderShortcut = Signal()
    addSubfolderShortcut = Signal()
    saveTemplateShortcut = Signal()
    loadTemplateShortcut = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Animation method for the drag and drop functionality
        self.setAnimated(True)

        # ---- Drag & Drop configuration ----
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeWidget.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)

        # ---- Placeholder state ----
        self._placeholder = ""
        self._placeholder_bold = False
        
    def setPlaceholderText(self, text: str, bold: bool = False):
        self._placeholder = text
        self._placeholder_bold = bold
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.topLevelItemCount() != 0:
            return

        if not self._placeholder:
            return
        
        painter = QPainter(self.viewport())

        font = QFont("Segoe UI", 10)
        font.setBold(True)
        painter.setFont(font)

        painter.setPen(styles.tree_placeholder_color())

        painter.drawText(
            self.viewport().rect(),
            Qt.AlignCenter | Qt.TextWordWrap,
            self._placeholder
        )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():

            window = self.window()
            imported = False
            skipped_count = 0
            paths = []

            for url in event.mimeData().urls():
                path = url.toLocalFile()

                if not path:
                    self._set_nested_status(
                        window,
                        f"Could not read dropped item: {url.toString()}",
                        "error"
                    )
                    continue

                paths.append(Path(path))

            paths = self._normalize_dropped_paths(paths)

            for p in paths:
                suffix = p.suffix.lower()

                # ----------------------------
                # Template files (.json/.txt)
                # ----------------------------
                if p.is_file() and suffix in {".json", ".txt", ".md"}:
                    self.fileDropped.emit(str(p))
                    imported = True

                    # mimic template load behaviour
                    if self.topLevelItemCount() > 0:
                        root = self.topLevelItem(0)
                        self.setCurrentItem(root)

                    continue

                # ----------------------------
                # Folder import
                # ----------------------------
                try:
                    if p.is_dir():
                        result = window.service.nested_manager.import_folder_tree(str(p))
                        imported = True
                        skipped_count += len(result.get("skipped", [])) if result else 0

                        # select root node
                        if self.topLevelItemCount() > 0:
                            root = self.topLevelItem(0)
                            self.setCurrentItem(root)

                        self._set_nested_status(
                            window,
                            f'Imported folder tree "{p.name}".',
                            "success"
                        )
                    else:
                        self._set_nested_status(
                            window,
                            f'Dropped item is not a readable folder or template: "{p.name}"',
                            "error"
                        )

                except Exception as exc:
                    self._set_nested_status(
                        window,
                        f'Could not import "{p.name}": {exc}',
                        "error"
                    )

            if imported:
                self._refresh_nested_state(window)
                if self.topLevelItemCount() > 0:
                    root = self.topLevelItem(0)
                    message = f'Imported folder tree "{root.text(0)}".'
                    if skipped_count:
                        message = f"{message} Skipped {skipped_count} protected/generated folders."

                    self._set_nested_status(
                        window,
                        message,
                        "success"
                    )

            event.setDropAction(Qt.CopyAction)
            event.accept()

        else:
            super().dropEvent(event)

    def _refresh_nested_state(self, window):
        if hasattr(window, "ui_state"):
            window.ui_state.update_build_button_state()
            window.ui_state.update_nested_build_state()

    def _normalize_dropped_paths(self, paths):
        existing_paths = [path for path in paths if path.exists()]
        template_suffixes = {".json", ".txt", ".md"}

        if (
            len(existing_paths) > 1
            and all(path.is_file() for path in existing_paths)
            and all(path.suffix.lower() in template_suffixes for path in existing_paths)
        ):
            return existing_paths

        if len(existing_paths) > 1:
            common_parent = self._common_parent(existing_paths)
            if common_parent is not None:
                return [common_parent]

        folders = [path for path in existing_paths if path.is_dir()]
        if folders:
            return folders

        files = [path for path in existing_paths if path.is_file()]
        if not files:
            return existing_paths

        if len(files) == 1 and files[0].suffix.lower() in template_suffixes:
            return files

        common_parent = self._common_parent(files)
        return [common_parent] if common_parent is not None else files

    def _common_parent(self, paths):
        parents = []

        for path in paths:
            parents.append(path if path.is_dir() else path.parent)

        try:
            common = Path(os.path.commonpath([str(parent) for parent in parents]))
        except ValueError:
            return None

        if not common.exists() or not common.is_dir():
            return None

        return common

    def _set_nested_status(self, window, message: str, status_type: str = "info"):
        if hasattr(window, "status"):
            window.status.set(message, "nested", status_type)
        elif hasattr(window, "smart_status_text"):
            window.smart_status_text.clear()
                
    def keyPressEvent(self, event: QKeyEvent):
        window = self.window()
        
        # ---------------------------------------------------------
        # Paste indented text
        # ---------------------------------------------------------
        if event.matches(QKeySequence.Paste):
            clipboard = QApplication.clipboard()
            text = clipboard.text().strip()

            if not text:
                return

            # ---- Block JSON pastes ----
            stripped = text.lstrip()
            if stripped.startswith("{") or stripped.startswith("["):
                return

            try:
                data = window.service.nested_manager.parse_indented_text(text)

                self.clear()
                window.service.nested_manager.deserialize_tree(data)
                
                # ---- Select root item like other import methods ----
                if self.topLevelItemCount() > 0:
                    root = self.topLevelItem(0)
                    self.setCurrentItem(root)

                if hasattr(window, "update_build_button_state"):
                    window.update_build_button_state()

            except Exception:
                pass

            return
        # ---------------------------------------------------------
        # Delete key support
        # ---------------------------------------------------------
        if event.key() == Qt.Key_Delete:

            # Ignore delete if user is editing text
            if self.state() == QAbstractItemView.EditingState:
                super().keyPressEvent(event)
                return

            item = self.currentItem()

            if item:
                parent = item.parent()

                if parent:
                    parent.removeChild(item)
                else:
                    index = self.indexOfTopLevelItem(item)
                    self.takeTopLevelItem(index)

                if hasattr(window, "update_build_button_state"):
                    window.update_build_button_state()
                if hasattr(window, "update_nested_build_state"):
                    window.update_nested_build_state()

            return
        
        # ---------------------------------------------------------
        # Ctrl + N  → Add Folder
        # ---------------------------------------------------------
        if (event.modifiers() & Qt.ControlModifier) and event.key() == Qt.Key_N and not (event.modifiers() & Qt.ShiftModifier):
            self.addFolderShortcut.emit()
            return

        # ---------------------------------------------------------
        # Ctrl + Shift + N → Add Subfolder
        # ---------------------------------------------------------
        if (event.modifiers() & Qt.ControlModifier) and (event.modifiers() & Qt.ShiftModifier) and event.key() == Qt.Key_N:
            self.addSubfolderShortcut.emit()
            return

        # ---------------------------------------------------------
        # Ctrl + S → Save Template
        # ---------------------------------------------------------
        if (event.modifiers() & Qt.ControlModifier) and event.key() == Qt.Key_S:
            self.saveTemplateShortcut.emit()
            return

        # ---------------------------------------------------------
        # Ctrl + O → Load Template
        # ---------------------------------------------------------
        if (event.modifiers() & Qt.ControlModifier) and event.key() == Qt.Key_O:
            self.loadTemplateShortcut.emit()
            return

        # ---------------------------------------------------------
        # F2 → Rename
        # ---------------------------------------------------------
        if event.key() == Qt.Key_F2:
            item = self.currentItem()
            if item:
                self.editItem(item, 0)
            return

        super().keyPressEvent(event)

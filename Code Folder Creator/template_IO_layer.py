import json
import sys
import os
import sys
import shutil
from typing import Any
from PySide6.QtWidgets import QFileDialog
from pathlib import Path

class TemplatePaths:

    def __init__(self):
        self.appdata_dir = Path(os.getenv("LOCALAPPDATA")) / "FolderCreator"

        # ✅ separate folders
        self.default_dir = self.appdata_dir / "default_templates"
        self.user_dir = self.appdata_dir / "user_templates"

        self.default_dir.mkdir(parents=True, exist_ok=True)
        self.user_dir.mkdir(parents=True, exist_ok=True)

        # bundled defaults (source only)
        if getattr(sys, "frozen", False):
            self.bundle_dir = Path(sys._MEIPASS) / "Default Templates"
        else:
            self.bundle_dir = Path(__file__).resolve().parent / "Default Templates"

        self._ensure_templates()

    def _ensure_templates(self):
        if any(self.default_dir.iterdir()):
            return

        if not self.bundle_dir.exists():
            return

        for file in self.bundle_dir.glob("*.txt"):
            shutil.copy(file, self.default_dir / file.name)
    
class TemplateService:
    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------

    def save_json(self, file_path: str, data: Any) -> tuple[str, str]:
        """
        Returns (status, message)
        """

        if not file_path:
            return "cancelled", ""

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

            return "success", "Template saved successfully"

        except Exception:
            return "error", "Error saving template"
        
    def load_template(self, file_path: str, text_parser):
        """
        Loads either JSON template or indented text template.
        Returns deserialized tree data or None on failure.
        """

        path = file_path.lower()

        try:
            if path.endswith(".json"):
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)

            elif path.endswith((".txt", ".md")):
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
                return text_parser(text)

            else:
                return None  # ← don’t crash

        except Exception:
            return None  # ← safe fallback
        
    # ---------------------------------------------------------
    # Load
    # ---------------------------------------------------------

    def load_into_tree(self, parent, tree_manager):
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            "Load Template",
            "",
            "Templates (*.json *.txt);;JSON Files (*.json);;Text Outline (*.txt)"
        )

        if not file_path:
            return "cancelled", ""

        try:
            data = self.load_template(
                file_path,
                tree_manager.parse_indented_text
            )

            tree_manager.deserialize_tree(data)
            return "success", "Template loaded"

        except Exception:
            return "error", "Error loading template"

    def save_from_tree(self, parent, tree_manager):
        if tree_manager.tree.topLevelItemCount() == 0:
            return "empty", "Tree is empty."

        file_path, _ = QFileDialog.getSaveFileName(
            parent,
            "Save Template",
            "",
            "JSON Files (*.json)"
        )

        if not file_path:
            return "cancelled", ""

        data = tree_manager.serialize_tree()
        return self.save_json(file_path, data)
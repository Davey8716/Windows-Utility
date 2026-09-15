import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QFileDialog

from folder_creator.features.tree.outline_parser import parse_indented_text


class TemplatePaths:
    """Locate Folder Creator templates in the shared master backup location."""

    ROOT_FOLDER_NAME = "Folder Creator Templates"
    DEFAULT_FOLDER_NAME = "default_templates"
    USER_FOLDER_NAME = "user_templates"

    @staticmethod
    def is_readme_template(path: Path) -> bool:
        return path.name.casefold() == "readme.md"

    def __init__(self, state: dict):
        self.available = not state.get("master_backup_path_unavailable", False)
        raw_master_path = str(state.get("master_backup_output_path") or "").strip()
        self.root_dir: Path | None = (
            Path(raw_master_path) / self.ROOT_FOLDER_NAME
            if self.available and raw_master_path
            else None
        )
        self.default_dir: Path | None = None
        self.user_dir: Path | None = None
        self.legacy_appdata_dir = self._legacy_appdata_dir()

        if self.root_dir is None:
            self.available = False
            return

        self.default_dir = self.root_dir / self.DEFAULT_FOLDER_NAME
        self.user_dir = self.root_dir / self.USER_FOLDER_NAME
        self.default_dir.mkdir(parents=True, exist_ok=True)
        self.user_dir.mkdir(parents=True, exist_ok=True)

        if getattr(sys, "frozen", False):
            self.bundle_dir = Path(sys._MEIPASS) / "Default Templates"
        else:
            self.bundle_dir = Path(__file__).resolve().parents[3] / "Default Templates"

        self._migrate_legacy_templates()
        self._remove_user_template_readmes()
        self._ensure_templates()

    @staticmethod
    def _legacy_appdata_dir() -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "FolderCreator"
        return Path.home() / "AppData" / "Local" / "FolderCreator"

    def _migrate_legacy_templates(self) -> None:
        assert self.default_dir is not None and self.user_dir is not None
        for legacy_name, destination in (
            (self.DEFAULT_FOLDER_NAME, self.default_dir),
            (self.USER_FOLDER_NAME, self.user_dir),
        ):
            source = self.legacy_appdata_dir / legacy_name
            if not source.is_dir():
                continue
            for file in source.iterdir():
                if file.is_file() and not (destination / file.name).exists():
                    shutil.copy2(file, destination / file.name)

    def _ensure_templates(self) -> None:
        assert self.default_dir is not None
        if not self.bundle_dir.is_dir():
            return
        for file in self.bundle_dir.glob("*.txt"):
            destination = self.default_dir / file.name
            if not destination.exists():
                shutil.copy2(file, destination)

    def _remove_user_template_readmes(self) -> None:
        assert self.user_dir is not None
        for file in self.user_dir.iterdir():
            if file.is_file() and self.is_readme_template(file):
                file.unlink()


class TemplateService:
    def save_json(self, file_path: str, data: Any) -> tuple[str, str]:
        if not file_path:
            return "cancelled", ""
        try:
            with open(file_path, "w", encoding="utf-8") as file_obj:
                json.dump(data, file_obj, indent=4)
            return "success", "Template saved successfully"
        except Exception:
            return "error", "Error saving template"

    def load_template(self, file_path: str, text_parser):
        path = file_path.lower()
        try:
            if path.endswith(".json"):
                with open(file_path, "r", encoding="utf-8") as file_obj:
                    return json.load(file_obj)
            if path.endswith((".txt", ".md")):
                with open(file_path, "r", encoding="utf-8") as file_obj:
                    return text_parser(file_obj.read())
            return None
        except Exception:
            return None

    def load_into_tree(self, parent, tree_controller):
        file_path, _ = QFileDialog.getOpenFileName(
            parent, "Load Template", "",
            "Templates (*.json *.txt);;JSON Files (*.json);;Text Outline (*.txt)",
        )
        if not file_path:
            return "cancelled", ""
        try:
            data = self.load_template(file_path, parse_indented_text)
            tree_controller.deserialize_tree(data)
            return "success", "Template loaded"
        except Exception:
            return "error", "Error loading template"

    def save_from_tree(self, parent, tree_controller):
        if tree_controller.tree.topLevelItemCount() == 0:
            return "empty", "Tree is empty."
        file_path, _ = QFileDialog.getSaveFileName(
            parent, "Save Template", "", "JSON Files (*.json)"
        )
        if not file_path:
            return "cancelled", ""
        return self.save_json(file_path, tree_controller.serialize_tree())

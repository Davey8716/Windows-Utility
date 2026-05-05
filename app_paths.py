import sys
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from state_manager import save_state


class MasterBackupPathsMixin:
    def _get_app_module_attr(self, name: str, default):
        module = sys.modules.get(self.__class__.__module__)
        return getattr(module, name, default)

    def _get_master_backup_dir(self) -> str:
        path_type = self._get_app_module_attr("Path", Path)
        return (
            self.state.get("master_backup_output_path")
            or self.state.get("backup_output_path")
            or self.state.get("backup_folder_path")
            or str(path_type.home())
        )

    def _choose_master_backup_dir(self):
        path_type = self._get_app_module_attr("Path", Path)
        start_dir = self._get_master_backup_dir().strip() or str(path_type.home())
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Choose Master Backup Folder",
            start_dir,
        )

        if selected_dir:
            self._set_master_backup_dir(selected_dir)

    def _set_master_backup_dir(self, path: str):
        clean_path = path.strip()
        if not clean_path:
            return

        self.backup_path = clean_path
        self.state["master_backup_output_path"] = clean_path
        self.state["backup_output_path"] = clean_path
        self.state["backup_folder_path"] = clean_path

        if (
            hasattr(self, "backup_path_input")
            and self.backup_path_input.text() != clean_path
        ):
            self.backup_path_input.setText(clean_path)

        save_state_fn = self._get_app_module_attr("save_state", save_state)
        save_state_fn(self.state)

    def _build_master_output_path(self, filename: str) -> str:
        path_type = self._get_app_module_attr("Path", Path)
        base_dir = self._get_master_backup_dir().strip()
        return str(path_type(base_dir) / filename) if base_dir else filename

    def get_default_taskbar_backup_dir(self) -> str:
        path_type = self._get_app_module_attr("Path", Path)
        base_dir = self._get_master_backup_dir().strip() or str(path_type.home())
        return str(path_type(base_dir) / "TaskBarApps")

    def get_default_bookmarks_export_dir(self) -> str:
        path_type = self._get_app_module_attr("Path", Path)
        base_dir = self._get_master_backup_dir().strip() or str(path_type.home())
        return str(path_type(base_dir) / "Bookmarks")

    def get_default_desktop_layout_path(self) -> str:
        return self._build_master_output_path("desktop_icon_layout.json")

    def get_default_screenshot_path(self) -> str:
        return self._build_master_output_path("desktop_screenshot.png")

    def _refresh_taskbar_backup_folder_button(self):
        is_open = self.actions.is_backup_folder_open(
            self.get_default_taskbar_backup_dir()
        )
        self._taskbar_backup_folder_open = is_open

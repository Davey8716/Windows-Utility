import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFileDialog

from resurface.core.state_manager import save_state
from resurface.ui.tooltips import format_tooltip_text


class MasterBackupPathsMixin:
    MASTER_BACKUP_PATH_TOOLTIP_PREFIX = "Master backup folder:"

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
            def action():
                self._set_master_backup_dir(selected_dir)

            minimize_runner = getattr(self, "_run_with_optional_minimize", None)
            if callable(minimize_runner):
                minimize_runner(action)
            else:
                action()

    def _set_master_backup_dir(self, path: str):
        clean_path = path.strip()
        if not clean_path:
            return

        self.backup_path = clean_path
        self.state["master_backup_output_path"] = clean_path
        self.state["backup_output_path"] = clean_path
        self.state["backup_folder_path"] = clean_path

        self._refresh_master_backup_path_display()

        save_state_fn = self._get_app_module_attr("save_state", save_state)
        save_state_fn(self.state)

    def _get_master_backup_path_tooltip_text(self) -> str:
        full_path = self._get_master_backup_dir().strip()
        if not full_path:
            return ""
        return format_tooltip_text(
            f"{self.MASTER_BACKUP_PATH_TOOLTIP_PREFIX}\n{full_path}",
            wrap_width=160,
        )

    def _get_master_backup_path_display_text(self) -> str:
        full_path = self._get_master_backup_dir().strip()
        if not full_path:
            return ""

        display_widget = getattr(self, "backup_path_input", None)
        if display_widget is None:
            return full_path

        available_width = max(0, display_widget.width() - 24)
        if available_width <= 0:
            return full_path

        metrics = QFontMetrics(display_widget.font())
        if metrics.horizontalAdvance(full_path) <= available_width:
            return full_path

        return metrics.elidedText(
            full_path,
            Qt.TextElideMode.ElideRight,
            available_width,
        )

    def _refresh_master_backup_path_display(self) -> None:
        display_widget = getattr(self, "backup_path_input", None)
        if display_widget is None:
            return

        display_text = self._get_master_backup_path_display_text()
        if display_widget.text() != display_text:
            display_widget.setText(display_text)

        tooltip_text = self._get_master_backup_path_tooltip_text()
        if display_widget.toolTip() != tooltip_text:
            display_widget.setToolTip(tooltip_text)
        refresh_overview = getattr(self, "refresh_overview", None)
        if refresh_overview is not None:
            refresh_overview()

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
        base_path = path_type(base_dir)
        if base_path.name.lower() == "bookmarks":
            return str(base_path)
        return str(base_path / "Bookmarks")

    def get_default_desktop_layout_path(self) -> str:
        path_type = self._get_app_module_attr("Path", Path)
        base_dir = self._get_master_backup_dir().strip() or str(path_type.home())
        return str(
            path_type(base_dir) / "Desktop Icon Layout" / "desktop_icon_layout.json"
        )

    def get_default_screenshot_path(self) -> str:
        return self._build_master_output_path("desktop_screenshot.png")

    def _refresh_taskbar_backup_folder_button(self):
        is_open = self.actions.is_backup_folder_open(
            self.get_default_taskbar_backup_dir()
        )
        self._taskbar_backup_folder_open = is_open

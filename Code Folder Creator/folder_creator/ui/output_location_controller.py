import os
from pathlib import Path

from PySide6.QtWidgets import QDialog

from folder_creator.core.system_paths import get_desktop_path
from folder_creator.ui.output_directory_dialog import OutputDirectoryDialog


class OutputLocationController:
    """Own output-directory selection, persistence, and opening."""

    def __init__(self, window):
        self.window = window
        self.service = window.service

    def select_base_directory(self):
        desktop_path = get_desktop_path().resolve()
        current_path_text = self.window.base_path_line.text().strip()
        current_path = Path(current_path_text)
        start_directory = (
            current_path.resolve()
            if current_path_text and current_path.is_dir()
            else desktop_path
        )
        dialog = OutputDirectoryDialog(self.window, start_directory)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            directory = selected_files[0] if selected_files else ""
        else:
            directory = ""
        if directory:
            current_path = current_path.resolve()
            selected_path = Path(directory).resolve()
            if selected_path == desktop_path and current_path == desktop_path:
                self.window.update_build_button_state()
                self.window.status.set(
                    "Desktop is already the active output location.",
                    target="nested",
                    status_type="info",
                )
                return

            normalized = str(selected_path)
            self.window.base_path_line.setText(normalized)
            self.service.set_state("last_base_dir", normalized)
            self.window.ui_state.update_build_button_state()
            self.window.status.set(
                f"Base directory set: {normalized}",
                target="nested",
                status_type="info",
            )
            return

        current_path = current_path.resolve()
        if current_path != desktop_path:
            self.window.status.set(
                "No directory selected.", target="nested", status_type="error"
            )

    def default_to_desktop(self):
        desktop_path = get_desktop_path()
        self.window.base_path_line.setText(str(desktop_path))
        self.service.set_state("last_base_dir", str(desktop_path))
        self.window.update_build_button_state()
        self.window.status.set(
            "Base directory set to Desktop.",
            target="nested",
            status_type="info",
        )

    def open_output_folder(self, path: str):
        output_path = Path(path)
        if not output_path.exists():
            return
        try:
            os.startfile(str(output_path))
        except Exception:
            pass

    def connect_signals(self):
        self.window.output_location_btn.clicked.connect(self.select_base_directory)
        self.window.default_to_desktop_btn.clicked.connect(self.default_to_desktop)
        self.window.base_path_line.textChanged.connect(
            self.window.ui_state.update_build_button_state
        )

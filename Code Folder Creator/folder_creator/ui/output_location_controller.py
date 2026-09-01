import os
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from folder_creator.core.system_paths import get_desktop_path


class OutputLocationController:
    """Own output-directory selection, persistence, and opening."""

    def __init__(self, window):
        self.window = window
        self.service = window.service

    def select_base_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self.window, "Select Base Directory"
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

        desktop_path = get_desktop_path().resolve()
        current_path = Path(self.window.base_path_line.text().strip()).resolve()
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

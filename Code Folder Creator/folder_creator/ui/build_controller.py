from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


class BuildController:
    """Own folder builds and their persisted UI options."""

    def __init__(self, window, output_location_controller):
        self.window = window
        self.service = window.service
        self.output_location_controller = output_location_controller

    @staticmethod
    def _date_mode(text):
        if "ISO" in text:
            return "ISO"
        if "UK" in text:
            return "UK"
        if "US" in text:
            return "US"
        return "ISO"

    def nested_on_date_stamp_toggled(self, checked: bool):
        self.window.nested_date_config.setEnabled(checked)
        self.service.set_state("nested_date_stamp_enabled", checked)

    def nested_on_date_mode_changed(self, _index: int):
        self.service.set_state(
            "nested_date_stamp_mode",
            self._date_mode(self.window.nested_date_config.currentText()),
        )

    def build_folders_from_tree(self):
        base_path = self.window.base_path_line.text().strip()
        if not base_path:
            self.window.status.set(
                "No base directory selected.", target="nested", status_type="error"
            )
            return

        mode = None
        if self.window.nested_date_toggle.isChecked():
            mode = self._date_mode(self.window.nested_date_config.currentText())
            self.service.state_manager.update("nested_date_stamp_mode", mode)

        status, message = self.service.build_tree(base_path, mode)
        if status == "success":
            if self.window.open_folder_build_toggle.isChecked():
                self.output_location_controller.open_output_folder(base_path)
            if self.window.minimize_after_build_toggle.isChecked():
                QTimer.singleShot(3000, self.minimize_after_build)
            if self.window.close_app_after_build_toggle.isChecked():
                QTimer.singleShot(5000, self.close_after_build)

        self.window.status.set(
            message,
            target="nested",
            status_type="success" if status == "success" else "error",
        )

    def minimize_after_build(self):
        self.window.showMinimized()

    def close_after_build(self):
        QApplication.quit()

    def connect_signals(self):
        window = self.window
        window.minimize_after_build_toggle.toggled.connect(
            lambda checked: window.close_app_after_build_toggle.setEnabled(not checked)
        )
        window.close_app_after_build_toggle.toggled.connect(
            lambda checked: window.minimize_after_build_toggle.setEnabled(not checked)
        )
        window.close_app_after_build_toggle.setEnabled(
            not window.minimize_after_build_toggle.isChecked()
        )
        window.minimize_after_build_toggle.setEnabled(
            not window.close_app_after_build_toggle.isChecked()
        )
        window.minimize_after_build_toggle.toggled.connect(
            lambda value: self.service.state_manager.update(
                "minimize_after_build", value
            )
        )
        window.close_app_after_build_toggle.toggled.connect(
            lambda value: self.service.state_manager.update("close_after_build", value)
        )
        window.open_folder_build_toggle.toggled.connect(
            lambda value: self.service.state_manager.update(
                "open_folder_after_build", value
            )
        )
        window.nested_date_toggle.toggled.connect(self.nested_on_date_stamp_toggled)
        window.nested_date_config.currentIndexChanged.connect(
            self.nested_on_date_mode_changed
        )
        window.build_folders_btn.clicked.connect(self.build_folders_from_tree)

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox

from resurface.core.app_paths import MasterBackupPathsMixin
from resurface.ui.application_pages import ApplicationPageComposer


class PathApp(MasterBackupPathsMixin):
    def __init__(self, master_backup_path):
        self.state = {"master_backup_output_path": str(master_backup_path)}


class FakeHoverService:
    def __init__(self, *, error=None):
        self.error = error
        self.destinations = []

    def export_all_data(self, destination):
        self.destinations.append(destination)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(directory=destination / "Hover Export")


class FakeApp:
    def __init__(self, destination, response, *, export_error=None):
        self.state = {}
        self.destination = destination
        self.response = response
        self.hover_window_controls = FakeHoverService(error=export_error)
        self.modal_calls = []
        self.timed_calls = []

    def get_default_hover_controls_export_dir(self):
        return str(self.destination)

    def _show_modal_message(self, *args, **kwargs):
        self.modal_calls.append((args, kwargs))
        return self.response

    def _show_timed_message(self, *args, **kwargs):
        self.timed_calls.append((args, kwargs))


def composer_for(app):
    return ApplicationPageComposer(app, shell=None)


def test_hover_export_path_uses_dedicated_master_backup_subfolder(tmp_path):
    app = PathApp(tmp_path / "Master Backup")

    assert Path(app.get_default_hover_controls_export_dir()) == (
        tmp_path / "Master Backup" / "Hover Window Controls"
    )


def test_hover_export_confirms_then_exports_to_master_subfolder(tmp_path):
    destination = tmp_path / "Master Backup" / "Hover Window Controls"
    app = FakeApp(destination, QMessageBox.StandardButton.Save)

    composer_for(app)._export_hover_controls()

    assert app.hover_window_controls.destinations == [destination]
    assert destination.is_dir()
    assert len(app.modal_calls) == 1
    assert str(destination) in app.modal_calls[0][0][2]
    assert app.timed_calls[0][0][1] == "Hover data exported"


def test_hover_export_cancel_does_not_create_folder_or_export(tmp_path):
    destination = tmp_path / "Master Backup" / "Hover Window Controls"
    app = FakeApp(destination, QMessageBox.StandardButton.Cancel)

    composer_for(app)._export_hover_controls()

    assert not destination.exists()
    assert app.hover_window_controls.destinations == []
    assert len(app.modal_calls) == 1
    assert app.timed_calls == []


def test_hover_export_failure_uses_styled_pyside_modal(tmp_path):
    destination = tmp_path / "Master Backup" / "Hover Window Controls"
    app = FakeApp(
        destination,
        QMessageBox.StandardButton.Save,
        export_error=OSError("disk unavailable"),
    )

    composer_for(app)._export_hover_controls()

    assert len(app.modal_calls) == 2
    error_args = app.modal_calls[1][0]
    assert error_args[0] == QMessageBox.Icon.Critical
    assert error_args[1] == "Export failed"
    assert "disk unavailable" in error_args[2]
    assert app.timed_calls == []

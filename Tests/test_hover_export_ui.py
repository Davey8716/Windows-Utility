from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from resurface.core.app_paths import MasterBackupPathsMixin
from resurface.ui import styles
from resurface.ui.app_notifications import WindowMessageMixin
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


class FakeExplorerService:
    def __init__(self, *, opened=True):
        self.opened = opened
        self.paths = []

    def open_or_focus_folder(self, path):
        self.paths.append(path)
        return self.opened


class FakeApp:
    def __init__(
        self,
        destination,
        response,
        *,
        export_error=None,
        folder_opened=True,
    ):
        self.state = {}
        self.destination = destination
        self.response = response
        self.hover_window_controls = FakeHoverService(error=export_error)
        self.explorer_windows = FakeExplorerService(opened=folder_opened)
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
    assert callable(app.modal_calls[0][1]["link_activated"])
    assert app.timed_calls[0][0][1] == "Hover data exported"


def test_hover_export_path_link_creates_and_opens_destination(tmp_path):
    destination = tmp_path / "Master Backup" / "Hover Window Controls"
    app = FakeApp(destination, QMessageBox.StandardButton.Cancel)

    composer_for(app)._export_hover_controls()
    link_activated = app.modal_calls[0][1]["link_activated"]
    link_activated("open-export-destination")

    assert destination.is_dir()
    assert app.explorer_windows.paths == [str(destination)]
    assert app.hover_window_controls.destinations == []


def test_hover_export_path_is_html_escaped(tmp_path):
    destination = tmp_path / "Master & Backup" / "Hover <Controls>"
    app = FakeApp(destination, QMessageBox.StandardButton.Cancel)

    composer_for(app)._export_hover_controls()

    prompt = app.modal_calls[0][0][2]
    assert "Master &amp; Backup" in prompt
    assert "Hover &lt;Controls&gt;" in prompt
    assert f">{destination}</a>" not in prompt


def test_hover_export_path_link_uses_current_theme_color(tmp_path):
    destination = tmp_path / "Master Backup" / "Hover Window Controls"

    try:
        for is_dark, link_color in ((True, "#ffffff"), (False, "#000000")):
            styles.set_theme(is_dark)
            app = FakeApp(destination, QMessageBox.StandardButton.Cancel)

            composer_for(app)._export_hover_controls()

            prompt = app.modal_calls[0][0][2]
            assert (
                f'style="color: {link_color}; text-decoration: underline;"'
                in prompt
            )
    finally:
        styles.set_theme(True)


def test_hover_export_path_link_reports_open_failure(tmp_path):
    destination = tmp_path / "Master Backup" / "Hover Window Controls"
    app = FakeApp(
        destination,
        QMessageBox.StandardButton.Cancel,
        folder_opened=False,
    )

    composer_for(app)._export_hover_controls()
    app.modal_calls[0][1]["link_activated"]("open-export-destination")

    assert len(app.modal_calls) == 2
    assert app.modal_calls[1][0][1] == "Open export folder failed"
    assert app.hover_window_controls.destinations == []


def test_hover_export_path_link_reports_directory_creation_failure(
    monkeypatch,
    tmp_path,
):
    destination = tmp_path / "Master Backup" / "Hover Window Controls"
    app = FakeApp(destination, QMessageBox.StandardButton.Cancel)

    def fail_to_create(_path, *args, **kwargs):
        raise OSError("folder unavailable")

    monkeypatch.setattr(Path, "mkdir", fail_to_create)
    composer_for(app)._export_hover_controls()
    app.modal_calls[0][1]["link_activated"]("open-export-destination")

    assert len(app.modal_calls) == 2
    assert app.modal_calls[1][0][1] == "Open export folder failed"
    assert "folder unavailable" in app.modal_calls[1][0][2]
    assert app.explorer_windows.paths == []
    assert app.hover_window_controls.destinations == []


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


def test_modal_message_link_callback_is_wired_to_rich_text_label(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    dialogs = []
    activated = []

    class MessageHost(WindowMessageMixin, QMessageBox):
        pass

    def capture_dialog(dialog):
        dialogs.append(dialog)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "exec", capture_dialog)
    host = MessageHost()
    try:
        styles.set_theme(True)
        host._show_modal_message(
            QMessageBox.Icon.NoIcon,
            "Linked message",
            '<a href="destination">Destination</a>',
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
            link_activated=activated.append,
        )

        label = dialogs[0].findChild(QLabel, "qt_msgbox_label")
        assert label.textFormat() == Qt.TextFormat.RichText
        assert (
            label.textInteractionFlags()
            & Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        assert not label.openExternalLinks()
        assert dialogs[0].styleSheet() == styles.message_box_style()
        assert label.palette().color(QPalette.ColorRole.Link).name() == "#ffffff"
        assert label.palette().color(QPalette.ColorRole.LinkVisited).name() == "#ffffff"

        label.linkActivated.emit("destination")
        assert activated == ["destination"]
    finally:
        styles.set_theme(True)
        host.close()
        host.deleteLater()
        qt_app.processEvents()

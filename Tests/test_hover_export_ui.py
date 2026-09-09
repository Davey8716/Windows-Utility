from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox

from resurface.core.app_paths import MasterBackupPathsMixin
from resurface.ui import application_pages, styles
from resurface.ui.app_notifications import WindowMessageMixin
from resurface.ui.application_pages import ApplicationPageComposer
from resurface.ui.pages.hover_window_controls_page import HoverWindowControlsPage


class PathApp(MasterBackupPathsMixin):
    def __init__(self, master_backup_path):
        self.state = {"master_backup_output_path": str(master_backup_path)}


class FakeHoverService:
    def __init__(self, *, error=None, result=True):
        self.error = error
        self.result = result
        self.destinations = []
        self.has_changes = True

    def has_export_changes(self, _destination):
        return self.has_changes

    def export_all_data(self, destination):
        self.destinations.append(destination)
        if self.error is not None:
            raise self.error
        if not self.result:
            return None
        return SimpleNamespace(directory=destination)


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
        export_result=True,
        folder_opened=True,
    ):
        self.state = {}
        self.destination = destination
        self.response = response
        self.hover_window_controls = FakeHoverService(
            error=export_error,
            result=export_result,
        )
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


def test_hover_export_button_reflects_change_callback():
    qt_app = QApplication.instance() or QApplication([])
    changes = [False]
    page = HoverWindowControlsPage(
        {},
        lambda *_args: None,
        has_export_changes=lambda: changes[-1],
    )
    try:
        assert not page.export_button.isEnabled()
        assert page.export_button.property("lightModeBlackDisabledText") is True

        changes.append(True)
        page.sync_settings(True, True, 750)
        assert page.export_button.isEnabled()

        def fail_comparison():
            raise OSError("backup unavailable")

        page._has_export_changes = fail_comparison
        page.refresh_export_button()
        assert page.export_button.isEnabled()
    finally:
        page.close()
        page.deleteLater()
        qt_app.processEvents()


def test_hover_export_button_starts_enabled_when_data_has_changed():
    qt_app = QApplication.instance() or QApplication([])
    page = HoverWindowControlsPage(
        {},
        lambda *_args: None,
        has_export_changes=lambda: True,
    )
    try:
        assert page.export_button.isEnabled()
    finally:
        page.close()
        page.deleteLater()
        qt_app.processEvents()


def test_dwell_dropdown_matches_and_aligns_with_hover_toggle():
    qt_app = QApplication.instance() or QApplication([])
    page = HoverWindowControlsPage({}, lambda *_args: None)
    try:
        page.resize(800, page.sizeHint().height())
        page.show()
        qt_app.processEvents()

        assert page.dwell_combo.width() == page.enabled_button.width()
        assert page.dwell_combo.width() == page.LEFT_CONTROL_COLUMN_WIDTH
        assert page.dwell_combo.mapTo(page, QPoint()).x() == (
            page.enabled_button.mapTo(page, QPoint()).x()
        )
        assert page.dwell_combo.parentWidget() is page.dwell_row
        assert page.dwell_row.width() == page.CONTROL_ROW_WIDTH

        page.dwell_combo.setCurrentIndex(page.dwell_combo.findData(1250))
        assert page.dwell_combo.currentData() == 1250
        page.sync_settings(True, True, 1750)
        assert page.dwell_combo.currentData() == 1750
    finally:
        page.close()
        page.deleteLater()
        qt_app.processEvents()


def test_unchanged_hover_data_skips_export_confirmation(tmp_path):
    destination = tmp_path / "Hover Window Controls"
    app = FakeApp(destination, QMessageBox.StandardButton.Save)
    app.hover_window_controls.has_changes = False

    composer_for(app)._export_hover_controls()

    assert app.modal_calls == []
    assert app.hover_window_controls.destinations == []


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
    assert (
        app.modal_calls[0][1]["popup_corner_radius"]
        == styles.BUTTON_CORNER_RADIUS
    )
    assert app.timed_calls[0][0][1] == "Hover data exported"
    assert str(destination) in app.timed_calls[0][0][2]
    assert (
        app.timed_calls[0][1]["popup_corner_radius"]
        == styles.BUTTON_CORNER_RADIUS
    )


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


def test_hover_export_failure_uses_styled_timed_message(tmp_path):
    destination = tmp_path / "Master Backup" / "Hover Window Controls"
    app = FakeApp(
        destination,
        QMessageBox.StandardButton.Save,
        export_error=OSError("disk unavailable"),
    )

    composer_for(app)._export_hover_controls()

    assert len(app.modal_calls) == 1
    assert len(app.timed_calls) == 1
    error_args = app.timed_calls[0][0]
    assert error_args[0] == QMessageBox.Icon.Critical
    assert error_args[1] == "Export failed"
    assert "disk unavailable" in error_args[2]
    assert (
        app.timed_calls[0][1]["popup_corner_radius"]
        == styles.BUTTON_CORNER_RADIUS
    )
    assert app.timed_calls[0][1]["timeout_ms"] == 10_000
    assert app.timed_calls[0][1]["show_close_now_button"] is True


def test_unchanged_hover_data_does_not_show_exported_message(tmp_path):
    destination = tmp_path / "Master Backup" / "Hover Window Controls"
    app = FakeApp(
        destination,
        QMessageBox.StandardButton.Save,
        export_result=False,
    )

    composer_for(app)._export_hover_controls()

    assert app.hover_window_controls.destinations == [destination]
    assert app.timed_calls == []


def test_hover_import_selects_validates_confirms_and_imports(
    monkeypatch,
    tmp_path,
):
    destination = tmp_path / "Master Backup" / "Hover Window Controls"
    manifest = destination / "export_manifest.json"
    validated = []
    imported = []

    class FakeFileDialog:
        class Option:
            DontUseNativeDialog = object()

        class FileMode:
            ExistingFile = object()

        class AcceptMode:
            AcceptOpen = object()

        def __init__(self, *_args):
            pass

        def setOption(self, *_args):
            pass

        def setFileMode(self, *_args):
            pass

        def setAcceptMode(self, *_args):
            pass

        def setWindowFlag(self, *_args):
            pass

        def setStyleSheet(self, *_args):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def selectedFiles(self):
            return [str(manifest)]

    monkeypatch.setattr(application_pages, "QFileDialog", FakeFileDialog)
    app = FakeApp(destination, QMessageBox.StandardButton.Yes)
    app.hover_window_controls.validate_import = validated.append

    def import_data(source):
        imported.append(source)
        return SimpleNamespace(source_directory=source)

    app.hover_window_controls.import_all_data = import_data

    composer_for(app)._import_hover_controls()

    assert validated == [destination]
    assert imported == [destination]
    assert app.modal_calls[0][0][1] == "Import Hover Data"
    assert (
        app.modal_calls[0][1]["popup_corner_radius"]
        == styles.BUTTON_CORNER_RADIUS
    )
    assert app.timed_calls[0][0][1] == "Hover data imported"
    assert str(destination) in app.timed_calls[0][0][2]
    assert (
        app.timed_calls[0][1]["popup_corner_radius"]
        == styles.BUTTON_CORNER_RADIUS
    )


def test_hover_import_cancel_does_not_replace_data(monkeypatch, tmp_path):
    destination = tmp_path / "Hover Window Controls"

    class CancelledFileDialog:
        class Option:
            DontUseNativeDialog = object()

        class FileMode:
            ExistingFile = object()

        class AcceptMode:
            AcceptOpen = object()

        def __init__(self, *_args):
            pass

        def setOption(self, *_args):
            pass

        def setFileMode(self, *_args):
            pass

        def setAcceptMode(self, *_args):
            pass

        def setWindowFlag(self, *_args):
            pass

        def setStyleSheet(self, *_args):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(application_pages, "QFileDialog", CancelledFileDialog)
    app = FakeApp(destination, QMessageBox.StandardButton.Yes)

    composer_for(app)._import_hover_controls()

    assert app.modal_calls == []
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
            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
        )

        label = dialogs[0].findChild(QLabel, "qt_msgbox_label")
        assert label.textFormat() == Qt.TextFormat.RichText
        assert (
            label.textInteractionFlags()
            & Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        assert not label.openExternalLinks()
        assert dialogs[0]._popup_corner_radius == styles.BUTTON_CORNER_RADIUS
        assert dialogs[0].styleSheet() == styles.message_box_style(
            radius=styles.BUTTON_CORNER_RADIUS
        )
        qt_app.processEvents()
        assert not dialogs[0].mask().isEmpty()
        assert label.palette().color(QPalette.ColorRole.Link).name() == "#ffffff"
        assert label.palette().color(QPalette.ColorRole.LinkVisited).name() == "#ffffff"

        label.linkActivated.emit("destination")
        assert activated == ["destination"]
    finally:
        styles.set_theme(True)
        host.close()
        host.deleteLater()
        qt_app.processEvents()

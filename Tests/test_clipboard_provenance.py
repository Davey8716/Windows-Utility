from datetime import datetime
import json
from pathlib import Path

from PySide6.QtCore import QMimeData, QObject, Qt, QUrl, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QMessageBox,
    QToolButton,
)

from resurface.features import clipboard_provenance as provenance
from resurface.ui import styles
from resurface.ui.clipboard_provenance_page import (
    ClipboardClearConfirmationDialog,
    ClipboardExportDeleteConfirmationDialog,
    ClipboardProvenancePage,
)
from resurface.ui.tooltips import tooltip_text


class FakeClipboard(QObject):
    dataChanged = Signal()

    def __init__(self):
        super().__init__()
        self.mime = QMimeData()

    def mimeData(self):
        return self.mime


def make_service(state=None, clipboard=None, source=None):
    saves = []
    service = provenance.ClipboardProvenanceService(
        state if state is not None else {},
        lambda value: saves.append(value.copy()),
        clipboard=clipboard or FakeClipboard(),
        source_provider=source or (lambda: {"program_name": "Editor"}),
        now=lambda: datetime(2025, 1, 2, 3, 4, 5),
    )
    return service, saves


def test_clipboard_provenance_uses_shared_control_and_card_spacing():
    app = QApplication.instance() or QApplication([])
    service, _saves = make_service()
    service._append({"content_type": "text", "text": "record"})
    page = ClipboardProvenancePage(
        None, service=service, get_master_backup_dir=lambda: ""
    )
    try:
        page.show()
        app.processEvents()
        panel_layout = page.panel.layout()
        controls = panel_layout.itemAt(0).layout()
        assert page.layout().spacing() == styles.PAGE_CONTROL_ROW_GAP
        assert panel_layout.spacing() == styles.PAGE_CONTROL_ROW_GAP
        assert controls.spacing() == styles.PAGE_CONTROL_GAP
        assert page.history_layout.spacing() == styles.PAGE_CONTROL_ROW_GAP
        assert page.recording_button.x() == styles.PAGE_CONTROL_GAP
        assert [
            controls.itemAt(index).widget().text()
            for index in range(controls.count())
        ] == ["Recording: Off", "Export History", "Clear All", "Delete All"]
        assert page.panel.width() - page.delete_exports_button.geometry().right() - 1 == (
            styles.PAGE_CONTROL_GAP
        )
    finally:
        page.deleteLater()


def test_records_text_only_while_enabled():
    clipboard = FakeClipboard()
    service, saves = make_service(clipboard=clipboard)
    service.start()
    clipboard.mime.setText("secret copied text")
    clipboard.dataChanged.emit()
    assert service.history == []

    service.set_enabled(True)
    clipboard.dataChanged.emit()
    record = service.history[0]
    assert record["content_type"] == "text"
    assert record["text"] == "secret copied text"
    assert record["source"]["program_name"] == "Editor"
    assert record["timestamp"].startswith("2025-01-02T03:04:05")
    assert saves
    service.stop()


def test_ignores_file_copies_and_empty_content():
    clipboard = FakeClipboard()
    service, _saves = make_service(clipboard=clipboard)
    service.set_enabled(True)
    service.start()
    clipboard.mime.setUrls([QUrl.fromLocalFile(r"C:\Reports\one.txt")])
    clipboard.dataChanged.emit()
    assert service.history == []

    clipboard.mime = QMimeData()
    clipboard.dataChanged.emit()
    assert service.history == []
    service.stop()


def test_history_is_capped_and_delete_clear_persist():
    service, saves = make_service()
    for index in range(102):
        service._append({"content_type": "text", "text": str(index)})
    assert len(service.history) == provenance.HISTORY_LIMIT
    assert service.history[0]["text"] == "2"
    service.delete(service.history[0]["id"])
    assert len(service.history) == 99
    service.clear()
    assert service.history == []
    assert saves


def test_extracts_unique_http_urls_and_ignores_non_web_schemes():
    text = (
        "Read https://example.com/docs, then http://example.org/a. "
        "Repeat https://example.com/docs and ignore mailto:test@example.com."
    )
    assert provenance.extract_web_urls(text) == [
        "https://example.com/docs",
        "http://example.org/a",
    ]


def test_normalizes_legacy_records_to_program_names_and_urls():
    records = provenance.normalize_history([
        {
            "id": "text", "timestamp": "now", "content_type": "text",
            "text": "See https://example.com.",
            "source": {"executable": r"C:\Program Files\Browser\browser.exe"},
        },
        {
            "id": "file", "timestamp": "then", "content_type": "files",
            "files": [r"C:\Reports\one.txt"], "source": {"process_name": "Explorer.exe"},
        },
    ])
    assert records[0]["source"]["program_name"] == "browser"
    assert records[0]["urls"] == ["https://example.com"]
    assert records[1]["content_type"] == "files"
    assert records[1]["source"]["program_name"] == "Explorer.exe"


def test_repository_exports_versioned_json(tmp_path):
    repository = provenance.ClipboardProvenanceRepository(
        lambda: str(tmp_path), now=lambda: datetime(2025, 1, 2, 3, 4, 5, 6)
    )
    path = repository.export_history([
        {"id": "one", "timestamp": "2025-01-02T03:04:05+00:00", "content_type": "text", "text": "hello https://example.com", "source": {"program_name": "Browser"}},
    ])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path.parent == tmp_path / "Clipboard Provenance"
    assert payload["format"] == provenance.BACKUP_FORMAT
    assert payload["version"] == provenance.BACKUP_VERSION
    assert payload["records"][0]["text"] == "hello https://example.com"
    assert payload["records"][0]["urls"] == ["https://example.com"]
    assert not repository.has_export_changes(payload["records"])
    assert repository.has_export_changes([
        *payload["records"],
        {"id": "two", "timestamp": "later", "content_type": "text", "text": "new", "source": {}},
    ])


def test_repository_ignores_invalid_newer_backup(tmp_path):
    history = [{"id": "one", "timestamp": "now", "content_type": "text", "text": "same", "source": {}}]
    repository = provenance.ClipboardProvenanceRepository(
        lambda: str(tmp_path), now=lambda: datetime(2025, 1, 2, 3, 4, 5, 6)
    )
    repository.export_history(history)
    invalid = tmp_path / "Clipboard Provenance" / "clipboard_provenance_20250103_030405_000006.json"
    invalid.write_text("not json", encoding="utf-8")
    assert not repository.has_export_changes(history)


def test_repository_deletes_only_app_managed_exports(tmp_path):
    repository = provenance.ClipboardProvenanceRepository(
        lambda: str(tmp_path), now=lambda: datetime(2025, 1, 2, 3, 4, 5, 6)
    )
    exported = repository.export_history([])
    folder = exported.parent
    unrelated = folder / "notes.json"
    unrelated.write_text("keep me", encoding="utf-8")
    nested = folder / "clipboard_provenance_20250103_030405_000006.json"
    nested.mkdir()

    assert repository.export_paths() == [exported]
    assert repository.delete_exports() == 1
    assert not exported.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep me"
    assert nested.is_dir()


def test_delete_exports_button_reflects_matching_backup_files(tmp_path):
    app = QApplication.instance() or QApplication([])
    service, _saves = make_service()
    page = ClipboardProvenancePage(
        None, service=service, get_master_backup_dir=lambda: str(tmp_path)
    )
    try:
        assert not page.delete_exports_button.isEnabled()
        repository = provenance.ClipboardProvenanceRepository(lambda: str(tmp_path))
        repository.export_history([])
        page._render_history(service.history)
        assert page.delete_exports_button.isEnabled()
    finally:
        page.deleteLater()
        app.processEvents()


def test_page_exports_history_renders_inline_links_and_top_right_delete(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    service, _saves = make_service()
    service._append({"content_type": "text", "text": "complete clipboard item https://example.com"})
    page = ClipboardProvenancePage(
        None,
        service=service,
        get_master_backup_dir=lambda: str(tmp_path),
        open_backup_folder=lambda _path: True,
    )
    exported = []
    modal_calls = []
    page._show_modal_message = lambda *_args, **kwargs: modal_calls.append(kwargs) or QMessageBox.StandardButton.Save
    page._show_timed_message = lambda *args, **kwargs: exported.append((args, kwargs))
    try:
        assert page.export_button.isEnabled()
        link_label = next(
            label for label in page.findChildren(QLabel)
            if 'href="https://example.com"' in label.text()
        )
        opened = []
        monkeypatch.setattr(
            "resurface.ui.clipboard_provenance_page.QDesktopServices.openUrl",
            lambda url: opened.append(url.toString()) or True,
        )
        link_label.linkActivated.emit("https://example.com")
        assert opened == ["https://example.com"]
        assert any(
            label.text() == "Source program: Editor" for label in page.findChildren(QLabel)
        )
        assert any(button.text() == "×" for button in page.findChildren(QToolButton))
        assert not any(
            button.text().startswith("Open source:")
            for button in page.findChildren(type(page.export_button))
        )
        page._export_history()
        files = list((tmp_path / "Clipboard Provenance").glob("*.json"))
        assert len(files) == 1
        assert exported
        message = exported[0][0][2]
        message_lines = message.splitlines()
        assert message_lines[0] == "Clipboard provenance was exported to:"
        assert len(message_lines) >= 3
        assert "".join(message_lines[1:]) == str(files[0])
        assert exported[0][1]["fixed_popup_width"] == 380
        assert exported[0][1]["center_text_block"] is True
        assert modal_calls[0]["popup_corner_radius"] == styles.BUTTON_CORNER_RADIUS
        assert exported[0][1]["popup_corner_radius"] == styles.BUTTON_CORNER_RADIUS
        assert not page.export_button.isEnabled()
    finally:
        page.deleteLater()
        app.processEvents()


def test_page_registers_export_and_clear_history_tooltips():
    app = QApplication.instance() or QApplication([])
    service, _saves = make_service()
    registered = {}
    page = ClipboardProvenancePage(
        None,
        service=service,
        get_master_backup_dir=lambda: "",
        register_tooltip=lambda widget, text: registered.__setitem__(widget, text),
    )
    try:
        assert registered[page.export_button] == tooltip_text("clipboard_provenance_export")
        assert registered[page.clear_button] == tooltip_text("clipboard_provenance_clear")
        assert registered[page.delete_exports_button] == tooltip_text(
            "clipboard_provenance_delete_exports"
        )
    finally:
        page.deleteLater()
        app.processEvents()


def test_empty_history_actions_use_black_disabled_text_in_light_mode():
    app = QApplication.instance() or QApplication([])
    service, _saves = make_service()
    styles.set_theme(False)
    page = ClipboardProvenancePage(
        None, service=service, get_master_backup_dir=lambda: ""
    )
    try:
        assert not service.enabled
        for button in (page.export_button, page.clear_button):
            assert not button.isEnabled()
            assert button.property("lightModeBlackDisabledText") is True
            assert 'QPushButton[lightModeBlackDisabledText="true"]:disabled' in (
                button.styleSheet()
            )
            assert "color: #000000;" in button.styleSheet()

        assert not page.delete_exports_button.isEnabled()
        assert page.delete_exports_button.property("quickActionSeverity") == "red"
        assert page.delete_exports_button.property("lightModeBlackText") is True
        assert (
            f"background-color: {styles.power_action_color('red').name()};"
            in page.delete_exports_button.styleSheet()
        )
        assert "QPushButton:disabled" in page.delete_exports_button.styleSheet()

        styles.set_theme(True)
        assert 'QPushButton[lightModeBlackDisabledText="true"]:disabled' not in (
            styles.organizing_button_style(12)
        )
    finally:
        styles.set_theme(True)
        page.deleteLater()
        app.processEvents()


def test_export_success_text_wraps_a_long_path_without_clipping_it():
    app = QApplication.instance() or QApplication([])
    service, _saves = make_service()
    page = ClipboardProvenancePage(
        None, service=service, get_master_backup_dir=lambda: ""
    )
    path = Path(
        r"C:\Users\davey\Desktop\Windows Resurface Backup\Clipboard Provenance\clipboard_provenance_20260914_203017_354088.json"
    )
    try:
        message_lines = page._format_export_success_text(path).splitlines()

        assert message_lines[0] == "Clipboard provenance was exported to:"
        assert len(message_lines) > 3
        assert "".join(message_lines[1:]) == str(path)
        assert max(
            page.fontMetrics().horizontalAdvance(line)
            for line in message_lines[1:]
        ) <= 330
    finally:
        page.deleteLater()
        app.processEvents()


def test_clear_confirmation_matches_the_frameless_hover_import_dialog():
    app = QApplication.instance() or QApplication([])
    dialog = ClipboardClearConfirmationDialog()

    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert not dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert dialog.mask().isEmpty()
    assert not dialog.isSizeGripEnabled()
    assert dialog.minimumSize() == dialog.maximumSize()
    assert dialog.icon() == QMessageBox.Icon.NoIcon
    text_label = dialog.findChild(QLabel, "qt_msgbox_label")
    assert text_label is not None
    assert text_label.alignment() & Qt.AlignmentFlag.AlignHCenter
    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box is not None
    assert button_box.centerButtons()
    assert (
        dialog.standardButton(dialog.defaultButton())
        == QMessageBox.StandardButton.Cancel
    )
    dialog.deleteLater()
    app.processEvents()


def test_clear_confirmation_only_clears_history_after_yes(monkeypatch):
    app = QApplication.instance() or QApplication([])
    service, _saves = make_service()
    service._append({"content_type": "text", "text": "record"})
    page = ClipboardProvenancePage(
        None, service=service, get_master_backup_dir=lambda: ""
    )
    try:
        monkeypatch.setattr(
            ClipboardClearConfirmationDialog,
            "exec",
            lambda _dialog: QMessageBox.StandardButton.Cancel,
        )
        page._clear_history()
        assert service.history

        monkeypatch.setattr(
            ClipboardClearConfirmationDialog,
            "exec",
            lambda _dialog: QMessageBox.StandardButton.Yes,
        )
        page._clear_history()
        assert service.history == []
    finally:
        page.deleteLater()
        app.processEvents()


def test_delete_exports_confirmation_and_action_keep_local_history(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    service, _saves = make_service()
    service._append({"content_type": "text", "text": "local record"})
    repository = provenance.ClipboardProvenanceRepository(lambda: str(tmp_path))
    first = repository.export_history([])
    second = repository.export_history([])
    unrelated = first.parent / "readme.txt"
    unrelated.write_text("keep", encoding="utf-8")
    page = ClipboardProvenancePage(
        None, service=service, get_master_backup_dir=lambda: str(tmp_path)
    )
    try:
        dialog_text = []
        monkeypatch.setattr(
            ClipboardExportDeleteConfirmationDialog,
            "exec",
            lambda dialog: dialog_text.append(dialog.text()) or QMessageBox.StandardButton.Cancel,
        )
        page._delete_exports()
        assert first.exists() and second.exists()
        assert "2 exported Clipboard Provenance files" in dialog_text[0]

        monkeypatch.setattr(
            ClipboardExportDeleteConfirmationDialog,
            "exec",
            lambda _dialog: QMessageBox.StandardButton.Yes,
        )
        page._delete_exports()
        assert not first.exists() and not second.exists()
        assert unrelated.read_text(encoding="utf-8") == "keep"
        assert service.history[0]["text"] == "local record"
        assert not page.delete_exports_button.isEnabled()
    finally:
        page.deleteLater()
        app.processEvents()


def test_delete_exports_reports_filesystem_failure(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    service, _saves = make_service()
    repository = provenance.ClipboardProvenanceRepository(lambda: str(tmp_path))
    exported = repository.export_history([])
    page = ClipboardProvenancePage(
        None, service=service, get_master_backup_dir=lambda: str(tmp_path)
    )
    warnings = []
    try:
        monkeypatch.setattr(
            ClipboardExportDeleteConfirmationDialog,
            "exec",
            lambda _dialog: QMessageBox.StandardButton.Yes,
        )
        monkeypatch.setattr(
            page._repository,
            "delete_exports",
            lambda: (_ for _ in ()).throw(OSError("access denied")),
        )
        monkeypatch.setattr(
            "resurface.ui.clipboard_provenance_page.QMessageBox.warning",
            lambda *_args: warnings.append(_args),
        )

        page._delete_exports()

        assert exported.exists()
        assert warnings
        assert "Could not delete all exported clipboard provenance files" in warnings[0][2]
        assert page.delete_exports_button.isEnabled()
    finally:
        page.deleteLater()
        app.processEvents()


def test_page_renders_url_only_copy_as_a_single_underlined_link():
    app = QApplication.instance() or QApplication([])
    service, _saves = make_service()
    service._append({"content_type": "text", "text": "https://example.com/docs"})
    page = ClipboardProvenancePage(
        None, service=service, get_master_backup_dir=lambda: ""
    )
    try:
        links = [
            label for label in page.findChildren(QLabel)
            if 'href="https://example.com/docs"' in label.text()
        ]
        assert len(links) == 1
        assert "<a href=" in links[0].text()
    finally:
        page.deleteLater()
        app.processEvents()


def test_page_renders_text_and_file_records_as_rounded_cards():
    app = QApplication.instance() or QApplication([])
    service, _saves = make_service()
    service._append({"content_type": "text", "text": "record"})
    service._append({"content_type": "files", "files": [r"C:\\Reports\\one.txt"]})
    page = ClipboardProvenancePage(
        None, service=service, get_master_backup_dir=lambda: ""
    )
    try:
        cards = page.findChildren(QFrame, "ClipboardProvenanceRecordCard")
        assert len(cards) == 2
        for card in cards:
            assert f"background-color: {styles.qcolor_css(styles.WINDOW_BG)}" in card.styleSheet()
            assert "border: 1px solid" in card.styleSheet()
            assert "border-radius: 8px" in card.styleSheet()
    finally:
        page.deleteLater()
        app.processEvents()


def test_provenance_link_color_tracks_theme():
    app = QApplication.instance() or QApplication([])
    service, _saves = make_service()
    service._append({"content_type": "text", "text": "https://example.com"})
    page = ClipboardProvenancePage(
        None, service=service, get_master_backup_dir=lambda: ""
    )
    try:
        styles.set_theme(True)
        page.refresh_theme()
        dark_link = [
            label for label in page.findChildren(QLabel)
            if 'href="https://example.com"' in label.text()
        ][-1]
        assert "color: #ffffff" in dark_link.text()
        styles.set_theme(False)
        page.refresh_theme()
        light_link = [
            label for label in page.findChildren(QLabel)
            if 'href="https://example.com"' in label.text()
        ][-1]
        assert "color: #000000" in light_link.text()
    finally:
        styles.set_theme(True)
        page.deleteLater()
        app.processEvents()

from datetime import datetime
import json

from PySide6.QtCore import QMimeData, QObject, Qt, QUrl, Signal
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QMessageBox, QToolButton

from resurface.features import clipboard_provenance as provenance
from resurface.ui import styles
from resurface.ui.clipboard_provenance_page import (
    ClipboardClearConfirmationDialog,
    ClipboardProvenancePage,
)


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
    page._show_timed_message = lambda *_args, **kwargs: exported.append(kwargs)
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
        assert modal_calls[0]["popup_corner_radius"] == styles.BUTTON_CORNER_RADIUS
        assert exported[0]["popup_corner_radius"] == styles.BUTTON_CORNER_RADIUS
        assert not page.export_button.isEnabled()
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
            assert "background-color:" in card.styleSheet()
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

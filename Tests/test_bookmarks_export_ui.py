from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from resurface.ui.controllers import organising_actions
from resurface.ui.controllers.organising_actions import OrganisingActionsController


class FakeExporter:
    def __init__(self, browser_name, *, has_bookmarks=True, succeeds=True):
        self.output_filename = f"{browser_name}_Bookmarks.html"
        self.browser_name = browser_name
        self._has_bookmarks = has_bookmarks
        self._succeeds = succeeds
        self.export_calls = []

    def has_bookmarks(self): return self._has_bookmarks

    def export_to_file(self, out_path):
        self.export_calls.append(out_path)
        if not self._succeeds:
            return False
        Path(out_path).write_text(f"{self.browser_name} replacement", encoding="utf-8")
        return True


class FakeApp:
    def __init__(self, export_dir, response):
        self.export_dir = export_dir
        self.response = response
        self.state = {}
        self.modal_calls = []
        self.minimize_calls = 0

    def get_default_bookmarks_export_dir(self): return str(self.export_dir)
    def _show_modal_message(self, *args):
        self.modal_calls.append(args)
        return self.response
    def showMinimized(self): self.minimize_calls += 1


def run_export(monkeypatch, tmp_path, exporters, response):
    monkeypatch.setattr(organising_actions.BraveBookmarksExporter, "supported_exporters", lambda: exporters)
    saved_states = []
    monkeypatch.setattr(organising_actions, "save_state", lambda state: saved_states.append(state))
    app = FakeApp(tmp_path / "Bookmarks", response)
    result = OrganisingActionsController(app, None, None, None).run_bookmarks_export()
    return result, app, saved_states


def test_bulk_export_writes_three_detected_browsers_after_one_prompt(monkeypatch, tmp_path):
    exporters = [FakeExporter("Brave"), FakeExporter("Chrome"), FakeExporter("Edge")]
    result, app, states = run_export(monkeypatch, tmp_path, exporters, QMessageBox.StandardButton.Save)
    expected = [str(app.export_dir / exporter.output_filename) for exporter in exporters]
    assert result == expected
    assert len(app.modal_calls) == 1 and app.minimize_calls == 1 and states == [app.state]
    assert all(path in app.modal_calls[0][2] for path in expected)
    assert all(exporter.export_calls == [path] for exporter, path in zip(exporters, expected))


def test_bulk_export_overwrites_existing_and_creates_new_files(monkeypatch, tmp_path):
    exporters = [FakeExporter("Brave"), FakeExporter("Chrome")]
    export_dir = tmp_path / "Bookmarks"
    export_dir.mkdir()
    existing = export_dir / exporters[0].output_filename
    existing.write_text("old content", encoding="utf-8")
    result, app, _ = run_export(monkeypatch, tmp_path, exporters, QMessageBox.StandardButton.Save)
    assert result == [str(export_dir / exporter.output_filename) for exporter in exporters]
    assert existing.read_text(encoding="utf-8") == "Brave replacement"
    assert "will be overwritten" in app.modal_calls[0][2]


def test_bulk_export_cancel_leaves_destinations_unchanged(monkeypatch, tmp_path):
    exporter = FakeExporter("Brave")
    export_dir = tmp_path / "Bookmarks"
    export_dir.mkdir()
    existing = export_dir / exporter.output_filename
    existing.write_text("keep this", encoding="utf-8")
    result, app, states = run_export(monkeypatch, tmp_path, [exporter], QMessageBox.StandardButton.Cancel)
    assert result is None and existing.read_text(encoding="utf-8") == "keep this"
    assert exporter.export_calls == [] and app.minimize_calls == 0 and states == []


def test_bulk_export_returns_false_without_detected_bookmarks(monkeypatch, tmp_path):
    result, app, states = run_export(monkeypatch, tmp_path, [FakeExporter("Brave", has_bookmarks=False)], QMessageBox.StandardButton.Save)
    assert result is False and app.modal_calls == [] and app.minimize_calls == 0 and states == []


def test_bulk_export_returns_false_when_every_export_fails(monkeypatch, tmp_path):
    exporters = [FakeExporter("Brave", succeeds=False), FakeExporter("Chrome", succeeds=False)]
    result, app, states = run_export(monkeypatch, tmp_path, exporters, QMessageBox.StandardButton.Save)
    assert result is False and len(app.modal_calls) == 1 and app.minimize_calls == 1
    assert all(len(exporter.export_calls) == 1 for exporter in exporters) and states == []

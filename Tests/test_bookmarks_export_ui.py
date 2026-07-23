from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox

import right_utility_gui
from right_utility_gui import AdvancedToolsPanel


class FakeExporter:
    def __init__(self, browser_name, *, has_bookmarks=True, succeeds=True):
        self.browser_name = browser_name
        self.output_filename = f"{browser_name}_Bookmarks.html"
        self._has_bookmarks = has_bookmarks
        self._succeeds = succeeds
        self.export_calls = []

    def has_bookmarks(self):
        return self._has_bookmarks

    def export_to_file(self, out_path):
        self.export_calls.append(out_path)
        if not self._succeeds:
            return False
        Path(out_path).write_text(
            f"{self.browser_name} replacement",
            encoding="utf-8",
        )
        return True


class FakeApp:
    def __init__(self, export_dir, response):
        self.export_dir = export_dir
        self.response = response
        self.state = {}
        self.modal_calls = []
        self.minimize_calls = 0

    def get_default_bookmarks_export_dir(self):
        return str(self.export_dir)

    def _show_modal_message(self, *args):
        self.modal_calls.append(args)
        return self.response

    def _run_with_optional_minimize(self, action):
        self.minimize_calls += 1
        action()


def run_export(monkeypatch, tmp_path, exporters, response):
    monkeypatch.setattr(
        right_utility_gui.BraveBookmarksExporter,
        "supported_exporters",
        lambda: exporters,
    )
    saved_states = []
    monkeypatch.setattr(
        right_utility_gui,
        "save_state",
        lambda state: saved_states.append(state),
    )
    app = FakeApp(tmp_path / "Bookmarks", response)
    panel = SimpleNamespace(app=app)

    result = AdvancedToolsPanel._run_brave_export(panel)

    return result, app, saved_states


def test_bulk_export_writes_three_detected_browsers_after_one_prompt(
    monkeypatch,
    tmp_path,
):
    exporters = [
        FakeExporter("Brave"),
        FakeExporter("Chrome"),
        FakeExporter("Edge"),
    ]

    result, app, saved_states = run_export(
        monkeypatch,
        tmp_path,
        exporters,
        QMessageBox.StandardButton.Save,
    )

    expected_paths = [
        str(app.export_dir / exporter.output_filename)
        for exporter in exporters
    ]
    assert result == expected_paths
    assert len(app.modal_calls) == 1
    assert app.minimize_calls == 1
    assert saved_states == [app.state]
    prompt = app.modal_calls[0][2]
    assert all(path in prompt for path in expected_paths)
    assert all(exporter.export_calls == [path] for exporter, path in zip(exporters, expected_paths))


def test_bulk_export_overwrites_existing_and_creates_new_files(
    monkeypatch,
    tmp_path,
):
    exporters = [FakeExporter("Brave"), FakeExporter("Chrome")]
    export_dir = tmp_path / "Bookmarks"
    export_dir.mkdir()
    existing_path = export_dir / exporters[0].output_filename
    existing_path.write_text("old content", encoding="utf-8")

    result, app, _saved_states = run_export(
        monkeypatch,
        tmp_path,
        exporters,
        QMessageBox.StandardButton.Save,
    )

    assert result == [
        str(export_dir / exporter.output_filename)
        for exporter in exporters
    ]
    assert existing_path.read_text(encoding="utf-8") == "Brave replacement"
    assert (export_dir / exporters[1].output_filename).read_text(
        encoding="utf-8"
    ) == "Chrome replacement"
    assert len(app.modal_calls) == 1
    assert "will be overwritten" in app.modal_calls[0][2]


def test_bulk_export_cancel_leaves_destinations_unchanged(monkeypatch, tmp_path):
    exporter = FakeExporter("Brave")
    export_dir = tmp_path / "Bookmarks"
    export_dir.mkdir()
    existing_path = export_dir / exporter.output_filename
    existing_path.write_text("keep this", encoding="utf-8")

    result, app, saved_states = run_export(
        monkeypatch,
        tmp_path,
        [exporter],
        QMessageBox.StandardButton.Cancel,
    )

    assert result is None
    assert existing_path.read_text(encoding="utf-8") == "keep this"
    assert exporter.export_calls == []
    assert app.minimize_calls == 0
    assert saved_states == []


def test_bulk_export_returns_false_without_detected_bookmarks(
    monkeypatch,
    tmp_path,
):
    result, app, saved_states = run_export(
        monkeypatch,
        tmp_path,
        [FakeExporter("Brave", has_bookmarks=False)],
        QMessageBox.StandardButton.Save,
    )

    assert result is False
    assert app.modal_calls == []
    assert app.minimize_calls == 0
    assert saved_states == []


def test_bulk_export_returns_false_when_every_export_fails(monkeypatch, tmp_path):
    exporters = [
        FakeExporter("Brave", succeeds=False),
        FakeExporter("Chrome", succeeds=False),
    ]

    result, app, saved_states = run_export(
        monkeypatch,
        tmp_path,
        exporters,
        QMessageBox.StandardButton.Save,
    )

    assert result is False
    assert len(app.modal_calls) == 1
    assert app.minimize_calls == 1
    assert all(len(exporter.export_calls) == 1 for exporter in exporters)
    assert saved_states == []

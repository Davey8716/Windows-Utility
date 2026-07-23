import json

import pytest

from universal_bookmarks_export import BraveBookmarksExporter


@pytest.mark.parametrize(
    ("browser_name", "browser_path"),
    [
        ("Chrome", ("Google", "Chrome", "User Data")),
        ("Edge", ("Microsoft", "Edge", "User Data")),
    ],
)
def test_chromium_export_creates_backup_when_profile_has_no_bookmarks(
    monkeypatch,
    tmp_path,
    browser_name,
    browser_path,
):
    local_app_data = tmp_path / "LocalAppData"
    profile_dir = local_app_data.joinpath(*browser_path, "Default")
    profile_dir.mkdir(parents=True)
    (profile_dir / "Bookmarks").write_text(
        json.dumps(
            {
                "roots": {
                    "bookmark_bar": {"type": "folder", "children": []},
                    "other": {"type": "folder", "children": []},
                    "synced": {"type": "folder", "children": []},
                },
                "version": 1,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    exporter = next(
        exporter
        for exporter in BraveBookmarksExporter.supported_exporters()
        if exporter.browser_name == browser_name
    )
    out_path = tmp_path / exporter.output_filename

    assert exporter.has_bookmarks() is True
    assert exporter.export_to_file(out_path) is True
    assert out_path.is_file()
    html = out_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE NETSCAPE-Bookmark-file-1>" in html
    assert f"<TITLE>{browser_name} Bookmarks Export</TITLE>" in html

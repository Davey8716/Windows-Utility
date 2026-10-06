import json
import hashlib
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from html import escape
from pathlib import Path


@dataclass(frozen=True)
class _BrowserConfig:
    browser_name: str
    export_stem: str
    title: str
    source_kind: str
    env_var: str
    path_parts: tuple[str, ...]
    multi_profile: bool = True


class BraveBookmarksExporter:
    SUPPORTED_BROWSERS = (
        _BrowserConfig(
            browser_name="Brave",
            export_stem="Brave",
            title="Brave Bookmarks Export",
            source_kind="chromium",
            env_var="LOCALAPPDATA",
            path_parts=("BraveSoftware", "Brave-Browser", "User Data"),
        ),
        _BrowserConfig(
            browser_name="Chrome",
            export_stem="Chrome",
            title="Chrome Bookmarks Export",
            source_kind="chromium",
            env_var="LOCALAPPDATA",
            path_parts=("Google", "Chrome", "User Data"),
        ),
        _BrowserConfig(
            browser_name="Edge",
            export_stem="Edge",
            title="Edge Bookmarks Export",
            source_kind="chromium",
            env_var="LOCALAPPDATA",
            path_parts=("Microsoft", "Edge", "User Data"),
        ),
        _BrowserConfig(
            browser_name="Firefox",
            export_stem="Firefox",
            title="Firefox Bookmarks Export",
            source_kind="firefox",
            env_var="APPDATA",
            path_parts=("Mozilla", "Firefox", "Profiles"),
        ),
        _BrowserConfig(
            browser_name="Opera",
            export_stem="Opera",
            title="Opera Bookmarks Export",
            source_kind="chromium",
            env_var="APPDATA",
            path_parts=("Opera Software", "Opera Stable"),
            multi_profile=False,
        ),
        _BrowserConfig(
            browser_name="Opera GX",
            export_stem="Opera_GX",
            title="Opera GX Bookmarks Export",
            source_kind="chromium",
            env_var="APPDATA",
            path_parts=("Opera Software", "Opera GX Stable"),
            multi_profile=False,
        ),
        _BrowserConfig(
            browser_name="Vivaldi",
            export_stem="Vivaldi",
            title="Vivaldi Bookmarks Export",
            source_kind="chromium",
            env_var="LOCALAPPDATA",
            path_parts=("Vivaldi", "User Data"),
        ),
        _BrowserConfig(
            browser_name="Chromium",
            export_stem="Chromium",
            title="Chromium Bookmarks Export",
            source_kind="chromium",
            env_var="LOCALAPPDATA",
            path_parts=("Chromium", "User Data"),
        ),
    )

    FIREFOX_ROOTS = (
        ("toolbar_____", ""),
        ("menu________", "Bookmarks Menu"),
        ("unfiled_____", "Other Bookmarks"),
        ("mobile______", "Mobile Bookmarks"),
    )

    def __init__(self, title=None, config=None):
        self._config = config or self.SUPPORTED_BROWSERS[0]
        self.title = title or self._config.title
        self.browser_name = self._config.browser_name
        self.export_stem = self._config.export_stem

    @classmethod
    def supported_exporters(cls):
        return [cls(config=config) for config in cls.SUPPORTED_BROWSERS]

    @property
    def output_filename(self):
        return f"{self.export_stem}_Bookmarks.html"

    def has_bookmarks(self):
        return bool(self._find_bookmark_sources())

    def bookmark_fingerprint(self):
        """Return a digest of exportable bookmarks, ignoring unrelated browser data."""
        sources = self._find_bookmark_sources()
        if not sources:
            return None

        lines = [self._netscape_header()]
        exported_any = False
        for source_path in sources:
            try:
                if self._config.source_kind == "firefox":
                    exported_any = self._export_firefox_bookmarks(source_path, lines) or exported_any
                else:
                    with open(source_path, "r", encoding="utf-8") as bookmarks_file:
                        data = json.load(bookmarks_file)
                    exported_any = self._export_chromium_bookmarks(data, lines) or exported_any
            except Exception:
                continue

        if not exported_any:
            return None
        lines.append("</DL><p>\n")
        return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

    def _netscape_header(self):
        return (
            "<!DOCTYPE NETSCAPE-Bookmark-file-1>\n"
            "<META HTTP-EQUIV=\"Content-Type\" CONTENT=\"text/html; charset=UTF-8\">\n"
            f"<TITLE>{escape(self.title)}</TITLE>\n"
            f"<H1>{escape(self.title)}</H1>\n"
            "<DL><p>\n"
        )

    def _walk_chromium_node(self, node, lines, indent=1):
        ind = "    " * indent
        node_type = node.get("type")
        add_date = str(node.get("date_added", ""))[:10]

        if node_type == "folder":
            title = node.get("name", "Folder")
            lines.append(f'{ind}<DT><H3 ADD_DATE="{add_date}">{escape(title)}</H3>')
            lines.append(f"{ind}<DL><p>")

            for child in node.get("children", []):
                self._walk_chromium_node(child, lines, indent + 1)

            lines.append(f"{ind}</DL><p>")
            return

        if node_type == "url":
            title = node.get("name", "")
            href = node.get("url", "")
            lines.append(
                f'{ind}<DT><A HREF="{escape(href)}" ADD_DATE="{add_date}">{escape(title)}</A>'
            )

    def _export_chromium_bookmarks(self, bookmarks_json, lines):
        roots = bookmarks_json.get("roots")
        if not isinstance(roots, dict):
            return False

        for key in ("bookmark_bar", "other", "synced"):
            section = roots.get(key)
            if not section or not section.get("children"):
                continue

            is_bar = key == "bookmark_bar"
            indent = 1 if is_bar else 2

            if not is_bar:
                lines.append(f'    <DT><H3>{escape(key.title())}</H3>')
                lines.append("    <DL><p>")

            for child in section["children"]:
                self._walk_chromium_node(child, lines, indent)

            if not is_bar:
                lines.append("    </DL><p>")

        return True

    def _firefox_add_date(self, raw_value):
        try:
            timestamp = int(raw_value)
        except (TypeError, ValueError):
            return ""

        if timestamp <= 0:
            return ""

        return str(timestamp // 1_000_000)

    def _walk_firefox_node(self, node, children_by_parent, lines, indent=1):
        ind = "    " * indent
        node_type = node["type"]
        add_date = self._firefox_add_date(node["dateAdded"])

        if node_type == 2:
            title = node["title"] or "Folder"
            lines.append(f'{ind}<DT><H3 ADD_DATE="{add_date}">{escape(title)}</H3>')
            lines.append(f"{ind}<DL><p>")

            for child in children_by_parent.get(node["id"], []):
                self._walk_firefox_node(child, children_by_parent, lines, indent + 1)

            lines.append(f"{ind}</DL><p>")
            return

        if node_type == 1 and node["url"]:
            title = node["title"] or node["url"]
            lines.append(
                f'{ind}<DT><A HREF="{escape(node["url"])}" ADD_DATE="{add_date}">{escape(title)}</A>'
            )

    def _copy_sqlite_bundle(self, source_path):
        source = Path(source_path)
        temp_dir = Path(tempfile.mkdtemp(prefix="bookmarks-export-"))
        copied_main = temp_dir / source.name
        shutil.copy2(source, copied_main)

        for suffix in ("-wal", "-shm"):
            extra_source = source.with_name(source.name + suffix)
            if extra_source.is_file():
                shutil.copy2(extra_source, copied_main.with_name(copied_main.name + suffix))

        return temp_dir, copied_main

    def _read_firefox_rows(self, database_path, *, uri=False):
        connection = sqlite3.connect(database_path, uri=uri)
        connection.row_factory = sqlite3.Row
        try:
            return connection.execute(
                """
                SELECT
                    b.id,
                    b.parent,
                    b.position,
                    b.type,
                    b.fk,
                    COALESCE(b.title, '') AS title,
                    COALESCE(b.dateAdded, 0) AS dateAdded,
                    COALESCE(b.guid, '') AS guid,
                    COALESCE(p.url, '') AS url
                FROM moz_bookmarks AS b
                LEFT JOIN moz_places AS p
                    ON p.id = b.fk
                ORDER BY b.parent, b.position
                """
            ).fetchall()
        finally:
            connection.close()

    def _load_firefox_rows(self, places_path):
        try:
            database_uri = Path(places_path).resolve().as_uri() + "?mode=ro"
            return self._read_firefox_rows(database_uri, uri=True)
        except (OSError, ValueError, sqlite3.Error):
            try:
                temp_dir, copied_db = self._copy_sqlite_bundle(places_path)
            except OSError:
                return []

            try:
                return self._read_firefox_rows(str(copied_db))
            except sqlite3.Error:
                return []
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _export_firefox_bookmarks(self, places_path, lines):
        rows = self._load_firefox_rows(places_path)
        if not rows:
            return False

        before_count = len(lines)
        children_by_parent = {}
        root_by_guid = {}

        for row in rows:
            children_by_parent.setdefault(row["parent"], []).append(row)
            if row["guid"]:
                root_by_guid[row["guid"]] = row

        for guid, section_title in self.FIREFOX_ROOTS:
            root = root_by_guid.get(guid)
            if not root:
                continue

            children = children_by_parent.get(root["id"], [])
            if not children:
                continue

            if section_title:
                lines.append(f'    <DT><H3>{escape(section_title)}</H3>')
                lines.append("    <DL><p>")
                indent = 2
            else:
                indent = 1

            for child in children:
                self._walk_firefox_node(child, children_by_parent, lines, indent)

            if section_title:
                lines.append("    </DL><p>")

        return len(lines) > before_count

    def _find_bookmark_sources(self):
        if self._config.source_kind == "firefox":
            return self._find_firefox_profiles()
        return self._find_chromium_profiles()

    def _base_dir(self):
        root = os.environ.get(self._config.env_var, "")
        if not root:
            return None
        return Path(root, *self._config.path_parts)

    def _find_chromium_profiles(self):
        base = self._base_dir()
        if base is None or not base.is_dir():
            return []

        if not self._config.multi_profile:
            bookmarks_file = base / "Bookmarks"
            return [bookmarks_file] if bookmarks_file.is_file() else []

        paths = []
        try:
            for child in sorted(base.iterdir(), key=lambda path: path.name.lower()):
                bookmarks_file = child / "Bookmarks"
                if bookmarks_file.is_file():
                    paths.append(bookmarks_file)
        except OSError:
            return []

        return paths

    def _find_firefox_profiles(self):
        base = self._base_dir()
        if base is None or not base.is_dir():
            return []

        paths = []
        try:
            for child in sorted(base.iterdir(), key=lambda path: path.name.lower()):
                places_db = child / "places.sqlite"
                if places_db.is_file():
                    paths.append(places_db)
        except OSError:
            return []

        return paths

    def export_to_file(self, out_path):
        sources = self._find_bookmark_sources()
        if not sources:
            return False

        lines = [self._netscape_header()]
        exported_any = False

        for source_path in sources:
            try:
                if self._config.source_kind == "firefox":
                    exported_any = self._export_firefox_bookmarks(source_path, lines) or exported_any
                    continue

                with open(source_path, "r", encoding="utf-8") as bookmarks_file:
                    data = json.load(bookmarks_file)
                exported_any = self._export_chromium_bookmarks(data, lines) or exported_any
            except Exception:
                continue

        if not exported_any:
            return False

        lines.append("</DL><p>\n")
        with open(out_path, "w", encoding="utf-8") as output_file:
            output_file.write("\n".join(lines))

        return True


if __name__ == "__main__":
    raise SystemExit("Run bookmark exports from the app UI.")

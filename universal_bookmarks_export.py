"""
export_brave_bookmarks.py
-----------------------------------------------------
Exports all Brave bookmarks into a single HTML file.
Opens a Save As dialog (default name includes date stamp).
No pop-ups after saving.
"""

import os
import json
from html import escape



class BraveBookmarksExporter:
    def __init__(self, title="Brave Bookmarks Export"):
        self.title = title

    # ─────────────────────────────────────────────
    # HTML helpers
    # ─────────────────────────────────────────────
    def _netscape_header(self):
        return (
            "<!DOCTYPE NETSCAPE-Bookmark-file-1>\n"
            "<META HTTP-EQUIV=\"Content-Type\" CONTENT=\"text/html; charset=UTF-8\">\n"
            f"<TITLE>{escape(self.title)}</TITLE>\n"
            f"<H1>{escape(self.title)}</H1>\n"
            "<DL><p>\n"
        )

    def _walk_nodes(self, node, lines, indent=1):
        IND = "    " * indent
        t = node.get("type")
        add_date = str(node.get("date_added", ""))[:10]

        if t == "folder":
            title = node.get("name", "Folder")
            lines.append(f'{IND}<DT><H3 ADD_DATE="{add_date}">{escape(title)}</H3>')
            lines.append(f"{IND}<DL><p>")

            for child in node.get("children", []):
                self._walk_nodes(child, lines, indent + 1)

            lines.append(f"{IND}</DL><p>")
            return

        if t == "url":
            title = node.get("name", "")
            href = node.get("url", "")
            lines.append(
                f'{IND}<DT><A HREF="{escape(href)}" ADD_DATE="{add_date}">{escape(title)}</A>'
            )

    def _export_chromium_bookmarks(self, bookmarks_json, lines):
        roots = bookmarks_json.get("roots", {})

        for key in ("bookmark_bar", "other", "synced"):
            section = roots.get(key)
            if not section or not section.get("children"):
                continue

            is_bar = key == "bookmark_bar"
            indent = 1 if is_bar else 2

            if not is_bar:
                lines.append(f'    <DT><H3>{escape(key.title())}</H3>')
                lines.append('    <DL><p>')

            for child in section["children"]:
                self._walk_nodes(child, lines, indent)

            if not is_bar:
                lines.append('    </DL><p>')

    # ─────────────────────────────────────────────
    # Brave profile discovery
    # ─────────────────────────────────────────────
    def _find_brave_profiles(self):
        local_app = os.environ.get("LOCALAPPDATA", "")
        base = os.path.join(
            local_app, "BraveSoftware", "Brave-Browser", "User Data"
        )
        if not os.path.isdir(base):
            return []

        paths = []
        for name in os.listdir(base):
            bookmarks_file = os.path.join(base, name, "Bookmarks")
            if os.path.isfile(bookmarks_file):
                paths.append(bookmarks_file)

        return paths

    # ─────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────
    def export_to_file(self, out_path):
        profiles = self._find_brave_profiles()
        if not profiles:
            return False

        lines = [self._netscape_header()]

        for path in profiles:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._export_chromium_bookmarks(data, lines)
            except Exception:
                pass

        lines.append("</DL><p>\n")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return True

# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    BraveBookmarksExporter().run_save_dialog()

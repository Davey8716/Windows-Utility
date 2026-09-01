import os
import sys
from datetime import datetime
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FOLDER_CREATOR_DIR = PROJECT_ROOT / "Code Folder Creator"
sys.path.insert(0, str(FOLDER_CREATOR_DIR))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from folder_creator.core.app_service import AppService  # noqa: E402
from folder_creator.features.tree.filesystem_builder import FolderStructureBuilder  # noqa: E402
from folder_creator.features.tree.outline_parser import parse_indented_text  # noqa: E402
from folder_creator.features.tree.tree_controller import TreeController  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem  # noqa: E402


def test_outline_parser_returns_empty_tree_for_empty_and_comment_only_text():
    assert parse_indented_text("") == []
    assert parse_indented_text("\n  # comment\n\t# another comment\n") == []


def test_outline_parser_handles_multiple_roots_and_nested_siblings():
    text = """Root A
    Child A
        Grandchild
    Child B
Root B
"""

    assert parse_indented_text(text) == [
        {
            "name": "Root A",
            "children": [
                {
                    "name": "Child A",
                    "children": [{"name": "Grandchild", "children": []}],
                },
                {"name": "Child B", "children": []},
            ],
        },
        {"name": "Root B", "children": []},
    ]


def test_outline_parser_handles_tabs_mixed_indentation_and_indent_jumps():
    text = "Root\n\tTab child\n\t    Mixed grandchild\nSecond\n        Jumped child"

    assert parse_indented_text(text) == [
        {
            "name": "Root",
            "children": [
                {
                    "name": "Tab child",
                    "children": [{"name": "Mixed grandchild", "children": []}],
                }
            ],
        },
        {"name": "Second", "children": [{"name": "Jumped child", "children": []}]},
    ]


def test_filesystem_builder_creates_nested_folders_files_and_skips_blank_nodes(tmp_path):
    nodes = [
        {
            "name": "Project",
            "kind": "folder",
            "children": [
                {
                    "name": "src",
                    "kind": "folder",
                    "children": [
                        {"name": "main.py", "kind": "file", "children": []},
                        {"name": "  ", "kind": "folder", "children": []},
                    ],
                }
            ],
        }
    ]

    result = FolderStructureBuilder().build(nodes, tmp_path)

    assert result == ("success", "Folder structure created successfully.")
    assert (tmp_path / "Project" / "src").is_dir()
    assert (tmp_path / "Project" / "src" / "main.py").is_file()


def test_filesystem_builder_reports_empty_and_existing_trees(tmp_path):
    builder = FolderStructureBuilder()
    assert builder.build([], tmp_path) == ("empty", "Tree is empty.")

    (tmp_path / "Existing").mkdir()
    result = builder.build([{"name": "Existing", "children": []}], tmp_path)
    assert result == ("exists", "Folder structure already exists.")


@pytest.mark.parametrize(
    ("mode", "suffix"),
    [("ISO", "2026-09-01"), ("UK", "01-09-2026"), ("US", "09-01-2026")],
)
def test_filesystem_builder_applies_supported_root_timestamps(tmp_path, mode, suffix):
    builder = FolderStructureBuilder(now=lambda: datetime(2026, 9, 1, 12, 30))

    result = builder.build([{"name": "Project", "children": []}], tmp_path, mode)

    assert result[0] == "success"
    assert (tmp_path / f"Project_{suffix}").is_dir()


def test_filesystem_builder_returns_generic_error_for_invalid_base_path(tmp_path):
    base_file = tmp_path / "not-a-directory"
    base_file.write_text("content", encoding="utf-8")

    result = FolderStructureBuilder().build(
        [{"name": "Project", "children": []}],
        base_file,
    )

    assert result == ("error", "Error creating folder structure.")


def test_tree_controller_keeps_template_schema_and_build_file_metadata():
    app = QApplication.instance() or QApplication([])
    tree = QTreeWidget()
    root = QTreeWidgetItem(["Project"])
    file_item = QTreeWidgetItem(["README.md"])
    file_item.setData(0, Qt.UserRole, "file")
    root.addChild(file_item)
    tree.addTopLevelItem(root)
    controller = TreeController(tree)

    assert controller.serialize_tree() == [
        {
            "name": "Project",
            "children": [{"name": "README.md", "children": []}],
        }
    ]
    assert controller.serialize_build_tree() == [
        {
            "name": "Project",
            "kind": "folder",
            "children": [
                {"name": "README.md", "kind": "file", "children": []}
            ],
        }
    ]
    assert app is not None


def test_app_service_build_tree_passes_plain_nodes_to_builder():
    expected_nodes = [{"name": "Project", "kind": "folder", "children": []}]

    class ControllerStub:
        def serialize_build_tree(self):
            return expected_nodes

    class BuilderStub:
        def __init__(self):
            self.call = None

        def build(self, nodes, base_path, timestamp_mode):
            self.call = (nodes, base_path, timestamp_mode)
            return "success", "done"

    service = object.__new__(AppService)
    service.tree_controller = ControllerStub()
    service.folder_builder = BuilderStub()

    assert service.build_tree("C:/output", "ISO") == ("success", "done")
    assert service.folder_builder.call == (expected_nodes, "C:/output", "ISO")


def test_app_service_load_template_uses_standalone_outline_parser():
    class TemplateServiceStub:
        def __init__(self):
            self.parser = None

        def load_template(self, path, parser):
            self.parser = parser
            return parser("Root\n    Child")

    service = object.__new__(AppService)
    service.template_service = TemplateServiceStub()

    assert service.load_template_data("outline.txt") == [
        {
            "name": "Root",
            "children": [{"name": "Child", "children": []}],
        }
    ]
    assert service.template_service.parser is parse_indented_text

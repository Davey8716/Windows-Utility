import ast
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FOLDER_CREATOR_DIR = PROJECT_ROOT / "Code Folder Creator"
WINDOWS_RESURFACE_DIR = PROJECT_ROOT / "Code Windows Resurface"
for path in (FOLDER_CREATOR_DIR, WINDOWS_RESURFACE_DIR):
    sys.path.insert(0, str(path))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from folder_creator.ui.main_window import MainWindow  # noqa: E402
from folder_creator.ui.output_options_panel import OutputOptionsPanel  # noqa: E402
from folder_creator.ui.post_build_panel import PostBuildPanel  # noqa: E402
from folder_creator.ui.template_panel import TemplatePanel  # noqa: E402
from folder_creator.ui.tree_editor_panel import TreeEditorPanel  # noqa: E402


def test_launcher_main_is_small_and_reexports_main_window():
    main_path = FOLDER_CREATOR_DIR / "main.py"
    source = main_path.read_text(encoding="utf-8")
    module = ast.parse(source)

    assert len(source.splitlines()) < 75
    assert not any(
        isinstance(node, ast.ClassDef) and node.name == "MainWindow"
        for node in module.body
    )
    assert MainWindow.__module__ == "folder_creator.ui.main_window"


def test_main_window_declares_the_four_extracted_panel_types():
    source = (FOLDER_CREATOR_DIR / "folder_creator" / "ui" / "main_window.py").read_text(
        encoding="utf-8"
    )

    for panel_type in (
        TemplatePanel,
        TreeEditorPanel,
        OutputOptionsPanel,
        PostBuildPanel,
    ):
        assert f"{panel_type.__name__}(" in source


def test_panels_export_unique_legacy_widget_bindings():
    exported = [
        name
        for panel_type in (
            TemplatePanel,
            TreeEditorPanel,
            OutputOptionsPanel,
            PostBuildPanel,
        )
        for name in panel_type.EXPORTED_WIDGETS
    ]

    assert len(exported) == len(set(exported))
    assert {"tree", "load_template_btn", "build_folders_btn"} <= set(exported)

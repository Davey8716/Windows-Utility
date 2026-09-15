import ast
import os
import subprocess
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


def test_folder_creator_initializes_from_its_own_directory(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["LOCALAPPDATA"] = str(tmp_path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    command = (
        "from PySide6.QtWidgets import QApplication; "
        "from folder_creator.ui.main_window import MainWindow; "
        "app = QApplication([]); "
        "window = MainWindow(); "
        "print(f'FOLDER_CREATOR_READY={window.windowTitle()}')"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=FOLDER_CREATOR_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "FOLDER_CREATOR_READY=Folder Generator" in result.stdout


def test_folder_creator_uses_frameless_theme_aware_title_bar(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["LOCALAPPDATA"] = str(tmp_path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    command = (
        "from PySide6.QtCore import Qt; "
        "from PySide6.QtWidgets import QApplication; "
        "from folder_creator.ui.main_window import MainWindow; "
        "app = QApplication([]); "
        "minimize_calls = []; close_calls = []; "
        "MainWindow.showMinimized = lambda window: minimize_calls.append(window); "
        "MainWindow.close = lambda window: close_calls.append(window); "
        "window = MainWindow(); window.show(); app.processEvents(); "
        "assert window.windowFlags() & Qt.WindowType.FramelessWindowHint; "
        "assert window.windowTitle() == 'Folder Generator'; "
        "assert window.window_title_bar.height() == 50; "
        "assert window.title_label.text() == 'Nested Folder Creator'; "
        "assert window.window_minimize_btn.parent() is window.window_title_bar; "
        "assert window.window_close_btn.parent() is window.window_title_bar; "
        "assert window.window_minimize_btn.size().width() == 42; "
        "assert window.window_minimize_btn.size().height() == 40; "
        "assert window.window_close_btn.x() > window.window_minimize_btn.x(); "
        "assert not window.window_minimize_btn.icon().isNull(); "
        "assert not window.window_close_btn.icon().isNull(); "
        "window.window_minimize_btn.click(); window.window_close_btn.click(); "
        "assert minimize_calls == [window] and close_calls == [window]; "
        "window.apply_theme(False); "
        "assert 'QToolButton:hover' in window.window_minimize_btn.styleSheet(); "
        "assert 'QToolButton:hover' in window.window_close_btn.styleSheet(); "
        "print('FOLDER_CREATOR_CUSTOM_CHROME_READY')"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=FOLDER_CREATOR_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "FOLDER_CREATOR_CUSTOM_CHROME_READY" in result.stdout


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

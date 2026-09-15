import ast
import ctypes
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

import folder_creator.ui.main_window as folder_creator_main_window  # noqa: E402
from folder_creator.ui import styles  # noqa: E402
from folder_creator.ui.main_window import MainWindow  # noqa: E402
from folder_creator.ui.output_options_panel import OutputOptionsPanel  # noqa: E402
from folder_creator.ui.post_build_panel import PostBuildPanel  # noqa: E402
from folder_creator.ui.template_panel import (  # noqa: E402
    TEMPLATE_TOP_ALIGNMENT_SPACER,
    TemplatePanel,
)
from folder_creator.ui.tree_editor_panel import TreeEditorPanel  # noqa: E402
from PySide6.QtWidgets import QApplication, QGridLayout, QWidget  # noqa: E402


def test_folder_creator_initializes_from_its_own_directory(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["LOCALAPPDATA"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
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
    env["USERPROFILE"] = str(tmp_path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    command = (
        "from PySide6.QtCore import QPoint, Qt; "
        "from PySide6.QtWidgets import QApplication, QPushButton; "
        "from folder_creator.ui.main_window import MainWindow; "
        "app = QApplication([]); "
        "minimize_calls = []; close_calls = []; "
        "MainWindow.showMinimized = lambda window: minimize_calls.append(window); "
        "MainWindow.close = lambda window: close_calls.append(window); "
        "window = MainWindow(); window.show(); app.processEvents(); "
        "assert window.windowFlags() & Qt.WindowType.FramelessWindowHint; "
        "assert window.windowTitle() == 'Folder Generator'; "
        "assert window.size().toTuple() == (1000, 860); "
        "assert window.window_title_bar.height() == 50; "
        "assert window.title_label.text() == 'Nested Folder Creator'; "
        "assert window.window_minimize_btn.parent() is window.window_title_bar; "
        "assert window.window_close_btn.parent() is window.window_title_bar; "
        "assert window.window_minimize_btn.size().width() == 42; "
        "assert window.window_minimize_btn.size().height() == 40; "
        "assert window.window_close_btn.x() > window.window_minimize_btn.x(); "
        "assert not window.window_minimize_btn.icon().isNull(); "
        "assert not window.window_close_btn.icon().isNull(); "
        "assert all(button.toolTip() for button in window.findChildren(QPushButton)); "
        "assert 'text-align: center' in window.add_folder_btn.toolTip(); "
        "assert window._tooltip_router is not None; "
        "tree_left = window.tree.mapTo(window, QPoint()).x(); "
        "expand_left = window.expand_tree_btn.mapTo(window, QPoint()).x(); "
        "find_right = window.find_output_line.mapTo(window, QPoint()).x() + window.find_output_line.width(); "
        "assert tree_left == expand_left; "
        "assert tree_left + window.tree.width() == find_right; "
        "tree_top = window.tree.mapTo(window, QPoint()).y(); "
        "tree_bottom = tree_top + window.tree.height(); "
        "toolbar_top = window.expand_tree_btn.mapTo(window, QPoint()).y(); "
        "template_path_top = window.template_path_column.mapTo(window, QPoint()).y(); "
        "output_path_top = window.base_path_column.mapTo(window, QPoint()).y(); "
        "assert window.folder_buttons_frame.mapTo(window, QPoint()).y() + window.folder_buttons_frame.height() <= tree_top; "
        "assert tree_top - (window.template_controls_frame.mapTo(window, QPoint()).y() + window.template_controls_frame.height()) <= 16; "
        "assert tree_bottom < toolbar_top; "
        "assert toolbar_top + window.expand_tree_btn.height() < template_path_top; "
        "assert toolbar_top + window.expand_tree_btn.height() < output_path_top; "
        "tree_frame_bottom = window.tree_frame.mapTo(window, QPoint()).y() + window.tree_frame.height(); "
        "padding_top = window.tree_toolbar_top_padding.mapTo(window, QPoint()).y(); "
        "assert padding_top == tree_frame_bottom; "
        "assert window.tree_toolbar_top_padding.height() == 16; "
        "assert toolbar_top >= padding_top + window.tree_toolbar_top_padding.height(); "
        "window.tree_gui_stretch(); app.processEvents(); "
        "expanded_toolbar_top = window.expand_tree_btn.mapTo(window, QPoint()).y(); "
        "expanded_tree_frame_bottom = window.tree_frame.mapTo(window, QPoint()).y() + window.tree_frame.height(); "
        "expanded_padding_top = window.tree_toolbar_top_padding.mapTo(window, QPoint()).y(); "
        "assert window.tree_toolbar_top_padding.isVisible(); "
        "assert expanded_padding_top == expanded_tree_frame_bottom; "
        "assert window.tree_toolbar_top_padding.height() == 16; "
        "assert expanded_toolbar_top >= expanded_padding_top + window.tree_toolbar_top_padding.height(); "
        "assert all(widget.mapTo(window, QPoint()).y() >= 0 and widget.mapTo(window, QPoint()).y() + widget.height() <= window.height() for widget in (window.tree, window.expand_tree_btn, window.expand_folders_collapse_btn, window.sort_btn, window.find_btn, window.find_output_line, window.template_path_column, window.base_path_column)); "
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


def test_folder_creator_path_displays_use_surfaced_labels_in_both_themes(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["LOCALAPPDATA"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    command = (
        "from PySide6.QtCore import QPoint; "
        "from PySide6.QtWidgets import QApplication; "
        "from folder_creator.ui import styles; "
        "from folder_creator.ui.main_window import MainWindow; "
        "app = QApplication([]); window = MainWindow(); window.show(); app.processEvents(); "
        "paths = (window.template_path_line, window.base_path_line); "
        "assert [path.size().toTuple() for path in paths] == [(450, 40), (450, 40)]; "
        "path_lefts = [path.mapTo(window, QPoint()).x() for path in paths]; "
        "assert all(left >= 0 and left + path.width() <= window.width() for left, path in zip(path_lefts, paths)); "
        "assert path_lefts[0] + paths[0].width() <= path_lefts[1]; "
        "assert all(path.property('surfaceLabelStyle') for path in paths); "
        "assert not any(path.property('plainThemeLabelStyle') for path in paths); "
        "assert all(path.property('styleFontSize') == 14 for path in paths)\n"
        "for is_dark in (True, False):\n"
        " window.apply_theme(is_dark)\n"
        " app.processEvents()\n"
        " assert all(path.styleSheet() == styles.surfaced_label_style(14) for path in paths)\n"
        "print('FOLDER_CREATOR_SURFACED_PATHS_READY')"
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
    assert "FOLDER_CREATOR_SURFACED_PATHS_READY" in result.stdout


def test_folder_creator_tree_refreshes_to_the_maintenance_output_surface(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["LOCALAPPDATA"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    command = (
        "from PySide6.QtWidgets import QApplication\n"
        "from folder_creator.ui import styles\n"
        "from folder_creator.ui.main_window import MainWindow\n"
        "app = QApplication([])\n"
        "window = MainWindow()\n"
        "window.show()\n"
        "app.processEvents()\n"
        "for is_dark in (True, False):\n"
        " window.apply_theme(is_dark)\n"
        " app.processEvents()\n"
        " surface = styles.qcolor_css(styles.resurface_styles.SURFACE_BG)\n"
        " assert window.tree.styleSheet() == styles.surfaced_tree_widget_style()\n"
        " assert f'background-color: {surface};' in window.tree.styleSheet()\n"
        " assert f'background-color: {surface};' in styles.resurface_styles.frame_text_edit_style('Consolas', 15)\n"
        "print('FOLDER_CREATOR_TREE_SURFACE_READY')"
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
    assert "FOLDER_CREATOR_TREE_SURFACE_READY" in result.stdout


def test_folder_creator_uses_black_disabled_control_text_in_light_mode(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["LOCALAPPDATA"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    command = (
        "from PySide6.QtWidgets import QApplication, QComboBox, QPushButton\n"
        "from folder_creator.ui import styles\n"
        "from folder_creator.ui.main_window import MainWindow\n"
        "app = QApplication([])\n"
        "window = MainWindow()\n"
        "buttons = window.findChildren(QPushButton)\n"
        "combos = window.findChildren(QComboBox)\n"
        "assert buttons and combos\n"
        "assert window.load_template_btn.property('lightModeBlackDisabledText') is True\n"
        "assert window.load_user_template_dropdown.property('lightModeBlackDisabledText') is True\n"
        "assert all(button.property('lightModeBlackDisabledText') is True for button in buttons if button is not window.load_template_btn)\n"
        "assert all(combo.property('lightModeBlackDisabledText') is True for combo in combos)\n"
        "window.apply_theme(False)\n"
        "assert 'QPushButton[lightModeBlackDisabledText=\\\"true\\\"]:disabled' in styles.organizing_button_style(14)\n"
        "assert 'QComboBox[lightModeBlackDisabledText=\\\"true\\\"]:disabled' in styles.organizing_combo_style(14)\n"
        "window.show()\n"
        "app.processEvents()\n"
        "top_row_y = window.open_folder_build_toggle.mapTo(window, window.open_folder_build_toggle.rect().topLeft()).y()\n"
        "assert window.load_template_btn.mapTo(window, window.load_template_btn.rect().topLeft()).y() == top_row_y\n"
        "assert window.default_to_desktop_btn.mapTo(window, window.default_to_desktop_btn.rect().topLeft()).y() == top_row_y\n"
        "window.apply_theme(True)\n"
        "assert 'lightModeBlackDisabledText' not in styles.organizing_button_style(14)\n"
        "assert 'lightModeBlackDisabledText' not in styles.organizing_combo_style(14)\n"
        "print('FOLDER_CREATOR_LIGHT_DISABLED_TEXT_READY')"
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
    assert "FOLDER_CREATOR_LIGHT_DISABLED_TEXT_READY" in result.stdout


def test_folder_creator_user_templates_dropdown_matches_add_blank_treatment(
    tmp_path,
):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["LOCALAPPDATA"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    command = (
        "from PySide6.QtWidgets import QApplication\n"
        "from folder_creator.ui import styles\n"
        "from folder_creator.ui.main_window import MainWindow\n"
        "app = QApplication([])\n"
        "window = MainWindow()\n"
        "dropdown = window.load_user_template_dropdown\n"
        "template_path = window.service.template_paths.user_dir / 'project.json'\n"
        "assert dropdown.objectName() == 'FolderCreatorUserTemplatesDropdown'\n"
        "for is_dark in (True, False):\n"
        " window.apply_theme(is_dark)\n"
        " if template_path.exists(): template_path.unlink()\n"
        " window.nested_ui.template_controller.refresh_user_templates_dropdown()\n"
        " window.remove_all_btn.click()\n"
        " window.show()\n"
        " app.processEvents()\n"
        " disabled_background = styles.qcolor_css(styles.resurface_styles.themed_button_disabled_bg())\n"
        " disabled_border = styles.qcolor_css(styles.resurface_styles.themed_button_disabled_border())\n"
        " assert not dropdown.isEnabled()\n"
        " assert not window.file_dropdown.isEnabled()\n"
        " for control in (dropdown, window.file_dropdown):\n"
        "  image = control.grab().toImage()\n"
        "  assert image.pixelColor(10, 15).name() == disabled_background\n"
        "  assert image.pixelColor(148, 15).name() == disabled_background\n"
        " template_path.write_text('[]', encoding='utf-8')\n"
        " window.nested_ui.template_controller.refresh_user_templates_dropdown()\n"
        " window.add_folder_btn.click()\n"
        " app.processEvents()\n"
        " active_background = styles.qcolor_css(styles.resurface_styles.themed_button_bg())\n"
        " assert dropdown.isEnabled()\n"
        " assert window.file_dropdown.isEnabled()\n"
        " for control in (dropdown, window.file_dropdown):\n"
        "  image = control.grab().toImage()\n"
        "  assert image.pixelColor(10, 15).name() == active_background\n"
        "  assert image.pixelColor(148, 15).name() == active_background\n"
        " assert disabled_border in dropdown.styleSheet()\n"
        "print('FOLDER_CREATOR_USER_TEMPLATES_DROPDOWN_THEME_READY')"
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
    assert "FOLDER_CREATOR_USER_TEMPLATES_DROPDOWN_THEME_READY" in result.stdout


def test_folder_creator_add_blank_dropdown_matches_user_templates_height(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["LOCALAPPDATA"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    command = (
        "from PySide6.QtWidgets import QApplication\n"
        "from folder_creator.ui import styles\n"
        "from folder_creator.ui.main_window import MainWindow\n"
        "app = QApplication([])\n"
        "window = MainWindow()\n"
        "assert window.file_dropdown.width() == 170\n"
        "assert window.file_dropdown.height() == window.load_user_template_dropdown.height()\n"
        "assert window.file_dropdown.height() == styles.DEFAULT_BUTTON_HEIGHT\n"
        "print('FOLDER_CREATOR_FILE_DROPDOWN_SIZE_READY')"
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
    assert "FOLDER_CREATOR_FILE_DROPDOWN_SIZE_READY" in result.stdout


def test_folder_creator_add_blank_dropdown_uses_theme_disabled_treatment(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["LOCALAPPDATA"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    command = (
        "from PySide6.QtWidgets import QApplication\n"
        "from folder_creator.ui import styles\n"
        "from folder_creator.ui.main_window import MainWindow\n"
        "app = QApplication([])\n"
        "window = MainWindow()\n"
        "dropdown = window.file_dropdown\n"
        "assert dropdown.objectName() == 'FolderCreatorAddBlankDropdown'\n"
        "assert not dropdown.isEnabled()\n"
        "for is_dark, text_color, chevron_name in ((True, '#ffffff', 'Dropdown Chevron.svg'), (False, '#000000', 'Dropdown Chevron Light.svg')):\n"
        " window.apply_theme(is_dark)\n"
        " window.show()\n"
        " app.processEvents()\n"
        " stylesheet = dropdown.styleSheet()\n"
        " assert f'color: {text_color};' in stylesheet\n"
        " disabled_background = styles.qcolor_css(styles.resurface_styles.themed_button_disabled_bg())\n"
        " disabled_border = styles.qcolor_css(styles.resurface_styles.themed_button_disabled_border())\n"
        " assert f'background-color: {disabled_background};' in stylesheet\n"
        " assert f'border-left: 1px solid {disabled_border};' in stylesheet\n"
        " assert chevron_name in stylesheet\n"
        " image = dropdown.grab().toImage()\n"
        " assert image.pixelColor(135, 15).name() == disabled_background\n"
        " assert image.pixelColor(148, 15).name() == disabled_background\n"
        " window.add_folder_btn.click()\n"
        " app.processEvents()\n"
        " assert dropdown.isEnabled()\n"
        " active_background = styles.qcolor_css(styles.resurface_styles.themed_button_bg())\n"
        " image = dropdown.grab().toImage()\n"
        " assert image.pixelColor(135, 15).name() == active_background\n"
        " assert image.pixelColor(148, 15).name() == active_background\n"
        " window.remove_all_btn.click()\n"
        " app.processEvents()\n"
        " assert not dropdown.isEnabled()\n"
        "print('FOLDER_CREATOR_FILE_DROPDOWN_THEME_DISABLED_READY')"
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
    assert "FOLDER_CREATOR_FILE_DROPDOWN_THEME_DISABLED_READY" in result.stdout


def test_folder_creator_date_stamp_dropdown_uses_theme_toggle_treatment(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["LOCALAPPDATA"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    command = (
        "from PySide6.QtWidgets import QApplication\n"
        "from folder_creator.ui import styles\n"
        "from folder_creator.ui.main_window import MainWindow\n"
        "app = QApplication([])\n"
        "window = MainWindow()\n"
        "dropdown = window.nested_date_config\n"
        "assert dropdown.objectName() == 'FolderCreatorDateStampDropdown'\n"
        "for is_dark, text_color, chevron_name in ((True, '#ffffff', 'Dropdown Chevron.svg'), (False, '#000000', 'Dropdown Chevron Light.svg')):\n"
        " window.apply_theme(is_dark)\n"
        " window.nested_date_toggle.setChecked(False)\n"
        " window.show()\n"
        " app.processEvents()\n"
        " assert not dropdown.isEnabled()\n"
        " stylesheet = dropdown.styleSheet()\n"
        " assert f'color: {text_color};' in stylesheet\n"
        " assert chevron_name in stylesheet\n"
        " disabled_background = styles.qcolor_css(styles.resurface_styles.themed_button_disabled_bg())\n"
        " image = dropdown.grab().toImage()\n"
        " assert image.pixelColor(135, 15).name() == disabled_background\n"
        " assert image.pixelColor(158, 15).name() == disabled_background\n"
        " window.nested_date_toggle.setChecked(True)\n"
        " app.processEvents()\n"
        " assert dropdown.isEnabled()\n"
        " active_background = styles.qcolor_css(styles.resurface_styles.themed_button_bg())\n"
        " image = dropdown.grab().toImage()\n"
        " assert image.pixelColor(135, 15).name() == active_background\n"
        " assert image.pixelColor(158, 15).name() == active_background\n"
        "print('FOLDER_CREATOR_DATE_DROPDOWN_THEME_READY')"
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
    assert "FOLDER_CREATOR_DATE_DROPDOWN_THEME_READY" in result.stdout


def test_folder_creator_requests_standard_dwm_rounded_corners(monkeypatch):
    calls = []

    class FakeDwmApi:
        def DwmSetWindowAttribute(self, hwnd, attribute, value, value_size):
            preference = ctypes.cast(
                value,
                ctypes.POINTER(ctypes.c_int),
            ).contents.value
            calls.append((hwnd, attribute, preference, value_size))
            return 0

    class FakeWindll:
        dwmapi = FakeDwmApi()

    class Window:
        def winId(self):
            return 1234

    monkeypatch.setattr(folder_creator_main_window.ctypes, "windll", FakeWindll())

    MainWindow._apply_native_window_corner_preference(Window())

    assert calls == [(1234, 33, 2, ctypes.sizeof(ctypes.c_int))]


def test_folder_creator_ignores_unavailable_dwm_api(monkeypatch):
    class FakeWindll:
        pass

    class Window:
        def winId(self):
            return 1234

    monkeypatch.setattr(folder_creator_main_window.ctypes, "windll", FakeWindll())

    MainWindow._apply_native_window_corner_preference(Window())


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


def test_template_panel_places_bulk_delete_below_delete_template():
    app = QApplication.instance() or QApplication([])
    panel = TemplatePanel(frame_padding=6, control_gap=8, tight_gap=4)
    layout = panel.template_controls_frame.layout()

    assert panel.delete_template_btn.text() == "Delete Template"
    assert not panel.delete_template_btn.isEnabled()
    assert panel.delete_all_templates_btn.text() == "Delete All Templates"
    assert not panel.delete_all_templates_btn.isEnabled()
    assert layout.itemAt(0).spacerItem().sizeHint().height() == TEMPLATE_TOP_ALIGNMENT_SPACER
    assert layout.indexOf(panel.delete_template_btn) == 3
    assert layout.indexOf(panel.delete_all_templates_btn) == 4
    assert layout.indexOf(panel.load_user_template_dropdown) == 5
    assert panel.delete_template_btn.width() == styles.DEFAULT_BUTTON_WIDTH
    assert panel.delete_template_btn.height() == styles.DEFAULT_BUTTON_HEIGHT
    assert panel.delete_all_templates_btn.width() == styles.DEFAULT_BUTTON_WIDTH
    assert panel.delete_all_templates_btn.height() == styles.DEFAULT_BUTTON_HEIGHT

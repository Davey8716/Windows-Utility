import importlib.util
from pathlib import Path

import pytest
from PySide6.QtGui import QColor

import styles


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FOLDER_CREATOR_STYLES_PATH = PROJECT_ROOT / "Code Folder Creator" / "styles.py"


@pytest.fixture(autouse=True)
def restore_dark_theme():
    yield
    styles.set_theme(True)


@pytest.mark.parametrize(
    ("is_dark", "window_color", "surface_color", "button_color"),
    [
        (True, "#171b24", "#222a36", "#1c66c4"),
        (False, "#dde3ea", "#eef2f6", "#2d73c8"),
    ],
)
def test_shared_palette_uses_darker_canvas_and_blue_controls(
    is_dark,
    window_color,
    surface_color,
    button_color,
):
    styles.set_theme(is_dark)

    assert styles.qcolor_css(styles.WINDOW_BG) == window_color
    assert styles.qcolor_css(styles.SURFACE_BG) == surface_color
    assert styles.qcolor_css(styles.themed_button_bg()) == button_color
    assert styles.control_text_color() == QColor(255, 255, 255)
    assert f"background-color: {button_color};" in styles.organizing_button_style(14)


@pytest.mark.parametrize(
    "style_factory",
    [
        styles.organizing_combo_style,
        styles.surfaced_combo_style,
        styles.connected_drives_combo_style,
        styles.combo_style,
    ],
)
@pytest.mark.parametrize(
    ("is_dark", "button_color"),
    [(True, "#1c66c4"), (False, "#2d73c8")],
)
def test_standard_dropdown_categories_share_modern_blue_treatment(
    style_factory,
    is_dark,
    button_color,
):
    styles.set_theme(is_dark)
    stylesheet = style_factory(14)

    assert f"background-color: {button_color};" in stylesheet
    assert "color: #ffffff;" in stylesheet
    assert "border-radius: 6px;" in stylesheet
    assert "padding: 4px 34px 4px 10px;" in stylesheet
    assert "width: 28px;" in stylesheet
    assert "border-left: 1px solid" in stylesheet
    assert 'image: url("' in stylesheet
    assert "width: 10px;" in stylesheet
    assert "height: 6px;" in stylesheet
    assert "padding: 6px 10px;" in stylesheet
    assert "QComboBox:disabled" in stylesheet
    assert "QComboBox:disabled::drop-down" in stylesheet


@pytest.mark.parametrize(
    ("is_dark", "power_color", "standard_color", "popup_color"),
    [
        (True, "#2b313c", "#1c66c4", "#222a36"),
        (False, "#46515f", "#2d73c8", "#eef2f6"),
    ],
)
def test_power_dropdown_is_charcoal_with_modern_popup_geometry(
    is_dark,
    power_color,
    standard_color,
    popup_color,
):
    styles.set_theme(is_dark)
    stylesheet = styles.power_combo_style(14)

    assert f"background-color: {power_color};" in stylesheet
    assert f"background-color: {standard_color};" not in stylesheet
    assert f"background-color: {popup_color};" in stylesheet
    assert "border-radius: 6px;" in stylesheet
    assert "width: 28px;" in stylesheet
    assert "padding: 6px 10px;" in stylesheet


def test_contrasting_text_color_favors_readable_severity_foregrounds():
    assert styles.contrasting_text_color(QColor(196, 162, 32)) == styles.TEXT_DARK
    assert styles.contrasting_text_color(QColor(176, 38, 38)) == styles.TEXT_LIGHT


@pytest.mark.parametrize("is_dark", [True, False])
def test_navigation_panel_joins_its_top_and_right_accent_lines(is_dark):
    styles.set_theme(is_dark)
    border = styles.qcolor_css(styles.SURFACE_BORDER)
    stylesheet = styles.navigation_list_style()

    assert f"border-top: 1px solid {border};" in stylesheet
    assert f"border-right: 1px solid {border};" in stylesheet


def test_dropdown_chevron_asset_is_available():
    assert styles.dropdown_chevron_path().is_file()


def test_folder_creator_uses_shared_palette_and_modern_combo_rules():
    spec = importlib.util.spec_from_file_location(
        "_test_folder_creator_styles",
        FOLDER_CREATOR_STYLES_PATH,
    )
    assert spec is not None and spec.loader is not None
    folder_styles = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(folder_styles)

    try:
        folder_styles.set_theme(False)
        stylesheet = folder_styles._application_stylesheet()

        assert "background-color: #dde3ea;" in stylesheet
        assert "background-color: #2d73c8;" in stylesheet
        assert "border-radius: 6px;" in stylesheet
        assert "width: 28px;" in stylesheet
        assert "padding: 6px 10px;" in stylesheet
        assert "qproperty-alignment: AlignCenter;" in stylesheet
    finally:
        folder_styles.set_theme(True)

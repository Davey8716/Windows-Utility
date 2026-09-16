import importlib.util
from pathlib import Path

import pytest
from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QComboBox

from resurface.ui import styles
from resurface.ui import control_styles, shell_styles, style_helpers, style_tokens


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FOLDER_CREATOR_STYLES_PATH = (
    PROJECT_ROOT / "Code Folder Creator" / "folder_creator" / "ui" / "styles.py"
)


@pytest.fixture(autouse=True)
def restore_dark_theme():
    yield
    styles.set_theme(True)


@pytest.mark.parametrize(
    ("is_dark", "window_color", "surface_color", "button_color", "button_text"),
    [
        (True, "#171b24", "#222a36", "#1c66c4", "#ffffff"),
        (False, "#dde3ea", "#eef2f6", "#2d73c8", "#000000"),
    ],
)
def test_shared_palette_uses_darker_canvas_and_blue_controls(
    is_dark,
    window_color,
    surface_color,
    button_color,
    button_text,
):
    styles.set_theme(is_dark)

    assert styles.qcolor_css(styles.WINDOW_BG) == window_color
    assert styles.qcolor_css(styles.SURFACE_BG) == surface_color
    assert styles.qcolor_css(styles.themed_button_bg()) == button_color
    assert styles.control_text_color() == QColor(255, 255, 255)
    button_style = styles.organizing_button_style(14)
    assert f"background-color: {button_color};" in button_style
    assert f"color: {button_text};" in button_style
    assert (
        f"color: {styles.qcolor_css(styles.themed_button_disabled_text())};"
        in button_style
    )


def test_all_button_styles_share_the_standard_corner_radius():
    radius_rule = f"border-radius: {styles.BUTTON_CORNER_RADIUS}px;"

    assert radius_rule in styles.organizing_button_style(14)
    assert radius_rule in styles.button_text_style(14)
    assert radius_rule in styles.toggle_button_style(14)
    assert radius_rule in styles.message_box_style()
    assert radius_rule in styles.title_bar_control_style()
    assert radius_rule in styles.arrow_button_style(
        styles.theme_text_color(),
        styles.SURFACE_HOVER,
    )


@pytest.mark.parametrize(
    ("is_dark", "background", "text", "border"),
    [
        (True, "#222a36", "#ffffff", "#5d6b7d"),
        (False, "#f5f5f0", "#111820", "#787878"),
    ],
)
def test_tooltips_use_rounded_corners_and_theme_colors(
    is_dark,
    background,
    text,
    border,
):
    styles.set_theme(is_dark)
    stylesheet = styles.tooltip_style()

    assert f"background-color: {background};" in stylesheet
    assert f"color: {text};" in stylesheet
    assert f"border: {styles.POPUP_BORDER_WIDTH}px solid {border};" in stylesheet
    assert f"border-radius: {styles.BUTTON_CORNER_RADIUS}px;" in stylesheet
    assert "padding: 0px;" in stylesheet
    assert "text-align: center;" in stylesheet


def test_message_box_style_supports_a_local_corner_radius_override():
    default_stylesheet = styles.message_box_style()
    rounded_stylesheet = styles.message_box_style(
        radius=styles.BUTTON_CORNER_RADIUS
    )

    assert f"border-radius: {styles.POPUP_CORNER_RADIUS}px;" in default_stylesheet
    assert f"border-radius: {styles.BUTTON_CORNER_RADIUS}px;" in rounded_stylesheet


def test_message_box_style_can_omit_its_outer_frame_for_custom_painting():
    stylesheet = styles.message_box_style(outer_frame=False)

    assert "QMessageBox {" in stylesheet
    assert "border: none;" in stylesheet


@pytest.mark.parametrize(
    ("is_dark", "link_color"),
    [(True, "#ffffff"), (False, "#000000")],
)
def test_message_box_links_are_white_in_dark_mode_and_black_in_light_mode(
    is_dark,
    link_color,
):
    styles.set_theme(is_dark)

    assert styles.message_box_link_color().name() == link_color
    assert "QMessageBox QLabel a {" not in styles.message_box_style()


@pytest.mark.parametrize(
    "style_factory",
    [
        styles.organizing_combo_style,
        styles.surfaced_combo_style,
        styles.combo_style,
    ],
)
@pytest.mark.parametrize(
    ("is_dark", "button_color", "text_color"),
    [(True, "#1c66c4", "#ffffff"), (False, "#2d73c8", "#111820")],
)
def test_standard_dropdown_categories_share_modern_blue_treatment(
    style_factory,
    is_dark,
    button_color,
    text_color,
):
    styles.set_theme(is_dark)
    stylesheet = style_factory(14)

    assert f"background-color: {button_color};" in stylesheet
    assert f"color: {text_color};" in stylesheet
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
    assert "font-size: 10.5pt;" in stylesheet
    assert "font-size: 14px;" not in stylesheet


@pytest.mark.parametrize(
    "style_factory",
    [
        styles.organizing_combo_style,
        styles.surfaced_combo_style,
        styles.connected_drives_combo_style,
        styles.power_combo_style,
        styles.combo_style,
    ],
)
@pytest.mark.parametrize("is_dark", [True, False])
def test_dropdown_popups_use_valid_point_sized_fonts_without_qt_warning(
    style_factory,
    is_dark,
):
    styles.set_theme(is_dark)
    app = QApplication.instance() or QApplication([])
    combo = QComboBox()
    combo.addItems(["First", "Second"])
    combo.setStyleSheet(style_factory(14))
    messages = []
    previous_handler = qInstallMessageHandler(
        lambda _message_type, _context, message: messages.append(message)
    )
    try:
        combo.show()
        app.processEvents()
        combo.showPopup()
        app.processEvents()
        combo.hidePopup()

        assert combo.font().pointSizeF() > 0
        assert combo.view().font().pointSizeF() > 0
        assert not any(
            "QFont::setPointSize: Point size <= 0" in message
            for message in messages
        )
    finally:
        combo.close()
        qInstallMessageHandler(previous_handler)


@pytest.mark.parametrize(
    ("is_dark", "power_color", "standard_color", "popup_color", "text_color"),
    [
        (True, "#2b313c", "#1c66c4", "#222a36", "#ffffff"),
        (False, "#46515f", "#2d73c8", "#eef2f6", "#111820"),
    ],
)
def test_power_dropdown_is_charcoal_with_modern_popup_geometry(
    is_dark,
    power_color,
    standard_color,
    popup_color,
    text_color,
):
    styles.set_theme(is_dark)
    stylesheet = styles.power_combo_style(14)

    assert f"background-color: {power_color};" in stylesheet
    assert f"background-color: {standard_color};" not in stylesheet
    assert f"background-color: {popup_color};" in stylesheet
    assert f"color: {text_color};" in stylesheet
    assert "border-radius: 6px;" in stylesheet
    assert "width: 28px;" in stylesheet
    assert "padding: 6px 10px;" in stylesheet


def test_light_mode_placeholder_button_overrides_only_its_disabled_text_color():
    styles.set_theme(False)
    light_style = styles.organizing_button_style(14)
    assert 'QPushButton[lightModePlaceholderButton="true"]:disabled' in light_style
    assert "color: #111820;" in light_style
    assert f"color: {styles.qcolor_css(styles.themed_button_disabled_text())};" in light_style

    styles.set_theme(True)


def test_styles_facade_delegates_to_focused_modules():
    assert styles.set_theme is style_tokens.set_theme
    assert styles.coerce_font_size is style_helpers.coerce_font_size
    assert styles.window_style is shell_styles.window_style
    assert styles.organizing_button_style is control_styles.organizing_button_style


def test_window_style_uses_wide_rounded_vertical_scrollbars():
    stylesheet = styles.window_style()

    assert "QScrollBar:vertical" in stylesheet
    assert "width: 14px;" in stylesheet
    assert stylesheet.count("border-radius: 7px;") == 2


def test_styles_facade_exposes_live_theme_tokens_after_theme_changes():
    styles.set_theme(False)

    assert styles.THEME_IS_DARK is False
    assert styles.WINDOW_BG is style_tokens.WINDOW_BG
    assert "background-color: #dde3ea;" in styles.window_style()

    styles.set_theme(True)

    assert styles.THEME_IS_DARK is True
    assert styles.WINDOW_BG is style_tokens.WINDOW_BG
    assert "background-color: #171b24;" in styles.window_style()
    dark_style = styles.organizing_button_style(14)
    assert 'QPushButton[lightModePlaceholderButton="true"]:disabled' not in dark_style


def test_light_mode_buttons_use_black_text_when_enabled_and_opted_in_when_disabled():
    styles.set_theme(False)
    light_style = styles.organizing_button_style(14)
    enabled_rules, disabled_rules = light_style.split("QPushButton:disabled", 1)

    assert "color: #000000;" in enabled_rules
    assert 'QPushButton[lightModeBlackDisabledText="true"]:disabled' in light_style
    assert "color: #000000;" in disabled_rules

    styles.set_theme(True)
    dark_style = styles.organizing_button_style(14)
    assert 'QPushButton[lightModeBlackDisabledText="true"]:disabled' not in dark_style


def test_light_mode_opt_in_keeps_disabled_dropdown_text_black():
    styles.set_theme(False)
    light_style = styles.organizing_combo_style(14)
    disabled_background = styles.qcolor_css(styles.themed_button_disabled_bg())
    disabled_border = styles.qcolor_css(styles.themed_button_disabled_border())

    assert 'QComboBox[lightModeBlackDisabledText="true"]:disabled' in light_style
    assert 'QComboBox[lightModeBlackDisabledText="true"] QAbstractItemView::item:disabled' in light_style
    assert 'QComboBox[lightModeKeepEnabledBackground="true"]:enabled' in light_style
    assert 'QComboBox[lightModeKeepEnabledBackground="true"]:enabled::drop-down' in light_style
    assert 'QComboBox[lightModeBlackDisabledText="true"][unavailableCurrentValue="true"]' in light_style
    assert 'QComboBox[lightModeBlackDisabledText="true"][unavailableCurrentValue="true"]::drop-down' in light_style
    assert "color: #111820;" in light_style
    assert f"background-color: {disabled_background};" in light_style
    assert f"border: 1px solid {disabled_border};" in light_style
    assert f"border-left: 1px solid {disabled_border};" in light_style

    styles.set_theme(True)
    dark_style = styles.organizing_combo_style(14)
    assert 'QComboBox[lightModeBlackDisabledText="true"]:disabled' not in dark_style


@pytest.mark.parametrize(("is_dark", "text_color"), [(True, "#ffffff"), (False, "#000000")])
def test_folder_creator_add_blank_dropdown_style_matches_theme_when_disabled(
    is_dark,
    text_color,
):
    styles.set_theme(is_dark)
    stylesheet = styles.organizing_combo_style(14)
    disabled_background = styles.qcolor_css(styles.themed_button_disabled_bg())
    disabled_border = styles.qcolor_css(styles.themed_button_disabled_border())

    assert 'QComboBox#FolderCreatorAddBlankDropdown:disabled' in stylesheet
    assert (
        'QComboBox#FolderCreatorAddBlankDropdown::drop-down:disabled'
        in stylesheet
    )
    assert 'QComboBox#FolderCreatorAddBlankDropdown:enabled' in stylesheet
    assert 'QComboBox#FolderCreatorAddBlankDropdown::drop-down:enabled' in stylesheet
    assert f"color: {text_color};" in stylesheet
    assert f"background-color: {disabled_background};" in stylesheet
    assert f"border: 1px solid {disabled_border};" in stylesheet
    assert f"border-left: 1px solid {disabled_border};" in stylesheet


def test_shared_typography_is_explicit_in_controls_and_popups():
    family_rule = f"font-family: {styles.FONT_FAMILY};"

    assert styles.FONT_PRIMARY_FAMILY == "Segoe UI Variable"
    assert styles.FONT_FALLBACK_FAMILY == "Segoe UI"
    assert styles.FONT_SIZE_DISPLAY == 24
    assert styles.FONT_SIZE_DIALOG_TITLE == 20
    assert styles.FONT_SIZE_SECTION == 17
    assert styles.FONT_SIZE_STANDARD == 14
    assert styles.FONT_SIZE_SUPPORTING == 13
    assert styles.FONT_SIZE_COMPACT == 12

    for stylesheet in (
        styles.organizing_button_style(styles.FONT_SIZE_STANDARD),
        styles.organizing_combo_style(styles.FONT_SIZE_STANDARD),
        styles.line_edit_style(styles.FONT_SIZE_STANDARD),
        styles.surfaced_list_widget_style(),
        styles.message_box_style(),
        styles.message_popup_menu_style(),
        styles.file_dialog_style(),
        styles.tooltip_style(),
        styles.window_style(),
    ):
        assert family_rule in stylesheet

    assert f"font-size: {styles.FONT_SIZE_DISPLAY}px;" in styles.page_title_style()
    assert f"font-size: {styles.FONT_SIZE_SECTION}px;" in styles.page_section_heading_style()
    assert f"font-size: {styles.FONT_SIZE_COMPACT}px;" in styles.organizing_button_style(
        styles.FONT_SIZE_COMPACT
    )


@pytest.mark.parametrize(("is_dark", "text_color"), [(True, "#ffffff"), (False, "#000000")])
def test_folder_creator_user_templates_dropdown_style_matches_add_blank_treatment(
    is_dark,
    text_color,
):
    styles.set_theme(is_dark)
    stylesheet = styles.organizing_combo_style(14)
    disabled_background = styles.qcolor_css(styles.themed_button_disabled_bg())
    disabled_border = styles.qcolor_css(styles.themed_button_disabled_border())

    assert 'QComboBox#FolderCreatorUserTemplatesDropdown:disabled' in stylesheet
    assert (
        'QComboBox#FolderCreatorUserTemplatesDropdown::drop-down:disabled'
        in stylesheet
    )
    assert 'QComboBox#FolderCreatorUserTemplatesDropdown:enabled' in stylesheet
    assert (
        'QComboBox#FolderCreatorUserTemplatesDropdown::drop-down:enabled'
        in stylesheet
    )
    assert f"color: {text_color};" in stylesheet
    assert f"background-color: {disabled_background};" in stylesheet
    assert f"border: 1px solid {disabled_border};" in stylesheet
    assert f"border-left: 1px solid {disabled_border};" in stylesheet


@pytest.mark.parametrize(("is_dark", "text_color"), [(True, "#ffffff"), (False, "#000000")])
def test_folder_creator_date_stamp_dropdown_style_matches_theme_when_disabled(
    is_dark,
    text_color,
):
    styles.set_theme(is_dark)
    stylesheet = styles.organizing_combo_style(14)
    disabled_background = styles.qcolor_css(styles.themed_button_disabled_bg())
    disabled_border = styles.qcolor_css(styles.themed_button_disabled_border())

    assert 'QComboBox#FolderCreatorDateStampDropdown:disabled' in stylesheet
    assert (
        'QComboBox#FolderCreatorDateStampDropdown::drop-down:disabled'
        in stylesheet
    )
    assert 'QComboBox#FolderCreatorDateStampDropdown:enabled' in stylesheet
    assert (
        'QComboBox#FolderCreatorDateStampDropdown::drop-down:enabled'
        in stylesheet
    )
    assert f"color: {text_color};" in stylesheet
    assert f"background-color: {disabled_background};" in stylesheet
    assert f"border: 1px solid {disabled_border};" in stylesheet
    assert f"border-left: 1px solid {disabled_border};" in stylesheet


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
    assert f"border-top-right-radius: {styles.BUTTON_CORNER_RADIUS}px;" in stylesheet


@pytest.mark.parametrize("is_dark", [True, False])
def test_surfaced_output_boxes_use_thin_rounded_borders(is_dark):
    styles.set_theme(is_dark)
    border = styles.qcolor_css(styles.themed_surface_field_border())

    for stylesheet in (
        styles.surfaced_text_edit_style("Consolas", 15),
        styles.surfaced_list_widget_style("Consolas", 15),
    ):
        assert f"border: 1px solid {border};" in stylesheet
        assert "border-radius: 6px;" in stylesheet


@pytest.mark.parametrize("is_dark", [True, False])
def test_maintenance_output_and_connected_drives_use_theme_surface_frames(is_dark):
    styles.set_theme(is_dark)
    background = styles.qcolor_css(styles.SURFACE_BG)
    border = styles.qcolor_css(styles.SURFACE_BORDER)
    text = styles.qcolor_css(styles.theme_text_color())

    for stylesheet in (
        styles.frame_text_edit_style("Consolas", 15),
        styles.frame_list_widget_style("Consolas", 15),
        styles.connected_drives_combo_style(14),
    ):
        assert f"background-color: {background};" in stylesheet
        assert f"border: 1px solid {border};" in stylesheet
        assert f"color: {text};" in stylesheet
        assert "border-radius: 6px;" in stylesheet

    drive_list_stylesheet = styles.frame_list_widget_style("Consolas", 15)
    assert f"background-color: {styles.qcolor_css(styles.SURFACE_HOVER)};" in drive_list_stylesheet

    drive_stylesheet = styles.connected_drives_combo_style(14)
    assert f"selection-background-color: {styles.qcolor_css(styles.SURFACE_HOVER)};" in drive_stylesheet
    assert f"border-left: 3px solid {styles.qcolor_css(styles.STATUS_ACCENT)};" in drive_stylesheet


def test_dropdown_chevron_asset_is_available():
    styles.set_theme(True)
    assert styles.dropdown_chevron_path().name == "Dropdown Chevron.svg"
    assert styles.dropdown_chevron_path().is_file()
    assert "#FFFFFF" in styles.dropdown_chevron_path().read_text(encoding="utf-8")

    styles.set_theme(False)
    assert styles.dropdown_chevron_path().name == "Dropdown Chevron Light.svg"
    assert styles.dropdown_chevron_path().is_file()
    assert "#000000" in styles.dropdown_chevron_path().read_text(encoding="utf-8")


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
        assert stylesheet.count("QWidget {") == 1
        assert f"font-family: {styles.FONT_FAMILY};" in stylesheet
        assert (
            f"font-family: {styles.FONT_FAMILY};"
            in folder_styles.title_label_style()
        )
    finally:
        folder_styles.set_theme(True)


@pytest.mark.parametrize("is_dark", [True, False])
def test_folder_creator_tree_uses_the_maintenance_output_surface(is_dark):
    spec = importlib.util.spec_from_file_location(
        "_test_folder_creator_tree_styles",
        FOLDER_CREATOR_STYLES_PATH,
    )
    assert spec is not None and spec.loader is not None
    folder_styles = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(folder_styles)

    try:
        folder_styles.set_theme(is_dark)
        tree_stylesheet = folder_styles.surfaced_tree_widget_style()
        maintenance_stylesheet = folder_styles.resurface_styles.frame_text_edit_style(
            "Consolas", 15
        )
        surface_background = folder_styles.qcolor_css(
            folder_styles.resurface_styles.SURFACE_BG
        )

        assert f"background-color: {surface_background};" in tree_stylesheet
        assert f"background-color: {surface_background};" in maintenance_stylesheet
    finally:
        folder_styles.set_theme(True)

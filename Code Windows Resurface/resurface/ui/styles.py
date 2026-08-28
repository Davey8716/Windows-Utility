import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics

TEXT_LIGHT = QColor(255, 255, 255)
TEXT_DARK = QColor(17, 24, 32)
OFF_WHITE_FIELD_BG = QColor(245, 245, 240)

WINDOW_BG = QColor(23, 27, 36)
SURFACE_BG = QColor(34, 42, 54)
SURFACE_HOVER = QColor(49, 68, 95)
PANEL_BG = QColor(58, 72, 96)
PANEL_HOVER = QColor(74, 111, 168)
PANEL_BORDER = QColor(255, 255, 255)
SURFACE_BORDER = QColor(93, 107, 125)
SURFACE_DARK = SURFACE_BG
SURFACE_HOVER_DARK = SURFACE_HOVER
SURFACE_HOVER_LIGHT = SURFACE_HOVER
CURRENT_TEXT = TEXT_LIGHT
THEME_IS_DARK = True
BUTTON_BORDER = SURFACE_BORDER
BUTTON_ACTIVE_BG = QColor(47, 93, 58)
BUTTON_ACTIVE_BORDER = QColor(93, 162, 113)
STATUS_ACCENT = QColor(45, 125, 210)
ORGANIZE_BUTTON_BG = QColor(28, 102, 196)
ORGANIZE_BUTTON_HOVER = QColor(42, 120, 218)
ORGANIZE_BUTTON_PRESSED = QColor(20, 78, 154)
ORGANIZE_BUTTON_PRESSED_HOVER = QColor(30, 92, 176)
ORGANIZE_BUTTON_BORDER = QColor(138, 198, 246)

DEFAULT_BUTTON_WIDTH = 180
DEFAULT_BUTTON_HEIGHT = 30
PAGE_CONTROL_WIDTH = 250
PAGE_CONTROL_HEIGHT = 34
PAGE_CONTROL_GAP = 12
PAGE_COMPACT_CONTROL_WIDTH = 119
PAGE_WIDE_CONTROL_MAX_WIDTH = 300
PAGE_COMBO_POPUP_MAX_WIDTH = 420
LEFT_SECTION_MAX_WIDTH = 420
RIGHT_SECTION_MAX_WIDTH = 492
EXTERNAL_DRIVES_CONTENT_WIDTH = RIGHT_SECTION_MAX_WIDTH - 4
EXTERNAL_DRIVES_CONTROL_WIDTH = (
    EXTERNAL_DRIVES_CONTENT_WIDTH - PAGE_CONTROL_GAP
) // 2
POPUP_CORNER_RADIUS = 0
POPUP_BORDER_WIDTH = 2


def arrow_glyph(arrow_type: Qt.ArrowType) -> str:
    return {
        Qt.ArrowType.LeftArrow: "◀",
        Qt.ArrowType.RightArrow: "▶",
        Qt.ArrowType.UpArrow: "▲",
        Qt.ArrowType.DownArrow: "▼",
    }.get(arrow_type, "")


def side_panel_toggle_slot_size() -> tuple[int, int]:
    return 40, 28


def left_master_toggle_slot_size() -> tuple[int, int]:
    return 28, 20


def right_master_toggle_slot_size() -> tuple[int, int]:
    return 28, 20


def section_toggle_slot_size() -> tuple[int, int]:
    return 28, 20


def _toggle_glyph_style(
    text_color: QColor,
    font_size: int,
) -> str:
    return f"""
        QPushButton, QToolButton {{
            color: {qcolor_css(text_color)};
            background: transparent;
            border: none;
            padding: 0px;
            font-size: {font_size}px;
            font-weight: bold;
            text-align: center;
        }}
    """


def side_panel_toggle_style(text_color: QColor, hover_color: QColor) -> str:
    return _toggle_glyph_style(text_color, 25)


def title_bar_control_style(*, close_button: bool = False) -> str:
    text = qcolor_css(CURRENT_TEXT)
    hover = qcolor_css(QColor(190, 57, 47) if close_button else SURFACE_HOVER)
    pressed = qcolor_css(QColor(151, 42, 35) if close_button else SURFACE_BG)
    return f"""
        QToolButton {{
            color: {text};
            background: transparent;
            border: none;
            padding: 0px;
            font-size: 18px;
            font-weight: bold;
        }}
        QToolButton:hover {{ background-color: {hover}; }}
        QToolButton:pressed {{ background-color: {pressed}; }}
    """


def left_master_toggle_style(text_color: QColor, hover_color: QColor) -> str:
    return _toggle_glyph_style(text_color, 20)


def right_master_toggle_style(text_color: QColor, hover_color: QColor) -> str:
    return _toggle_glyph_style(text_color, 20)


def section_toggle_style(text_color: QColor, hover_color: QColor) -> str:
    return _toggle_glyph_style(text_color, 15)


def set_theme(is_dark: bool) -> None:
    global WINDOW_BG, SURFACE_BG, SURFACE_HOVER, PANEL_BG, PANEL_HOVER
    global SURFACE_BORDER, SURFACE_DARK, SURFACE_HOVER_DARK, SURFACE_HOVER_LIGHT
    global CURRENT_TEXT, THEME_IS_DARK, BUTTON_BORDER, LEFT_PANEL_FRAME_STYLE, RIGHT_PANEL_FRAME_STYLE

    # Blue data-entry and output surfaces stay unchanged in both themes.
    PANEL_BG = QColor(58, 72, 96)
    PANEL_HOVER = QColor(74, 111, 168)

    if is_dark:
        THEME_IS_DARK = True
        WINDOW_BG = QColor(23, 27, 36)
        SURFACE_BG = QColor(34, 42, 54)
        SURFACE_HOVER = QColor(49, 68, 95)
        SURFACE_BORDER = QColor(93, 107, 125)
        CURRENT_TEXT = TEXT_LIGHT
    else:
        THEME_IS_DARK = False
        WINDOW_BG = QColor(221, 227, 234)
        SURFACE_BG = QColor(238, 242, 246)
        SURFACE_HOVER = QColor(203, 216, 231)
        SURFACE_BORDER = QColor(126, 142, 160)
        CURRENT_TEXT = TEXT_DARK

    SURFACE_DARK = SURFACE_BG
    SURFACE_HOVER_DARK = SURFACE_HOVER
    SURFACE_HOVER_LIGHT = SURFACE_HOVER
    BUTTON_BORDER = SURFACE_BORDER
    LEFT_PANEL_FRAME_STYLE = collapsible_section_frame_style()
    RIGHT_PANEL_FRAME_STYLE = collapsible_section_frame_style()


def theme_text_color() -> QColor:
    return CURRENT_TEXT


def control_text_color() -> QColor:
    return TEXT_LIGHT


def dropdown_text_color() -> QColor:
    """Return the selected-value color used by shared combo-box controls."""
    return TEXT_LIGHT if THEME_IS_DARK else theme_text_color()


def button_text_color() -> QColor:
    """Return the enabled text color for standard action buttons."""
    return TEXT_LIGHT if THEME_IS_DARK else QColor(0, 0, 0)


def contrasting_text_color(background: QColor) -> QColor:
    def linear_channel(channel: int) -> float:
        normalized = channel / 255.0
        if normalized <= 0.04045:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    luminance = (
        0.2126 * linear_channel(background.red())
        + 0.7152 * linear_channel(background.green())
        + 0.0722 * linear_channel(background.blue())
    )
    light_contrast = 1.05 / (luminance + 0.05)
    dark_luminance = (
        0.2126 * linear_channel(TEXT_DARK.red())
        + 0.7152 * linear_channel(TEXT_DARK.green())
        + 0.0722 * linear_channel(TEXT_DARK.blue())
    )
    dark_contrast = (luminance + 0.05) / (dark_luminance + 0.05)
    return TEXT_LIGHT if light_contrast >= dark_contrast else TEXT_DARK


def themed_surface_field_bg() -> QColor:
    return PANEL_BG if THEME_IS_DARK else OFF_WHITE_FIELD_BG


def themed_surface_field_text() -> QColor:
    return TEXT_LIGHT if THEME_IS_DARK else TEXT_DARK


def themed_surface_field_border() -> QColor:
    return PANEL_BORDER if THEME_IS_DARK else SURFACE_BORDER


def tooltip_bg() -> QColor:
    return SURFACE_BG if THEME_IS_DARK else OFF_WHITE_FIELD_BG


def tooltip_text_color() -> QColor:
    return CURRENT_TEXT


def tooltip_border() -> QColor:
    return SURFACE_BORDER if THEME_IS_DARK else QColor(120, 120, 120)


def qcolor_css(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexRgb)


def dropdown_chevron_path() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    roots = []
    if bundle_root:
        roots.append(Path(bundle_root))
    roots.append(Path(__file__).resolve().parents[3])

    chevron_name = (
        "Dropdown Chevron.svg" if THEME_IS_DARK else "Dropdown Chevron Light.svg"
    )
    for root in roots:
        candidate = root / "App Icons" / chevron_name
        if candidate.is_file():
            return candidate

    return roots[-1] / "App Icons" / chevron_name


def coerce_font_size(
    font_size: int | float | str | None,
    default: int | None = None,
) -> int | None:
    try:
        normalized = int(font_size) if font_size is not None else None
    except (TypeError, ValueError):
        normalized = None

    if normalized is not None and normalized > 0:
        return normalized

    if default is None:
        return None

    try:
        fallback = int(default)
    except (TypeError, ValueError):
        return None

    return fallback if fallback > 0 else None


def label_style(font_size: int | None = None, bold: bool = True, color: QColor | None = None, font_family: str | None = None) -> str:
    font_size = coerce_font_size(font_size)
    parts = []
    if font_family:
        parts.append(f"font-family: {font_family};")
    if font_size is not None:
        parts.append(f"font-size: {font_size}px;")
    if bold:
        parts.append("font-weight: bold;")
    if color is not None:
        parts.append(f"color: {qcolor_css(color)};")
    return " ".join(parts)


def theme_muted_text_color() -> QColor:
    return QColor(176, 188, 204) if THEME_IS_DARK else QColor(76, 88, 104)


def page_title_style() -> str:
    return label_style(font_size=28, bold=True, color=theme_text_color())


def page_description_style() -> str:
    return label_style(font_size=14, bold=False, color=theme_muted_text_color())


def page_section_heading_style() -> str:
    return label_style(font_size=17, bold=True, color=theme_text_color())


def summary_label_style() -> str:
    return label_style(font_size=13, bold=False, color=theme_muted_text_color())


def summary_value_style() -> str:
    return label_style(font_size=13, bold=True, color=theme_text_color())


def summary_frame_style() -> str:
    return f"""
        QFrame#OverviewSummary, QFrame#MonitorRulesEmptyState {{
            background-color: {qcolor_css(SURFACE_BG)};
            border: 1px solid {qcolor_css(SURFACE_BORDER)};
            border-radius: 8px;
        }}
        QFrame#OverviewSummary QLabel, QFrame#MonitorRulesEmptyState QLabel {{
            border: none;
            background: transparent;
        }}
    """


def navigation_list_style() -> str:
    selected = QColor(43, 68, 98) if THEME_IS_DARK else QColor(202, 222, 244)
    hover = QColor(38, 48, 63) if THEME_IS_DARK else QColor(226, 234, 243)
    return f"""
        QListWidget#NavigationList {{
            background-color: {qcolor_css(SURFACE_BG)};
            color: {qcolor_css(theme_text_color())};
            border: none;
            border-top: 1px solid {qcolor_css(SURFACE_BORDER)};
            border-right: 1px solid {qcolor_css(SURFACE_BORDER)};
            outline: none;
            padding: 12px 8px;
            font-size: 13px;
            font-weight: 600;
        }}
        QListWidget#NavigationList::item {{
            border: none;
            border-left: 3px solid transparent;
            border-radius: 5px;
            padding: 0px 10px;
            margin: 1px 0px;
        }}
        QListWidget#NavigationList::item:hover {{
            background-color: {qcolor_css(hover)};
        }}
        QListWidget#NavigationList::item:selected {{
            background-color: {qcolor_css(selected)};
            color: {qcolor_css(theme_text_color())};
            border-left: 3px solid {qcolor_css(STATUS_ACCENT)};
        }}
    """


def sidebar_version_label_style() -> str:
    return f"""
        QLabel#SidebarVersionLabel {{
            background-color: {qcolor_css(SURFACE_BG)};
            color: {qcolor_css(theme_muted_text_color())};
            border: none;
            border-right: 1px solid {qcolor_css(SURFACE_BORDER)};
            padding: 12px 16px 16px;
            font-size: 11px;
            font-weight: 600;
        }}
    """


def arrow_button_style(text_color: QColor, hover_color: QColor, font_size: int = 18) -> str:
    font_size = coerce_font_size(font_size, 18) or 18
    return f"""
        QPushButton, QToolButton {{
            color: {qcolor_css(text_color)};
            background: transparent;
            border: none;
            padding: 0px;
            font-size: {font_size}px;
            font-weight: bold;
            text-align: center;
        }}
    """

def collapsible_section_frame_style(border_color: QColor | None = None, radius: int = 10) -> str:
    border = border_color or WINDOW_BG
    return f"""
        QFrame#CollapsibleSectionFrame {{
            border: 2px solid {qcolor_css(border)};
            border-radius: {radius}px;
            background-color: {qcolor_css(WINDOW_BG)};
        }}
    """


def message_box_style(radius: int = 10) -> str:
    radius = POPUP_CORNER_RADIUS
    border = qcolor_css(SURFACE_BORDER)
    background = qcolor_css(SURFACE_BG)
    hover = qcolor_css(SURFACE_HOVER)
    text = qcolor_css(CURRENT_TEXT)
    return f"""
        QMessageBox {{
            background-color: {background};
            color: {text};
            border: {POPUP_BORDER_WIDTH}px solid {border};
            border-radius: 0px;
        }}
        QMessageBox QLabel {{
            background: transparent;
            color: {text};
            border: none;
            font-weight: bold;
        }}
        QMessageBox QPushButton {{
            background-color: {background};
            color: {text};
            border: 2px solid {border};
            border-radius: 0px;
            padding: 5px 12px;
            min-width: 72px;
            font-weight: bold;
        }}
        QMessageBox QPushButton:hover {{
            background-color: {hover};
        }}
        QMessageBox QPushButton:pressed {{
            background-color: {hover};
        }}
    """


def message_popup_menu_style(radius: int = 10) -> str:
    radius = POPUP_CORNER_RADIUS
    border = qcolor_css(SURFACE_BORDER)
    background = qcolor_css(SURFACE_BG)
    hover = qcolor_css(SURFACE_HOVER)
    text = qcolor_css(CURRENT_TEXT)
    return f"""
        QMenu {{
            background-color: {background};
            color: {text};
            border: {POPUP_BORDER_WIDTH}px solid {border};
            border-radius: 0px;
            padding: 6px;
        }}
        QMenu::item {{
            background-color: transparent;
            color: {text};
            padding: 7px 12px;
            border-radius: 0px;
            margin: 1px 0px;
            font-weight: bold;
        }}
        QMenu::item:selected {{
            background-color: {hover};
            color: {text};
        }}
        QMenu::separator {{
            height: 1px;
            margin: 4px 8px;
            background: {border};
        }}
    """


def apply_popup_menu_style(menu) -> None:
    if hasattr(menu, "setStyleSheet"):
        menu.setStyleSheet(message_popup_menu_style())


def window_style() -> str:
    return f"""
        QWidget {{
            background-color: {qcolor_css(WINDOW_BG)};
            color: {qcolor_css(CURRENT_TEXT)};
        }}
        QScrollBar:vertical {{
            background-color: {qcolor_css(SURFACE_BG)};
            width: 12px;
            margin: 2px 2px 2px 2px;
            border: 1px solid {qcolor_css(SURFACE_BORDER)};
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {qcolor_css(SURFACE_HOVER)};
            min-height: 28px;
            border: 1px solid {qcolor_css(SURFACE_BORDER)};
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {qcolor_css(STATUS_ACCENT)};
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background: transparent;
            border: none;
            height: 0px;
        }}
    """


def tooltip_style() -> str:
    return f"""
        QToolTip {{
            background-color: {qcolor_css(tooltip_bg())};
            color: {qcolor_css(tooltip_text_color())};
            border: {POPUP_BORDER_WIDTH}px solid {qcolor_css(tooltip_border())};
            border-radius: {POPUP_CORNER_RADIUS}px;
            padding: 0px;
            font-weight: 700;
        }}
    """


def themed_button_bg() -> QColor:
    return ORGANIZE_BUTTON_BG if THEME_IS_DARK else QColor(45, 115, 200)


def themed_button_hover() -> QColor:
    return ORGANIZE_BUTTON_HOVER if THEME_IS_DARK else QColor(62, 134, 220)


def themed_button_pressed() -> QColor:
    return ORGANIZE_BUTTON_PRESSED if THEME_IS_DARK else QColor(33, 91, 160)


def themed_button_pressed_hover() -> QColor:
    return ORGANIZE_BUTTON_PRESSED_HOVER if THEME_IS_DARK else QColor(40, 107, 184)


def themed_button_border() -> QColor:
    return ORGANIZE_BUTTON_BORDER if THEME_IS_DARK else QColor(25, 79, 135)


def themed_button_disabled_bg() -> QColor:
    return QColor(54, 82, 117) if THEME_IS_DARK else QColor(137, 168, 204)


def themed_button_disabled_text() -> QColor:
    return QColor(217, 230, 242) if THEME_IS_DARK else QColor(247, 251, 255)


def themed_button_disabled_border() -> QColor:
    return QColor(97, 120, 150) if THEME_IS_DARK else QColor(110, 142, 180)

def organizing_button_style(font_size: int | None = None) -> str:
    font_size = coerce_font_size(font_size)
    font_rule = f"font-size: {font_size}px;" if font_size is not None else ""
    placeholder_disabled_override = ""
    black_disabled_text_override = ""
    if not THEME_IS_DARK:
        placeholder_disabled_override = f"""
        QPushButton[lightModePlaceholderButton=\"true\"]:disabled {{
            color: {qcolor_css(theme_text_color())};
        }}
        """
        black_disabled_text_override = f"""
        QPushButton[lightModeBlackDisabledText=\"true\"]:disabled {{
            color: {qcolor_css(button_text_color())};
        }}
        """
    return f"""
        QPushButton {{
            text-align: center;
            padding: 4px 8px;
            {font_rule}
            font-weight: bold;
            color: {qcolor_css(button_text_color())};
            border: 1px solid {qcolor_css(themed_button_border())};
            border-radius: 3px;
            background-color: {qcolor_css(themed_button_bg())};
        }}
        QPushButton:hover {{
            background-color: {qcolor_css(themed_button_hover())};
        }}
        QPushButton:checked:hover {{
            background-color: {qcolor_css(themed_button_pressed_hover())};
        }}
        QPushButton:pressed,
        QPushButton[flashActive="true"],
        QPushButton:checked {{
            background-color: {qcolor_css(themed_button_pressed())};
            border: 1px solid {qcolor_css(themed_button_border())};
        }}
        QPushButton:disabled {{
            color: {qcolor_css(themed_button_disabled_text())};
            border: 1px solid {qcolor_css(themed_button_disabled_border())};
            background-color: {qcolor_css(themed_button_disabled_bg())};
        }}
        {placeholder_disabled_override}
        {black_disabled_text_override}
    """

def toggle_button_style(font_size: int | None = None) -> str:
    return organizing_button_style(font_size=font_size)

def hotkey_edit_style(font_size: int = 13) -> str:
    """Style the Screen Mover shortcut editor as a persistent surface field."""
    font_size = coerce_font_size(font_size, 13) or 13
    return f"""
        QKeySequenceEdit#ScreenMoverShortcutEdit {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=themed_surface_field_text(),
            )}
            min-height: 26px;
            padding: 4px 8px;
            background-color: {qcolor_css(themed_surface_field_bg())};
            border: 2px solid {qcolor_css(themed_surface_field_border())};
            border-radius: 6px;
            selection-background-color: {qcolor_css(PANEL_HOVER)};
        }}
        QKeySequenceEdit#ScreenMoverShortcutEdit QLineEdit {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=themed_surface_field_text(),
            )}
            padding: 4px 8px;
            background-color: {qcolor_css(themed_surface_field_bg())};
            border: 2px solid {qcolor_css(themed_surface_field_border())};
            border-radius: 6px;
            selection-background-color: {qcolor_css(PANEL_HOVER)};
        }}
        QKeySequenceEdit#ScreenMoverShortcutEdit:hover,
        QKeySequenceEdit#ScreenMoverShortcutEdit:focus {{
            border-color: {qcolor_css(themed_surface_field_border())};
            background-color: {qcolor_css(themed_surface_field_bg())};
        }}
        QKeySequenceEdit#ScreenMoverShortcutEdit QLineEdit:hover,
        QKeySequenceEdit#ScreenMoverShortcutEdit QLineEdit:focus {{
            border-color: {qcolor_css(themed_surface_field_border())};
            background-color: {qcolor_css(themed_surface_field_bg())};
        }}
    """

def text_edit_style(font_family: str, font_size: int) -> str:
    return f"""
        QTextEdit {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=TEXT_LIGHT,
                font_family=font_family,
            )}
            background-color: {qcolor_css(PANEL_BG)};
            border: 2px solid {qcolor_css(PANEL_BORDER)};
            border-radius: 6px;
            selection-background-color: {qcolor_css(PANEL_HOVER)};
        }}
    """

def surfaced_text_edit_style(font_family: str, font_size: int) -> str:
    return f"""
        QTextEdit {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=themed_surface_field_text(),
                font_family=font_family,
            )}
            background-color: {qcolor_css(themed_surface_field_bg())};
            border: 1px solid {qcolor_css(themed_surface_field_border())};
            border-radius: 6px;
            selection-background-color: {qcolor_css(PANEL_HOVER)};
        }}
    """


def button_text_style(font_size: int) -> str:
    return organizing_button_style(font_size=font_size)

def line_edit_style(font_size: int) -> str:
    return f"""
        QLineEdit {{
            {label_style(font_size=font_size, bold=True, color=TEXT_LIGHT)}
            background-color: {qcolor_css(PANEL_BG)};
            border: 2px solid {qcolor_css(PANEL_BORDER)};
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {qcolor_css(PANEL_HOVER)};
        }}
    """

def surfaced_line_edit_style(font_size: int) -> str:
    return f"""
        QLineEdit {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=themed_surface_field_text(),
            )}
            background-color: {qcolor_css(themed_surface_field_bg())};
            border: 2px solid {qcolor_css(themed_surface_field_border())};
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {qcolor_css(PANEL_HOVER)};
        }}
    """


def frameless_surfaced_line_edit_style(font_size: int) -> str:
    return f"""
        QLineEdit {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=themed_surface_field_text(),
            )}
            background-color: {qcolor_css(themed_surface_field_bg())};
            border: none;
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {qcolor_css(PANEL_HOVER)};
        }}
    """


def plain_theme_line_edit_style(font_size: int) -> str:
    return f"""
        QLineEdit {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=theme_text_color(),
            )}
            background-color: {qcolor_css(WINDOW_BG)};
            border: none;
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {qcolor_css(PANEL_HOVER)};
        }}
    """


def plain_theme_label_style(font_size: int) -> str:
    return f"""
        QLabel {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=theme_text_color(),
            )}
            background-color: {qcolor_css(WINDOW_BG)};
            border: none;
            border-radius: 6px;
            padding: 4px 8px;
        }}
    """


def surfaced_label_style(font_size: int = 14) -> str:
    return f"""
        QLabel {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=theme_text_color(),
            )}
            background-color: {qcolor_css(SURFACE_BG)};
            border: 1px solid {qcolor_css(SURFACE_BORDER)};
            border-radius: 8px;
            padding: 0px 10px;
        }}
    """

def _modern_combo_style(
    font_size: int,
    *,
    background: QColor,
    hover: QColor,
    pressed: QColor,
    pressed_hover: QColor,
    border: QColor,
    text: QColor,
    popup_background: QColor | None = None,
    popup_text: QColor | None = None,
    disabled_text: QColor | None = None,
    disabled_border: QColor | None = None,
    font_family: str | None = None,
) -> str:
    font_size = coerce_font_size(font_size, 14) or 14
    popup_background = popup_background or background
    popup_text = popup_text or text
    disabled_text = disabled_text or themed_button_disabled_text()
    disabled_border = disabled_border or themed_button_disabled_border()
    chevron_path = dropdown_chevron_path().as_posix()
    return f"""
        QComboBox {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=text,
                font_family=font_family,
            )}
            background-color: {qcolor_css(background)};
            border: 1px solid {qcolor_css(border)};
            border-radius: 6px;
            padding: 4px 34px 4px 10px;
        }}
        QComboBox:disabled {{
            color: {qcolor_css(disabled_text)};
            border: 1px solid {qcolor_css(disabled_border)};
        }}
        QComboBox:enabled {{
            color: {qcolor_css(text)};
            border: 1px solid {qcolor_css(border)};
        }}
        QComboBox:hover {{
            border-color: {qcolor_css(pressed_hover)};
        }}
        QComboBox[persistPressed="true"] {{
            border: 2px solid {qcolor_css(text)};
        }}
        QComboBox[persistPressed="true"]:hover {{
            border-color: {qcolor_css(text)};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 28px;
            background-color: {qcolor_css(background)};
            border: none;
            border-left: 1px solid {qcolor_css(border)};
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
        }}
        QComboBox:disabled::drop-down {{
            background-color: {qcolor_css(background)};
            border: none;
            border-left: 1px solid {qcolor_css(disabled_border)};
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
        }}
        QComboBox:enabled::drop-down {{
            background-color: {qcolor_css(background)};
            border-left: 1px solid {qcolor_css(border)};
        }}
        QComboBox:hover::drop-down {{
            background-color: {qcolor_css(background)};
        }}
        QComboBox::drop-down:on {{
            background-color: {qcolor_css(background)};
        }}
        QComboBox::down-arrow {{
            image: url("{chevron_path}");
            width: 10px;
            height: 6px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {qcolor_css(popup_background)};
            color: {qcolor_css(popup_text)};
            selection-background-color: {qcolor_css(hover)};
            selection-color: {qcolor_css(popup_text)};
            border: 1px solid {qcolor_css(border)};
            border-radius: 6px;
            padding: 4px;
            outline: 0;
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 18px;
            padding: 6px 10px;
            border: none;
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {qcolor_css(hover)};
            color: {qcolor_css(popup_text)};
            border-left: 3px solid {qcolor_css(pressed)};
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {qcolor_css(hover)};
            color: {qcolor_css(popup_text)};
        }}
    """


def surfaced_combo_style(font_size: int) -> str:
    return _modern_combo_style(
        font_size,
        background=themed_button_bg(),
        hover=themed_button_hover(),
        pressed=themed_button_pressed(),
        pressed_hover=themed_button_pressed_hover(),
        border=themed_button_border(),
        text=dropdown_text_color(),
    )


def connected_drives_combo_style(font_size: int, font_family: str = "Segoe UI") -> str:
    return _modern_combo_style(
        font_size,
        background=themed_button_bg(),
        hover=themed_button_hover(),
        pressed=themed_button_pressed(),
        pressed_hover=themed_button_pressed_hover(),
        border=themed_button_border(),
        text=dropdown_text_color(),
        font_family=font_family,
    )


def power_combo_style(font_size: int) -> str:
    if THEME_IS_DARK:
        power_bg = QColor(43, 49, 60)
        power_hover = QColor(56, 65, 80)
        power_pressed = QColor(32, 38, 47)
        power_pressed_hover = QColor(48, 57, 70)
        power_border = QColor(101, 113, 132)
    else:
        power_bg = QColor(70, 81, 95)
        power_hover = QColor(89, 102, 117)
        power_pressed = QColor(53, 64, 77)
        power_pressed_hover = QColor(74, 87, 102)
        power_border = QColor(40, 52, 66)

    return _modern_combo_style(
        font_size,
        background=power_bg,
        hover=power_hover,
        pressed=power_pressed,
        pressed_hover=power_pressed_hover,
        border=power_border,
        text=dropdown_text_color(),
        popup_background=SURFACE_BG,
        popup_text=theme_text_color(),
        disabled_text=QColor(211, 216, 223),
        disabled_border=SURFACE_BORDER,
    )


def emphasized_surface_line_edit_style(font_size: int) -> str:
    active_bg = PANEL_HOVER if THEME_IS_DARK else QColor(214, 226, 242)
    return f"""
        QLineEdit {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=themed_surface_field_text(),
            )}            
            background-color: {qcolor_css(active_bg)};
            border: none;
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {qcolor_css(PANEL_BG)};
        }}
    """

def combo_style(font_size: int) -> str:
    return _modern_combo_style(
        font_size,
        background=themed_button_bg(),
        hover=themed_button_hover(),
        pressed=themed_button_pressed(),
        pressed_hover=themed_button_pressed_hover(),
        border=themed_button_border(),
        text=dropdown_text_color(),
    )


LEFT_PANEL_FRAME_STYLE = collapsible_section_frame_style()
RIGHT_PANEL_FRAME_STYLE = collapsible_section_frame_style()


def surfaced_list_widget_style(font_family: str, font_size: int) -> str:
    return (
        """
        QListWidget {
            %s
            background-color: %s;
            color: %s;
            border: 1px solid %s;
            border-radius: 6px;
            padding: 6px;
        }
        QListWidget::item {
            padding: 1px 6px;
            margin: 0px;
            border: none;
            outline: 0;
        }
        QListWidget::item:selected {
            background-color: %s;
            color: %s;
            border: none;
            outline: 0;
        }
        QListWidget::item:selected:active,
        QListWidget::item:selected:focus {
            border: none;
            outline: 0;
        }
        QListView::item {
            border: none;
            outline: 0;
        }
        QListView::item:selected,
        QListView::item:selected:active,
        QListView::item:selected:focus {
            background-color: %s;
            color: %s;
            border: none;
            outline: 0;
        }
        """
        % (
            label_style(
                font_size=font_size,
                bold=True,
                color=themed_surface_field_text(),
                font_family=font_family,
            ),
            qcolor_css(themed_surface_field_bg()),
            qcolor_css(themed_surface_field_text()),
            qcolor_css(themed_surface_field_border()),
            qcolor_css(PANEL_HOVER),
            qcolor_css(themed_surface_field_text()),
            qcolor_css(PANEL_HOVER),
            qcolor_css(themed_surface_field_text()),
        )
    )

def organizing_combo_style(font_size: int) -> str:
    return _modern_combo_style(
        font_size,
        background=themed_button_bg(),
        hover=themed_button_hover(),
        pressed=themed_button_pressed(),
        pressed_hover=themed_button_pressed_hover(),
        border=themed_button_border(),
        text=dropdown_text_color(),
    )

def apply_default_button_size(
    button,
    width: int = DEFAULT_BUTTON_WIDTH,
    height: int = DEFAULT_BUTTON_HEIGHT,
) -> None:
    button.setFixedSize(width, height)


def apply_page_control_size(
    widget,
    *,
    width: int = PAGE_CONTROL_WIDTH,
    height: int = PAGE_CONTROL_HEIGHT,
    role: str = "standard",
) -> None:
    widget.setFixedSize(int(width), int(height))
    widget.setProperty("pageControlRole", role)


def fit_page_combo_width(
    combo,
    *,
    placeholder: str | None = None,
    font_size: int | None = None,
) -> int:
    """Size a page combo predictably and expose every item through its popup."""
    font_size = coerce_font_size(
        font_size if font_size is not None else combo.property("styleFontSize"),
        14,
    ) or 14
    metrics = QFontMetrics(
        QFont(
            combo.font().family().strip() or "Segoe UI",
            max(1, round(font_size * 0.75)),
        )
    )
    collapsed_text = placeholder if placeholder is not None else combo.currentText()
    collapsed_needed = metrics.horizontalAdvance(collapsed_text.strip()) + 58
    width = min(
        PAGE_WIDE_CONTROL_MAX_WIDTH,
        max(PAGE_CONTROL_WIDTH, collapsed_needed),
    )
    role = "wide" if width > PAGE_CONTROL_WIDTH else "standard"
    apply_page_control_size(combo, width=width, role=role)

    popup_needed = width
    for row in range(combo.count()):
        item_text = combo.itemText(row)
        popup_needed = max(popup_needed, metrics.horizontalAdvance(item_text) + 42)
        combo.setItemData(row, item_text, Qt.ItemDataRole.ToolTipRole)
    popup_width = min(PAGE_COMBO_POPUP_MAX_WIDTH, popup_needed)
    combo.view().setMinimumWidth(popup_width)
    combo.setProperty("comboPopupWidth", popup_width)
    return width

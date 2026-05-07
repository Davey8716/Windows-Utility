from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

TEXT_LIGHT = QColor(255, 255, 255)
TEXT_DARK = QColor(0, 0, 0)
OFF_WHITE_FIELD_BG = QColor(245, 245, 240)

WINDOW_BG = QColor(40, 40, 50)
SURFACE_BG = QColor(58, 72, 96)
SURFACE_HOVER = QColor(74, 111, 168)
PANEL_BG = QColor(58, 72, 96)
PANEL_HOVER = QColor(74, 111, 168)
PANEL_BORDER = QColor(255, 255, 255)
SURFACE_BORDER = QColor(255, 255, 255)
SURFACE_DARK = SURFACE_BG
SURFACE_HOVER_DARK = SURFACE_HOVER
SURFACE_HOVER_LIGHT = SURFACE_HOVER
CURRENT_TEXT = TEXT_LIGHT
THEME_IS_DARK = True
BUTTON_BORDER = SURFACE_BORDER
BUTTON_ACTIVE_BG = QColor(47, 93, 58)
BUTTON_ACTIVE_BORDER = QColor(93, 162, 113)
STATUS_ACCENT = QColor(45, 125, 210)
ORGANIZE_BUTTON_BG = QColor(72, 152, 91)
ORGANIZE_BUTTON_HOVER = QColor(84, 168, 104)
ORGANIZE_BUTTON_PRESSED = QColor(38, 92, 52)
ORGANIZE_BUTTON_PRESSED_HOVER = QColor(50, 112, 65)
ORGANIZE_BUTTON_BORDER = QColor(102, 182, 120)

DEFAULT_BUTTON_WIDTH = 180
DEFAULT_BUTTON_HEIGHT = 30
LEFT_SECTION_MAX_WIDTH = 420
RIGHT_SECTION_MAX_WIDTH = 492
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
        WINDOW_BG = QColor(40, 40, 50)
        SURFACE_BG = QColor(58, 72, 96)
        SURFACE_HOVER = QColor(74, 111, 168)
        SURFACE_BORDER = QColor(255, 255, 255)
        CURRENT_TEXT = TEXT_LIGHT
    else:
        THEME_IS_DARK = False
        WINDOW_BG = QColor(255, 255, 255)
        SURFACE_BG = QColor(255, 255, 255)
        SURFACE_HOVER = QColor(230, 236, 244)
        SURFACE_BORDER = QColor(0, 0, 0)
        CURRENT_TEXT = TEXT_DARK

    SURFACE_DARK = SURFACE_BG
    SURFACE_HOVER_DARK = SURFACE_HOVER
    SURFACE_HOVER_LIGHT = SURFACE_HOVER
    BUTTON_BORDER = SURFACE_BORDER
    LEFT_PANEL_FRAME_STYLE = collapsible_section_frame_style()
    RIGHT_PANEL_FRAME_STYLE = collapsible_section_frame_style()


def theme_text_color() -> QColor:
    return CURRENT_TEXT


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

def label_style(font_size: int | None = None, bold: bool = True, color: QColor | None = None, font_family: str | None = None) -> str:
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

def arrow_button_style(text_color: QColor, hover_color: QColor, font_size: int = 18) -> str:
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
    return ORGANIZE_BUTTON_BG if THEME_IS_DARK else QColor(228, 228, 228)


def themed_button_hover() -> QColor:
    return ORGANIZE_BUTTON_HOVER if THEME_IS_DARK else QColor(212, 212, 212)


def themed_button_pressed() -> QColor:
    return ORGANIZE_BUTTON_PRESSED if THEME_IS_DARK else QColor(184, 184, 184)


def themed_button_pressed_hover() -> QColor:
    return ORGANIZE_BUTTON_PRESSED_HOVER if THEME_IS_DARK else QColor(170, 170, 170)


def themed_button_border() -> QColor:
    return ORGANIZE_BUTTON_BORDER if THEME_IS_DARK else QColor(120, 120, 120)

def organizing_button_style(font_size: int | None = None) -> str:
    font_rule = f"font-size: {font_size}px;" if font_size is not None else ""
    return f"""
        QPushButton {{
            text-align: center;
            padding: 4px 8px;
            {font_rule}
            font-weight: bold;
            color: {qcolor_css(theme_text_color())};
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
            color: {qcolor_css(theme_text_color())};
            border: 1px solid {qcolor_css(themed_button_border())};
            background-color: {qcolor_css(themed_button_bg())};
        }}
    """

def toggle_button_style(font_size: int | None = None) -> str:
    return organizing_button_style(font_size=font_size)

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
            border: 2px solid {qcolor_css(themed_surface_field_border())};
            border-radius: 0px;
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

def surfaced_combo_style(font_size: int) -> str:
    return f"""
        QComboBox {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=themed_surface_field_text(),
            )}
            background-color: {qcolor_css(themed_surface_field_bg())};
            border: 2px solid {qcolor_css(themed_surface_field_border())};
            border-radius: 6px;
            padding: 4px 28px 4px 8px;
        }}
        QComboBox:hover,
        QComboBox:on {{
            background-color: {qcolor_css(themed_surface_field_bg())};
        }}
        QComboBox::drop-down {{
            border: none;
            background: transparent;
            width: 22px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {qcolor_css(themed_surface_field_bg())};
            color: {qcolor_css(themed_surface_field_text())};
            selection-background-color: {qcolor_css(PANEL_HOVER)};
            selection-color: {qcolor_css(themed_surface_field_text())};
            border: 2px solid {qcolor_css(themed_surface_field_border())};
            outline: 0;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 4px 8px;
            border: none;
        }}
    """


def connected_drives_combo_style(font_size: int, font_family: str = "Segoe UI") -> str:
    return f"""
        QComboBox {{
            {label_style(
                font_size=font_size,
                bold=True,
                color=themed_surface_field_text(),
                font_family=font_family,
            )}
            background-color: {qcolor_css(WINDOW_BG)};
            border: none;
            border-radius: 6px;
            padding: 4px 24px 4px 6px;
        }}
        QComboBox:hover,
        QComboBox:on {{
            background-color: {qcolor_css(WINDOW_BG)};
        }}
        QComboBox::drop-down {{
            border: none;
            background: transparent;
            width: 18px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {qcolor_css(WINDOW_BG)};
            color: {qcolor_css(themed_surface_field_text())};
            selection-background-color: {qcolor_css(PANEL_HOVER)};
            selection-color: {qcolor_css(themed_surface_field_text())};
            border: none;
            outline: 0;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 4px 8px;
            border: none;
        }}
    """


def power_combo_style(font_size: int) -> str:
    power_bg = QColor(26, 118, 214) if THEME_IS_DARK else QColor(42, 134, 230)
    power_hover = QColor(44, 138, 235) if THEME_IS_DARK else QColor(58, 148, 242)
    power_pressed = QColor(18, 94, 176) if THEME_IS_DARK else QColor(30, 108, 196)
    power_border = QColor(132, 198, 255) if THEME_IS_DARK else QColor(23, 86, 158)

    return f"""
        QComboBox {{
            {label_style(font_size=font_size, bold=True, color=theme_text_color())}
            background-color: {qcolor_css(power_bg)};
            border: 1px solid {qcolor_css(power_border)};
            border-radius: 3px;
            padding: 4px 8px;
        }}
        QComboBox:hover {{
            background-color: {qcolor_css(power_hover)};
        }}
        QComboBox:on {{
            background-color: {qcolor_css(power_pressed)};
        }}
        QComboBox QAbstractItemView {{
            background-color: {qcolor_css(themed_surface_field_bg())};
            color: {qcolor_css(theme_text_color())};
            border: 1px solid {qcolor_css(power_border)};
            outline: 0;
            padding: 2px;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 4px 8px;
            border: none;
        }}
    """


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
    return f"""
        QComboBox {{
            {label_style(font_size=font_size, bold=True, color=TEXT_LIGHT)}
            background-color: {qcolor_css(PANEL_BG)};
            border: 2px solid {qcolor_css(PANEL_BORDER)};
            border-radius: 6px;
            padding: 4px 8px;
        }}
        QComboBox:hover {{
            background-color: {qcolor_css(PANEL_HOVER)};
        }}
        QComboBox QAbstractItemView {{
            background-color: {qcolor_css(PANEL_BG)};
            color: {qcolor_css(TEXT_LIGHT)};
            selection-background-color: {qcolor_css(PANEL_HOVER)};
            border: 2px solid {qcolor_css(PANEL_BORDER)};
        }}
    """


LEFT_PANEL_FRAME_STYLE = collapsible_section_frame_style()
RIGHT_PANEL_FRAME_STYLE = collapsible_section_frame_style()


def surfaced_list_widget_style(font_family: str, font_size: int) -> str:
    return (
        """
        QListWidget {
            %s
            background-color: %s;
            color: %s;
            border: 2px solid %s;
            border-radius: 0px;
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
    return f"""
        QComboBox {{
            {label_style(font_size=font_size, bold=True, color=theme_text_color())}
            background-color: {qcolor_css(themed_button_bg())};
            border: 1px solid {qcolor_css(themed_button_border())};
            border-radius: 3px;
            padding: 4px 8px;
        }}
        QComboBox:hover {{
            background-color: {qcolor_css(themed_button_hover())};
        }}
        QComboBox:disabled {{
            background-color: {qcolor_css(themed_surface_field_bg())};
            color: {qcolor_css(themed_surface_field_border())};
            border: 1px solid {qcolor_css(themed_surface_field_border())};
        }}
        QComboBox:on {{
            background-color: {qcolor_css(themed_button_pressed())};
        }}
        QComboBox[persistPressed="true"] {{
            background-color: {qcolor_css(themed_button_pressed())};
        }}
        QComboBox QAbstractItemView {{
            background-color: {qcolor_css(themed_button_bg())};
            color: {qcolor_css(theme_text_color())};
            selection-background-color: {qcolor_css(themed_button_hover())};
            selection-color: {qcolor_css(theme_text_color())};
            border: 1px solid {qcolor_css(themed_button_border())};
            outline: 0;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 4px 8px;
            border: none;
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {qcolor_css(themed_button_hover())};
            color: {qcolor_css(theme_text_color())};
            border-left: 3px solid {qcolor_css(themed_button_pressed())};
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {qcolor_css(themed_button_hover())};
            color: {qcolor_css(theme_text_color())};
        }}
    """

def apply_default_button_size(
    button,
    width: int = DEFAULT_BUTTON_WIDTH,
    height: int = DEFAULT_BUTTON_HEIGHT,
) -> None:
    button.setFixedSize(width, height)

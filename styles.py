from PySide6.QtGui import QColor

WINDOW_BG = QColor(40, 40, 50)
PANEL_BG = QColor(58, 72, 96)
PANEL_HOVER = QColor(74, 111, 168)
PANEL_BORDER = QColor(255, 255, 255)
TEXT_LIGHT = QColor(255, 255, 255)
TEXT_DARK = QColor(255, 255, 255)
SURFACE_DARK = PANEL_BG
SURFACE_HOVER_DARK = PANEL_HOVER
SURFACE_HOVER_LIGHT = PANEL_HOVER
BUTTON_BORDER = PANEL_BORDER
BUTTON_ACTIVE_BG = QColor(47, 93, 58)
BUTTON_ACTIVE_BORDER = QColor(93, 162, 113)
STATUS_ACCENT = QColor(45, 125, 210)
ORGANIZE_BUTTON_BG = QColor(72, 152, 91)
ORGANIZE_BUTTON_HOVER = QColor(84, 168, 104)
ORGANIZE_BUTTON_PRESSED = QColor(38, 92, 52)
ORGANIZE_BUTTON_BORDER = QColor(102, 182, 120)

DEFAULT_BUTTON_WIDTH = 170
DEFAULT_BUTTON_HEIGHT = 30
ICON_BUTTON_WIDTH = 32
ICON_BUTTON_HEIGHT = 28
SECTION_TOGGLE_WIDTH = 28
SECTION_TOGGLE_HEIGHT = 20

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
    parts.append(f"color: {qcolor_css(color or TEXT_LIGHT)};")
    return " ".join(parts)

def arrow_button_style(text_color: QColor, hover_color: QColor, font_size: int = 18) -> str:
    return f"""
        QPushButton, QToolButton {{
            color: {qcolor_css(text_color)};
            background: transparent;
            border: none;
            padding: 0px;
            font-weight: bold;
            text-align: center;
        }}
    """

def collapsible_section_frame_style(border_color: QColor | None = None, radius: int = 10) -> str:
    border = border_color or PANEL_BORDER
    return f"""
        QFrame#CollapsibleSectionFrame {{
            border: 2px solid {qcolor_css(border)};
            border-radius: {radius}px;
            background-color: {qcolor_css(PANEL_BG)};
        }}
    """


def window_style() -> str:
    return f"""
        QWidget {{
            background-color: {qcolor_css(WINDOW_BG)};
            color: {qcolor_css(TEXT_LIGHT)};
        }}
        QScrollBar:vertical {{
            background-color: {qcolor_css(PANEL_BG)};
            width: 12px;
            margin: 2px 2px 2px 2px;
            border: 1px solid {qcolor_css(PANEL_BORDER)};
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {qcolor_css(PANEL_HOVER)};
            min-height: 28px;
            border: 1px solid {qcolor_css(PANEL_BORDER)};
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

def organizing_button_style(font_size: int | None = None) -> str:
    font_rule = f"font-size: {font_size}px;" if font_size is not None else ""
    return f"""
        QPushButton {{
            text-align: center;
            padding: 4px 8px;
            {font_rule}
            font-weight: bold;
            color: {qcolor_css(TEXT_LIGHT)};
            border: 1px solid {qcolor_css(ORGANIZE_BUTTON_BORDER)};
            border-radius: 3px;
            background-color: {qcolor_css(ORGANIZE_BUTTON_BG)};
        }}
        QPushButton:hover {{
            background-color: {qcolor_css(ORGANIZE_BUTTON_HOVER)};
        }}
        QPushButton:pressed,
        QPushButton[flashActive="true"],
        QPushButton:checked {{
            background-color: {qcolor_css(ORGANIZE_BUTTON_PRESSED)};
            border: 1px solid {qcolor_css(ORGANIZE_BUTTON_BORDER)};
        }}
        QPushButton:disabled {{
            color: {qcolor_css(TEXT_LIGHT)};
            border: 1px solid {qcolor_css(ORGANIZE_BUTTON_BORDER)};
            background-color: {qcolor_css(ORGANIZE_BUTTON_BG)};
        }}
    """

def toggle_button_style(font_size: int | None = None) -> str:
    return organizing_button_style(font_size=font_size)

def text_edit_style(font_family: str, font_size: int) -> str:
    return f"""
        QTextEdit {{
            {label_style(font_size=font_size, bold=True, font_family=font_family)}
            background-color: {qcolor_css(PANEL_BG)};
            border: 2px solid {qcolor_css(PANEL_BORDER)};
            border-radius: 6px;
            selection-background-color: {qcolor_css(PANEL_HOVER)};
        }}
    """

def button_text_style(font_size: int) -> str:
    return organizing_button_style(font_size=font_size)

def line_edit_style(font_size: int) -> str:
    return f"""
        QLineEdit {{
            {label_style(font_size=font_size, bold=True)}
            background-color: {qcolor_css(PANEL_BG)};
            border: 2px solid {qcolor_css(PANEL_BORDER)};
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {qcolor_css(PANEL_HOVER)};
        }}
    """

def combo_style(font_size: int) -> str:
    return f"""
        QComboBox {{
            {label_style(font_size=font_size, bold=True)}
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

def apply_default_button_size(
    button,
    width: int = DEFAULT_BUTTON_WIDTH,
    height: int = DEFAULT_BUTTON_HEIGHT,
) -> None:
    button.setFixedSize(width, height)

from PySide6.QtGui import QColor

TEXT_LIGHT = QColor(230, 230, 230)
TEXT_DARK = QColor(26, 26, 26)
SURFACE_DARK = QColor(32, 32, 32)
SURFACE_HOVER_DARK = QColor(48, 48, 48)
SURFACE_HOVER_LIGHT = QColor(208, 208, 208)
BUTTON_BORDER = QColor(74, 74, 74)
BUTTON_ACTIVE_BG = QColor(47, 93, 58)
BUTTON_ACTIVE_BORDER = QColor(93, 162, 113)
STATUS_ACCENT = QColor(31, 106, 165)
ORGANIZE_BUTTON_BG = QColor(38, 92, 52)
ORGANIZE_BUTTON_HOVER = QColor(49, 115, 65)
ORGANIZE_BUTTON_PRESSED = QColor(72, 152, 91)
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
        QPushButton:hover, QToolButton:hover {{
            background-color: {qcolor_css(hover_color)};
        }}
    """


def collapsible_section_frame_style(border_color: QColor | None = None, radius: int = 10) -> str:
    border = border_color or TEXT_DARK
    return f"""
        QFrame#CollapsibleSectionFrame {{
            border: 2px solid {qcolor_css(border)};
            border-radius: {radius}px;
            background-color: transparent;
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
            border-radius: 6px;
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


def toggle_button_style() -> str:
    return organizing_button_style()


def text_edit_style(font_family: str, font_size: int) -> str:
    return label_style(font_size=font_size, bold=True, font_family=font_family)


def button_text_style(font_size: int) -> str:
    return organizing_button_style(font_size=font_size)


def line_edit_style(font_size: int) -> str:
    return label_style(font_size=font_size, bold=True)


def combo_style(font_size: int) -> str:
    return label_style(font_size=font_size, bold=True)


def apply_default_button_size(button) -> None:
    button.setFixedSize(DEFAULT_BUTTON_WIDTH, DEFAULT_BUTTON_HEIGHT)

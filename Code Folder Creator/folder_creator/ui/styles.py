from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton


_RESURFACE_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[3] / "Code Windows Resurface"
)
_RESURFACE_STYLES_PATH = (
    _RESURFACE_PACKAGE_ROOT
    / "resurface"
    / "ui"
    / "styles.py"
)
_RESURFACE_MODULE_NAME = "_folder_creator_resurface_styles"


def _load_resurface_styles():
    module = sys.modules.get(_RESURFACE_MODULE_NAME)
    if module is not None:
        return module

    package_root = str(_RESURFACE_PACKAGE_ROOT)
    if package_root not in sys.path:
        sys.path.insert(0, package_root)

    spec = importlib.util.spec_from_file_location(
        _RESURFACE_MODULE_NAME,
        _RESURFACE_STYLES_PATH,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load shared styles from {_RESURFACE_STYLES_PATH}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[_RESURFACE_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


resurface_styles = _load_resurface_styles()
WINDOW_BG = QColor()
SURFACE_BG = QColor()
SURFACE_HOVER = QColor()
SURFACE_BORDER = QColor()
TEXT_COLOR = QColor()
BUTTON_BG = QColor()
BUTTON_HOVER = QColor()
BUTTON_PRESSED = QColor()
BUTTON_BORDER = QColor()
TREE_PLACEHOLDER = QColor(140, 140, 140)
DEFAULT_BUTTON_WIDTH = resurface_styles.DEFAULT_BUTTON_WIDTH
DEFAULT_BUTTON_HEIGHT = resurface_styles.DEFAULT_BUTTON_HEIGHT


def _refresh_theme_globals() -> None:
    global WINDOW_BG, SURFACE_BG, SURFACE_HOVER, SURFACE_BORDER
    global TEXT_COLOR, BUTTON_BG, BUTTON_HOVER, BUTTON_PRESSED, BUTTON_BORDER

    WINDOW_BG = QColor(resurface_styles.WINDOW_BG)
    SURFACE_BG = QColor(resurface_styles.SURFACE_BG)
    SURFACE_HOVER = QColor(resurface_styles.SURFACE_HOVER)
    SURFACE_BORDER = QColor(resurface_styles.SURFACE_BORDER)
    TEXT_COLOR = QColor(resurface_styles.theme_text_color())
    BUTTON_BG = QColor(resurface_styles.themed_button_bg())
    BUTTON_HOVER = QColor(resurface_styles.themed_button_hover())
    BUTTON_PRESSED = QColor(resurface_styles.themed_button_pressed())
    BUTTON_BORDER = QColor(resurface_styles.themed_button_border())


def set_theme(is_dark: bool) -> None:
    resurface_styles.set_theme(is_dark)
    _refresh_theme_globals()


_refresh_theme_globals()


def qcolor_css(color: QColor) -> str:
    return resurface_styles.qcolor_css(color)


def theme_text_color() -> QColor:
    return QColor(TEXT_COLOR)


def create_fluent_icon(glyph: str, icon_size: int = 16) -> QIcon:
    """Create a theme-aware Windows Fluent icon for a control."""
    pixmap = QPixmap(icon_size, icon_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    font = QFont("Segoe Fluent Icons")
    font.setPixelSize(icon_size)
    painter.setFont(font)
    painter.setPen(theme_text_color())
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QIcon(pixmap)


def apply_fluent_icon(button: QPushButton, glyph: str, icon_size: int = 16) -> None:
    """Attach an icon and retain its metadata for theme refreshes."""
    button.setProperty("fluentIconGlyph", glyph)
    button.setProperty("fluentIconSize", icon_size)
    button.setIconSize(QSize(icon_size, icon_size))
    button.setIcon(create_fluent_icon(glyph, icon_size))


def create_window_action_icon(action: str, icon_size: int = 16) -> QIcon:
    """Create consistently sized minimize and close glyphs for action buttons."""
    pixmap = QPixmap(icon_size, icon_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(theme_text_color())
    pen.setWidthF(max(1.25, icon_size / 10))
    pen.setCapStyle(Qt.PenCapStyle.SquareCap)
    painter.setPen(pen)

    inset = icon_size * 0.25
    far_edge = icon_size - inset
    centre = icon_size / 2
    if action == "minimize":
        painter.drawLine(inset, centre, far_edge, centre)
    elif action == "close":
        painter.drawLine(inset, inset, far_edge, far_edge)
        painter.drawLine(inset, far_edge, far_edge, inset)
    else:
        raise ValueError(f"Unsupported window action icon: {action}")

    painter.end()
    return QIcon(pixmap)


def apply_window_action_icon(
    button: QPushButton, action: str, icon_size: int = 16
) -> None:
    """Attach a fixed-bounds window action icon that survives theme refreshes."""
    button.setProperty("windowActionIcon", action)
    button.setProperty("windowActionIconSize", icon_size)
    button.setIconSize(QSize(icon_size, icon_size))
    button.setIcon(create_window_action_icon(action, icon_size))


def apply_fluent_item_icon(
    combo: QComboBox, index: int, glyph: str, icon_size: int = 16
) -> None:
    """Attach a Fluent icon to a combo-box item and preserve it across themes."""
    item_icons = dict(combo.property("fluentItemIcons") or {})
    item_icons[index] = (glyph, icon_size)
    combo.setProperty("fluentItemIcons", item_icons)
    combo.setIconSize(QSize(icon_size, icon_size))
    combo.setItemIcon(index, create_fluent_icon(glyph, icon_size))


def refresh_fluent_icons(widget) -> None:
    """Repaint Fluent control icons with the active theme's text colour."""
    for button in widget.findChildren(QPushButton):
        window_action = button.property("windowActionIcon")
        if window_action:
            icon_size = int(button.property("windowActionIconSize") or 16)
            apply_window_action_icon(button, str(window_action), icon_size)
            continue
        glyph = button.property("fluentIconGlyph")
        if glyph:
            icon_size = int(button.property("fluentIconSize") or 16)
            apply_fluent_icon(button, glyph, icon_size)
    for combo in widget.findChildren(QComboBox):
        item_icons = combo.property("fluentItemIcons") or {}
        for index, (glyph, icon_size) in item_icons.items():
            combo.setItemIcon(index, create_fluent_icon(glyph, int(icon_size)))


def tree_placeholder_color() -> QColor:
    return QColor(TREE_PLACEHOLDER)


def title_label_style() -> str:
    return f"""
        QLabel {{
            background: transparent;
            border: none;
            color: {qcolor_css(TEXT_COLOR)};
            font-family: {resurface_styles.FONT_FAMILY};
            font-size: {resurface_styles.FONT_SIZE_DIALOG_TITLE}px;
            font-weight: 1000;
        }}
    """


def title_bar_control_style(*, close_button: bool = False) -> str:
    """Return the shared title-bar control treatment for the active theme."""
    return resurface_styles.title_bar_control_style(close_button=close_button)


def status_label_style() -> str:
    return resurface_styles.label_style(
        font_size=resurface_styles.FONT_SIZE_STANDARD,
        bold=True,
        color=TEXT_COLOR,
    )


def plain_theme_label_style(font_size: int) -> str:
    return resurface_styles.plain_theme_label_style(font_size)


def surfaced_label_style(font_size: int = 14) -> str:
    return resurface_styles.surfaced_label_style(font_size)


def plain_display_line_edit_style(font_size: int) -> str:
    return f"""
        QLineEdit {{
            {resurface_styles.label_style(
                font_size=font_size,
                bold=True,
                color=theme_text_color(),
            )}
            background-color: {qcolor_css(WINDOW_BG)};
            border: none;
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {qcolor_css(SURFACE_HOVER)};
        }}
        QLineEdit:hover,
        QLineEdit:focus,
        QLineEdit:read-only {{
            background-color: {qcolor_css(WINDOW_BG)};
            border: none;
        }}
    """


def frameless_surfaced_line_edit_style(font_size: int) -> str:
    return resurface_styles.frameless_surfaced_line_edit_style(font_size)


def tree_outer_frame_style() -> str:
    return f"""
        QFrame {{
            background-color: {qcolor_css(SURFACE_BG)};
            border: 1px solid {qcolor_css(SURFACE_BORDER)};
            border-radius: 2px;
        }}
    """


def surfaced_tree_widget_style(font_size: int = 14) -> str:
    # Match the standard read-only output surface used by Maintenance, rather
    # than the blue data-entry field treatment used by editable controls.
    surface_bg = qcolor_css(QColor(resurface_styles.SURFACE_BG))
    surface_text = qcolor_css(QColor(resurface_styles.theme_text_color()))
    selection_bg = qcolor_css(QColor(resurface_styles.PANEL_HOVER))

    return f"""
        QTreeWidget {{
            {resurface_styles.label_style(font_size=font_size, bold=True, color=QColor(resurface_styles.theme_text_color()))}
            background-color: {surface_bg};
            color: {surface_text};
            border: none;
            border-radius: 0px;
            padding: 6px;
            selection-background-color: {selection_bg};
        }}

        QTreeWidget::item:selected {{
            background-color: {selection_bg};
            color: {surface_text};
        }}

        QTreeWidget::item:selected:active {{
            background-color: {selection_bg};
            color: {surface_text};
        }}

        QTreeWidget::item:selected:!active {{
            background-color: {selection_bg};
            color: {surface_text};
        }}
    """


def organizing_button_style(font_size: int = 14) -> str:
    return resurface_styles.organizing_button_style(font_size=font_size)


def organizing_combo_style(font_size: int = 14) -> str:
    return resurface_styles.organizing_combo_style(font_size=font_size)


def apply_default_button_size(widget, width: int = DEFAULT_BUTTON_WIDTH, height: int = DEFAULT_BUTTON_HEIGHT) -> None:
    resurface_styles.apply_default_button_size(widget, width=width, height=height)


def apply_standard_button_styles(widget, font_size: int = 14) -> None:
    button_style = organizing_button_style(font_size=font_size)
    for button in widget.findChildren(QPushButton):
        button.setStyleSheet(button_style)


def opt_in_light_mode_black_disabled_text(widget) -> None:
    """Keep disabled Folder Creator controls legible in the light theme."""
    for button in widget.findChildren(QPushButton):
        button.setProperty(
            "lightModeBlackDisabledText",
            not bool(button.property("themeMutedDisabledAppearance")),
        )
    for combo in widget.findChildren(QComboBox):
        combo.setProperty(
            "lightModeBlackDisabledText",
            not bool(combo.property("themeMutedDisabledAppearance")),
        )


def _application_stylesheet() -> str:
    return f"""
        {resurface_styles.window_style()}

        QLineEdit {{
            {resurface_styles.label_style(font_size=resurface_styles.FONT_SIZE_STANDARD, bold=True, color=TEXT_COLOR)}
            background-color: {qcolor_css(SURFACE_BG)};
            border: 2px solid {qcolor_css(SURFACE_BORDER)};
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {qcolor_css(SURFACE_HOVER)};
        }}

        QLabel {{
            background: transparent;
            border: none;
            color: {qcolor_css(TEXT_COLOR)};
            font-family: {resurface_styles.FONT_FAMILY};
            font-size: {resurface_styles.FONT_SIZE_STANDARD}px;
            font-weight: 700;
        }}

        {organizing_button_style(font_size=14)}

        {organizing_combo_style(font_size=14)}

        QComboBox QLineEdit {{
            background: transparent;
            border: none;
            color: {qcolor_css(resurface_styles.control_text_color())};
            qproperty-alignment: AlignCenter;
        }}

        QSpinBox {{
            {resurface_styles.label_style(font_size=resurface_styles.FONT_SIZE_STANDARD, bold=True, color=TEXT_COLOR)}
            background-color: {qcolor_css(SURFACE_BG)};
            color: {qcolor_css(TEXT_COLOR)};
            border: 2px solid {qcolor_css(SURFACE_BORDER)};
            border-radius: 6px;
            padding: 10px;
            text-align: center;
        }}

        QSpinBox:disabled {{
            background-color: {qcolor_css(SURFACE_BG)};
            color: {qcolor_css(TEXT_COLOR)};
            border: 2px solid {qcolor_css(SURFACE_BORDER)};
        }}

        QSpinBox::up-button,
        QSpinBox::down-button {{
            width: 4px;
        }}

        QTreeWidget {{
            {resurface_styles.label_style(font_size=resurface_styles.FONT_SIZE_STANDARD, bold=True, color=TEXT_COLOR)}
            background-color: {qcolor_css(SURFACE_BG)};
            color: {qcolor_css(TEXT_COLOR)};
            border: 2px solid {qcolor_css(SURFACE_BORDER)};
            border-radius: 2px;
            selection-background-color: {qcolor_css(SURFACE_BG)};
        }}

        QTreeWidget::item:selected {{
            background-color: {qcolor_css(SURFACE_BG)};
            color: {qcolor_css(TEXT_COLOR)};
        }}

        QTreeWidget::item:selected:active {{
            background-color: {qcolor_css(SURFACE_HOVER)};
        }}

        QTreeWidget::item:selected:!active {{
            background-color: {qcolor_css(SURFACE_BG)};
        }}

        {resurface_styles.tooltip_style()}
        {resurface_styles.message_box_style()}
    """


def apply_app_theme(app: QApplication | None) -> None:
    if app is None:
        raise RuntimeError("styles.apply_app_theme requires an active QApplication instance.")
    resurface_styles.apply_application_font(app)
    app.setStyleSheet(_application_stylesheet())

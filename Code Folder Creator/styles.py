from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QPushButton


_RESURFACE_STYLES_PATH = (
    Path(__file__).resolve().parent.parent
    / "Code Windows Resurface"
    / "styles.py"
)
_RESURFACE_MODULE_NAME = "_folder_creator_resurface_styles"


def _load_resurface_styles():
    module = sys.modules.get(_RESURFACE_MODULE_NAME)
    if module is not None:
        return module

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
resurface_styles.set_theme(True)


WINDOW_BG = QColor(resurface_styles.WINDOW_BG)
SURFACE_BG = QColor(resurface_styles.SURFACE_BG)
SURFACE_HOVER = QColor(resurface_styles.SURFACE_HOVER)
SURFACE_BORDER = QColor(resurface_styles.SURFACE_BORDER)
TEXT_COLOR = QColor(resurface_styles.theme_text_color())
BUTTON_BG = QColor(resurface_styles.themed_button_bg())
BUTTON_HOVER = QColor(resurface_styles.themed_button_hover())
BUTTON_PRESSED = QColor(resurface_styles.themed_button_pressed())
BUTTON_BORDER = QColor(resurface_styles.themed_button_border())
TREE_PLACEHOLDER = QColor(140, 140, 140)


def qcolor_css(color: QColor) -> str:
    return resurface_styles.qcolor_css(color)


def theme_text_color() -> QColor:
    return QColor(TEXT_COLOR)


def tree_placeholder_color() -> QColor:
    return QColor(TREE_PLACEHOLDER)


def title_label_style() -> str:
    return f"""
        QLabel {{
            background: transparent;
            border: none;
            color: {qcolor_css(TEXT_COLOR)};
            font-family: "Segoe UI";
            font-size: 20px;
            font-weight: 1000;
        }}
    """


def status_label_style() -> str:
    return resurface_styles.label_style(
        font_size=14,
        bold=True,
        color=TEXT_COLOR,
        font_family="Segoe UI",
    )


def plain_theme_label_style(font_size: int) -> str:
    return resurface_styles.plain_theme_label_style(font_size)


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


def organizing_button_style(font_size: int = 14) -> str:
    return resurface_styles.organizing_button_style(font_size=font_size)


def organizing_combo_style(font_size: int = 14) -> str:
    return resurface_styles.organizing_combo_style(font_size=font_size)


def apply_standard_button_styles(widget, font_size: int = 14) -> None:
    button_style = organizing_button_style(font_size=font_size)
    for button in widget.findChildren(QPushButton):
        button.setStyleSheet(button_style)


def _application_stylesheet() -> str:
    return f"""
        QWidget {{
            background-color: {qcolor_css(WINDOW_BG)};
            color: {qcolor_css(TEXT_COLOR)};
        }}

        QLineEdit {{
            {resurface_styles.label_style(font_size=15, bold=True, color=TEXT_COLOR, font_family="Segoe UI")}
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
            font-family: "Segoe UI";
            font-size: 14px;
            font-weight: 700;
        }}

        {organizing_button_style(font_size=14)}

        QComboBox {{
            {resurface_styles.label_style(font_size=14, bold=True, color=TEXT_COLOR, font_family="Segoe UI")}
            background-color: {qcolor_css(BUTTON_BG)};
            color: {qcolor_css(TEXT_COLOR)};
            border: 1px solid {qcolor_css(BUTTON_BORDER)};
            border-radius: 3px;
            padding: 4px 8px;
        }}

        QComboBox:disabled {{
            background-color: {qcolor_css(BUTTON_BG)};
            color: {qcolor_css(TEXT_COLOR)};
            border: 1px solid {qcolor_css(BUTTON_BORDER)};
        }}

        QComboBox QLineEdit {{
            background: transparent;
            border: none;
            color: {qcolor_css(TEXT_COLOR)};
            qproperty-alignment: AlignCenter;
        }}

        QComboBox:hover,
        QComboBox:on {{
            background-color: {qcolor_css(BUTTON_HOVER)};
        }}

        QComboBox::drop-down {{
            border: none;
            background: transparent;
            width: 22px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {qcolor_css(BUTTON_BG)};
            color: {qcolor_css(TEXT_COLOR)};
            selection-background-color: {qcolor_css(BUTTON_HOVER)};
            selection-color: {qcolor_css(TEXT_COLOR)};
            border: 1px solid {qcolor_css(BUTTON_BORDER)};
            padding: 4px;
            outline: 0;
        }}

        QComboBox QAbstractItemView::item {{
            padding: 4px 8px;
            border: none;
        }}

        QComboBox QAbstractItemView::item:selected {{
            background-color: {qcolor_css(BUTTON_HOVER)};
            color: {qcolor_css(TEXT_COLOR)};
            border-left: 3px solid {qcolor_css(BUTTON_PRESSED)};
        }}

        QComboBox QAbstractItemView::item:hover {{
            background-color: {qcolor_css(BUTTON_HOVER)};
            color: {qcolor_css(TEXT_COLOR)};
        }}

        QSpinBox {{
            {resurface_styles.label_style(font_size=14, bold=True, color=TEXT_COLOR, font_family="Segoe UI")}
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
            {resurface_styles.label_style(font_size=14, bold=True, color=TEXT_COLOR, font_family="Segoe UI")}
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

        {resurface_styles.window_style()}
        {resurface_styles.tooltip_style()}
        {resurface_styles.message_box_style()}
    """


def apply_app_theme(app: QApplication | None) -> None:
    if app is None:
        raise RuntimeError("styles.apply_app_theme requires an active QApplication instance.")
    app.setStyleSheet(_application_stylesheet())

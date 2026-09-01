"""Application shell, navigation, dialog, and popup styles."""

from PySide6.QtGui import QColor

from resurface.ui import style_helpers as H
from resurface.ui import style_tokens as T

def title_bar_control_style(*, close_button: bool = False) -> str:
    text = H.qcolor_css(T.CURRENT_TEXT)
    hover = H.qcolor_css(QColor(190, 57, 47) if close_button else T.SURFACE_HOVER)
    pressed = H.qcolor_css(QColor(151, 42, 35) if close_button else T.SURFACE_BG)
    return f"""
        QToolButton {{
            color: {text};
            background: transparent;
            border: none;
            border-radius: {T.BUTTON_CORNER_RADIUS}px;
            padding: 0px;
            font-size: 18px;
            font-weight: bold;
        }}
        QToolButton:hover {{ background-color: {hover}; }}
        QToolButton:pressed {{ background-color: {pressed}; }}
    """

def page_title_style() -> str:
    return H.label_style(font_size=28, bold=True, color=T.theme_text_color())

def page_description_style() -> str:
    return H.label_style(font_size=14, bold=False, color=T.theme_muted_text_color())

def page_section_heading_style() -> str:
    return H.label_style(font_size=17, bold=True, color=T.theme_text_color())

def summary_label_style() -> str:
    return H.label_style(font_size=13, bold=False, color=T.theme_muted_text_color())

def summary_value_style() -> str:
    return H.label_style(font_size=13, bold=True, color=T.theme_text_color())

def summary_frame_style() -> str:
    return f"""
        QFrame#OverviewSummary, QFrame#MonitorRulesEmptyState {{
            background-color: {H.qcolor_css(T.SURFACE_BG)};
            border: 1px solid {H.qcolor_css(T.SURFACE_BORDER)};
            border-radius: 8px;
        }}
        QFrame#OverviewSummary QLabel, QFrame#MonitorRulesEmptyState QLabel {{
            border: none;
            background: transparent;
        }}
    """

def navigation_list_style() -> str:
    selected = QColor(43, 68, 98) if T.THEME_IS_DARK else QColor(202, 222, 244)
    hover = QColor(38, 48, 63) if T.THEME_IS_DARK else QColor(226, 234, 243)
    return f"""
        QListWidget#NavigationList {{
            background-color: {H.qcolor_css(T.SURFACE_BG)};
            color: {H.qcolor_css(T.theme_text_color())};
            border: none;
            border-top: 1px solid {H.qcolor_css(T.SURFACE_BORDER)};
            border-right: 1px solid {H.qcolor_css(T.SURFACE_BORDER)};
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
            background-color: {H.qcolor_css(hover)};
        }}
        QListWidget#NavigationList::item:selected {{
            background-color: {H.qcolor_css(selected)};
            color: {H.qcolor_css(T.theme_text_color())};
            border-left: 3px solid {H.qcolor_css(T.STATUS_ACCENT)};
        }}
    """

def sidebar_version_label_style() -> str:
    return f"""
        QLabel#SidebarVersionLabel {{
            background-color: {H.qcolor_css(T.SURFACE_BG)};
            color: {H.qcolor_css(T.theme_muted_text_color())};
            border: none;
            border-right: 1px solid {H.qcolor_css(T.SURFACE_BORDER)};
            padding: 12px 16px 16px;
            font-size: 11px;
            font-weight: 600;
        }}
    """

def arrow_button_style(text_color: QColor, hover_color: QColor, font_size: int = 18) -> str:
    font_size = H.coerce_font_size(font_size, 18) or 18
    return f"""
        QPushButton, QToolButton {{
            color: {H.qcolor_css(text_color)};
            background: transparent;
            border: none;
            border-radius: {T.BUTTON_CORNER_RADIUS}px;
            padding: 0px;
            font-size: {font_size}px;
            font-weight: bold;
            text-align: center;
        }}
    """

def message_box_style(radius: int = 10) -> str:
    radius = T.POPUP_CORNER_RADIUS
    border = H.qcolor_css(T.SURFACE_BORDER)
    background = H.qcolor_css(T.SURFACE_BG)
    hover = H.qcolor_css(T.SURFACE_HOVER)
    text = H.qcolor_css(T.CURRENT_TEXT)
    return f"""
        QMessageBox {{
            background-color: {background};
            color: {text};
            border: {T.POPUP_BORDER_WIDTH}px solid {border};
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
            border-radius: {T.BUTTON_CORNER_RADIUS}px;
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
    radius = T.POPUP_CORNER_RADIUS
    border = H.qcolor_css(T.SURFACE_BORDER)
    background = H.qcolor_css(T.SURFACE_BG)
    hover = H.qcolor_css(T.SURFACE_HOVER)
    text = H.qcolor_css(T.CURRENT_TEXT)
    return f"""
        QMenu {{
            background-color: {background};
            color: {text};
            border: {T.POPUP_BORDER_WIDTH}px solid {border};
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
            background-color: {H.qcolor_css(T.WINDOW_BG)};
            color: {H.qcolor_css(T.CURRENT_TEXT)};
        }}
        QScrollBar:vertical {{
            background-color: {H.qcolor_css(T.SURFACE_BG)};
            width: 12px;
            margin: 2px 2px 2px 2px;
            border: 1px solid {H.qcolor_css(T.SURFACE_BORDER)};
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {H.qcolor_css(T.SURFACE_HOVER)};
            min-height: 28px;
            border: 1px solid {H.qcolor_css(T.SURFACE_BORDER)};
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {H.qcolor_css(T.STATUS_ACCENT)};
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

def file_dialog_style() -> str:
    """Return the current app theme for non-native Qt file dialogs."""
    background = H.qcolor_css(T.WINDOW_BG)
    surface = H.qcolor_css(T.SURFACE_BG)
    hover = H.qcolor_css(T.SURFACE_HOVER)
    border = H.qcolor_css(T.SURFACE_BORDER)
    text = H.qcolor_css(T.theme_text_color())
    selected = H.qcolor_css(T.PANEL_HOVER)
    accent = H.qcolor_css(T.STATUS_ACCENT)
    return (
        window_style()
        + tooltip_style()
        + f"""
        QFileDialog {{
            background-color: {background};
            color: {text};
        }}
        QFileDialog QLabel {{
            background: transparent;
            color: {text};
        }}
        QFileDialog QLineEdit,
        QFileDialog QComboBox,
        QFileDialog QAbstractItemView {{
            background-color: {surface};
            color: {text};
            border: 1px solid {border};
            border-radius: 6px;
            selection-background-color: {selected};
            selection-color: {text};
        }}
        QFileDialog QLineEdit,
        QFileDialog QComboBox {{
            min-height: 26px;
            padding: 2px 7px;
        }}
        QFileDialog QAbstractItemView::item:hover {{
            background-color: {hover};
        }}
        QFileDialog QAbstractItemView::item:selected {{
            background-color: {selected};
            color: {text};
        }}
        QFileDialog QPushButton {{
            color: {H.qcolor_css(T.button_text_color())};
            background-color: {H.qcolor_css(T.themed_button_bg())};
            border: 1px solid {H.qcolor_css(T.themed_button_border())};
            border-radius: {T.BUTTON_CORNER_RADIUS}px;
            min-height: 26px;
            padding: 2px 10px;
            font-weight: bold;
        }}
        QFileDialog QPushButton:hover {{
            background-color: {H.qcolor_css(T.themed_button_hover())};
        }}
        QFileDialog QPushButton:pressed {{
            background-color: {H.qcolor_css(T.themed_button_pressed())};
        }}
        QFileDialog QToolButton {{
            color: {text};
            background-color: {surface};
            border: 1px solid {border};
            border-radius: {T.BUTTON_CORNER_RADIUS}px;
            padding: 3px;
        }}
        QFileDialog QToolButton:hover {{
            background-color: {hover};
            border-color: {accent};
        }}
        QFileDialog QHeaderView::section {{
            background-color: {surface};
            color: {text};
            border: none;
            border-right: 1px solid {border};
            border-bottom: 1px solid {border};
            padding: 4px;
        }}
        """
    )

def tooltip_style() -> str:
    return f"""
        QToolTip {{
            background-color: {H.qcolor_css(T.tooltip_bg())};
            color: {H.qcolor_css(T.tooltip_text_color())};
            border: {T.POPUP_BORDER_WIDTH}px solid {H.qcolor_css(T.tooltip_border())};
            border-radius: {T.POPUP_CORNER_RADIUS}px;
            padding: 0px;
            font-weight: 700;
        }}
    """

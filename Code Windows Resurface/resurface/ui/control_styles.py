"""Button, input, combo-box, label, and output control styles."""

from PySide6.QtGui import QColor

from resurface.ui import style_helpers as H
from resurface.ui import style_tokens as T

def organizing_button_style(font_size: int | None = None) -> str:
    font_size = H.coerce_font_size(font_size)
    font_rule = f"font-size: {font_size}px;" if font_size is not None else ""
    placeholder_disabled_override = ""
    black_disabled_text_override = ""
    if not T.THEME_IS_DARK:
        placeholder_disabled_override = f"""
        QPushButton[lightModePlaceholderButton=\"true\"]:disabled {{
            color: {H.qcolor_css(T.theme_text_color())};
        }}
        """
        black_disabled_text_override = f"""
        QPushButton[lightModeBlackDisabledText=\"true\"]:disabled {{
            color: {H.qcolor_css(T.button_text_color())};
        }}
        """
    return f"""
        QPushButton {{
            text-align: center;
            padding: 4px 8px;
            {font_rule}
            font-weight: bold;
            color: {H.qcolor_css(T.button_text_color())};
            border: 1px solid {H.qcolor_css(T.themed_button_border())};
            border-radius: {T.BUTTON_CORNER_RADIUS}px;
            background-color: {H.qcolor_css(T.themed_button_bg())};
        }}
        QPushButton:hover {{
            background-color: {H.qcolor_css(T.themed_button_hover())};
        }}
        QPushButton:checked:hover {{
            background-color: {H.qcolor_css(T.themed_button_pressed_hover())};
        }}
        QPushButton:pressed,
        QPushButton[flashActive="true"],
        QPushButton:checked {{
            background-color: {H.qcolor_css(T.themed_button_pressed())};
            border: 1px solid {H.qcolor_css(T.themed_button_border())};
        }}
        QPushButton:disabled {{
            color: {H.qcolor_css(T.themed_button_disabled_text())};
            border: 1px solid {H.qcolor_css(T.themed_button_disabled_border())};
            background-color: {H.qcolor_css(T.themed_button_disabled_bg())};
        }}
        {placeholder_disabled_override}
        {black_disabled_text_override}
    """

def toggle_button_style(font_size: int | None = None) -> str:
    return organizing_button_style(font_size=font_size)

def power_action_button_style(
    font_size: int | None, severity: str, label: str
) -> str:
    """Style a Quick Action tile with its Power & Session semantic colour."""
    font_size = H.coerce_font_size(font_size)
    font_rule = f"font-size: {font_size}px;" if font_size is not None else ""
    background = T.power_action_color(severity)
    foreground = T.power_action_item_foreground(label, background)
    hover = background.lighter(112)
    pressed = background.darker(118)
    pressed_hover = background.darker(108)
    border = background.lighter(135) if T.THEME_IS_DARK else background.darker(130)
    return f"""
        QPushButton {{
            text-align: center;
            padding: 4px 8px;
            {font_rule}
            font-weight: bold;
            color: {H.qcolor_css(foreground)};
            border: 1px solid {H.qcolor_css(border)};
            border-radius: {T.BUTTON_CORNER_RADIUS}px;
            background-color: {H.qcolor_css(background)};
        }}
        QPushButton:hover {{ background-color: {H.qcolor_css(hover)}; }}
        QPushButton:pressed {{
            background-color: {H.qcolor_css(pressed)};
            border: 1px solid {H.qcolor_css(border)};
        }}
        QPushButton:pressed:hover {{ background-color: {H.qcolor_css(pressed_hover)}; }}
        QPushButton:disabled {{
            color: {H.qcolor_css(T.themed_button_disabled_text())};
            border: 1px solid {H.qcolor_css(T.themed_button_disabled_border())};
            background-color: {H.qcolor_css(T.themed_button_disabled_bg())};
        }}
    """

def hotkey_edit_style(font_size: int = 13) -> str:
    """Style the Screen Mover shortcut editor as a persistent surface field."""
    font_size = H.coerce_font_size(font_size, 13) or 13
    conflict_border = QColor(218, 92, 92) if T.THEME_IS_DARK else QColor(176, 45, 45)
    return f"""
        QKeySequenceEdit#ScreenMoverShortcutEdit {{
            {H.label_style(
                font_size=font_size,
                bold=True,
                color=T.themed_surface_field_text(),
            )}
            min-height: 22px;
            padding: 4px 8px;
            background-color: {H.qcolor_css(T.themed_surface_field_bg())};
            border: 2px solid {H.qcolor_css(T.themed_surface_field_border())};
            border-radius: 6px;
            selection-background-color: {H.qcolor_css(T.PANEL_HOVER)};
        }}
        QKeySequenceEdit#ScreenMoverShortcutEdit QLineEdit {{
            {H.label_style(
                font_size=font_size,
                bold=True,
                color=T.themed_surface_field_text(),
            )}
            padding: 4px 8px;
            background-color: {H.qcolor_css(T.themed_surface_field_bg())};
            border: 2px solid {H.qcolor_css(T.themed_surface_field_border())};
            border-radius: 6px;
            selection-background-color: {H.qcolor_css(T.PANEL_HOVER)};
        }}
        QKeySequenceEdit#ScreenMoverShortcutEdit:hover,
        QKeySequenceEdit#ScreenMoverShortcutEdit:focus {{
            border-color: {H.qcolor_css(T.themed_surface_field_border())};
            background-color: {H.qcolor_css(T.themed_surface_field_bg())};
        }}
        QKeySequenceEdit#ScreenMoverShortcutEdit QLineEdit:hover,
        QKeySequenceEdit#ScreenMoverShortcutEdit QLineEdit:focus {{
            border-color: {H.qcolor_css(T.themed_surface_field_border())};
            background-color: {H.qcolor_css(T.themed_surface_field_bg())};
        }}
        QKeySequenceEdit#ScreenMoverShortcutEdit[shortcutConflict="true"] {{
            border-color: {H.qcolor_css(conflict_border)};
        }}
    """

def hotkey_conflict_message_style(font_size: int = 9) -> str:
    """Theme-aware style for a duplicate warning inside a shortcut editor."""
    font_size = H.coerce_font_size(font_size, 9) or 9
    text = QColor(255, 173, 173) if T.THEME_IS_DARK else QColor(126, 25, 25)
    return f"""
        QLabel#ScreenMoverDuplicateMessage {{
            {H.label_style(font_size=font_size, bold=True, color=text)}
            padding: 0px 4px;
            border: none;
            background-color: {H.qcolor_css(T.themed_surface_field_bg())};
        }}
    """

def text_edit_style(font_family: str, font_size: int) -> str:
    return f"""
        QTextEdit {{
            {H.label_style(
                font_size=font_size,
                bold=True,
                color=T.TEXT_LIGHT,
                font_family=font_family,
            )}
            background-color: {H.qcolor_css(T.PANEL_BG)};
            border: 2px solid {H.qcolor_css(T.PANEL_BORDER)};
            border-radius: 6px;
            selection-background-color: {H.qcolor_css(T.PANEL_HOVER)};
        }}
    """

def surfaced_text_edit_style(font_family: str, font_size: int) -> str:
    return f"""
        QTextEdit {{
            {H.label_style(
                font_size=font_size,
                bold=True,
                color=T.themed_surface_field_text(),
                font_family=font_family,
            )}
            background-color: {H.qcolor_css(T.themed_surface_field_bg())};
            border: 1px solid {H.qcolor_css(T.themed_surface_field_border())};
            border-radius: 6px;
            selection-background-color: {H.qcolor_css(T.PANEL_HOVER)};
        }}
    """

def button_text_style(font_size: int) -> str:
    return organizing_button_style(font_size=font_size)

def line_edit_style(font_size: int) -> str:
    return f"""
        QLineEdit {{
            {H.label_style(font_size=font_size, bold=True, color=T.TEXT_LIGHT)}
            background-color: {H.qcolor_css(T.PANEL_BG)};
            border: 2px solid {H.qcolor_css(T.PANEL_BORDER)};
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {H.qcolor_css(T.PANEL_HOVER)};
        }}
    """

def surfaced_line_edit_style(font_size: int) -> str:
    return f"""
        QLineEdit {{
            {H.label_style(
                font_size=font_size,
                bold=True,
                color=T.themed_surface_field_text(),
            )}
            background-color: {H.qcolor_css(T.themed_surface_field_bg())};
            border: 2px solid {H.qcolor_css(T.themed_surface_field_border())};
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {H.qcolor_css(T.PANEL_HOVER)};
        }}
    """

def frameless_surfaced_line_edit_style(font_size: int) -> str:
    return f"""
        QLineEdit {{
            {H.label_style(
                font_size=font_size,
                bold=True,
                color=T.themed_surface_field_text(),
            )}
            background-color: {H.qcolor_css(T.themed_surface_field_bg())};
            border: none;
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {H.qcolor_css(T.PANEL_HOVER)};
        }}
    """

def plain_theme_line_edit_style(font_size: int) -> str:
    return f"""
        QLineEdit {{
            {H.label_style(
                font_size=font_size,
                bold=True,
                color=T.theme_text_color(),
            )}
            background-color: {H.qcolor_css(T.WINDOW_BG)};
            border: none;
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {H.qcolor_css(T.PANEL_HOVER)};
        }}
    """

def plain_theme_label_style(font_size: int) -> str:
    return f"""
        QLabel {{
            {H.label_style(
                font_size=font_size,
                bold=True,
                color=T.theme_text_color(),
            )}
            background-color: {H.qcolor_css(T.WINDOW_BG)};
            border: none;
            border-radius: 6px;
            padding: 4px 8px;
        }}
    """

def surfaced_label_style(font_size: int = 14) -> str:
    return f"""
        QLabel {{
            {H.label_style(
                font_size=font_size,
                bold=True,
                color=T.theme_text_color(),
            )}
            background-color: {H.qcolor_css(T.SURFACE_BG)};
            border: none;
            border-bottom: 1px solid {H.qcolor_css(T.SURFACE_BORDER)};
            border-radius: 6px;
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
    font_size = H.coerce_font_size(font_size, 14) or 14
    font_point_size = font_size * 72 / 96
    font_point_rule = f"font-size: {font_point_size:g}pt;"
    popup_background = popup_background or background
    popup_text = popup_text or text
    disabled_text = disabled_text or T.themed_button_disabled_text()
    disabled_border = disabled_border or T.themed_button_disabled_border()
    chevron_path = H.dropdown_chevron_path().as_posix()
    return f"""
        QComboBox {{
            {H.label_style(
                font_size=None,
                bold=True,
                color=text,
                font_family=font_family,
            )}
            {font_point_rule}
            background-color: {H.qcolor_css(background)};
            border: 1px solid {H.qcolor_css(border)};
            border-radius: 6px;
            padding: 4px 34px 4px 10px;
        }}
        QComboBox:disabled {{
            color: {H.qcolor_css(disabled_text)};
            border: 1px solid {H.qcolor_css(disabled_border)};
        }}
        QComboBox:enabled {{
            color: {H.qcolor_css(text)};
            border: 1px solid {H.qcolor_css(border)};
        }}
        QComboBox:hover {{
            border-color: {H.qcolor_css(pressed_hover)};
        }}
        QComboBox[persistPressed="true"] {{
            border: 2px solid {H.qcolor_css(text)};
        }}
        QComboBox[persistPressed="true"]:hover {{
            border-color: {H.qcolor_css(text)};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 28px;
            background-color: {H.qcolor_css(background)};
            border: none;
            border-left: 1px solid {H.qcolor_css(border)};
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
        }}
        QComboBox:disabled::drop-down {{
            background-color: {H.qcolor_css(background)};
            border: none;
            border-left: 1px solid {H.qcolor_css(disabled_border)};
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
        }}
        QComboBox:enabled::drop-down {{
            background-color: {H.qcolor_css(background)};
            border-left: 1px solid {H.qcolor_css(border)};
        }}
        QComboBox:hover::drop-down {{
            background-color: {H.qcolor_css(background)};
        }}
        QComboBox::drop-down:on {{
            background-color: {H.qcolor_css(background)};
        }}
        QComboBox::down-arrow {{
            image: url("{chevron_path}");
            width: 10px;
            height: 6px;
        }}
        QComboBox QAbstractItemView {{
            {font_point_rule}
            background-color: {H.qcolor_css(popup_background)};
            color: {H.qcolor_css(popup_text)};
            selection-background-color: {H.qcolor_css(hover)};
            selection-color: {H.qcolor_css(popup_text)};
            border: 1px solid {H.qcolor_css(border)};
            border-radius: 6px;
            padding: 4px;
            outline: 0;
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 18px;
            padding: 6px 10px;
            border: none;
        }}
        QComboBox QAbstractItemView::item:disabled {{
            color: {H.qcolor_css(disabled_text)};
            background-color: {H.qcolor_css(popup_background)};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {H.qcolor_css(hover)};
            color: {H.qcolor_css(popup_text)};
            border-left: 3px solid {H.qcolor_css(pressed)};
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {H.qcolor_css(hover)};
            color: {H.qcolor_css(popup_text)};
        }}
    """

def surfaced_combo_style(font_size: int) -> str:
    return _modern_combo_style(
        font_size,
        background=T.themed_button_bg(),
        hover=T.themed_button_hover(),
        pressed=T.themed_button_pressed(),
        pressed_hover=T.themed_button_pressed_hover(),
        border=T.themed_button_border(),
        text=T.dropdown_text_color(),
    )

def connected_drives_combo_style(font_size: int, font_family: str = "Segoe UI") -> str:
    return _modern_combo_style(
        font_size,
        background=T.themed_button_bg(),
        hover=T.themed_button_hover(),
        pressed=T.themed_button_pressed(),
        pressed_hover=T.themed_button_pressed_hover(),
        border=T.themed_button_border(),
        text=T.dropdown_text_color(),
        font_family=font_family,
    )

def power_combo_style(font_size: int) -> str:
    if T.THEME_IS_DARK:
        power_bg = T.power_action_title_background_color()
        power_hover = QColor(39, 132, 224)
        power_pressed = QColor(19, 94, 174)
        power_pressed_hover = QColor(31, 111, 197)
        power_border = QColor(86, 166, 244)
    else:
        power_bg = T.power_action_title_background_color()
        power_hover = QColor(68, 153, 238)
        power_pressed = QColor(31, 108, 188)
        power_pressed_hover = QColor(52, 130, 208)
        power_border = QColor(25, 92, 160)

    return _modern_combo_style(
        font_size,
        background=power_bg,
        hover=power_hover,
        pressed=power_pressed,
        pressed_hover=power_pressed_hover,
        border=power_border,
        text=T.dropdown_text_color(),
        popup_background=T.SURFACE_BG,
        popup_text=T.theme_text_color(),
        disabled_text=QColor(211, 216, 223),
        disabled_border=T.SURFACE_BORDER,
    )

def emphasized_surface_line_edit_style(font_size: int) -> str:
    active_bg = T.PANEL_HOVER if T.THEME_IS_DARK else QColor(214, 226, 242)
    return f"""
        QLineEdit {{
            {H.label_style(
                font_size=font_size,
                bold=True,
                color=T.themed_surface_field_text(),
            )}            
            background-color: {H.qcolor_css(active_bg)};
            border: none;
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {H.qcolor_css(T.PANEL_BG)};
        }}
    """

def combo_style(font_size: int) -> str:
    return _modern_combo_style(
        font_size,
        background=T.themed_button_bg(),
        hover=T.themed_button_hover(),
        pressed=T.themed_button_pressed(),
        pressed_hover=T.themed_button_pressed_hover(),
        border=T.themed_button_border(),
        text=T.dropdown_text_color(),
    )

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
            H.label_style(
                font_size=font_size,
                bold=True,
                color=T.themed_surface_field_text(),
                font_family=font_family,
            ),
            H.qcolor_css(T.themed_surface_field_bg()),
            H.qcolor_css(T.themed_surface_field_text()),
            H.qcolor_css(T.themed_surface_field_border()),
            H.qcolor_css(T.PANEL_HOVER),
            H.qcolor_css(T.themed_surface_field_text()),
            H.qcolor_css(T.PANEL_HOVER),
            H.qcolor_css(T.themed_surface_field_text()),
        )
    )

def organizing_combo_style(font_size: int) -> str:
    return _modern_combo_style(
        font_size,
        background=T.themed_button_bg(),
        hover=T.themed_button_hover(),
        pressed=T.themed_button_pressed(),
        pressed_hover=T.themed_button_pressed_hover(),
        border=T.themed_button_border(),
        text=T.dropdown_text_color(),
    )

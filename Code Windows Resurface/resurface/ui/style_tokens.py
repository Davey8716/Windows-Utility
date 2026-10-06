"""Mutable theme palette and shared layout tokens."""

from PySide6.QtGui import QColor

TEXT_LIGHT = QColor(255, 255, 255)
TEXT_DARK = QColor(17, 24, 32)
# The light theme uses quiet blue-grey surfaces instead of pure/off-white.
# This keeps the app comfortable to look at over long sessions, while fields
# still have a clear, slightly lighter separation from their containers.
OFF_WHITE_FIELD_BG = QColor(229, 236, 242)

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
PAGE_CONTROL_ROW_GAP = 12
PAGE_COMPACT_CONTROL_WIDTH = 119
PAGE_WIDE_CONTROL_MAX_WIDTH = 300
PAGE_COMBO_POPUP_MAX_WIDTH = 420
RIGHT_SECTION_MAX_WIDTH = 492
EXTERNAL_DRIVES_CONTENT_WIDTH = RIGHT_SECTION_MAX_WIDTH - 4
EXTERNAL_DRIVES_CONTROL_WIDTH = (
    EXTERNAL_DRIVES_CONTENT_WIDTH - PAGE_CONTROL_GAP
) // 2
POPUP_CORNER_RADIUS = 0
POPUP_BORDER_WIDTH = 2
BUTTON_CORNER_RADIUS = 6

def set_theme(is_dark: bool) -> None:
    global WINDOW_BG, SURFACE_BG, SURFACE_HOVER, PANEL_BG, PANEL_HOVER
    global SURFACE_BORDER, SURFACE_DARK, SURFACE_HOVER_DARK, SURFACE_HOVER_LIGHT
    global CURRENT_TEXT, THEME_IS_DARK, BUTTON_BORDER

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
        WINDOW_BG = QColor(91, 101, 112)
        SURFACE_BG = QColor(106, 116, 128)
        SURFACE_HOVER = QColor(120, 131, 143)
        SURFACE_BORDER = QColor(126, 142, 160)
        CURRENT_TEXT = TEXT_DARK

    SURFACE_DARK = SURFACE_BG
    SURFACE_HOVER_DARK = SURFACE_HOVER
    SURFACE_HOVER_LIGHT = SURFACE_HOVER
    BUTTON_BORDER = SURFACE_BORDER

def theme_text_color() -> QColor:
    return CURRENT_TEXT

def control_text_color() -> QColor:
    return TEXT_LIGHT

def dropdown_text_color() -> QColor:
    """Return the selected-value color used by shared combo-box controls."""
    # Dropdowns use the same blue control surface in both themes, so their
    # foreground should remain the calm light control colour rather than the
    # high-contrast light-theme text colour.
    return TEXT_LIGHT

def button_text_color() -> QColor:
    """Return the enabled text color for standard action buttons."""
    # Standard actions use blue surfaces in both themes.  Keeping their text
    # light avoids the stark black-on-blue treatment in light mode.
    return TEXT_LIGHT

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

def power_action_title_background_color() -> QColor:
    return QColor(42, 134, 230) if not THEME_IS_DARK else QColor(26, 118, 214)

def power_action_title_color() -> QColor:
    return dropdown_text_color()

def power_action_color(severity: str) -> QColor:
    """Return the theme-aware colour associated with a Power & Session action."""
    dark_colors = {
        "placeholder": QColor(26, 118, 214), "blue": QColor(36, 104, 196),
        "yellow": QColor(120, 99, 0), "amber": QColor(146, 86, 0),
        "orange": QColor(169, 75, 0), "orange_red": QColor(198, 67, 35),
        "red": QColor(176, 38, 38),
    }
    light_colors = {
        "placeholder": QColor(42, 134, 230), "blue": QColor(36, 104, 196),
        "yellow": QColor(120, 99, 0), "amber": QColor(146, 86, 0),
        "orange": QColor(169, 75, 0), "orange_red": QColor(198, 67, 35),
        "red": QColor(204, 52, 52),
    }
    return (dark_colors if THEME_IS_DARK else light_colors)[severity]

def power_action_item_foreground(label: str, background: QColor) -> QColor:
    """Return the accessible text colour used on a Power & Session action."""
    return TEXT_LIGHT

def tooltip_border() -> QColor:
    return SURFACE_BORDER if THEME_IS_DARK else QColor(120, 120, 120)

def theme_muted_text_color() -> QColor:
    return QColor(176, 188, 204) if THEME_IS_DARK else QColor(76, 88, 104)

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


"""Shared style formatting, asset, and widget-sizing helpers."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics

from resurface.ui import style_tokens as T
from resurface.ui.tooltips import format_tooltip_text

def qcolor_css(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexRgb)

def dropdown_chevron_path() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    roots = []
    if bundle_root:
        roots.append(Path(bundle_root))
    roots.append(Path(__file__).resolve().parents[3])

    chevron_name = (
        "Dropdown Chevron.svg" if T.THEME_IS_DARK else "Dropdown Chevron Light.svg"
    )
    for root in roots:
        for icon_dir in (root / "App Icons", root / "App Icons" / "Light Theme"):
            candidate = icon_dir / chevron_name
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

def label_style(
    font_size: int | None = None,
    bold: bool = True,
    color: QColor | None = None,
    font_family: str | None = None,
) -> str:
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

def apply_default_button_size(
    button,
    width: int = T.DEFAULT_BUTTON_WIDTH,
    height: int = T.DEFAULT_BUTTON_HEIGHT,
) -> None:
    button.setFixedSize(width, height)
    button.setCursor(Qt.CursorShape.PointingHandCursor)

def apply_page_control_size(
    widget,
    *,
    width: int = T.PAGE_CONTROL_WIDTH,
    height: int = T.PAGE_CONTROL_HEIGHT,
    role: str = "standard",
) -> None:
    widget.setFixedSize(int(width), int(height))
    widget.setProperty("pageControlRole", role)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)

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
        T.PAGE_WIDE_CONTROL_MAX_WIDTH,
        max(T.PAGE_CONTROL_WIDTH, collapsed_needed),
    )
    role = "wide" if width > T.PAGE_CONTROL_WIDTH else "standard"
    apply_page_control_size(combo, width=width, role=role)

    popup_needed = width
    for row in range(combo.count()):
        item_text = combo.itemText(row)
        popup_needed = max(popup_needed, metrics.horizontalAdvance(item_text) + 42)
        combo.setItemData(row, format_tooltip_text(item_text), Qt.ItemDataRole.ToolTipRole)
    popup_width = min(T.PAGE_COMBO_POPUP_MAX_WIDTH, popup_needed)
    combo.view().setMinimumWidth(popup_width)
    combo.setProperty("comboPopupWidth", popup_width)
    return width

"""Shared presentation details for external-drive notifications."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize

from resurface.ui import styles


USB_POPUP_ICON_SIZE = QSize(126, 126)


def usb_popup_icon_path() -> Path:
    """Return the bundled USB artwork after its historical asset move."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    roots = [Path(bundle_root)] if bundle_root else []
    roots.append(Path(__file__).resolve().parents[3])

    for root in roots:
        candidate = root / "App Icons" / "Light Theme" / "Usb Icon.png"
        if candidate.is_file():
            return candidate

    return roots[-1] / "App Icons" / "Light Theme" / "Usb Icon.png"


def status_popup_options() -> dict:
    """Options shared by non-blocking external-drive status notifications."""
    return {
        "timeout_ms": 10_000,
        "accessory_icon_path": usb_popup_icon_path(),
        "accessory_icon_size": USB_POPUP_ICON_SIZE,
        "minimum_popup_width": 460,
        "text_minimum_width": 320,
        "center_text_block": True,
        "accessory_leading_spacer_width": 34,
        "show_close_now_button": True,
        "popup_corner_radius": styles.BUTTON_CORNER_RADIUS,
    }


def reminder_popup_options() -> dict:
    """Options shared by acknowledgement-only external-drive reminders."""
    return {
        "accessory_icon_path": usb_popup_icon_path(),
        "accessory_icon_size": USB_POPUP_ICON_SIZE,
        "minimum_popup_width": 460,
        "text_minimum_width": 320,
        "center_text_block": True,
        "accessory_leading_spacer_width": 34,
        "popup_corner_radius": styles.BUTTON_CORNER_RADIUS,
    }

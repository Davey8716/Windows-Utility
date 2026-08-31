from __future__ import annotations

from resurface.features.desktop.desktop_icon_layout import (
    desktop_icons_visible,
    set_desktop_icons_visible,
)


class ZenModeService:
    def set_enabled(self, enabled: bool) -> bool | None:
        try:
            changed = set_desktop_icons_visible(not enabled)
        except Exception as exc:
            print("[DESKTOP ICONS] Visibility change failed:", exc)
            return None
        if not changed:
            print("[DESKTOP ICONS] Desktop list view not found")
            return None
        return enabled

    def icons_visible(self) -> bool | None:
        try:
            return desktop_icons_visible()
        except Exception as exc:
            print("[DESKTOP ICONS] Visibility read failed:", exc)
            return None

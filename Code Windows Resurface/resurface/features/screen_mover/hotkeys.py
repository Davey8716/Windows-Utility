from __future__ import annotations

from collections import OrderedDict
import re
from typing import Callable, Mapping

try:
    from pynput import keyboard
except Exception:  # pragma: no cover - exercised only when dependency is absent.
    keyboard = None


ACTION_LABELS = OrderedDict(
    (
        ("FAR_LEFT", "Move Far Left"),
        ("LEFT", "Move Left"),
        ("RIGHT", "Move Right"),
        ("FAR_RIGHT", "Move Far Right"),
        ("MINIMIZE", "Minimize Window"),
        ("MAXIMIZE", "Maximize Window"),
    )
)
VALID_ACTIONS = tuple(ACTION_LABELS.keys())

_MODIFIER_ALIASES = {
    "ctrl": "<ctrl>",
    "control": "<ctrl>",
    "ctl": "<ctrl>",
    "alt": "<alt>",
    "option": "<alt>",
    "shift": "<shift>",
    "win": "<cmd>",
    "windows": "<cmd>",
    "cmd": "<cmd>",
    "command": "<cmd>",
    "meta": "<cmd>",
    "super": "<cmd>",
}
_MODIFIER_ORDER = ("<ctrl>", "<alt>", "<shift>", "<cmd>")
_SPECIAL_KEY_ALIASES = {
    "esc": "<esc>",
    "escape": "<esc>",
    "enter": "<enter>",
    "return": "<enter>",
    "space": "<space>",
    "tab": "<tab>",
    "backspace": "<backspace>",
    "delete": "<delete>",
    "del": "<delete>",
    "insert": "<insert>",
    "ins": "<insert>",
    "home": "<home>",
    "end": "<end>",
    "pageup": "<page_up>",
    "page_up": "<page_up>",
    "pgup": "<page_up>",
    "pagedown": "<page_down>",
    "page_down": "<page_down>",
    "pgdn": "<page_down>",
    "left": "<left>",
    "right": "<right>",
    "up": "<up>",
    "down": "<down>",
}
_DISPLAY_NAMES = {
    "<ctrl>": "Ctrl",
    "<alt>": "Alt",
    "<shift>": "Shift",
    "<cmd>": "Win",
    "<esc>": "Esc",
    "<enter>": "Enter",
    "<space>": "Space",
    "<tab>": "Tab",
    "<backspace>": "Backspace",
    "<delete>": "Delete",
    "<insert>": "Insert",
    "<home>": "Home",
    "<end>": "End",
    "<page_up>": "PageUp",
    "<page_down>": "PageDown",
    "<left>": "Left",
    "<right>": "Right",
    "<up>": "Up",
    "<down>": "Down",
}


def normalize_hotkey(value: object) -> str:
    raw = str(value or "").strip()
    if not raw or raw.lower() in {"off", "none", "disabled"}:
        return ""

    parts = [part for part in re.split(r"\s*\+\s*", raw) if part]
    if not parts:
        return ""

    modifiers = set()
    key = None
    for part in parts:
        token = part.strip().lower()
        token = token.strip("<>")
        token = token.replace(" ", "").replace("-", "_")

        modifier = _MODIFIER_ALIASES.get(token)
        if modifier:
            modifiers.add(modifier)
            continue

        candidate = _normalize_key_token(token)
        if not candidate or key is not None:
            return ""
        key = candidate

    if not key:
        return ""

    ordered_modifiers = [
        modifier for modifier in _MODIFIER_ORDER if modifier in modifiers
    ]
    return "+".join([*ordered_modifiers, key])


def _normalize_key_token(token: str) -> str:
    if len(token) == 1:
        return token

    if re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", token):
        return f"<{token}>"

    return _SPECIAL_KEY_ALIASES.get(token, "")


def normalize_hotkeys(values: Mapping[str, object] | None) -> dict[str, str]:
    values = values or {}
    return {
        action: normalize_hotkey(values.get(action, ""))
        for action in VALID_ACTIONS
    }


def normalize_unique_hotkeys(
    values: Mapping[str, object] | None,
) -> dict[str, str]:
    """Normalize shortcuts and keep only their first action assignment."""
    normalized = normalize_hotkeys(values)
    assigned = set()
    for action in VALID_ACTIONS:
        hotkey = normalized[action]
        if not hotkey:
            continue
        if hotkey in assigned:
            normalized[action] = ""
            continue
        assigned.add(hotkey)
    return normalized


def active_hotkeys(values: Mapping[str, object] | None) -> dict[str, str]:
    return {
        action: hotkey
        for action, hotkey in normalize_unique_hotkeys(values).items()
        if hotkey
    }


def hotkey_to_display(value: object) -> str:
    hotkey = normalize_hotkey(value)
    if not hotkey:
        return ""

    display_parts = []
    for part in hotkey.split("+"):
        if part in _DISPLAY_NAMES:
            display_parts.append(_DISPLAY_NAMES[part])
            continue
        if re.fullmatch(r"<f([1-9]|1[0-9]|2[0-4])>", part):
            display_parts.append(part.strip("<>").upper())
            continue
        display_parts.append(part.upper() if len(part) == 1 else part)
    return "+".join(display_parts)


class GlobalHotkeyManager:
    def __init__(
        self,
        action_callback: Callable[[str], None],
        *,
        listener_factory: Callable[[dict[str, Callable[[], None]]], object] | None = None,
    ):
        self.action_callback = action_callback
        self.listener_factory = listener_factory
        self.listener = None
        self.hotkeys: dict[str, str] = {}
        self.capture_active = False
        self._shutdown = False

    def update_hotkeys(
        self,
        hotkeys: Mapping[str, object] | None,
    ) -> None:
        normalized = active_hotkeys(hotkeys)
        if normalized == self.hotkeys:
            return

        self._stop_listener()
        self.hotkeys = normalized
        self._start_listener()

    def set_capture_active(self, active: bool) -> None:
        active = bool(active)
        if active == self.capture_active:
            return
        self.capture_active = active
        if active:
            self._stop_listener()
            return
        self._start_listener()

    def _start_listener(self) -> None:
        if (
            self._shutdown
            or self.capture_active
            or not self.hotkeys
            or self.listener is not None
        ):
            return

        bindings = {
            hotkey: self._make_callback(action)
            for action, hotkey in self.hotkeys.items()
        }
        factory = self.listener_factory
        if factory is None:
            if keyboard is None:
                print("[HOTKEYS] pynput keyboard support is unavailable.")
                return
            factory = keyboard.GlobalHotKeys

        try:
            self.listener = factory(bindings)
            self.listener.start()
        except Exception as exc:
            self.listener = None
            print(f"[HOTKEYS] Failed to start global hotkeys: {exc}")

    def stop(self) -> None:
        self._shutdown = True
        self._stop_listener()

    def _stop_listener(self) -> None:
        listener = self.listener
        self.listener = None
        if listener is None:
            return

        try:
            listener.stop()
        except Exception as exc:
            print(f"[HOTKEYS] Failed to stop global hotkeys: {exc}")

    def _make_callback(self, action: str) -> Callable[[], None]:
        def callback() -> None:
            if self.capture_active:
                return
            self.action_callback(action)

        return callback

"""Registry and source-control integration for user-configurable Quick Actions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, Signal
from PySide6.QtWidgets import QComboBox, QMenu, QPushButton, QWidget

from resurface.ui import styles
from resurface.ui.tooltips import registered_tooltip_text


DEFAULT_QUICK_ACTION_IDS = (
    "organising.desktop_screenshot",
    "organising.export_bookmarks",
    "folder.create_desktop_folder",
    "recycle.open",
)


@dataclass(frozen=True)
class QuickActionSpec:
    action_id: str
    label: str
    invoke: Callable[[], None]
    tooltip: str = ""
    source: QPushButton | None = None
    checked: Callable[[], bool] | None = None
    set_checked: Callable[[bool], None] | None = None
    available: Callable[[], tuple[bool, str]] | None = None

    @property
    def is_toggle(self) -> bool:
        return self.checked is not None and self.set_checked is not None


class _SourceWatcher(QObject):
    def __init__(self, registry: "QuickActionRegistry", action_id: str, parent: QObject):
        super().__init__(parent)
        self.registry = registry
        self.action_id = action_id

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.ContextMenu:
            self.registry.show_source_menu(watched, event.globalPos())
            return True
        if event.type() in (
            QEvent.Type.EnabledChange,
            QEvent.Type.ToolTipChange,
            QEvent.Type.StyleChange,
        ):
            self.registry.action_changed.emit(self.action_id)
        return False


class _DropdownWatcher(QObject):
    def __init__(
        self,
        registry: "QuickActionRegistry",
        action_ids: tuple[str, ...],
        parent: QObject,
    ):
        super().__init__(parent)
        self.registry = registry
        self.action_ids = action_ids

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.ContextMenu:
            self.registry.show_dropdown_menu(watched, self.action_ids, event.globalPos())
            return True
        return False


class QuickActionRegistry(QObject):
    pins_changed = Signal()
    action_changed = Signal(str)

    def __init__(self, state: dict, save_state: Callable[[dict], None], parent=None):
        super().__init__(parent)
        self.state = state
        self._save_state = save_state
        self._specs: dict[str, QuickActionSpec] = {}
        self._button_watchers: list[QObject] = []
        self._raw_ids = state.get("quick_action_ids", DEFAULT_QUICK_ACTION_IDS)
        self._pinned_ids = self._normalize_shape(self._raw_ids)

    @staticmethod
    def _normalize_shape(value) -> list[str]:
        if not isinstance(value, list):
            value = list(DEFAULT_QUICK_ACTION_IDS)
        result: list[str] = []
        seen: set[str] = set()
        for value_id in value:
            if not isinstance(value_id, str) or value_id in seen:
                continue
            seen.add(value_id)
            result.append(value_id)
        return result

    def register(self, spec: QuickActionSpec) -> None:
        if spec.action_id in self._specs:
            raise ValueError(f"Duplicate Quick Action ID: {spec.action_id}")
        self._specs[spec.action_id] = spec
        if spec.source is not None:
            watcher = _SourceWatcher(self, spec.action_id, spec.source)
            spec.source.installEventFilter(watcher)
            self._button_watchers.append(watcher)
            if spec.source.isCheckable():
                spec.source.toggled.connect(
                    lambda _checked, action_id=spec.action_id: self.action_changed.emit(action_id)
                )
        self.action_changed.emit(spec.action_id)

    def register_button(
        self,
        action_id: str,
        label: str,
        button: QPushButton,
        *,
        tooltip: str = "",
        available: Callable[[], tuple[bool, str]] | None = None,
    ) -> None:
        tooltip = tooltip or registered_tooltip_text(button)
        checked = (lambda: button.isChecked()) if button.isCheckable() else None
        set_checked = (lambda value: button.setChecked(bool(value))) if checked else None
        self.register(
            QuickActionSpec(
                action_id,
                label,
                button.click,
                tooltip,
                button,
                checked,
                set_checked,
                available,
            )
        )

    def register_dropdown(
        self,
        combo: QComboBox,
        actions: list[QuickActionSpec],
    ) -> None:
        ids = []
        fallback_tooltip = registered_tooltip_text(combo)
        for spec in actions:
            if not spec.tooltip and fallback_tooltip:
                spec = replace(spec, tooltip=fallback_tooltip)
            self.register(spec)
            ids.append(spec.action_id)
        watcher = _DropdownWatcher(self, tuple(ids), combo)
        combo.installEventFilter(watcher)
        self._button_watchers.append(watcher)

    def finalize(self) -> None:
        normalized = [action_id for action_id in self._pinned_ids if action_id in self._specs]
        if normalized != self._pinned_ids or self.state.get("quick_action_ids") != normalized:
            self._pinned_ids = normalized
            self._persist()
        self.pins_changed.emit()

    def specs(self) -> list[QuickActionSpec]:
        return [self._specs[action_id] for action_id in self._pinned_ids if action_id in self._specs]

    def spec(self, action_id: str) -> QuickActionSpec | None:
        return self._specs.get(action_id)

    def pinned_ids(self) -> list[str]:
        return list(self._pinned_ids)

    def is_pinned(self, action_id: str) -> bool:
        return action_id in self._pinned_ids

    def pin(self, action_id: str) -> bool:
        if action_id not in self._specs or action_id in self._pinned_ids:
            return False
        self._pinned_ids.append(action_id)
        self._persist()
        return True

    def unpin(self, action_id: str) -> bool:
        if action_id not in self._pinned_ids:
            return False
        self._pinned_ids.remove(action_id)
        self._persist()
        return True

    def move(self, action_id: str, target_index: int) -> bool:
        if action_id not in self._pinned_ids:
            return False
        old_index = self._pinned_ids.index(action_id)
        target_index = max(0, min(int(target_index), len(self._pinned_ids) - 1))
        if old_index == target_index:
            return False
        self._pinned_ids.pop(old_index)
        self._pinned_ids.insert(target_index, action_id)
        self._persist()
        return True

    def reset(self) -> None:
        self._pinned_ids = [
            action_id for action_id in DEFAULT_QUICK_ACTION_IDS if action_id in self._specs
        ]
        self._persist()

    def availability(self, spec: QuickActionSpec) -> tuple[bool, str]:
        if spec.available is not None:
            try:
                return spec.available()
            except Exception as error:
                return False, f"Unavailable: {error}"
        if spec.source is not None and not spec.source.isEnabled():
            reason = spec.source.toolTip() or "This action is currently unavailable."
            return False, reason
        return True, ""

    def show_source_menu(self, source: QWidget, global_pos: QPoint) -> None:
        menu = self.source_menu(source)
        if menu is not None:
            menu.exec(global_pos)

    def source_menu(self, source: QWidget) -> QMenu | None:
        spec = next((item for item in self._specs.values() if item.source is source), None)
        if spec is None:
            return None
        menu = QMenu(source)
        styles.apply_popup_menu_style(menu)
        if self.is_pinned(spec.action_id):
            action = menu.addAction("Unpin from Quick Actions")
            action.triggered.connect(lambda: self.unpin(spec.action_id))
        else:
            action = menu.addAction("Pin to Quick Actions")
            action.triggered.connect(lambda: self.pin(spec.action_id))
        return menu

    def show_dropdown_menu(
        self, source: QWidget, action_ids: tuple[str, ...], global_pos: QPoint
    ) -> None:
        self.dropdown_menu(source, action_ids).exec(global_pos)

    def dropdown_menu(self, source: QWidget, action_ids: tuple[str, ...]) -> QMenu:
        menu = QMenu(source)
        styles.apply_popup_menu_style(menu)
        unpinned = [self._specs[action_id] for action_id in action_ids if not self.is_pinned(action_id)]
        pinned = [self._specs[action_id] for action_id in action_ids if self.is_pinned(action_id)]
        if unpinned:
            pin_menu = QMenu("Pin to Quick Actions", menu)
            menu.addMenu(pin_menu)
            for spec in unpinned:
                pin_menu.addAction(
                    spec.label,
                    lambda _checked=False, action_id=spec.action_id: self.pin(action_id),
                )
        if pinned:
            unpin_menu = QMenu("Unpin from Quick Actions", menu)
            menu.addMenu(unpin_menu)
            for spec in pinned:
                unpin_menu.addAction(
                    spec.label,
                    lambda _checked=False, action_id=spec.action_id: self.unpin(action_id),
                )
        return menu

    def _persist(self) -> None:
        self.state["quick_action_ids"] = list(self._pinned_ids)
        self._save_state(self.state)
        self.pins_changed.emit()

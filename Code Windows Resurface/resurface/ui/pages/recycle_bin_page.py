from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget, QVBoxLayout, QSizePolicy

from resurface.ui import styles
from resurface.ui.pages.page_controls import PageControls
from resurface.ui.tooltips import tooltip_text


class RecycleBinPage(PageControls):
    action_requested = Signal(str)
    settings_changed = Signal(dict)
    availability_changed = Signal(bool)

    def __init__(self, settings: dict, register_tooltip, parent=None):
        super().__init__("recycle_bin_actions", register_tooltip, parent)
        controls = QWidget(); controls.setProperty("centeredControlGrid", True)
        controls.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QGridLayout(controls); layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(self.CONTROL_COLUMN_GAP); layout.setVerticalSpacing(styles.PAGE_CONTROL_ROW_GAP)
        actions = self.make_action_dropdown(
            " Cleanup Actions ", ["Open Recycle Bin", "Run Auto-Clean Now", "Empty Recycle Bin"],
            lambda name: self.action_requested.emit({"Open Recycle Bin": "open", "Run Auto-Clean Now": "run", "Empty Recycle Bin": "empty"}[name]),
        )
        layout.addWidget(actions, 0, 0)
        self.actions_combo = actions
        actions.setProperty("lightModeBlackDisabledText", True)
        actions.setProperty("lightModeKeepEnabledBackground", True)
        actions.setStyleSheet(styles.organizing_combo_style(14))
        self._has_items_checker: Callable[[], bool] | None = None
        self._background_refresh = None
        self._empty_action_timer = QTimer(self)
        self._empty_action_timer.setInterval(2_000)
        self._empty_action_timer.timeout.connect(self.refresh_empty_action_availability)
        self.register_tooltip(actions, tooltip_text("cleanup_actions"))
        enabled = bool(settings.get("recycle_bin_auto_clean_enabled", False))
        toggle = self.make_toggle_button("Auto-clean", enabled)
        self.auto_clean_button = toggle
        self.bind_toggle_state_text(toggle, "Auto-clean")
        toggle.setFixedWidth(self.RIGHT_CONTROL_COLUMN_WIDTH); layout.addWidget(toggle, 0, 1)
        self.register_tooltip(toggle, tooltip_text("recycle_bin_auto_clean"))
        days = int(settings.get("recycle_bin_age_rule_days", 30))
        age = self.make_value_dropdown(["7 days", "14 days", "30 days"], f"{days} days")
        self.age_combo = age
        age.setProperty("lightModeBlackDisabledText", True)
        age.setStyleSheet(styles.organizing_combo_style(14))
        age.setFixedWidth(self.RIGHT_CONTROL_COLUMN_WIDTH)
        self.register_tooltip(age, tooltip_text("recycle_bin_age_rule"))
        label = QLabel("Delete items older than:"); label.setFixedWidth(self.LEFT_CONTROL_COLUMN_WIDTH)
        label.setProperty("surfaceLabelStyle", True); label.setProperty("styleFontSize", 14)
        label.setStyleSheet(styles.surfaced_label_style(14))
        self._age_row = QWidget(); age_layout = QGridLayout(self._age_row)
        age_layout.setContentsMargins(0, 0, 0, 0); age_layout.setHorizontalSpacing(self.CONTROL_COLUMN_GAP)
        age_layout.addWidget(label, 0, 0); age_layout.addWidget(age, 0, 1)
        slot = QWidget(); slot.setFixedWidth(self.CONTROL_ROW_WIDTH); slot.setFixedHeight(self._age_row.sizeHint().height())
        slot_layout = QVBoxLayout(slot); slot_layout.setContentsMargins(0, 0, 0, 0); slot_layout.addWidget(self._age_row)
        layout.addWidget(slot, 1, 0, 1, 2)
        controls.setFixedWidth(self.CONTROL_ROW_WIDTH); self.content_layout.addWidget(controls)
        self._settings = {"recycle_bin_auto_clean_enabled": enabled, "recycle_bin_age_rule_days": days}
        self._age_row.setVisible(enabled)
        self._set_cleanup_actions_enabled(enabled)
        toggle.toggled.connect(self._enabled_changed)
        age.currentTextChanged.connect(self._age_changed)

    def set_empty_action_availability_checker(
        self, has_items: Callable[[], bool]
    ) -> None:
        """Update the disabled state from the live Windows Recycle Bin state."""
        self._has_items_checker = has_items
        self.refresh_empty_action_availability()
        self._empty_action_timer.start()

    def set_background_refresh(self, refresh) -> None:
        self._background_refresh = refresh
        refresh.recycle_ready.connect(self.apply_empty_action_snapshot)
        self._empty_action_timer.timeout.disconnect(self.refresh_empty_action_availability)
        self._empty_action_timer.timeout.connect(refresh.request_recycle_scan)
        refresh.request_recycle_scan()

    def apply_empty_action_snapshot(self, has_items: bool) -> None:
        self.availability_changed.emit(bool(has_items))

    def refresh_empty_action_availability(self) -> None:
        if self._has_items_checker is None:
            return
        try:
            has_items = bool(self._has_items_checker())
        except Exception:
            has_items = False
        self.availability_changed.emit(has_items)

    def _set_cleanup_actions_enabled(self, enabled: bool) -> None:
        for label in ("Run Auto-Clean Now", "Empty Recycle Bin"):
            index = self.actions_combo.findText(label)
            item = self.actions_combo.model().item(index)
            if item is not None:
                item.setEnabled(enabled)

    def _enabled_changed(self, enabled: bool) -> None:
        self._settings["recycle_bin_auto_clean_enabled"] = bool(enabled)
        self._age_row.setVisible(enabled)
        self._set_cleanup_actions_enabled(enabled)
        self.settings_changed.emit(dict(self._settings))

    def _age_changed(self, text: str) -> None:
        try: days = int(text.split()[0])
        except (IndexError, ValueError): return
        self._settings["recycle_bin_age_rule_days"] = days
        self.settings_changed.emit(dict(self._settings))

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget, QVBoxLayout, QSizePolicy

from resurface.ui import styles
from resurface.ui.pages.page_controls import PageControls
from resurface.ui.tooltips import tooltip_text


class RecycleBinPage(PageControls):
    action_requested = Signal(str)
    settings_changed = Signal(dict)

    def __init__(self, settings: dict, register_tooltip, parent=None):
        super().__init__("recycle_bin_actions", register_tooltip, parent)
        controls = QWidget(); controls.setProperty("centeredControlGrid", True)
        controls.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QGridLayout(controls); layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(self.CONTROL_COLUMN_GAP); layout.setVerticalSpacing(10)
        actions = self.make_action_dropdown(
            " Cleanup Actions ", ["Open Recycle Bin", "Run Auto-Clean Now", "Empty Recycle Bin"],
            lambda name: self.action_requested.emit({"Open Recycle Bin": "open", "Run Auto-Clean Now": "run", "Empty Recycle Bin": "empty"}[name]),
        )
        layout.addWidget(actions, 0, 0)
        self.actions_combo = actions
        self._has_items_checker: Callable[[], bool] | None = None
        self._cleanup_age_availability_checker: Callable[[], dict[int, bool]] | None = None
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
        toggle.toggled.connect(self._enabled_changed)
        age.currentTextChanged.connect(self._age_changed)

    def set_empty_action_availability_checker(
        self, has_items: Callable[[], bool]
    ) -> None:
        """Update the disabled state from the live Windows Recycle Bin state."""
        self._has_items_checker = has_items
        self.refresh_empty_action_availability()
        self._empty_action_timer.start()

    def set_cleanup_age_availability_checker(
        self, availability: Callable[[], dict[int, bool]]
    ) -> None:
        """Disable cleanup choices for ages with no qualifying bin entries."""
        self._cleanup_age_availability_checker = availability
        self.refresh_cleanup_age_availability()

    def refresh_empty_action_availability(self) -> None:
        if self._has_items_checker is None:
            return
        try:
            has_items = bool(self._has_items_checker())
        except Exception:
            has_items = False
        index = self.actions_combo.findText("Empty Recycle Bin")
        item = self.actions_combo.model().item(index)
        if item is not None:
            item.setEnabled(has_items)
        self.refresh_cleanup_age_availability()

    def refresh_cleanup_age_availability(self) -> None:
        if self._cleanup_age_availability_checker is None:
            return
        try:
            available = self._cleanup_age_availability_checker()
        except Exception:
            available = {}

        has_eligible_items = False
        for days in (7, 14, 30):
            is_available = bool(available.get(days, False))
            has_eligible_items |= is_available
            index = self.age_combo.findText(f"{days} days")
            item = self.age_combo.model().item(index)
            if item is not None:
                item.setEnabled(is_available)

        # Keep the native disabled palette so both light and dark themes remain
        # consistent with the other dropdowns.
        self.age_combo.setEnabled(has_eligible_items)
        run_index = self.actions_combo.findText("Run Auto-Clean Now")
        run_item = self.actions_combo.model().item(run_index)
        if run_item is not None:
            run_item.setEnabled(
                bool(available.get(self._settings["recycle_bin_age_rule_days"], False))
            )

    def _enabled_changed(self, enabled: bool) -> None:
        self._settings["recycle_bin_auto_clean_enabled"] = bool(enabled)
        self._age_row.setVisible(enabled); self.settings_changed.emit(dict(self._settings))

    def _age_changed(self, text: str) -> None:
        try: days = int(text.split()[0])
        except (IndexError, ValueError): return
        self._settings["recycle_bin_age_rule_days"] = days
        self.refresh_cleanup_age_availability()
        self.settings_changed.emit(dict(self._settings))

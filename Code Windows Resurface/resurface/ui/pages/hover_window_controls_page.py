"""Settings page for dwell-based window caption controls."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QPushButton, QWidget

from resurface.features.hover_window_controls.app.identity import (
    DWELL_STEP_MS,
    MAX_DWELL_MS,
    MIN_DWELL_MS,
)
from resurface.features.hover_window_controls.service import normalized_dwell_ms
from resurface.ui import styles
from resurface.ui.pages.page_controls import PageControls
from resurface.ui.tooltips import tooltip_text


class HoverWindowControlsPage(PageControls):
    enabled_changed = Signal(bool)
    taskbar_restore_enabled_changed = Signal(bool)
    dwell_changed = Signal(int)
    calibration_requested = Signal()
    export_requested = Signal()
    import_requested = Signal()
    clear_requested = Signal()

    def __init__(
        self,
        settings: dict,
        register_tooltip,
        *,
        taskbar_restore_available: bool = True,
        enabled: bool = True,
        taskbar_restore_enabled: bool = True,
        dwell_ms: int = 750,
        has_export_changes=None,
        parent=None,
    ) -> None:
        super().__init__("hover_window_controls", register_tooltip, parent)
        self._has_export_changes = has_export_changes
        self.content_layout.setSpacing(8)
        enabled = bool(enabled)
        taskbar_restore_enabled = bool(taskbar_restore_enabled)
        dwell_ms = normalized_dwell_ms(dwell_ms)
        self.enabled_button = self.make_toggle_button("Hover Controls", enabled)
        self.bind_toggle_state_text(self.enabled_button, "Hover Controls")
        self.dwell_combo = QComboBox(self)
        for delay in range(
            MIN_DWELL_MS,
            MAX_DWELL_MS + DWELL_STEP_MS,
            DWELL_STEP_MS,
        ):
            self.dwell_combo.addItem(f"{delay:,} ms dwell", delay)
        self.dwell_combo.setCurrentIndex(self.dwell_combo.findData(dwell_ms))
        self.dwell_combo.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(self.dwell_combo)
        self.dwell_combo.setProperty("styleFontSize", 14)
        self.dwell_combo.setStyleSheet(styles.organizing_combo_style(14))
        styles.fit_page_combo_width(self.dwell_combo, font_size=14)
        self.taskbar_restore_button = self.make_toggle_button(
            "Taskbar Restoration", taskbar_restore_enabled
        )
        self.bind_toggle_state_text(
            self.taskbar_restore_button, "Taskbar Restoration"
        )
        self.add_two_column_control_row(
            self.content_layout,
            self.enabled_button,
            self.taskbar_restore_button,
        )
        self.dwell_combo.setFixedWidth(self.LEFT_CONTROL_COLUMN_WIDTH)
        self.dwell_spacer = QWidget(self)
        self.dwell_row = self.add_two_column_control_row(
            self.content_layout,
            self.dwell_combo,
            self.dwell_spacer,
        )

        if not taskbar_restore_available:
            self.taskbar_restore_button.setEnabled(False)

        self.calibrate_button = self.style_action_button(
            QPushButton("Calibrate Application", self)
        )
        self.export_button = self.style_action_button(
            QPushButton("Export Hover Data", self)
        )
        self.export_button.setProperty("lightModeBlackDisabledText", True)
        self.import_button = self.style_action_button(
            QPushButton("Import Hover Data", self)
        )
        self.clear_button = self.style_action_button(
            QPushButton("Clear Learned Buttons", self)
        )
        self.add_two_column_control_row(
            self.content_layout,
            self.calibrate_button,
            self.clear_button,
        )
        self.add_two_column_control_row(
            self.content_layout,
            self.import_button,
            self.export_button,
        )

        self.register_tooltip(
            self.enabled_button, tooltip_text("hover_controls_enabled")
        )
        self.register_tooltip(
            self.taskbar_restore_button,
            tooltip_text("hover_controls_taskbar_restore"),
        )
        self.register_tooltip(
            self.dwell_combo, tooltip_text("hover_controls_dwell")
        )
        self.register_tooltip(
            self.calibrate_button, tooltip_text("hover_controls_calibrate")
        )
        self.register_tooltip(
            self.import_button, tooltip_text("hover_controls_import")
        )
        self.register_tooltip(
            self.export_button, tooltip_text("hover_controls_export")
        )
        self.register_tooltip(
            self.clear_button, tooltip_text("hover_controls_clear")
        )

        self.enabled_button.toggled.connect(self.enabled_changed)
        self.taskbar_restore_button.toggled.connect(
            self.taskbar_restore_enabled_changed
        )
        self.dwell_combo.currentIndexChanged.connect(self._dwell_selected)
        self.calibrate_button.clicked.connect(self.calibration_requested)
        self.export_button.clicked.connect(self.export_requested)
        self.import_button.clicked.connect(self.import_requested)
        self.clear_button.clicked.connect(self.clear_requested)
        self.refresh_export_button()

    def refresh_export_button(self) -> None:
        try:
            self.export_button.setEnabled(bool(self._has_export_changes()))
        except Exception:
            self.export_button.setEnabled(True)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_export_button()

    def _dwell_selected(self) -> None:
        value = self.dwell_combo.currentData()
        if value is not None:
            self.dwell_changed.emit(int(value))

    def sync_settings(
        self,
        enabled: bool,
        taskbar_restore_enabled: bool,
        dwell_ms: int,
    ) -> None:
        self.enabled_button.blockSignals(True)
        self.enabled_button.setChecked(bool(enabled))
        self.enabled_button.setText(
            "Hover Controls On" if enabled else "Hover Controls Off"
        )
        self.enabled_button.blockSignals(False)
        self.taskbar_restore_button.blockSignals(True)
        self.taskbar_restore_button.setChecked(bool(taskbar_restore_enabled))
        self.taskbar_restore_button.setText(
            "Taskbar Restoration On"
            if taskbar_restore_enabled
            else "Taskbar Restoration Off"
        )
        self.taskbar_restore_button.blockSignals(False)
        index = self.dwell_combo.findData(normalized_dwell_ms(dwell_ms))
        if index >= 0:
            self.dwell_combo.blockSignals(True)
            self.dwell_combo.setCurrentIndex(index)
            self.dwell_combo.blockSignals(False)
        self.refresh_export_button()


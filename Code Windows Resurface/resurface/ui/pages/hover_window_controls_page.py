"""Settings page for dwell-based window caption controls."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton

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
    dwell_changed = Signal(int)
    calibration_requested = Signal()
    export_requested = Signal()
    clear_requested = Signal()

    def __init__(
        self,
        settings: dict,
        register_tooltip,
        *,
        taskbar_restore_available: bool = True,
        parent=None,
    ) -> None:
        super().__init__("hover_window_controls", register_tooltip, parent)
        self.content_layout.setSpacing(16)

        enabled = bool(settings.get("hover_window_controls_enabled", True))
        dwell_ms = normalized_dwell_ms(
            settings.get("hover_window_controls_dwell_ms", 750)
        )
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
        self.add_two_column_control_row(
            self.content_layout, self.enabled_button, self.dwell_combo
        )

        self.calibrate_button = self.style_action_button(
            QPushButton("Calibrate Application…", self)
        )
        self.export_button = self.style_action_button(
            QPushButton("Export Hover Data…", self)
        )
        self.add_two_column_control_row(
            self.content_layout, self.calibrate_button, self.export_button
        )
        self.clear_button = self.style_action_button(
            QPushButton("Clear Learned Buttons…", self)
        )
        self.content_layout.addWidget(
            self.clear_button, 0, Qt.AlignmentFlag.AlignHCenter
        )

        self.taskbar_status = QLabel(self)
        self.taskbar_status.setObjectName("HoverTaskbarRestoreStatus")
        self.taskbar_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.taskbar_status.setWordWrap(True)
        self.taskbar_status.setProperty("styleFontSize", 12)
        self.taskbar_status.setStyleSheet(styles.label_style(font_size=12))
        self.taskbar_status.setText(
            "Taskbar preview restoration is available."
            if taskbar_restore_available
            else (
                "Taskbar preview restoration requires AutoHotkey v2. "
                "Caption-button hover controls remain available."
            )
        )
        self.content_layout.addWidget(
            self.taskbar_status, 0, Qt.AlignmentFlag.AlignHCenter
        )

        self.register_tooltip(
            self.enabled_button, tooltip_text("hover_controls_enabled")
        )
        self.register_tooltip(
            self.dwell_combo, tooltip_text("hover_controls_dwell")
        )
        self.register_tooltip(
            self.calibrate_button, tooltip_text("hover_controls_calibrate")
        )
        self.register_tooltip(
            self.export_button, tooltip_text("hover_controls_export")
        )
        self.register_tooltip(
            self.clear_button, tooltip_text("hover_controls_clear")
        )

        self.enabled_button.toggled.connect(self.enabled_changed)
        self.dwell_combo.currentIndexChanged.connect(self._dwell_selected)
        self.calibrate_button.clicked.connect(self.calibration_requested)
        self.export_button.clicked.connect(self.export_requested)
        self.clear_button.clicked.connect(self.clear_requested)

    def _dwell_selected(self) -> None:
        value = self.dwell_combo.currentData()
        if value is not None:
            self.dwell_changed.emit(int(value))

    def sync_settings(self, enabled: bool, dwell_ms: int) -> None:
        self.enabled_button.blockSignals(True)
        self.enabled_button.setChecked(bool(enabled))
        self.enabled_button.setText(
            "Hover Controls On" if enabled else "Hover Controls Off"
        )
        self.enabled_button.blockSignals(False)
        index = self.dwell_combo.findData(normalized_dwell_ms(dwell_ms))
        if index >= 0:
            self.dwell_combo.blockSignals(True)
            self.dwell_combo.setCurrentIndex(index)
            self.dwell_combo.blockSignals(False)

    def apply_theme(self) -> None:
        self.taskbar_status.setStyleSheet(styles.label_style(font_size=12))

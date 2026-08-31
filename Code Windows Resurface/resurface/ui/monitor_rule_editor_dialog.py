"""Editor dialog for creating and changing a monitor rule."""

from __future__ import annotations

import copy
import os
import uuid

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QVBoxLayout,
)

from resurface.features.monitor_rules import (
    capture_window_geometry,
    enumerate_eligible_windows,
    enumerate_monitors,
    normalize_monitor_rule,
)
from resurface.ui import styles


PLACEMENT_LABELS = {
    "keep_size": "Keep current size",
    "maximize": "Maximize",
    "saved_geometry": "Use captured size and position",
}


class StateIndicatorCheckBox(QCheckBox):
    """Checkbox with an explicit green tick or red cross in its indicator."""

    def paintEvent(self, _event) -> None:
        option = QStyleOptionButton()
        self.initStyleOption(option)
        painter = QStylePainter(self)
        painter.drawControl(QStyle.ControlElement.CE_CheckBox, option)

        indicator = self.style().subElementRect(
            QStyle.SubElement.SE_CheckBoxIndicator, option, self
        ).adjusted(1, 1, -1, -1)
        if not indicator.isValid():
            return

        checked = self.isChecked()
        color = QColor(42, 166, 86) if checked else QColor(210, 70, 70)
        if not self.isEnabled():
            color.setAlpha(130)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(color.darker(125), 1))
        painter.setBrush(color)
        painter.drawRoundedRect(indicator, 3, 3)
        painter.setPen(
            QPen(
                QColor(255, 255, 255, 220 if self.isEnabled() else 150),
                2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        if checked:
            mark = QPainterPath()
            mark.moveTo(indicator.left() + indicator.width() * 0.22, indicator.center().y())
            mark.lineTo(
                indicator.left() + indicator.width() * 0.43,
                indicator.bottom() - indicator.height() * 0.23,
            )
            mark.lineTo(
                indicator.right() - indicator.width() * 0.18,
                indicator.top() + indicator.height() * 0.22,
            )
            painter.drawPath(mark)
        else:
            inset = max(3, int(indicator.width() * 0.27))
            painter.drawLine(
                indicator.topLeft() + QPoint(inset, inset),
                indicator.bottomRight() - QPoint(inset, inset),
            )
            painter.drawLine(
                indicator.topRight() + QPoint(-inset, inset),
                indicator.bottomLeft() + QPoint(inset, -inset),
            )
        painter.restore()


def style_button(button: QPushButton) -> None:
    button.setProperty("styleFontSize", 12)
    button.setStyleSheet(styles.organizing_button_style(12))


class MonitorRuleEditorDialog(QDialog):
    def __init__(
        self,
        parent,
        *,
        rule=None,
        app_hwnd=None,
        monitor_enumerator=None,
        window_enumerator=None,
        geometry_capturer=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Monitor Rule" if rule else "Add Monitor Rule")
        self.setModal(True)
        self.setMinimumWidth(640)
        self._original_rule = copy.deepcopy(rule) if rule else None
        self._app_hwnd = app_hwnd
        self._enumerate_monitors = monitor_enumerator or enumerate_monitors
        self._enumerate_windows = window_enumerator or enumerate_eligible_windows
        self._capture_window_geometry = geometry_capturer or capture_window_geometry
        self._captured_geometry = copy.deepcopy((rule or {}).get("saved_geometry"))
        self._running_windows = []
        self._monitors = []

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        selection_row = QHBoxLayout()
        self.window_combo = QComboBox(self)
        self.window_combo.setMinimumWidth(410)
        self.window_combo.currentIndexChanged.connect(self._running_window_selected)
        refresh_button = QPushButton("Refresh windows", self)
        browse_button = QPushButton("Browse executable", self)
        style_button(refresh_button)
        style_button(browse_button)
        refresh_button.clicked.connect(self.refresh_running_windows)
        browse_button.clicked.connect(self._browse_executable)
        selection_row.addWidget(self.window_combo, 1)
        selection_row.addWidget(refresh_button)
        selection_row.addWidget(browse_button)
        root.addLayout(selection_row)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.name_edit = QLineEdit(self)
        self.executable_edit = QLineEdit(self)
        self.executable_edit.setReadOnly(True)
        self.exact_path_check = StateIndicatorCheckBox(
            "Match this exact executable path", self
        )
        self.title_edit = QLineEdit(self)
        self.title_edit.setPlaceholderText(
            "Optional, case-insensitive text contained in the title"
        )
        self.class_edit = QLineEdit(self)
        self.class_edit.setPlaceholderText("Optional, exact window class")
        self.monitor_combo = QComboBox(self)
        self.placement_combo = QComboBox(self)
        for mode, label in PLACEMENT_LABELS.items():
            self.placement_combo.addItem(label, mode)
        self.placement_combo.currentIndexChanged.connect(self._sync_capture_state)
        self.enabled_check = StateIndicatorCheckBox("Rule enabled", self)
        self.reapply_check = StateIndicatorCheckBox(
            "Reapply if moved to another monitor", self
        )

        form.addRow("Rule name", self.name_edit)
        form.addRow("Executable", self.executable_edit)
        form.addRow("Matching", self.exact_path_check)
        form.addRow("Title contains", self.title_edit)
        form.addRow("Window class", self.class_edit)
        form.addRow("Target monitor", self.monitor_combo)
        form.addRow("Placement", self.placement_combo)
        form.addRow("Status", self.enabled_check)
        form.addRow("Enforcement", self.reapply_check)
        root.addLayout(form)

        geometry_row = QHBoxLayout()
        self.capture_button = QPushButton("Capture size and position", self)
        self.capture_status = QLabel(self)
        self.capture_status.setWordWrap(True)
        self.capture_status.setStyleSheet(styles.page_description_style())
        style_button(self.capture_button)
        self.capture_button.clicked.connect(self._capture_geometry)
        geometry_row.addWidget(self.capture_button)
        geometry_row.addWidget(self.capture_status, 1)
        root.addLayout(geometry_row)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.button_box.setStyleSheet(styles.organizing_button_style(12))
        self.button_box.accepted.connect(self._accept_if_valid)
        self.button_box.rejected.connect(self.reject)
        root.addWidget(self.button_box)

        self.refresh_monitors()
        self.refresh_running_windows()
        self._load_rule(rule or {})
        self._sync_capture_state()

    def _load_rule(self, rule: dict) -> None:
        self.name_edit.setText(str(rule.get("name", "")))
        executable_path = str(rule.get("executable_path", ""))
        executable_name = str(rule.get("executable_name", ""))
        self.executable_edit.setText(executable_path or executable_name)
        self.exact_path_check.setChecked(
            bool(rule.get("match_exact_path", executable_path))
        )
        self.exact_path_check.setEnabled(bool(executable_path))
        self.title_edit.setText(str(rule.get("title_contains", "")))
        self.class_edit.setText(str(rule.get("class_name", "")))
        self.enabled_check.setChecked(bool(rule.get("enabled", True)))
        self.reapply_check.setChecked(bool(rule.get("reapply_if_moved", False)))

        mode_index = self.placement_combo.findData(
            rule.get("placement_mode", "keep_size")
        )
        self.placement_combo.setCurrentIndex(max(0, mode_index))
        target_device = str(rule.get("target_device", ""))
        target_index = self.monitor_combo.findData(target_device)
        if target_device and target_index < 0:
            label = str(rule.get("target_label", target_device))
            self.monitor_combo.addItem(f"{label} (Unavailable)", target_device)
            target_index = self.monitor_combo.count() - 1
        if target_index >= 0:
            self.monitor_combo.setCurrentIndex(target_index)

    def refresh_monitors(self) -> None:
        current_device = self.monitor_combo.currentData()
        try:
            self._monitors = self._enumerate_monitors()
        except Exception:
            self._monitors = []
        self.monitor_combo.clear()
        for monitor in self._monitors:
            self.monitor_combo.addItem(monitor["label"], monitor["device"])
        index = self.monitor_combo.findData(current_device)
        if index >= 0:
            self.monitor_combo.setCurrentIndex(index)

    def refresh_running_windows(self) -> None:
        current_hwnd = self.window_combo.currentData()
        try:
            self._running_windows = self._enumerate_windows(app_hwnd=self._app_hwnd)
        except Exception:
            self._running_windows = []
        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        self.window_combo.addItem("Select a running window...", None)
        for details in self._running_windows:
            label = f"{details['title']} — {details['executable_name']}"
            self.window_combo.addItem(label, details["hwnd"])
            self.window_combo.setItemData(
                self.window_combo.count() - 1,
                details["class_name"],
                Qt.ItemDataRole.ToolTipRole,
            )
        index = self.window_combo.findData(current_hwnd)
        self.window_combo.setCurrentIndex(max(0, index))
        self.window_combo.blockSignals(False)
        self._sync_capture_state()

    def _selected_window(self) -> dict | None:
        hwnd = self.window_combo.currentData()
        return next(
            (item for item in self._running_windows if item["hwnd"] == hwnd), None
        )

    def _running_window_selected(self) -> None:
        details = self._selected_window()
        if details is None:
            self._sync_capture_state()
            return
        self.executable_edit.setText(
            details["executable_path"] or details["executable_name"]
        )
        self.exact_path_check.setEnabled(bool(details["executable_path"]))
        self.exact_path_check.setChecked(bool(details["executable_path"]))
        if not self.name_edit.text().strip():
            self.name_edit.setText(os.path.splitext(details["executable_name"])[0])
        self._sync_capture_state()

    def _browse_executable(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select application executable",
            "",
            "Applications (*.exe);;All files (*)",
        )
        if not path:
            return
        self.executable_edit.setText(os.path.normpath(path))
        self.exact_path_check.setEnabled(True)
        self.exact_path_check.setChecked(True)
        if not self.name_edit.text().strip():
            self.name_edit.setText(os.path.splitext(os.path.basename(path))[0])

    def _sync_capture_state(self) -> None:
        saved_mode = self.placement_combo.currentData() == "saved_geometry"
        self.capture_button.setVisible(saved_mode)
        self.capture_status.setVisible(saved_mode)
        self.capture_button.setEnabled(
            saved_mode and self._selected_window() is not None
        )
        if saved_mode:
            self.capture_status.setText(
                "Captured" if self._captured_geometry else "No geometry captured yet"
            )

    def _capture_geometry(self) -> None:
        details = self._selected_window()
        geometry = self._capture_window_geometry(details["hwnd"]) if details else None
        if geometry is None:
            QMessageBox.warning(self, "Monitor Rules", "Could not capture that window.")
            return
        self._captured_geometry = geometry
        self._sync_capture_state()

    def _draft_rule(self) -> dict | None:
        executable = self.executable_edit.text().strip()
        executable_path = executable if os.path.isabs(executable) else ""
        executable_name = os.path.basename(executable)
        monitor_index = self.monitor_combo.currentIndex()
        raw = {
            "id": (self._original_rule or {}).get("id") or str(uuid.uuid4()),
            "name": self.name_edit.text().strip()
            or os.path.splitext(executable_name)[0],
            "enabled": self.enabled_check.isChecked(),
            "reapply_if_moved": self.reapply_check.isChecked(),
            "executable_name": executable_name,
            "executable_path": executable_path,
            "match_exact_path": self.exact_path_check.isChecked(),
            "title_contains": self.title_edit.text().strip(),
            "class_name": self.class_edit.text().strip(),
            "target_device": self.monitor_combo.currentData(),
            "target_label": self.monitor_combo.currentText().replace(
                " (Unavailable)", ""
            ),
            "placement_mode": self.placement_combo.currentData(),
            "saved_geometry": self._captured_geometry,
        }
        if not executable_name or monitor_index < 0:
            return None
        return normalize_monitor_rule(raw)

    def _validation_message(self) -> str:
        if not self.executable_edit.text().strip():
            return "Select a running window or browse to an executable."
        if self.monitor_combo.currentIndex() < 0:
            return "Select a target monitor."
        if (
            self.placement_combo.currentData() == "saved_geometry"
            and not self._captured_geometry
        ):
            return "Capture a running window's size and position first."
        if self._draft_rule() is None:
            return "The rule contains invalid or incomplete settings."
        return ""

    def _accept_if_valid(self) -> None:
        message = self._validation_message()
        if message:
            QMessageBox.warning(self, "Monitor Rules", message)
            return
        self.accept()

    def result_rule(self) -> dict:
        return self._draft_rule()

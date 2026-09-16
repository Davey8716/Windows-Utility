from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSizePolicy, QWidget

from resurface.ui import styles
from resurface.ui.pages.page_controls import PageControls
from resurface.ui.tooltips import format_tooltip_text, tooltip_text


class ExternalDrivesPage(PageControls):
    settings_changed = Signal(dict)
    drive_open_requested = Signal(str)
    context_menu_requested = Signal(object)

    def __init__(self, settings: dict, register_tooltip, parent=None):
        super().__init__("drive_reminder_options", register_tooltip, parent)
        width = styles.EXTERNAL_DRIVES_CONTROL_WIDTH
        row_width = styles.EXTERNAL_DRIVES_CONTENT_WIDTH
        row = QWidget()
        row.setProperty("centeredControlGrid", True)
        row.setFixedWidth(row_width)
        row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(self.CONTROL_COLUMN_GAP)
        self._status_row = row

        self._drives = QComboBox()
        self._drives.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(self._drives, width=width, role="externalDrive")
        self._drives.setMinimumContentsLength(len("No Drives Connected"))
        self._drives.setProperty("connectedDrivesFieldStyle", True)
        self._drives.setProperty("surfaceFieldStyle", True)
        self._drives.setProperty("styleFontSize", 15)
        self._drives.setStyleSheet(styles.connected_drives_combo_style(15))
        self._drives.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._drives.customContextMenuRequested.connect(self.context_menu_requested.emit)
        self._drives.view().viewport().installEventFilter(self)

        self._empty_label = QLabel("No Drives Connected")
        self._empty_label.setProperty("surfaceLabelStyle", True)
        self._empty_label.setProperty("styleFontSize", 14)
        self._empty_label.setStyleSheet(styles.surfaced_label_style(14))
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._empty_label.setFixedSize(width, styles.PAGE_CONTROL_HEIGHT)

        leave = self.make_toggle_button(
            "Drive Leave Reminder", bool(settings.get("usb_idle_enabled", True))
        )
        styles.apply_page_control_size(leave, width=width, role="externalDrive")
        self.bind_toggle_state_text(leave, "Drive Leave Reminder")
        self.register_tooltip(leave, tooltip_text("idle_plugged_reminder"))
        self.leave_reminder_button = leave
        row_layout.addWidget(self._drives); row_layout.addWidget(self._empty_label); row_layout.addWidget(leave)
        self.content_layout.addWidget(row, 0, Qt.AlignmentFlag.AlignHCenter)

        label = QLabel("Plug/unplug notifications:")
        label.setProperty("surfaceLabelStyle", True)
        label.setProperty("styleFontSize", 14)
        label.setStyleSheet(styles.surfaced_label_style(14))
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        label.setFixedSize(width, styles.PAGE_CONTROL_HEIGHT)
        self._notify_combo = QComboBox()
        self._notify_combo.addItem("Off", "off"); self._notify_combo.addItem("On", "on")
        for index in range(self._notify_combo.count()):
            self._notify_combo.setItemData(
                index,
                format_tooltip_text(self._notify_combo.itemText(index)),
                Qt.ItemDataRole.ToolTipRole,
            )
        self._notify_combo.setCursor(Qt.CursorShape.ArrowCursor)
        self._notify_combo.setProperty("styleFontSize", 14)
        self._notify_combo.setProperty("plugUnplugNotificationCombo", True)
        self._notify_combo.setStyleSheet(styles.organizing_combo_style(14))
        styles.apply_page_control_size(self._notify_combo, width=width, role="externalDrive")
        self.register_tooltip(self._notify_combo, tooltip_text("plug_unplug_notify"))
        mode = str(settings.get("usb_plug_notify_mode", "")).lower()
        if mode not in {"on", "off"}:
            mode = "on" if settings.get("usb_plug_enabled", True) else "off"
        self._notify_combo.setCurrentIndex(self._notify_combo.findData(mode))
        self._set_combo_pressed()
        notify_row = QWidget(); notify_row.setProperty("centeredControlGrid", True); notify_row.setFixedWidth(row_width)
        notify_layout = QHBoxLayout(notify_row); notify_layout.setContentsMargins(0, 0, 0, 0); notify_layout.setSpacing(self.CONTROL_COLUMN_GAP)
        notify_layout.addWidget(label); notify_layout.addWidget(self._notify_combo)
        self.content_layout.addWidget(notify_row, 0, Qt.AlignmentFlag.AlignHCenter)
        self._settings = {"usb_idle_enabled": leave.isChecked(), "usb_plug_notify_mode": mode, "usb_plug_enabled": mode != "off"}
        leave.toggled.connect(self._leave_changed)
        self._notify_combo.currentTextChanged.connect(self._notify_changed)
        self.set_connected_drives(())

    def set_connected_drives(self, drives) -> None:
        drives = tuple(sorted(drives))
        self._drives.clear()
        if drives:
            for path in drives:
                text = f"{path} Connected"
                self._drives.addItem(text, path)
                self._drives.setItemData(self._drives.count() - 1, format_tooltip_text(text), Qt.ItemDataRole.ToolTipRole)
            self._drives.setCurrentIndex(0); self._drives.show(); self._empty_label.hide()
            self._drives.setToolTip(format_tooltip_text("Connected drives:\n" + "\n".join(f"{d} Connected" for d in drives)))
        else:
            self._drives.hide(); self._empty_label.show()
            self._empty_label.setToolTip(format_tooltip_text("No Drives Connected"))
        self.apply_drive_field_style()

    def apply_drive_field_style(self) -> None:
        visible_text = self._drives.currentText() or self._drives.placeholderText()
        chosen_size = 15
        chosen_family = "Segoe UI"
        text_width_limit = max(0, self._drives.width() - 34)
        if visible_text and text_width_limit:
            for family in ("Segoe UI", "Arial", "Consolas"):
                for size in (15, 14, 13, 12):
                    if QFontMetrics(QFont(family, size)).horizontalAdvance(visible_text) <= text_width_limit:
                        chosen_family, chosen_size = family, size
                        break
                else:
                    continue
                break
            else:
                chosen_family, chosen_size = "Arial", 12
        self._drives.setProperty("styleFontSize", chosen_size)
        self._drives.setProperty("styleFontFamily", chosen_family)
        self._drives.setStyleSheet(
            styles.connected_drives_combo_style(chosen_size, chosen_family)
        )
        styles.apply_page_control_size(self._drives, width=styles.EXTERNAL_DRIVES_CONTROL_WIDTH, role="externalDrive")
        self._status_row.setFixedWidth(
            styles.EXTERNAL_DRIVES_CONTROL_WIDTH * 2 + styles.PAGE_CONTROL_GAP
        )

    def drive_combo(self) -> QComboBox:
        """Narrow integration point for the existing context-menu controller."""
        return self._drives

    def _open_selected_drive(self, index: int) -> None:
        path = self._drives.itemData(index)
        if path:
            self.drive_open_requested.emit(path)

    def eventFilter(self, watched, event):
        viewport = self._drives.view().viewport()
        if watched is viewport:
            if event.type() == QEvent.Type.MouseButtonRelease:
                if self._drives.view().indexAt(event.pos()).isValid():
                    return True
            if event.type() == QEvent.Type.MouseButtonDblClick:
                index = self._drives.view().indexAt(event.pos())
                if index.isValid():
                    self._open_selected_drive(index.row())
                    self._drives.hidePopup()
                    return True
        return super().eventFilter(watched, event)

    def _leave_changed(self, enabled: bool) -> None:
        self._settings["usb_idle_enabled"] = bool(enabled); self.settings_changed.emit(dict(self._settings))

    def _notify_changed(self, _text: str) -> None:
        mode = self._notify_combo.currentData()
        self._settings.update({"usb_plug_notify_mode": mode, "usb_plug_enabled": mode != "off"})
        self._set_combo_pressed(); self.settings_changed.emit(dict(self._settings))

    def _set_combo_pressed(self) -> None:
        self._notify_combo.setProperty("persistPressed", self._notify_combo.currentData() != "off")
        self._notify_combo.style().unpolish(self._notify_combo); self._notify_combo.style().polish(self._notify_combo)

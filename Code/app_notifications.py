from pathlib import Path

import styles
from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QPainterPath, QPixmap, QRegion
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QMessageBox,
    QWidget,
)


class WindowMessageMixin:
    def _get_grouped_timed_message_boxes(self) -> dict:
        grouped_boxes = getattr(self, "_grouped_timed_message_boxes", None)
        if isinstance(grouped_boxes, dict):
            return grouped_boxes

        grouped_boxes = {}
        self._grouped_timed_message_boxes = grouped_boxes
        return grouped_boxes

    def _get_active_message_boxes(self) -> list:
        active_boxes = getattr(self, "_active_message_boxes", None)
        if isinstance(active_boxes, list):
            return active_boxes

        active_boxes = []
        self._active_message_boxes = active_boxes
        return active_boxes

    def _apply_message_box_icon(self, message_box: QMessageBox, icon) -> None:
        if icon == self._message_box_icon("NoIcon"):
            message_box._suppress_standard_icon = True
            message_box.setIcon(icon)
            message_box.setIconPixmap(QPixmap())
            return
        if icon == self._message_box_icon("Information"):
            message_box._suppress_standard_icon = True
            message_box.setIcon(self._message_box_icon("NoIcon"))
            message_box.setIconPixmap(QPixmap())
            return
        message_box._suppress_standard_icon = False
        message_box.setIcon(icon)

    def _compose_timed_message_text(self, text: str, timeout_seconds: int) -> str:
        return f"{text}\n\nThis message will close in {timeout_seconds} seconds."

    def _refresh_grouped_timed_message(
        self,
        message_box: QMessageBox,
        *,
        title: str,
        timeout_ms: int,
    ) -> None:
        entries = getattr(message_box, "_grouped_entries", [])
        timeout_seconds = max(1, timeout_ms // 1000)
        body = "\n\n".join(
            f"{entry_title}\n{entry_text}" for entry_title, entry_text in entries
        )
        message_box.setWindowTitle(title)
        message_box.setText(self._compose_timed_message_text(body, timeout_seconds))
        self._apply_rounded_window_mask(message_box)

    def _message_box_icon(self, name: str):
        icon_namespace = getattr(QMessageBox, "Icon", QMessageBox)
        return getattr(icon_namespace, name, None)

    def _message_box_button(self, name: str):
        button_namespace = getattr(QMessageBox, "StandardButton", QMessageBox)
        return getattr(button_namespace, name, 0)

    def _set_borderless_message_box(
        self,
        message_box: QMessageBox,
        *,
        stays_on_top: bool = False,
        tool_window: bool = False,
    ) -> QMessageBox:
        message_box.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        message_box.setWindowFlag(Qt.WindowType.CustomizeWindowHint, True)
        message_box.setWindowFlag(Qt.WindowType.WindowTitleHint, False)
        message_box.setWindowFlag(Qt.WindowType.WindowSystemMenuHint, False)
        message_box.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        message_box.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        message_box.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        message_box.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        message_box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, stays_on_top)
        message_box.setWindowFlag(Qt.WindowType.Tool, tool_window)
        message_box.setStyleSheet(styles.message_box_style())
        return message_box

    def _prepare_message_box_layout(self, message_box: QMessageBox) -> None:
        self._suppress_message_box_icon_label(message_box)
        self._balance_message_box_text_padding(message_box)
        self._apply_message_box_accessory(message_box)
        self._center_message_box_text_block(message_box)
        self._ensure_timed_close_button(message_box)
        self._center_message_box_buttons(message_box)

    def _suppress_message_box_icon_label(self, message_box: QMessageBox) -> None:
        if not getattr(message_box, "_suppress_standard_icon", False):
            return

        layout = message_box.layout()
        if not isinstance(layout, QGridLayout):
            return

        for object_name in ("qt_msgboxex_icon_label", "qt_msgbox_icon_label"):
            icon_label = message_box.findChild(QLabel, object_name)
            if icon_label is None:
                continue
            layout.removeWidget(icon_label)
            icon_label.clear()
            icon_label.hide()

    def _ensure_timed_close_button(self, message_box: QMessageBox) -> None:
        if not getattr(message_box, "_show_close_now_button", False):
            return

        if getattr(message_box, "_close_now_button", None) is not None:
            return

        close_button = message_box.addButton(
            "Close now",
            QMessageBox.ButtonRole.AcceptRole,
        )
        message_box._close_now_button = close_button

    def _center_message_box_buttons(self, message_box: QMessageBox) -> None:
        button_box = message_box.findChild(QDialogButtonBox)
        if button_box is None:
            return

        button_box.setCenterButtons(True)
        layout = message_box.layout()
        if isinstance(layout, QGridLayout):
            index = layout.indexOf(button_box)
            if index >= 0:
                row, _, row_span, _ = layout.getItemPosition(index)
                layout.removeWidget(button_box)
                column_span = max(1, layout.columnCount())
                layout.addWidget(
                    button_box,
                    row,
                    0,
                    row_span,
                    column_span,
                    Qt.AlignmentFlag.AlignHCenter,
                )

    def _balance_message_box_text_padding(
        self,
        message_box: QMessageBox,
        padding: int = 16,
    ) -> None:
        layout = message_box.layout()
        if not isinstance(layout, QGridLayout):
            return

        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setHorizontalSpacing(0)

        text_label = message_box.findChild(QLabel, "qt_msgbox_label")
        if text_label is None:
            return

        index = layout.indexOf(text_label)
        if index < 0:
            return

        row, _, row_span, _ = layout.getItemPosition(index)
        layout.removeWidget(text_label)
        text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        column_span = max(1, layout.columnCount())
        layout.addWidget(
            text_label,
            row,
            0,
            row_span,
            column_span,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

    def _center_message_box_text_block(self, message_box: QMessageBox) -> None:
        if not getattr(message_box, "_center_text_block", False):
            return

        text_label = message_box.findChild(QLabel, "qt_msgbox_label")
        if text_label is None:
            return

        text_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )

    def _apply_message_box_accessory(self, message_box: QMessageBox) -> None:
        accessory_path = getattr(message_box, "_accessory_icon_path", None)
        if not accessory_path:
            return

        layout = message_box.layout()
        if not isinstance(layout, QGridLayout):
            return

        text_label = message_box.findChild(QLabel, "qt_msgbox_label")
        if text_label is None:
            return

        accessory_label = getattr(message_box, "_accessory_icon_label", None)
        if accessory_label is None:
            accessory_label = QLabel(message_box)
            accessory_label.setObjectName("message_box_accessory_icon")
            accessory_label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            message_box._accessory_icon_label = accessory_label

        pixmap = QPixmap(str(accessory_path))
        if pixmap.isNull():
            return

        icon_size = getattr(message_box, "_accessory_icon_size", QSize(42, 42))
        scaled_pixmap = pixmap.scaled(
            icon_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        accessory_label.setPixmap(scaled_pixmap)
        accessory_label.setFixedSize(icon_size)

        text_label.setWordWrap(True)
        text_label.setMinimumWidth(
            max(
                int(getattr(message_box, "_text_minimum_width", 0)),
                text_label.minimumWidth(),
            )
        )

        leading_spacer_width = int(
            getattr(message_box, "_accessory_leading_spacer_width", 0)
        )

        text_index = layout.indexOf(text_label)
        if text_index < 0:
            return

        text_row, _, text_row_span, _ = layout.getItemPosition(text_index)
        layout.removeWidget(text_label)
        if leading_spacer_width > 0:
            layout.setColumnMinimumWidth(0, leading_spacer_width)
            layout.setColumnStretch(0, 0)
        else:
            layout.setColumnMinimumWidth(0, 0)
        layout.addWidget(
            text_label,
            text_row,
            1 if leading_spacer_width > 0 else 0,
            text_row_span,
            1,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        accessory_index = layout.indexOf(accessory_label)
        if accessory_index >= 0:
            layout.removeWidget(accessory_label)
        layout.addWidget(
            accessory_label,
            text_row,
            2 if leading_spacer_width > 0 else 1,
            text_row_span,
            1,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        minimum_width = int(getattr(message_box, "_minimum_popup_width", 0))
        if minimum_width > 0:
            message_box.setMinimumWidth(minimum_width)

    def _apply_rounded_window_mask(self, widget: QWidget, radius: int = 10) -> None:
        radius = int(getattr(styles, "POPUP_CORNER_RADIUS", radius))
        if radius <= 0:
            widget.clearMask()
            return
        rect = QRectF(widget.rect())
        if rect.isEmpty():
            return
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        widget.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _exec_message_box(
        self,
        message_box: QMessageBox,
        *,
        stays_on_top: bool = True,
        tool_window: bool = True,
    ) -> int:
        self._set_borderless_message_box(
            message_box,
            stays_on_top=stays_on_top,
            tool_window=tool_window,
        )
        self._prepare_message_box_layout(message_box)
        QTimer.singleShot(0, lambda: self._apply_rounded_window_mask(message_box))
        return message_box.exec()

    def _show_modal_message(
        self,
        icon,
        title: str,
        text: str,
        buttons,
        default_button,
        *,
        stays_on_top: bool = True,
        tool_window: bool = True,
        accessory_icon_path: str | Path | None = None,
        accessory_icon_size: QSize | None = None,
        minimum_popup_width: int | None = None,
        text_minimum_width: int | None = None,
        center_text_block: bool = False,
        accessory_leading_spacer_width: int | None = None,
    ) -> int:
        try:
            message_box = QMessageBox(self)
        except TypeError:
            return self._message_box_button("Cancel")
        self._apply_message_box_icon(message_box, icon)
        message_box.setWindowTitle(title)
        message_box.setText(text)
        if accessory_icon_path:
            message_box._accessory_icon_path = Path(accessory_icon_path)
            message_box._accessory_icon_size = accessory_icon_size or QSize(42, 42)
            message_box._minimum_popup_width = minimum_popup_width or 420
            message_box._text_minimum_width = text_minimum_width or 280
        message_box._center_text_block = center_text_block
        message_box._show_close_now_button = False
        if accessory_leading_spacer_width:
            message_box._accessory_leading_spacer_width = accessory_leading_spacer_width
        message_box.setStandardButtons(buttons)
        message_box.setDefaultButton(default_button)
        message_box.setWindowModality(Qt.WindowModality.ApplicationModal)
        return self._exec_message_box(
            message_box,
            stays_on_top=stays_on_top,
            tool_window=tool_window,
        )

    def _show_timed_message(
        self,
        icon,
        title: str,
        text: str,
        timeout_ms: int = 10_000,
        merge_group: str | None = None,
        merge_title: str | None = None,
        accessory_icon_path: str | Path | None = None,
        accessory_icon_size: QSize | None = None,
        minimum_popup_width: int | None = None,
        text_minimum_width: int | None = None,
        center_text_block: bool = False,
        accessory_leading_spacer_width: int | None = None,
        show_close_now_button: bool = False,
    ) -> QMessageBox:
        timeout_seconds = max(1, timeout_ms // 1000)
        grouped_boxes = self._get_grouped_timed_message_boxes()
        if merge_group:
            active_grouped_box = grouped_boxes.get(merge_group)
            if active_grouped_box is not None:
                active_grouped_box._grouped_entries.append((title, text))
                if icon == self._message_box_icon("Warning"):
                    active_grouped_box.setIcon(icon)
                self._refresh_grouped_timed_message(
                    active_grouped_box,
                    title=merge_title or title,
                    timeout_ms=timeout_ms,
                )
                close_timer = getattr(active_grouped_box, "_close_timer", None)
                if close_timer is not None:
                    close_timer.start(timeout_ms)
                active_grouped_box.show()
                active_grouped_box.raise_()
                active_grouped_box.activateWindow()
                return active_grouped_box
        try:
            message_box = QMessageBox(self)
        except TypeError:
            return None
        self._apply_message_box_icon(message_box, icon)
        message_box.setWindowTitle(title)
        if merge_group:
            message_box._grouped_entries = [(title, text)]
            self._refresh_grouped_timed_message(
                message_box,
                title=merge_title or title,
                timeout_ms=timeout_ms,
            )
        else:
            message_box.setText(
                self._compose_timed_message_text(text, timeout_seconds)
            )
        if accessory_icon_path:
            message_box._accessory_icon_path = Path(accessory_icon_path)
            message_box._accessory_icon_size = accessory_icon_size or QSize(42, 42)
            message_box._minimum_popup_width = minimum_popup_width or 420
            message_box._text_minimum_width = text_minimum_width or 280
        message_box._center_text_block = center_text_block
        message_box._show_close_now_button = show_close_now_button
        if accessory_leading_spacer_width:
            message_box._accessory_leading_spacer_width = accessory_leading_spacer_width
        message_box.setStandardButtons(self._message_box_button("NoButton"))
        message_box.setModal(False)
        self._set_borderless_message_box(
            message_box,
            stays_on_top=True,
            tool_window=True,
        )
        self._prepare_message_box_layout(message_box)
        self._get_active_message_boxes().append(message_box)
        close_timer = QTimer(message_box)
        close_timer.setSingleShot(True)
        message_box._close_timer = close_timer

        def cleanup_message_box():
            active_boxes = self._get_active_message_boxes()
            if message_box in active_boxes:
                active_boxes.remove(message_box)
            if merge_group:
                if grouped_boxes.get(merge_group) is message_box:
                    grouped_boxes.pop(merge_group, None)
            message_box.deleteLater()

        message_box.finished.connect(lambda _: cleanup_message_box())
        close_timer.timeout.connect(message_box.accept)
        if merge_group:
            grouped_boxes[merge_group] = message_box
        message_box.show()
        self._apply_rounded_window_mask(message_box)
        close_timer.start(timeout_ms)
        return message_box

    def _show_acknowledged_message(
        self,
        icon,
        title: str,
        text: str,
        on_close=None,
        accessory_icon_path: str | Path | None = None,
        accessory_icon_size: QSize | None = None,
        minimum_popup_width: int | None = None,
        text_minimum_width: int | None = None,
        center_text_block: bool = False,
        accessory_leading_spacer_width: int | None = None,
    ) -> QMessageBox:
        try:
            message_box = QMessageBox(self)
        except TypeError:
            if on_close:
                on_close()
            return None
        self._apply_message_box_icon(message_box, icon)
        message_box.setWindowTitle(title)
        message_box.setText(text)
        if accessory_icon_path:
            message_box._accessory_icon_path = Path(accessory_icon_path)
            message_box._accessory_icon_size = accessory_icon_size or QSize(42, 42)
            message_box._minimum_popup_width = minimum_popup_width or 420
            message_box._text_minimum_width = text_minimum_width or 280
        message_box._center_text_block = center_text_block
        message_box._show_close_now_button = False
        if accessory_leading_spacer_width:
            message_box._accessory_leading_spacer_width = accessory_leading_spacer_width
        message_box.setStandardButtons(self._message_box_button("Ok"))
        message_box.setWindowModality(Qt.WindowModality.NonModal)
        self._set_borderless_message_box(
            message_box,
            stays_on_top=True,
            tool_window=True,
        )
        self._prepare_message_box_layout(message_box)
        message_box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        message_box.setModal(False)
        self._get_active_message_boxes().append(message_box)

        def cleanup_message_box():
            active_boxes = self._get_active_message_boxes()
            if message_box in active_boxes:
                active_boxes.remove(message_box)
            if on_close:
                on_close()
            message_box.deleteLater()

        message_box.finished.connect(lambda _: cleanup_message_box())
        message_box.show()
        self._apply_rounded_window_mask(message_box)
        message_box.raise_()
        message_box.activateWindow()
        return message_box

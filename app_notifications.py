import styles
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QPainterPath, QPixmap, QRegion
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QMessageBox,
    QWidget,
)


class WindowMessageMixin:
    def _apply_message_box_icon(self, message_box: QMessageBox, icon) -> None:
        if icon == self._message_box_icon("NoIcon"):
            message_box.setIcon(icon)
            message_box.setIconPixmap(QPixmap())
            return
        if icon == self._message_box_icon("Information"):
            message_box.setIcon(self._message_box_icon("NoIcon"))
            message_box.setIconPixmap(QPixmap())
            return
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

    def _apply_rounded_window_mask(self, widget: QWidget, radius: int = 10) -> None:
        rect = QRectF(widget.rect())
        if rect.isEmpty():
            return
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        widget.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _show_timed_message(
        self,
        icon,
        title: str,
        text: str,
        timeout_ms: int = 10_000,
        merge_group: str | None = None,
        merge_title: str | None = None,
    ) -> QMessageBox:
        timeout_seconds = max(1, timeout_ms // 1000)
        if merge_group:
            active_grouped_box = getattr(self, "_grouped_timed_message_boxes", {}).get(
                merge_group
            )
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
        message_box.setStandardButtons(self._message_box_button("NoButton"))
        message_box.setModal(False)
        self._set_borderless_message_box(
            message_box,
            stays_on_top=True,
            tool_window=True,
        )
        self._active_message_boxes.append(message_box)
        close_timer = QTimer(message_box)
        close_timer.setSingleShot(True)
        message_box._close_timer = close_timer

        def cleanup_message_box():
            if message_box in self._active_message_boxes:
                self._active_message_boxes.remove(message_box)
            if merge_group:
                grouped_boxes = getattr(self, "_grouped_timed_message_boxes", {})
                if grouped_boxes.get(merge_group) is message_box:
                    grouped_boxes.pop(merge_group, None)
            message_box.deleteLater()

        message_box.finished.connect(lambda _: cleanup_message_box())
        close_timer.timeout.connect(message_box.accept)
        if merge_group:
            self._grouped_timed_message_boxes[merge_group] = message_box
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
        message_box.setStandardButtons(self._message_box_button("Ok"))
        message_box.setWindowModality(Qt.WindowModality.NonModal)
        self._set_borderless_message_box(
            message_box,
            stays_on_top=True,
            tool_window=True,
        )
        message_box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        message_box.setModal(False)
        self._active_message_boxes.append(message_box)

        def cleanup_message_box():
            if message_box in self._active_message_boxes:
                self._active_message_boxes.remove(message_box)
            if on_close:
                on_close()
            message_box.deleteLater()

        message_box.finished.connect(lambda _: cleanup_message_box())
        message_box.show()
        self._apply_rounded_window_mask(message_box)
        message_box.raise_()
        message_box.activateWindow()
        return message_box

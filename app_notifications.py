import styles
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QPainterPath, QRegion
from PySide6.QtWidgets import QMessageBox, QWidget


class WindowMessageMixin:
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
    ) -> QMessageBox:
        timeout_seconds = max(1, timeout_ms // 1000)
        try:
            message_box = QMessageBox(self)
        except TypeError:
            return None
        message_box.setIcon(icon)
        message_box.setWindowTitle(title)
        message_box.setText(
            f"{text}\n\nThis message will close in {timeout_seconds} seconds."
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

        def cleanup_message_box():
            if message_box in self._active_message_boxes:
                self._active_message_boxes.remove(message_box)
            message_box.deleteLater()

        message_box.finished.connect(lambda _: cleanup_message_box())
        close_timer.timeout.connect(message_box.accept)
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
        message_box.setIcon(icon)
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

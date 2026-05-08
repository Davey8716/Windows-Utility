from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox, QPushButton

class StatusController:
    def __init__(self, window, service):
        self.w = window
        self.service = service

        self.nested_timer = QTimer(window)
        self.nested_timer.setSingleShot(True)
        self.nested_timer.timeout.connect(lambda: self.reset("nested"))
        self._active_message_box = None
        self._active_dedupe_key = None

    # ---------------------------------------------------------
    # SET STATUS
    # ---------------------------------------------------------
    def set(
        self,
        message: str,
        target: str = "nested",
        status_type: str = "info",
        *,
        timeout_ms: int = 10_000,
        show_close_now_button: bool = True,
        dedupe_key: str | None = None,
    ):
        if (
            dedupe_key is not None
            and self._active_message_box is not None
            and self._active_message_box.isVisible()
            and self._active_dedupe_key == dedupe_key
        ):
            return

        self._close_active_message_box()
        self._active_dedupe_key = dedupe_key

        box = QMessageBox(self.w)
        box.setWindowTitle("Folder Creator")
        box.setText(message)
        box.setStandardButtons(QMessageBox.StandardButton.NoButton)

        if status_type == "success":
            box.setIcon(QMessageBox.Icon.Information)
        elif status_type == "error":
            box.setIcon(QMessageBox.Icon.Warning)
        else:
            box.setIcon(QMessageBox.Icon.Information)

        close_now_button = None
        if show_close_now_button:
            close_now_button = box.addButton(
                "Close Now",
                QMessageBox.ButtonRole.ActionRole,
            )

        box.finished.connect(self._on_message_box_finished)
        box.setModal(False)
        box.show()
        box.raise_()
        box.activateWindow()

        if close_now_button is not None and isinstance(close_now_button, QPushButton):
            close_now_button.setDefault(False)
            close_now_button.setAutoDefault(False)

        self._active_message_box = box
        QTimer.singleShot(timeout_ms, lambda: self._close_message_box(box))

    # ---------------------------------------------------------
    # RESET STATUS
    # ---------------------------------------------------------
    def reset(self, target: str):
        if hasattr(self.w, "smart_status_icon"):
            self.w.smart_status_icon.setText(">")
        if hasattr(self.w, "smart_status_text"):
            self.w.smart_status_text.clear()

    def _close_active_message_box(self) -> None:
        if self._active_message_box is not None:
            self._close_message_box(self._active_message_box)

    def _close_message_box(self, box) -> None:
        if box is None:
            return
        try:
            if box.isVisible():
                box.done(0)
        except RuntimeError:
            pass

    def _on_message_box_finished(self, _result: int) -> None:
        self._active_message_box = None
        self._active_dedupe_key = None

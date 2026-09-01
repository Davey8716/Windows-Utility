from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel


class PathDisplayLabel(QLabel):
    """A label with line-edit-compatible path and change-notification methods."""

    textChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._placeholder_text = ""

    def setPlaceholderText(self, text: str) -> None:
        self._placeholder_text = text

    def setText(self, text: str) -> None:
        previous = self.text()
        super().setText(text)
        if text != previous:
            self.textChanged.emit(text)

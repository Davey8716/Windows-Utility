"""Static placeholder for the retired Hover Window Controls feature."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class HoverWindowControlsPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        placeholder = QFrame(self)
        placeholder.setObjectName("HoverWindowControlsPlaceholder")
        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_layout.setContentsMargins(24, 24, 24, 24)

        message = QLabel("Hover Window Controls has been removed.", placeholder)
        message.setObjectName("HoverWindowControlsRemovedMessage")
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)
        placeholder_layout.addWidget(message)

        layout.addWidget(placeholder, 0, Qt.AlignmentFlag.AlignHCenter)

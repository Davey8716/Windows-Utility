from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout
)
from PyQt6.QtCore import Qt


class CollapsibleSection(QWidget):
    def __init__(self, parent, title_text, section_id, app, initial_open=True):
        super().__init__(parent)

        self.app = app
        self.section_id = section_id
        self.open = initial_open

        # ===============================
        # Main vertical layout
        # ===============================
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 10, 0, 0)
        self.main_layout.setSpacing(4)

        # ===============================
        # Header row
        # ===============================
        self.header = QFrame(self)
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(10, 0, 10, 0)

        self.label = QLabel(title_text, self.header)
        self.label.setStyleSheet("font-weight: bold;")
        self.header_layout.addWidget(self.label)

        self.header_layout.addStretch()

        self.toggle_btn = QPushButton(
            "▾" if initial_open else "▸",
            self.header
        )
        self.toggle_btn.setFixedSize(30, 20)
        self.toggle_btn.setFlat(True)
        self.toggle_btn.clicked.connect(self.toggle)

        self.header_layout.addWidget(self.toggle_btn)
        self.main_layout.addWidget(self.header)

        # ===============================
        # Content frame
        # ===============================
        self.content = QFrame(self)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(10, 0, 10, 10)

        self.content.setVisible(initial_open)
        self.main_layout.addWidget(self.content)

    # -------------------------------------------------
    # Toggle open / closed
    # -------------------------------------------------
    def toggle(self):
        self.open = not self.open
        self.content.setVisible(self.open)
        self.toggle_btn.setText("▾" if self.open else "▸")

        # Resize window if supported
        if hasattr(self.app, "resize_to_fit"):
            self.app.resize_to_fit()

        # Persist state if supported
        if hasattr(self.app, "save_section_states"):
            self.app.save_section_states()

        if hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

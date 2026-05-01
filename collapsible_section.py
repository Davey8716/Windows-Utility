from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QToolButton,
    QVBoxLayout, QHBoxLayout, QSizePolicy
)
from PySide6.QtCore import Qt

import styles

SECTION_FRAME_MAX_WIDTH = 400

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
        self.setMaximumWidth(SECTION_FRAME_MAX_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # ===============================
        # Header row
        # ===============================
        self.header = QFrame(self)
        self.header.setMaximumWidth(SECTION_FRAME_MAX_WIDTH)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(title_text, self.header)
        self.label.setStyleSheet(styles.label_style(font_size=15))
        self.header_layout.addWidget(self.label)

        self.header_layout.addStretch()

        self.toggle_btn = QToolButton(self.header)
        self.toggle_btn.setFixedSize(
            styles.SECTION_TOGGLE_WIDTH,
            styles.SECTION_TOGGLE_HEIGHT
        )
        self.toggle_btn.setAutoRaise(True)
        self.toggle_btn.setArrowType(
            Qt.ArrowType.DownArrow if initial_open else Qt.ArrowType.UpArrow
        )
        self.toggle_btn.setStyleSheet(
            styles.arrow_button_style(styles.TEXT_LIGHT, styles.SURFACE_DARK, font_size=16)
        )
        self.toggle_btn.clicked.connect(self.toggle)

        self.header_layout.addWidget(self.toggle_btn)
        self.main_layout.addWidget(self.header)

        self.container = QFrame(self)
        self.container.setObjectName("CollapsibleSectionFrame")
        self.container.setStyleSheet(styles.collapsible_section_frame_style())
        self.container.setMaximumWidth(SECTION_FRAME_MAX_WIDTH)
        self.container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.main_layout.addWidget(self.container)

        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(2, 2, 2, 2)
        self.container_layout.setSpacing(0)

        # ===============================
        # Content frame
        # ===============================
        self.content = QFrame(self.container)
        self.content.setMaximumWidth(SECTION_FRAME_MAX_WIDTH)
        self.content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(10, 10, 10, 10)

        self.container.setVisible(initial_open)
        self.content.setVisible(initial_open)
        self.container_layout.addWidget(self.content)

    @property
    def is_open(self):
        return self.open

    def set_open(self, is_open):
        if self.open == is_open:
            return
        self.toggle()

    # -------------------------------------------------
    # Toggle open / closed
    # -------------------------------------------------
    def toggle(self):
        self.open = not self.open
        self.container.setVisible(self.open)
        self.content.setVisible(self.open)
        self.toggle_btn.setArrowType(
            Qt.ArrowType.DownArrow if self.open else Qt.ArrowType.UpArrow
        )

        # Resize window if supported
        if hasattr(self.app, "resize_to_fit"):
            self.app.resize_to_fit()

        # Persist state if supported
        if hasattr(self.app, "save_section_states"):
            self.app.save_section_states()

        if hasattr(self.app, "save_all_settings"):
            self.app.save_all_settings()

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout

from folder_creator.ui import styles


class PostBuildPanel:
    """Build the post-build action toggles."""

    EXPORTED_WIDGETS = (
        "post_build_frame",
        "post_build_layout",
        "open_folder_build_toggle",
        "minimize_after_build_toggle",
        "close_app_after_build_toggle",
    )

    def __init__(self, frame_padding: int, control_gap: int):
        self.post_build_frame = QFrame()
        self.post_build_frame.setFrameShape(QFrame.NoFrame)
        self.post_build_frame.setFixedSize(210, 230)
        self.post_build_frame.setStyleSheet("border: none;")

        self.open_folder_build_toggle = QPushButton("Open Dir After Build")
        self.minimize_after_build_toggle = QPushButton("Minmize After Build")
        self.close_app_after_build_toggle = QPushButton("Close After Build")
        styles.apply_window_action_icon(self.minimize_after_build_toggle, "minimize")
        styles.apply_window_action_icon(self.close_app_after_build_toggle, "close")
        self.minimize_after_build_toggle.setProperty("postBuildActionButton", True)
        self.close_app_after_build_toggle.setProperty("postBuildActionButton", True)
        for button in (
            self.open_folder_build_toggle,
            self.minimize_after_build_toggle,
            self.close_app_after_build_toggle,
        ):
            button.setFixedSize(180, styles.DEFAULT_BUTTON_HEIGHT)
            button.setCheckable(True)
            button.setProperty("styleFontSize", 12)

        self.post_build_layout = QVBoxLayout(self.post_build_frame)
        self.post_build_layout.setContentsMargins(15, 15, 15, 15)
        self.post_build_layout.setSpacing(control_gap)
        self.post_build_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.post_build_layout.addWidget(
            self.open_folder_build_toggle, alignment=Qt.AlignLeft
        )
        self.post_build_layout.addWidget(
            self.minimize_after_build_toggle, alignment=Qt.AlignLeft
        )
        self.post_build_layout.addWidget(
            self.close_app_after_build_toggle, alignment=Qt.AlignLeft
        )

    def bind_to(self, window):
        for name in self.EXPORTED_WIDGETS:
            setattr(window, name, getattr(self, name))

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
        self.post_build_frame.setFixedSize(200, 230)
        self.post_build_frame.setStyleSheet("border: none;")

        self.open_folder_build_toggle = QPushButton("OPEN DIR AFTER BUILD")
        self.minimize_after_build_toggle = QPushButton("MINIMIZE AFTER BUILD")
        self.close_app_after_build_toggle = QPushButton("CLOSE AFTER BUILD")
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
            button.setProperty("styleFontSize", 11)

        self.post_build_layout = QVBoxLayout(self.post_build_frame)
        self.post_build_layout.setContentsMargins(
            frame_padding, frame_padding, frame_padding, frame_padding
        )
        self.post_build_layout.setSpacing(control_gap)
        self.post_build_layout.setAlignment(Qt.AlignTop)
        self.post_build_layout.addWidget(self.open_folder_build_toggle)
        self.post_build_layout.addWidget(self.minimize_after_build_toggle)
        self.post_build_layout.addWidget(self.close_app_after_build_toggle)

    def bind_to(self, window):
        for name in self.EXPORTED_WIDGETS:
            setattr(window, name, getattr(self, name))

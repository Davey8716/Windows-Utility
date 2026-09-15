from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from folder_creator.ui import styles
from folder_creator.ui.path_display_label import PathDisplayLabel


class TemplatePanel:
    """Build the template controls and template-save location display."""

    EXPORTED_WIDGETS = (
        "template_controls_frame",
        "load_template_btn",
        "save_template_btn",
        "load_user_template_dropdown",
        "load_default_template_dropdown",
        "template_path_column",
        "template_path_title",
        "template_path_line",
    )

    def __init__(self, frame_padding: int, control_gap: int, tight_gap: int):
        self.load_template_btn = QPushButton("Load Templates")
        self.save_template_btn = QPushButton("Save Templates")
        self.load_user_template_dropdown = QComboBox()
        self.load_user_template_dropdown.addItem("User Templates")
        self.load_user_template_dropdown.insertSeparator(
            self.load_user_template_dropdown.count()
        )

        self.load_default_template_dropdown = QComboBox()
        self.load_default_template_dropdown.addItem("Default Templates")
        self.load_default_template_dropdown.insertSeparator(
            self.load_default_template_dropdown.count()
        )
        self.load_default_template_dropdown.addItems(
            [
                "Architects",
                "Creative Writers",
                "Data Scientists",
                "Game Developers",
                "It Administrators",
                "Photographers",
                "Project Management",
                "Researchers",
                "Software Developers",
                "Video Editing",
            ]
        )
        self.load_default_template_dropdown.setSizeAdjustPolicy(
            QComboBox.AdjustToContentsOnFirstShow
        )
        for index in range(self.load_default_template_dropdown.count()):
            if self.load_default_template_dropdown.itemText(index):
                self.load_default_template_dropdown.setItemData(
                    index,
                    Qt.AlignLeft | Qt.AlignVCenter,
                    Qt.TextAlignmentRole,
                )

        self.template_controls_frame = QFrame()
        self.template_controls_frame.setFrameShape(QFrame.NoFrame)
        self.template_controls_frame.setFixedWidth(
            styles.DEFAULT_BUTTON_WIDTH + (frame_padding * 2)
        )
        self.template_controls_frame.setFixedHeight(230)
        self.template_controls_frame.setStyleSheet("border: none;")
        template_layout = QVBoxLayout(self.template_controls_frame)
        template_layout.setContentsMargins(
            frame_padding, frame_padding, frame_padding, frame_padding
        )
        template_layout.setSpacing(control_gap)
        template_layout.setAlignment(Qt.AlignCenter | Qt.AlignTop)
        template_layout.addWidget(self.load_template_btn)
        template_layout.addWidget(self.save_template_btn)
        template_layout.addWidget(self.load_user_template_dropdown)
        template_layout.addWidget(self.load_default_template_dropdown)

        for button in (self.load_template_btn, self.save_template_btn):
            styles.apply_default_button_size(button)
        for dropdown in (
            self.load_user_template_dropdown,
            self.load_default_template_dropdown,
        ):
            styles.apply_default_button_size(dropdown)
            dropdown.setProperty("styleFontSize", 14)
            dropdown.setStyleSheet(styles.organizing_combo_style(14))

        self.template_path_column = QFrame()
        self.template_path_column.setFrameShape(QFrame.NoFrame)
        self.template_path_column.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.template_path_column.setFixedWidth(400)
        self.template_path_column.setStyleSheet("border: none;")
        path_layout = QVBoxLayout(self.template_path_column)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(tight_gap)

        self.template_path_title = QLabel("TEMPLATE SAVE LOCATION")
        self.template_path_title.setFixedSize(288, 40)
        self.template_path_title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.template_path_title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.template_path_line = PathDisplayLabel()
        self.template_path_line.setPlaceholderText(
            "OUTPUT LOCATION FOR USER MADE TEMPLATES."
        )
        self.template_path_line.setFixedSize(288, 40)
        self.template_path_line.setProperty("surfaceLabelStyle", True)
        self.template_path_line.setProperty("styleFontSize", 14)
        self.template_path_line.setStyleSheet(styles.surfaced_label_style(14))
        self.template_path_line.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.template_path_line.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        path_layout.addWidget(self.template_path_title)
        path_layout.addWidget(self.template_path_line)

    def bind_to(self, window):
        for name in self.EXPORTED_WIDGETS:
            setattr(window, name, getattr(self, name))

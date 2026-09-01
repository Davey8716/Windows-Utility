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


class OutputOptionsPanel:
    """Build date, output-location, and build controls."""

    EXPORTED_WIDGETS = (
        "date_controls_frame",
        "build_buttons_frame",
        "auto_enumerate_folders",
        "nested_date_toggle",
        "nested_date_config",
        "default_to_desktop_btn",
        "output_location_btn",
        "build_folders_btn",
        "base_path_column",
        "base_path_title",
        "base_path_line",
    )

    def __init__(self, frame_padding: int, control_gap: int, tight_gap: int):
        self.auto_enumerate_folders = QPushButton(
            "AUTO NUMBER\nFOLDERS AND\n SUB FOLDERS\n(IF DUPLICATED)"
        )
        self.nested_date_toggle = QPushButton(
            "ADD DATE\n STAMP TO\nPARENT FOLDERS"
        )
        for button in (self.auto_enumerate_folders, self.nested_date_toggle):
            button.setFixedSize(145, 80)
            button.setCheckable(True)

        self.nested_date_config = QComboBox()
        self.nested_date_config.addItems(
            ["ISO YYYY-MM-DD", "UK DD-MM-YYYY", "US MM-DD-YYYY"]
        )
        self.nested_date_config.setEnabled(False)
        self.nested_date_config.setFixedSize(180, styles.DEFAULT_BUTTON_HEIGHT)
        self.nested_date_config.setProperty("styleFontSize", 14)
        self.nested_date_config.setStyleSheet(styles.organizing_combo_style(14))
        for index in range(self.nested_date_config.count()):
            self.nested_date_config.setItemData(
                index,
                Qt.AlignLeft | Qt.AlignVCenter,
                Qt.TextAlignmentRole,
            )
        self.nested_date_config.setEditable(True)
        self.nested_date_config.lineEdit().setAlignment(
            Qt.AlignLeft | Qt.AlignVCenter
        )
        self.nested_date_config.lineEdit().setReadOnly(True)

        self.date_controls_frame = QFrame()
        self.date_controls_frame.setFrameShape(QFrame.NoFrame)
        self.date_controls_frame.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self.date_controls_frame.setFixedSize(190, 230)
        self.date_controls_frame.setStyleSheet("border: none;")
        date_layout = QVBoxLayout(self.date_controls_frame)
        date_layout.setContentsMargins(
            frame_padding, frame_padding, frame_padding, frame_padding
        )
        date_layout.setSpacing(control_gap)
        date_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        date_layout.addWidget(self.auto_enumerate_folders, alignment=Qt.AlignHCenter)
        date_layout.addWidget(self.nested_date_toggle, alignment=Qt.AlignHCenter)
        date_layout.addWidget(self.nested_date_config, alignment=Qt.AlignHCenter)

        self.default_to_desktop_btn = QPushButton("Default To Desk")
        self.output_location_btn = QPushButton("Output Dir")
        self.build_folders_btn = QPushButton("Build 📁")
        for button in (
            self.default_to_desktop_btn,
            self.output_location_btn,
            self.build_folders_btn,
        ):
            styles.apply_default_button_size(button)

        self.build_buttons_frame = QFrame()
        self.build_buttons_frame.setFrameShape(QFrame.NoFrame)
        self.build_buttons_frame.setFixedWidth(
            styles.DEFAULT_BUTTON_WIDTH + (frame_padding * 2)
        )
        self.build_buttons_frame.setFixedHeight(230)
        self.build_buttons_frame.setStyleSheet("border: none;")
        build_layout = QVBoxLayout(self.build_buttons_frame)
        build_layout.setContentsMargins(
            frame_padding, frame_padding, frame_padding, frame_padding
        )
        build_layout.setSpacing(control_gap)
        build_layout.setAlignment(Qt.AlignTop)
        build_layout.addWidget(self.default_to_desktop_btn)
        build_layout.addWidget(self.output_location_btn)
        build_layout.addWidget(self.build_folders_btn)

        self.base_path_column = QFrame()
        self.base_path_column.setFrameShape(QFrame.NoFrame)
        self.base_path_column.setFixedWidth(300)
        self.base_path_column.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.base_path_column.setStyleSheet("border: none;")
        path_layout = QVBoxLayout(self.base_path_column)
        path_layout.setContentsMargins(100, 0, 0, 0)
        path_layout.setSpacing(tight_gap)

        self.base_path_title = QLabel("OUTPUT FOLDER LOCATION")
        self.base_path_title.setFixedSize(300, 40)
        self.base_path_title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.base_path_title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.base_path_line = PathDisplayLabel()
        self.base_path_line.setPlaceholderText(
            "Select base directory for output folder location"
        )
        self.base_path_line.setFixedSize(300, 40)
        self.base_path_line.setProperty("plainThemeLabelStyle", True)
        self.base_path_line.setStyleSheet(styles.plain_theme_label_style(15))
        self.base_path_line.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.base_path_line.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        path_layout.addWidget(self.base_path_title)
        path_layout.addWidget(self.base_path_line)

    def bind_to(self, window):
        for name in self.EXPORTED_WIDGETS:
            setattr(window, name, getattr(self, name))

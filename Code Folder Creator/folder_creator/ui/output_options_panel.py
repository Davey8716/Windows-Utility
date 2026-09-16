from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QVBoxLayout,
)

from folder_creator.ui import styles
from folder_creator.ui.path_display_label import PathDisplayLabel


PATH_DISPLAY_WIDTH = 450
DATE_STAMP_CONTROL_WIDTH = 180


class CenteredDateFormatComboBox(QComboBox):
    """A date-format selector whose current label is centered as a whole."""

    def paintEvent(self, event):
        option = QStyleOptionComboBox()
        self.initStyleOption(option)

        # Draw the normal styled frame and arrow without the default label,
        # whose text rectangle deliberately excludes the arrow button.
        option.currentText = ""
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.CC_ComboBox, option)

        painter.drawItemText(
            self.rect().adjusted(4, 0, -4, 0),
            Qt.AlignHCenter | Qt.AlignVCenter,
            option.palette,
            self.isEnabled(),
            self.currentText(),
        )


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
            "Auto number\nFolders and\n Sub Folders\n(If Duplicated)"
        )
        self.nested_date_toggle = QPushButton(
            "Add Date\n Stamp To\nParent Folders"
        )
        for button in (self.auto_enumerate_folders, self.nested_date_toggle):
            button.setFixedSize(DATE_STAMP_CONTROL_WIDTH, 80)
            button.setCheckable(True)
            button.setProperty("styleFontSize", 12)

        self.nested_date_config = CenteredDateFormatComboBox()
        self.nested_date_config.addItems(
            ["ISO YYYY-MM-DD", "UK DD-MM-YYYY", "US MM-DD-YYYY"]
        )
        self.nested_date_config.setEnabled(False)
        self.nested_date_config.setFixedSize(
            DATE_STAMP_CONTROL_WIDTH, styles.DEFAULT_BUTTON_HEIGHT
        )
        self.nested_date_config.setObjectName("FolderCreatorDateStampDropdown")
        self.nested_date_config.setProperty("styleFontSize", 12)
        self.nested_date_config.setStyleSheet(styles.organizing_combo_style(12))
        for index in range(self.nested_date_config.count()):
            self.nested_date_config.setItemData(
                index,
                Qt.AlignHCenter | Qt.AlignVCenter,
                Qt.TextAlignmentRole,
            )
        self.date_controls_frame = QFrame()
        self.date_controls_frame.setFrameShape(QFrame.NoFrame)
        self.date_controls_frame.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self.date_controls_frame.setFixedSize(210, 230)
        self.date_controls_frame.setStyleSheet("border: none;")
        date_layout = QVBoxLayout(self.date_controls_frame)
        date_layout.setContentsMargins(15, 15, 15, 15)
        date_layout.setSpacing(control_gap)
        date_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        date_layout.addWidget(self.auto_enumerate_folders, alignment=Qt.AlignLeft)
        date_layout.addWidget(self.nested_date_toggle, alignment=Qt.AlignLeft)
        date_layout.addWidget(self.nested_date_config, alignment=Qt.AlignLeft)

        self.default_to_desktop_btn = QPushButton("Default To Desk")
        self.output_location_btn = QPushButton("Output Dir")
        self.build_folders_btn = QPushButton("Build")
        styles.apply_fluent_icon(self.build_folders_btn, "\ue8b7")
        for button in (
            self.default_to_desktop_btn,
            self.output_location_btn,
            self.build_folders_btn,
        ):
            styles.apply_default_button_size(button)
            button.setProperty("styleFontSize", 12)

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
        self.base_path_column.setFixedWidth(PATH_DISPLAY_WIDTH)
        self.base_path_column.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.base_path_column.setStyleSheet("border: none;")
        path_layout = QVBoxLayout(self.base_path_column)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(tight_gap)

        self.base_path_title = QLabel("OUTPUT FOLDER LOCATION")
        self.base_path_title.setFixedSize(PATH_DISPLAY_WIDTH, 40)
        self.base_path_title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.base_path_title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.base_path_line = PathDisplayLabel()
        self.base_path_line.setPlaceholderText(
            "Select base directory for output folder location"
        )
        self.base_path_line.setFixedSize(PATH_DISPLAY_WIDTH, 40)
        self.base_path_line.setProperty("surfaceLabelStyle", True)
        self.base_path_line.setProperty("styleFontSize", 14)
        self.base_path_line.setStyleSheet(styles.surfaced_label_style(14))
        self.base_path_line.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.base_path_line.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        path_layout.addWidget(self.base_path_title)
        path_layout.addWidget(self.base_path_line)

    def bind_to(self, window):
        for name in self.EXPORTED_WIDGETS:
            setattr(window, name, getattr(self, name))

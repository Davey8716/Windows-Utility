import ctypes
import os
import sys
from ctypes import wintypes

from app_service import AppService
from nested_ui_controller import NestedUIController
from smart_tree_widget import SmartTreeWidget
from status_controller import StatusController
from ui_state_controller import UIStateController
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

MAX_NESTED_FOLDER_NAME_LENGTH = 64

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "FolderCreator_SingleInstance"

_single_instance_mutex = None


def already_running():
    global _single_instance_mutex

    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    create_mutex.restype = wintypes.HANDLE

    ctypes.set_last_error(0)

    handle = create_mutex(None, False, MUTEX_NAME)
    _single_instance_mutex = handle

    if handle is None or handle == 0:
        return False

    return ctypes.get_last_error() == ERROR_ALREADY_EXISTS


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.tree = SmartTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderHidden(True)
        self.tree.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.service = AppService(self.tree)
        self.status = StatusController(self, self.service)
        self.setWindowTitle("Folder Generator")

        self.window_width = 900
        self.window_height = 1085
        self.tree_default_height = 420
        self.tree_expanded_height = 620
        outer_margin = 8
        section_gap = 8
        frame_padding = 6
        control_gap = 8
        tight_gap = 4
        top_frame_inset = 1
        controls_to_tree_gap = 2
        tree_to_controls_gap = 2
        header_gap = 1
        self.setFixedSize(self.window_width, self.window_height)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignTop)
        main_layout.setContentsMargins(outer_margin, outer_margin, outer_margin, outer_margin)
        main_layout.setSpacing(section_gap)
        central_widget.setLayout(main_layout)

        header_grid = QGridLayout()
        header_grid.setContentsMargins(frame_padding, frame_padding, frame_padding, frame_padding)
        header_grid.setHorizontalSpacing(header_gap)
        header_grid.setVerticalSpacing(frame_padding)

        title_label = QLabel("Nested Folder Creator")
        title_label.setFixedSize(230, 50)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            """
            QLabel {
                background: transparent;
                border: none;
                color: #ffffff;
                font-family: "Segoe UI";
                font-size: 20px;
                font-weight: 1000;
            }
            """
        )

        header_grid.addWidget(title_label, 0, 0)
        header_grid.setColumnStretch(0, 1)
        main_layout.addLayout(header_grid)

        self.smart_folder_creator_frame = QFrame()
        self.smart_folder_creator_frame.setFrameShape(QFrame.NoFrame)
        self.smart_folder_creator_frame.setStyleSheet("border: none;")
        self.smart_folder_creator_frame.setFixedWidth(875)
        self.smart_folder_creator_frame.setFixedHeight(999)

        self.smart_layout = QVBoxLayout()
        self.smart_layout.setSpacing(0)
        self.smart_layout.setContentsMargins(frame_padding, top_frame_inset, frame_padding, frame_padding)
        self.smart_folder_creator_frame.setLayout(self.smart_layout)

        main_controls_layout = QGridLayout()
        main_controls_layout.setContentsMargins(0, 0, 0, 0)
        main_controls_layout.setHorizontalSpacing(section_gap)
        main_controls_layout.setVerticalSpacing(section_gap)
        main_controls_layout.setSizeConstraint(QLayout.SetFixedSize)
        self.smart_layout.addLayout(main_controls_layout)
        self.smart_layout.addSpacing(controls_to_tree_gap)

        self.add_folder_btn = QPushButton("📁 Add")
        self.add_subfolder_btn = QPushButton("📂 Sub")
        self.remove_btn = QPushButton("Remove\nSelected")
        self.remove_all_btn = QPushButton("Remove\nAll")
        self.load_template_btn = QPushButton("Load Templates")
        self.save_template_btn = QPushButton("Save Templates")

        self.load_user_template_dropdown = QComboBox()
        self.load_user_template_dropdown.addItems(["User Templates"])
        self.load_user_template_dropdown.insertSeparator(self.load_user_template_dropdown.count())

        self.load_default_template_dropdown = QComboBox()
        self.load_default_template_dropdown.addItem("Default Templates")
        self.load_default_template_dropdown.insertSeparator(self.load_default_template_dropdown.count())
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
        self.load_default_template_dropdown.setSizeAdjustPolicy(QComboBox.AdjustToContentsOnFirstShow)

        for i in range(self.load_default_template_dropdown.count()):
            if self.load_default_template_dropdown.itemText(i) == "":
                continue
            self.load_default_template_dropdown.setItemData(
                i,
                Qt.AlignLeft | Qt.AlignVCenter,
                Qt.TextAlignmentRole,
            )

        self.auto_enumerate_folders = QPushButton("AUTO NUMBER\nFOLDERS AND\n SUB FOLDERS\n(IF DUPLICATED)")
        self.nested_date_toggle = QPushButton("ADD DATE\n STAMP TO\nPARENT FOLDERS")

        for button in [self.auto_enumerate_folders, self.nested_date_toggle]:
            button.setFixedWidth(145)
            button.setCheckable(True)
            button.setFixedHeight(80)

        self.nested_date_config = QComboBox()
        self.nested_date_config.addItems(["ISO YYYY-MM-DD", "UK DD-MM-YYYY", "US MM-DD-YYYY"])
        self.nested_date_config.setEnabled(False)
        self.nested_date_config.setFixedWidth(160)
        self.nested_date_config.setFixedHeight(40)

        for i in range(self.nested_date_config.count()):
            self.nested_date_config.setItemData(
                i,
                Qt.AlignLeft | Qt.AlignVCenter,
                Qt.TextAlignmentRole,
            )

        self.nested_date_config.setEditable(True)
        self.nested_date_config.lineEdit().setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.nested_date_config.lineEdit().setReadOnly(True)

        self.template_controls_frame = QFrame()
        self.template_controls_frame.setFrameShape(QFrame.NoFrame)
        self.template_controls_frame.setFixedWidth(165)

        template_layout = QVBoxLayout()
        template_layout.setContentsMargins(frame_padding, frame_padding, frame_padding, frame_padding)
        template_layout.setSpacing(control_gap)
        self.template_controls_frame.setLayout(template_layout)
        template_layout.addWidget(self.load_template_btn)
        template_layout.addWidget(self.save_template_btn)
        template_layout.addWidget(self.load_user_template_dropdown)
        template_layout.addWidget(self.load_default_template_dropdown)
        template_layout.setAlignment(Qt.AlignCenter | Qt.AlignTop)

        self.folder_buttons_frame = QFrame()
        self.folder_buttons_frame.setFrameShape(QFrame.NoFrame)
        self.folder_buttons_frame.setFixedWidth(190)

        folder_buttons_layout = QVBoxLayout()
        folder_buttons_layout.setContentsMargins(frame_padding, frame_padding, frame_padding, frame_padding)
        folder_buttons_layout.setSpacing(control_gap)
        self.folder_buttons_frame.setLayout(folder_buttons_layout)

        top_row = QHBoxLayout()
        top_row.setSpacing(control_gap)
        self.add_folder_btn.setFixedSize(80, 40)
        self.add_subfolder_btn.setFixedSize(80, 40)
        top_row.addStretch()
        top_row.addWidget(self.add_folder_btn)
        top_row.addWidget(self.add_subfolder_btn)
        top_row.addStretch()

        file_row = QHBoxLayout()
        file_row.setSpacing(control_gap)
        self.file_dropdown = QComboBox()
        self.file_dropdown.addItems(
            [
                "ADD BLANK 📑",
                "──────────",
                "Python (.py)",
                "JavaScript (.js)",
                "HTML (.html)",
                "CSS (.css)",
                "──────────",
                "Text (.txt)",
                "Markdown (.md)",
                "README.md",
                "──────────",
                "JSON (.json)",
                "YAML (.yaml)",
                "ENV (.env)",
                "──────────",
                "Batch (.bat)",
                "PowerShell (.ps1)",
            ]
        )
        self.file_dropdown.setFixedSize(170, 40)
        file_row.addStretch()
        file_row.addWidget(self.file_dropdown)
        file_row.addStretch()

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(control_gap)
        self.remove_btn.setFixedSize(85, 50)
        self.remove_all_btn.setFixedSize(85, 50)
        bottom_row.addStretch()
        bottom_row.addWidget(self.remove_btn)
        bottom_row.addWidget(self.remove_all_btn)
        bottom_row.addStretch()

        folder_buttons_layout.addLayout(top_row)
        folder_buttons_layout.addLayout(file_row)
        folder_buttons_layout.addLayout(bottom_row)
        folder_buttons_layout.addStretch()

        self.date_controls_frame = QFrame()
        self.date_controls_frame.setFrameShape(QFrame.NoFrame)
        self.date_controls_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.date_controls_frame.setFixedWidth(190)

        date_layout = QVBoxLayout()
        date_layout.setContentsMargins(frame_padding, frame_padding, frame_padding, frame_padding)
        date_layout.setSpacing(control_gap)
        date_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.date_controls_frame.setLayout(date_layout)
        date_layout.addWidget(self.auto_enumerate_folders, alignment=Qt.AlignHCenter)
        date_layout.addWidget(self.nested_date_toggle, alignment=Qt.AlignHCenter)
        date_layout.addWidget(self.nested_date_config, alignment=Qt.AlignHCenter)

        self.build_buttons_frame = QFrame()
        self.build_buttons_frame.setFrameShape(QFrame.NoFrame)
        self.build_buttons_frame.setFixedWidth(145)

        build_layout = QVBoxLayout()
        build_layout.setContentsMargins(frame_padding, frame_padding, frame_padding, frame_padding)
        build_layout.setSpacing(control_gap)
        self.build_buttons_frame.setLayout(build_layout)

        self.default_to_desktop_btn = QPushButton("Default To Desk")
        self.output_location_btn = QPushButton("Output Dir")
        self.build_folders_btn = QPushButton("Build 📁")

        for btn in [self.load_template_btn, self.save_template_btn]:
            btn.setFixedSize(145, 40)

        for btn in [self.default_to_desktop_btn, self.output_location_btn, self.build_folders_btn]:
            btn.setFixedHeight(40)
            btn.setFixedWidth(125)

        build_layout.addWidget(self.default_to_desktop_btn)
        build_layout.addWidget(self.output_location_btn)
        build_layout.addWidget(self.build_folders_btn)
        build_layout.setAlignment(Qt.AlignTop)

        self.post_build_frame = QFrame()
        self.post_build_frame.setFrameShape(QFrame.NoFrame)
        self.post_build_frame.setFixedWidth(140)

        self.open_folder_build_toggle = QPushButton("OPEN OUTPUT\nDIR AFTER\n BUILD")
        self.minimize_after_build_toggle = QPushButton("▬ APP\nAFTER BUILD")
        self.close_app_after_build_toggle = QPushButton("❌ APP\nAFTER BUILD")

        for btn in [
            self.open_folder_build_toggle,
            self.minimize_after_build_toggle,
            self.close_app_after_build_toggle,
        ]:
            btn.setFixedWidth(120)
            btn.setMinimumHeight(60)
            btn.setCheckable(True)

        self.post_build_layout = QVBoxLayout()
        self.post_build_layout.setContentsMargins(frame_padding, frame_padding, frame_padding, frame_padding)
        self.post_build_layout.setSpacing(control_gap)
        self.post_build_layout.setAlignment(Qt.AlignTop)
        self.post_build_frame.setLayout(self.post_build_layout)
        self.post_build_layout.addWidget(self.open_folder_build_toggle)
        self.post_build_layout.addWidget(self.minimize_after_build_toggle)
        self.post_build_layout.addWidget(self.close_app_after_build_toggle)

        for frame in [
            self.build_buttons_frame,
            self.date_controls_frame,
            self.folder_buttons_frame,
            self.post_build_frame,
            self.template_controls_frame,
        ]:
            frame.setFixedHeight(230)
            frame.setStyleSheet("border: none;")

        for dropdown in [self.load_user_template_dropdown, self.load_default_template_dropdown]:
            dropdown.setFixedSize(145, 40)

        widgets = [
            self.folder_buttons_frame,
            self.date_controls_frame,
            self.post_build_frame,
            self.template_controls_frame,
            self.build_buttons_frame,
        ]
        for col, widget in enumerate(widgets):
            main_controls_layout.addWidget(widget, 0, col)
            main_controls_layout.setColumnStretch(col, 1)

        self.base_path_line = QLineEdit()
        self.base_path_line.setPlaceholderText("Select base directory for output folder location")
        self.template_path_line = QLineEdit()
        self.template_path_line.setPlaceholderText("OUTPUT LOCATION FOR USER MADE TEMPLATES.")

        paths_layout = QHBoxLayout()
        paths_layout.setContentsMargins(frame_padding, frame_padding, frame_padding, frame_padding)
        paths_layout.setSpacing(section_gap)

        self.template_path_column = QFrame()
        self.template_path_column.setFrameShape(QFrame.NoFrame)
        self.template_path_column.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.template_path_column.setFixedWidth(360)
        template_col_layout = QVBoxLayout()
        template_col_layout.setContentsMargins(frame_padding, frame_padding, frame_padding, frame_padding)
        template_col_layout.setSpacing(tight_gap)
        self.template_path_column.setLayout(template_col_layout)

        self.base_path_column = QFrame()
        self.base_path_column.setFrameShape(QFrame.NoFrame)
        self.base_path_column.setFixedWidth(396)
        self.base_path_column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        base_col_layout = QVBoxLayout()
        base_col_layout.setContentsMargins(frame_padding, frame_padding, frame_padding, frame_padding)
        base_col_layout.setSpacing(tight_gap)
        self.base_path_column.setLayout(base_col_layout)

        self.template_path_title = QLabel("TEMPLATE SAVE LOCATION")
        self.base_path_title = QLabel("OUTPUT FOLDER LOCATION")

        for location_line in [self.template_path_line, self.base_path_line]:
            location_line.setFixedSize(300, 40)
            location_line.setReadOnly(True)
            location_line.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        for title in [self.template_path_title, self.base_path_title]:
            title.setFixedWidth(200)
            title.setFixedHeight(40)
            title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            title.setAlignment(Qt.AlignCenter)

        template_col_layout.addWidget(self.template_path_title)
        template_col_layout.addWidget(self.template_path_line)
        base_col_layout.addWidget(self.base_path_title)
        base_col_layout.addWidget(self.base_path_line)

        paths_layout.addWidget(self.template_path_column)
        paths_layout.addStretch()
        paths_layout.addWidget(self.base_path_column)

        self.tree.setFixedWidth(852)
        self.tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.tree.setFixedHeight(self.tree_default_height)
        self.tree.setPlaceholderText(
            (
                "Files can either be drag drop loaded in here."
                "Or created/loaded using the buttons above."
                "(accepts .json, .txt, .md files).\n\n"
                "Default files can be added to folders and subfolders.\n"
                "Duplicate default files in these folders will be ignored.\n\n"
                "User templates using the save button are saved as .json, md or.txt."
                "A copy of them will be saved to:\n"
                "C:/Users/yourusername/AppData/Local/FolderCreator/.\n"
                "To access this easily, right click the dropdown arrow on 'User Templates'.\n"
                "Drag-and-dropped templates are also saved there automatically.\n\n"
                "Folder trees can be copy pasted in here using Ctrl + V as plain text."
                "Entire trees from your desktop can be dragged onto here.\n"
                "Files will be ignored and only the folder structure will be shown.\n\n"
                "Hotkeys:\n"
                "Ctrl + N → Add Folder."
                "Ctrl + Shift + N → Add Subfolder."
                "Ctrl + S → Save Template."
                "Ctrl + O → Load Template.\n"
                "F2 → Rename."
                "Delete → Remove selected folder.\n\n"
                "Template tip:\n"
                "Templates can be saved as .json, .txt, or .md using the save dialog.\n\n"
                "Tips:\n"
                "• Drag folders to change hierarchy."
                "• Drag below → new parent-level folder."
                "• Drag onto → make subfolder.\n"
                "• Auto-numbering only applies when using Add Folder/Subfolder buttons.\n"
                "• Auto-numbering is disabled for default templates."
                "• Drag-and-drop only changes structure."
            ),
            bold=True,
        )
        self.smart_layout.addWidget(self.tree, alignment=Qt.AlignHCenter)
        self.smart_layout.addSpacing(tree_to_controls_gap)

        tree_controls_layout = QHBoxLayout()
        tree_controls_layout.setContentsMargins(frame_padding, frame_padding, frame_padding, frame_padding)
        tree_controls_layout.setSpacing(control_gap)

        self.expand_tree_btn = QPushButton("EXPAND 🌳")
        self.expand_folders_collapse_btn = QPushButton("EXPAND FOLDERS")
        self.sort_btn = QPushButton("SORT A/Z ↕️")
        self.find_btn = QPushButton("FIND 🔎")
        self.find_output_line = QLineEdit()
        self.find_output_line.setPlaceholderText("INPUT FOR FINDING FOLDERS.")
        self.find_output_line.setEnabled(True)
        self.find_output_line.setFixedSize(230, 40)

        self.expand_tree_btn.setFixedSize(120, 40)
        self.expand_folders_collapse_btn.setFixedSize(140, 40)
        self.sort_btn.setFixedSize(110, 40)
        self.find_btn.setFixedSize(80, 40)

        tree_controls_layout.addWidget(self.expand_tree_btn)
        tree_controls_layout.addWidget(self.expand_folders_collapse_btn)
        tree_controls_layout.addStretch()
        tree_controls_layout.addWidget(self.sort_btn)
        tree_controls_layout.addWidget(self.find_btn)
        tree_controls_layout.addWidget(self.find_output_line)

        self.expand_folders_collapse_btn.setEnabled(False)
        self.find_btn.setEnabled(False)
        self.sort_btn.setEnabled(False)
        self.smart_layout.addLayout(tree_controls_layout)
        self.smart_layout.addSpacing(section_gap)

        self.bottom_info_frame = QFrame()
        self.bottom_info_frame.setFrameShape(QFrame.NoFrame)
        self.bottom_info_frame.setFixedWidth(854)
        self.bottom_info_frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        bottom_info_layout = QVBoxLayout()
        bottom_info_layout.setContentsMargins(frame_padding, frame_padding, frame_padding, frame_padding)
        bottom_info_layout.setSpacing(section_gap)
        bottom_info_layout.setSizeConstraint(QLayout.SetFixedSize)
        self.bottom_info_frame.setLayout(bottom_info_layout)

        bottom_info_layout.addLayout(paths_layout)

        self.smart_status_frame = QFrame()
        self.smart_status_frame.setObjectName("statusFrame")
        self.smart_status_frame.setFrameShape(QFrame.NoFrame)
        self.smart_status_frame.setFixedHeight(50)
        self.smart_status_frame.setFixedWidth(832)
        self.smart_status_frame.setStyleSheet("border: none;")

        smart_status_layout = QHBoxLayout()
        smart_status_layout.setContentsMargins(frame_padding, frame_padding, frame_padding, frame_padding)
        smart_status_layout.setSpacing(control_gap)
        self.smart_status_frame.setLayout(smart_status_layout)

        self.smart_status_icon = QLabel(">")
        self.smart_status_text = QLabel("")
        self.smart_status_text.setMaximumWidth(700)
        smart_status_layout.addWidget(self.smart_status_icon)
        smart_status_layout.addWidget(self.smart_status_text)
        smart_status_layout.addStretch()

        for frame in [self.template_path_column, self.base_path_column, self.bottom_info_frame]:
            frame.setStyleSheet("border: none;")

        bottom_info_layout.addWidget(self.smart_status_frame, alignment=Qt.AlignHCenter)
        self.smart_layout.addWidget(self.bottom_info_frame, alignment=Qt.AlignHCenter)
        main_layout.addWidget(self.smart_folder_creator_frame, alignment=Qt.AlignHCenter)

        self.ui_state = UIStateController(self)
        self.nested_ui = NestedUIController(self)
        self.nested_ui.connect_signals()

        self.tree.itemExpanded.connect(self.update_expand_button_text)
        self.tree.itemExpanded.connect(self.ui_state.update_build_button_state)
        self.tree.itemCollapsed.connect(self.ui_state.update_build_button_state)
        self.tree.itemCollapsed.connect(self.update_expand_button_text)
        self.tree.addFolderShortcut.connect(self.add_folder_btn.click)
        self.tree.addSubfolderShortcut.connect(self.add_subfolder_btn.click)
        self.tree.saveTemplateShortcut.connect(self.save_template_btn.click)
        self.tree.loadTemplateShortcut.connect(self.nested_ui.load_template)
        self.tree.itemChanged.connect(self.ui_state.update_build_button_state)
        self.tree.itemChanged.connect(self.enforce_tree_name_limit)
        self.tree.itemChanged.connect(self.ui_state.update_nested_build_state)
        self.expand_tree_btn.clicked.connect(self.tree_gui_stretch)
        self.expand_folders_collapse_btn.clicked.connect(self.toggle_tree_expand)

        self.load_user_template_dropdown.enterEvent = lambda e: (
            self.status.set(
                "Right-click to open user templates folder."
                "Can delete folders here if you wish.",
                target="nested",
                status_type="info",
            ),
            QComboBox.enterEvent(self.load_user_template_dropdown, e),
        )
        self.load_user_template_dropdown.leaveEvent = lambda e: (
            self.status.reset("nested"),
            QComboBox.leaveEvent(self.load_user_template_dropdown, e),
        )
        self.load_user_template_dropdown.setContextMenuPolicy(Qt.CustomContextMenu)
        self.load_user_template_dropdown.customContextMenuRequested.connect(
            lambda pos: os.startfile(str(self.service.template_paths.user_dir))
        )

        self.add_folder_btn.clicked.connect(
            lambda: (self.service.nested_manager.add_root_folder(), self.ui_state.update_build_button_state())
        )
        self.add_subfolder_btn.clicked.connect(
            lambda: (self.service.nested_manager.add_subfolder(), self.ui_state.update_build_button_state())
        )
        self.remove_btn.clicked.connect(
            lambda: (
                self.service.nested_manager.remove_selected_folders(),
                self.ui_state.update_build_button_state(),
                QTimer.singleShot(0, self.ui_state.update_nested_build_state),
            )
        )
        self.remove_all_btn.clicked.connect(
            lambda: (
                self.service.nested_manager.remove_all_folders(),
                self.load_user_template_dropdown.setCurrentIndex(0),
                self.load_default_template_dropdown.setCurrentIndex(0),
                setattr(self.nested_ui, "_current_loaded_template", None),
                self.ui_state.update_build_button_state(),
                QTimer.singleShot(0, self.ui_state.update_nested_build_state),
            )
        )
        self.tree.itemSelectionChanged.connect(self.ui_state.update_build_button_state)

        self.file_dropdown.currentIndexChanged.connect(
            lambda i: (
                None
                if i in (0, 1, 6, 10, 14)
                else (
                    self.service.nested_manager.add_file(
                        {
                            2: "main.py",
                            3: "script.js",
                            4: "index.html",
                            5: "styles.css",
                            7: "notes.txt",
                            8: "README.md",
                            9: "README.md",
                            11: "data.json",
                            12: "config.yaml",
                            13: ".env",
                            15: "run.bat",
                            16: "script.ps1",
                        }.get(i, "new_file.txt")
                    ),
                    self.file_dropdown.setCurrentIndex(0),
                    self.ui_state.update_build_button_state(),
                )
            )
        )

        self.open_folder_build_toggle.toggled.connect(
            lambda v: self.service.state_manager.update("open_folder_after_build", v)
        )
        self.base_path_line.textChanged.connect(self.ui_state.update_build_button_state)

        state = self.service.state
        self.service.theme_controller.select_theme(-2, self.service, self)

        self.smart_status_icon.setStyleSheet("font-weight: 700;")

        self.restore_timestamp_state(
            self.nested_date_toggle,
            self.nested_date_config,
            "nested_date_stamp_enabled",
            "nested_date_stamp_mode",
        )

        self.template_path_line.setText(str(self.service.template_paths.user_dir))
        self.base_path_line.setText(state.get("last_base_dir", ""))

        auto_number = state.get("nested_auto_number_enabled", False)
        self.auto_enumerate_folders.setChecked(auto_number)

        self.open_folder_build_toggle.setChecked(state.get("open_folder_after_build", False))
        self.minimize_after_build_toggle.setChecked(state.get("minimize_after_build", False))
        self.close_app_after_build_toggle.setChecked(state.get("close_after_build", False))
        self.close_app_after_build_toggle.setEnabled(not self.minimize_after_build_toggle.isChecked())
        self.minimize_after_build_toggle.setEnabled(not self.close_app_after_build_toggle.isChecked())

        self.nested_ui.refresh_user_templates_dropdown()
        self.update_expand_button_text()
        self.ui_state.update_build_button_state()
        self.ui_state.update_nested_build_state()

    def update_build_button_state(self):
        self.ui_state.update_build_button_state()

    def update_nested_build_state(self):
        self.ui_state.update_nested_build_state()

    def enforce_tree_name_limit(self, item, column):
        name = item.text(0)
        if len(name) > MAX_NESTED_FOLDER_NAME_LENGTH:
            item.setText(0, name[:MAX_NESTED_FOLDER_NAME_LENGTH])
            self.smart_status_icon.setText("⚠")
            self.smart_status_text.setText(
                f"Folder names limited to {MAX_NESTED_FOLDER_NAME_LENGTH} characters."
            )

    def restore_timestamp_state(self, toggle, combo, enabled_key, mode_key):
        enabled = self.service.state.get(enabled_key, False)
        toggle.setChecked(enabled)
        combo.setEnabled(enabled)

        mode = self.service.state.get(mode_key, "ISO")
        index_map = {"ISO": 0, "UK": 1, "US": 2}
        combo.setCurrentIndex(index_map.get(mode, 0))

    def toggle_tree_expand(self):
        if self.ui_state.tree_has_collapsed_nodes():
            self.tree.expandAll()
        else:
            self.tree.collapseAll()
        self.update_expand_button_text()

    def tree_gui_stretch(self):
        is_visible = self.smart_status_frame.isVisible()
        targets = [self.bottom_info_frame]

        if is_visible:
            for widget in targets:
                widget.hide()
            self.tree.setFixedHeight(self.tree_expanded_height)
            self.expand_tree_btn.setText("COLLAPSE 🌳")
        else:
            for widget in targets:
                widget.show()
            self.tree.setFixedHeight(self.tree_default_height)
            self.expand_tree_btn.setText("EXPAND 🌳")

        QTimer.singleShot(0, self.ui_state.update_build_button_state)
        self.tree.setVisible(True)

    def update_expand_button_text(self):
        if self.ui_state.tree_has_collapsed_nodes():
            self.expand_folders_collapse_btn.setText("EXPAND FOLDERS")
        else:
            self.expand_folders_collapse_btn.setText("COLLAPSE FOLDERS")


def main():
    if already_running():
        return

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

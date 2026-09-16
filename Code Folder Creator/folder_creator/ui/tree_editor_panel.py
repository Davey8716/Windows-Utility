from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from folder_creator.ui import styles


TREE_PLACEHOLDER = (
    "Files can either be drag drop loaded in here."
    "Or created/loaded using the buttons above."
    "(accepts .json, .txt, .md files).\n\n"
    "Default files can be added to folders and subfolders.\n"
    "Duplicate default files in these folders will be ignored.\n\n"
    "User templates using the save button are saved as .json, md or.txt."
    "A copy of them will be saved to:\n"
    "the Folder Creator Templates folder in the Master Backup Path.\n"
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
)


class TreeEditorPanel:
    """Build the folder/file editing controls, tree surface, and tree toolbar."""

    TREE_FRAME_BORDER_WIDTH = 1

    EXPORTED_WIDGETS = (
        "tree",
        "folder_buttons_frame",
        "add_folder_btn",
        "add_subfolder_btn",
        "remove_btn",
        "remove_all_btn",
        "file_dropdown",
        "tree_frame",
        "tree_controls_layout",
        "expand_tree_btn",
        "expand_folders_collapse_btn",
        "sort_btn",
        "find_btn",
        "find_output_line",
    )

    def __init__(
        self,
        tree,
        frame_padding: int,
        control_gap: int,
        tree_width: int,
        tree_height: int,
        tree_frame_padding: int,
        expand_width: int,
        collapse_width: int,
        sort_width: int,
        find_width: int,
        find_input_width: int,
    ):
        self.tree = tree
        self._configure_tree()

        self.add_folder_btn = QPushButton("Add")
        self.add_subfolder_btn = QPushButton("Sub")
        styles.apply_fluent_icon(self.add_folder_btn, "\ue710")
        styles.apply_fluent_icon(self.add_subfolder_btn, "\ue8b7")
        self.remove_btn = QPushButton("Remove\nSelected")
        self.remove_all_btn = QPushButton("Remove\nAll")
        for button in (
            self.add_folder_btn,
            self.add_subfolder_btn,
            self.remove_btn,
            self.remove_all_btn,
        ):
            button.setProperty("styleFontSize", 12)
        self.file_dropdown = self._create_file_dropdown()
        self.folder_buttons_frame = self._create_folder_controls(
            frame_padding, control_gap
        )

        self.tree_frame = QFrame()
        self.tree_frame.setFrameShape(QFrame.NoFrame)
        self.tree_frame.setFixedWidth(
            tree_width
            + ((tree_frame_padding + self.TREE_FRAME_BORDER_WIDTH) * 2)
        )
        self.tree_frame.setFixedHeight(tree_height + (tree_frame_padding * 2))
        self.tree_frame.setStyleSheet(styles.tree_outer_frame_style())
        tree_layout = QVBoxLayout(self.tree_frame)
        tree_layout.setContentsMargins(
            tree_frame_padding,
            tree_frame_padding,
            tree_frame_padding,
            tree_frame_padding,
        )
        tree_layout.setSpacing(0)
        self.tree.setFixedWidth(tree_width)
        self.tree.setFixedHeight(tree_height)
        self.tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.tree.setStyleSheet(styles.surfaced_tree_widget_style())
        self.tree.setPlaceholderText(TREE_PLACEHOLDER, bold=True)
        # The compact tree must show the full instructional placeholder.
        self.tree.setPlaceholderFontSize(self.tree.COMPACT_PLACEHOLDER_FONT_SIZE)
        tree_layout.addWidget(self.tree)

        self.expand_tree_btn = QPushButton("Expand")
        self.expand_folders_collapse_btn = QPushButton("Expand Folders")
        self.sort_btn = QPushButton("Sort A/Z")
        self.find_btn = QPushButton("Find")
        styles.apply_fluent_icon(self.expand_tree_btn, "\ue740")
        styles.apply_fluent_icon(self.expand_folders_collapse_btn, "\ue70d")
        styles.apply_fluent_icon(self.sort_btn, "\ue8cb")
        styles.apply_fluent_icon(self.find_btn, "\ue721")
        self.find_output_line = QLineEdit()
        self.find_output_line.setPlaceholderText("INPUT FOR FINDING FOLDERS.")
        self.find_output_line.setReadOnly(False)
        self.find_output_line.setEnabled(True)
        self.find_output_line.setFixedSize(find_input_width, 40)
        self.find_output_line.setProperty("framelessSurfaceFieldStyle", True)
        self.find_output_line.setStyleSheet(
            styles.frameless_surfaced_line_edit_style(styles.resurface_styles.FONT_SIZE_COMPACT)
        )
        self.expand_tree_btn.setFixedSize(expand_width, styles.DEFAULT_BUTTON_HEIGHT)
        self.expand_folders_collapse_btn.setFixedSize(
            collapse_width, styles.DEFAULT_BUTTON_HEIGHT
        )
        self.sort_btn.setFixedSize(sort_width, styles.DEFAULT_BUTTON_HEIGHT)
        self.find_btn.setFixedSize(find_width, styles.DEFAULT_BUTTON_HEIGHT)
        self.expand_folders_collapse_btn.setEnabled(False)
        self.find_btn.setEnabled(False)
        self.sort_btn.setEnabled(False)

        self.tree_controls_layout = QHBoxLayout()
        self.tree_controls_layout.setContentsMargins(
            frame_padding, frame_padding, frame_padding, frame_padding
        )
        self.tree_controls_layout.setSpacing(control_gap)
        self.tree_controls_layout.addWidget(self.expand_tree_btn)
        self.tree_controls_layout.addWidget(self.expand_folders_collapse_btn)
        self.tree_controls_layout.addStretch()
        self.tree_controls_layout.addWidget(self.sort_btn)
        self.tree_controls_layout.addWidget(self.find_btn)
        self.tree_controls_layout.addWidget(self.find_output_line)

    def _configure_tree(self):
        self.tree.setColumnCount(1)
        self.tree.setHeaderHidden(True)
        self.tree.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)

    @staticmethod
    def _create_file_dropdown():
        dropdown = QComboBox()
        dropdown.addItems(
            [
                "Add Blank 📑",
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
        dropdown.setFixedSize(170, styles.DEFAULT_BUTTON_HEIGHT)
        dropdown.setObjectName("FolderCreatorAddBlankDropdown")
        styles.apply_fluent_item_icon(dropdown, 0, "\ue8a5")
        dropdown.setProperty("styleFontSize", 12)
        # Keep the active blue treatment, but use the button palette across
        # both disabled segments when no folder is available to receive a file.
        dropdown.setProperty("lightModeKeepEnabledBackground", True)
        dropdown.setStyleSheet(styles.organizing_combo_style(12))
        return dropdown

    def _create_folder_controls(self, frame_padding, control_gap):
        frame = QFrame()
        frame.setFrameShape(QFrame.NoFrame)
        frame.setFixedSize(190, 230)
        frame.setStyleSheet("border: none;")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            frame_padding, frame_padding, frame_padding, frame_padding
        )
        layout.setSpacing(control_gap)

        top_row = QHBoxLayout()
        top_row.setSpacing(control_gap)
        self.add_folder_btn.setFixedSize(80, styles.DEFAULT_BUTTON_HEIGHT)
        self.add_subfolder_btn.setFixedSize(80, styles.DEFAULT_BUTTON_HEIGHT)
        top_row.addStretch()
        top_row.addWidget(self.add_folder_btn)
        top_row.addWidget(self.add_subfolder_btn)
        top_row.addStretch()

        file_row = QHBoxLayout()
        file_row.setSpacing(control_gap)
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

        layout.addLayout(top_row)
        layout.addLayout(file_row)
        layout.addLayout(bottom_row)
        layout.addStretch()
        return frame

    def bind_to(self, window):
        for name in self.EXPORTED_WIDGETS:
            setattr(window, name, getattr(self, name))

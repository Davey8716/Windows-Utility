from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QSizePolicy, QWidget

from resurface.core.saved_folder_names import load_saved_folder_names
from resurface.ui import styles
from resurface.ui.pages.page_controls import PageControls
from resurface.ui.tooltips import tooltip_text


class FolderUtilitiesPage(PageControls):
    create_folder_requested = Signal(str, bool)
    folder_creator_requested = Signal()

    def __init__(self, register_tooltip, parent=None):
        super().__init__("folder_utilities", register_tooltip, parent)
        self.content_layout.setSpacing(16)
        creator = self.style_action_button(QPushButton("Folder Creator"))
        creator.clicked.connect(self.folder_creator_requested.emit)
        self.register_tooltip(creator, tooltip_text("folder_creator_launcher"))
        create = self.style_action_button(QPushButton("Folder To Desktop"))
        create.setProperty("lightModePlaceholderButton", True)
        self.register_tooltip(create, tooltip_text("folder_to_desktop"))
        self._names = QComboBox()
        self._names.setEditable(True)
        self._names.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._names.setFixedSize(styles.PAGE_CONTROL_WIDTH, styles.PAGE_CONTROL_HEIGHT)
        self._names.setCursor(Qt.CursorShape.ArrowCursor)
        self._names.setStyleSheet(styles.organizing_combo_style(15))
        self._names.setProperty("styleFontSize", 15)
        self._input = self._names.lineEdit()
        self._input.setPlaceholderText("Folder name")
        self.register_tooltip(self._input, tooltip_text("folder_name_input"))
        self._save_name = self.make_toggle_button("Save Name")
        self._delete_name = self.make_toggle_button("Delete Name")
        self.register_tooltip(self._delete_name, tooltip_text("delete_name"))

        self.register_tooltip(self._save_name, "Save the next successfully created folder name for future use.")
        row = QWidget(); row.setProperty("centeredControlGrid", True)
        row.setFixedWidth(self.CONTROL_ROW_WIDTH)
        row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(self.CONTROL_COLUMN_GAP)
        layout.addWidget(self._names); layout.addWidget(create)
        self.content_layout.addWidget(row, 0, Qt.AlignmentFlag.AlignHCenter)
        secondary, secondary_layout = self.make_two_column_control_row()
        secondary_layout.setVerticalSpacing(self.content_layout.spacing())
        secondary_layout.addWidget(self._save_name, 0, 0)
        secondary_layout.addWidget(creator, 0, 1)
        secondary_layout.addWidget(self._delete_name, 1, 0)
        self.content_layout.addWidget(secondary, 0, Qt.AlignmentFlag.AlignHCenter)
        self.refresh_saved_names()
        self._input.textChanged.connect(lambda text: create.setEnabled(bool(text.strip())))
        create.clicked.connect(self._request_create)
        create.setEnabled(False)

    def refresh_saved_names(self, names: list[str] | None = None) -> None:
        names = load_saved_folder_names() if names is None else names
        text = self._input.text()
        self._names.blockSignals(True); self._names.clear(); self._names.addItems(names)
        self._names.setCurrentIndex(-1); self._names.setEditText(text); self._names.blockSignals(False)

    def focus_name_input(self) -> None:
        self._input.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def folder_created(self, saved_names: list[str] | None = None) -> None:
        if saved_names is not None:
            self.refresh_saved_names(saved_names)
        self._save_name.setChecked(False)
        self._input.clear()

    # def _delete_requested(self) -> None:
    #     for name in

    def _request_create(self) -> None:
        name = self._input.text().strip()
        if name:
            self.create_folder_requested.emit(name, self._save_name.isChecked())

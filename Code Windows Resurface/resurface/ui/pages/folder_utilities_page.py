from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QSizePolicy, QWidget

from resurface.core.saved_folder_names import load_saved_folder_names
from resurface.ui import styles
from resurface.ui.pages.page_controls import PageControls
from resurface.ui.tooltips import tooltip_text


class FolderUtilitiesPage(PageControls):
    create_folder_requested = Signal(str)
    save_name_requested = Signal(str)
    delete_name_requested = Signal(str)
    delete_all_names_requested = Signal()
    folder_creator_requested = Signal()

    def __init__(self, register_tooltip, parent=None, *, saved_names_path=None):
        super().__init__("folder_utilities", register_tooltip, parent)
        self._saved_names_path = saved_names_path
        self.content_layout.setSpacing(16)
        creator = self.style_action_button(QPushButton("Folder Creator"))
        creator.clicked.connect(self.folder_creator_requested.emit)
        self.folder_creator_button = creator
        self.register_tooltip(creator, tooltip_text("folder_creator_launcher"))
        create = self.style_action_button(QPushButton("Folder To Desktop"))
        self._create_folder = create
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
        self._save_name = self.style_action_button(QPushButton("Save Name"))
        self._save_name.setProperty("lightModeBlackDisabledText", True)
        self._delete_name = self.style_action_button(QPushButton("Delete Name"))
        self._delete_name.setProperty("lightModeBlackDisabledText", True)
        self.register_tooltip(self._delete_name, tooltip_text("delete_name"))
        self._delete_all_names = self.style_action_button(QPushButton("Delete All"))
        self._delete_all_names.setProperty("lightModeBlackDisabledText", True)
        self.register_tooltip(self._delete_all_names, tooltip_text("delete_all_names"))

        self.register_tooltip(self._save_name, "Save this folder name for future use.")
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
        secondary_layout.addWidget(self._delete_all_names, 1, 1)
        self.content_layout.addWidget(secondary, 0, Qt.AlignmentFlag.AlignHCenter)
        self.refresh_saved_names()
        self._input.textChanged.connect(self._set_name_action_state)
        create.clicked.connect(self._request_create)
        self._save_name.clicked.connect(self._request_save)
        self._delete_name.clicked.connect(self._request_delete)
        self._delete_all_names.clicked.connect(self.delete_all_names_requested.emit)
        create.setEnabled(False)
        self._save_name.setEnabled(False)

    def refresh_saved_names(self, names: list[str] | None = None) -> None:
        if names is None:
            names = (
                load_saved_folder_names(self._saved_names_path())
                if self._saved_names_path is not None
                else []
            )
        text = self._input.text()
        self._names.blockSignals(True); self._names.clear(); self._names.addItems(names)
        self._names.setCurrentIndex(-1); self._names.setEditText(text); self._names.blockSignals(False)
        self._delete_all_names.setEnabled(bool(names))
        self._set_name_action_state(text)

    def focus_name_input(self) -> None:
        self._input.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def folder_created(self, saved_names: list[str] | None = None) -> None:
        if saved_names is not None:
            self.refresh_saved_names(saved_names)
        self._input.clear()

    def folder_name_saved(self, saved_names: list[str], saved_name: str) -> None:
        self.refresh_saved_names(saved_names)
        self._names.setCurrentText(saved_name)

    def folder_name_deleted(self, saved_names: list[str]) -> None:
        self._input.clear()
        self.refresh_saved_names(saved_names)

    def _request_delete(self) -> None:
        name = self._input.text().strip()
        if name:
            self.delete_name_requested.emit(name)

    def _request_save(self) -> None:
        name = self._input.text().strip()
        if name and not self._name_is_saved(name):
            self.save_name_requested.emit(name)

    def _name_is_saved(self, name: str) -> bool:
        key = name.strip().casefold()
        return bool(key) and any(
            self._names.itemText(index).strip().casefold() == key
            for index in range(self._names.count())
        )

    def _set_name_action_state(self, text: str) -> None:
        clean_name = text.strip()
        self._create_folder.setEnabled(bool(clean_name))
        self._save_name.setEnabled(
            bool(clean_name) and not self._name_is_saved(clean_name)
        )
        self._delete_name.setEnabled(self._name_is_saved(clean_name))

    def _request_create(self) -> None:
        name = self._input.text().strip()
        if name:
            self.create_folder_requested.emit(name)

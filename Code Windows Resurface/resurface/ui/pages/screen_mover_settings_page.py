from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from resurface.features.screen_mover.hotkeys import (
    ACTION_LABELS, VALID_ACTIONS, hotkey_to_display, normalize_hotkey,
)
from resurface.ui import styles
from resurface.ui.pages.page_controls import PageControls
from resurface.ui.tooltips import tooltip_text


class ScreenMoverSettingsPage(PageControls):
    settings_changed = Signal(dict)

    def __init__(self, settings: dict, register_tooltip, parent=None):
        super().__init__("screen_mover", register_tooltip, parent)
        self.content_layout.setSpacing(16)
        self._settings = self._normalized_settings(settings)
        shortcuts_width = (styles.PAGE_CONTROL_WIDTH * 2) + self.CONTROL_COLUMN_GAP

        self.shortcuts_header = QWidget(self)
        self.shortcuts_header.setProperty("centeredControlGrid", True)
        self.shortcuts_header.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.shortcuts_header.setFixedWidth(shortcuts_width)
        header_layout = QHBoxLayout(self.shortcuts_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Keyboard Shortcuts", self.shortcuts_header)
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet(styles.label_style(font_size=14))
        header_layout.addStretch()
        header_layout.addWidget(title)
        header_layout.addStretch()
        self.content_layout.addWidget(self.shortcuts_header, 0, Qt.AlignmentFlag.AlignHCenter)

        self.shortcuts_container = QWidget(self)
        self.shortcuts_container.setProperty("centeredControlGrid", True)
        self.shortcuts_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.shortcuts_container.setFixedWidth(shortcuts_width)
        shortcuts_layout = QVBoxLayout(self.shortcuts_container)
        shortcuts_layout.setContentsMargins(0, 0, 0, 0)
        shortcuts_layout.setSpacing(6)
        self.content_layout.addWidget(self.shortcuts_container, 0, Qt.AlignmentFlag.AlignHCenter)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(self.CONTROL_COLUMN_GAP)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        shortcuts_layout.addLayout(grid)

        self._hotkey_edits: dict[str, QKeySequenceEdit] = {}
        labels = []
        hotkeys = self._settings["screen_mover_keyboard_hotkeys"]
        for row, (action, label_text) in enumerate(ACTION_LABELS.items()):
            label = QLabel(label_text, self.shortcuts_container)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            label.setStyleSheet(styles.label_style(font_size=12))
            labels.append(label)
            edit = QKeySequenceEdit(self.shortcuts_container)
            edit.setObjectName("ScreenMoverShortcutEdit")
            if hasattr(edit, "setMaximumSequenceLength"):
                edit.setMaximumSequenceLength(1)
            edit.setFixedHeight(styles.PAGE_CONTROL_HEIGHT)
            edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            edit.setKeySequence(QKeySequence(hotkey_to_display(hotkeys.get(action, ""))))
            edit.setStyleSheet(styles.hotkey_edit_style(13))
            edit.keySequenceChanged.connect(
                lambda _sequence, action=action, edit=edit: self._save_hotkey(action, edit)
            )
            self._hotkey_edits[action] = edit
            clear = QPushButton("Clear", self.shortcuts_container)
            clear.setCursor(Qt.CursorShape.ArrowCursor)
            styles.apply_page_control_size(clear, width=styles.PAGE_COMPACT_CONTROL_WIDTH, role="compact")
            clear.setProperty("styleFontSize", 11)
            clear.setStyleSheet(styles.organizing_button_style(11))
            clear.clicked.connect(
                lambda _checked=False, action=action: self._clear_hotkey(action)
            )
            grid.addWidget(label, row, 0)
            grid.addWidget(edit, row, 1)
            grid.addWidget(clear, row, 2)
            self.register_tooltip(edit, tooltip_text("screen_mover_hotkey"))
            self.register_tooltip(clear, tooltip_text("screen_mover_hotkey_clear"))

        label_width = max(label.sizeHint().width() for label in labels)
        for label in labels:
            label.setFixedWidth(label_width)
        grid.setColumnMinimumWidth(0, label_width)
        grid.setColumnMinimumWidth(2, styles.PAGE_COMPACT_CONTROL_WIDTH)

        self.reset_button = QPushButton("Reset Shortcut Defaults", self.shortcuts_container)
        self.reset_button.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(self.reset_button)
        self.reset_button.setProperty("styleFontSize", 12)
        self.reset_button.setStyleSheet(styles.organizing_button_style(12))
        self.reset_button.clicked.connect(self.reset_settings)
        shortcuts_layout.addWidget(self.reset_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.register_tooltip(self.reset_button, tooltip_text("screen_mover_reset"))

    @staticmethod
    def _normalized_settings(settings: dict) -> dict:
        values = settings.get("screen_mover_keyboard_hotkeys", {})
        if not isinstance(values, dict):
            values = {}
        return {
            "screen_mover_keyboard_hotkeys": {
                action: normalize_hotkey(values.get(action, "")) for action in VALID_ACTIONS
            },
        }

    def settings(self) -> dict:
        result = dict(self._settings)
        result["screen_mover_keyboard_hotkeys"] = dict(
            self._settings["screen_mover_keyboard_hotkeys"]
        )
        return result

    def reset_settings(self) -> None:
        self._settings["screen_mover_keyboard_hotkeys"] = {
            action: "" for action in VALID_ACTIONS
        }
        for edit in self._hotkey_edits.values():
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
        self.settings_changed.emit(self.settings())

    def refresh_shortcut_styles(self) -> None:
        for edit in self._hotkey_edits.values():
            internal_edits = edit.findChildren(QLineEdit)
            for internal in internal_edits:
                internal.setStyleSheet("")
            edit.setStyleSheet(styles.hotkey_edit_style(13))
            for widget in (edit, *internal_edits):
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()
            edit.setFixedHeight(styles.PAGE_CONTROL_HEIGHT)

    def _save_hotkey(self, action: str, edit: QKeySequenceEdit) -> None:
        portable = edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        normalized = normalize_hotkey(portable)
        self._settings["screen_mover_keyboard_hotkeys"][action] = normalized
        display = hotkey_to_display(normalized)
        if portable != display:
            edit.blockSignals(True)
            edit.setKeySequence(QKeySequence(display))
            edit.blockSignals(False)
        self.settings_changed.emit(self.settings())
        QTimer.singleShot(0, edit.clearFocus)

    def _clear_hotkey(self, action: str) -> None:
        self._settings["screen_mover_keyboard_hotkeys"][action] = ""
        edit = self._hotkey_edits[action]
        edit.blockSignals(True)
        edit.clear()
        edit.blockSignals(False)
        self.settings_changed.emit(self.settings())

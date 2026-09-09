from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from resurface.features.screen_mover.hotkeys import (
    ACTION_LABELS,
    VALID_ACTIONS,
    hotkey_to_display,
    normalize_hotkey,
    normalize_unique_hotkeys,
)
from resurface.ui import styles
from resurface.ui.pages.page_controls import PageControls
from resurface.ui.tooltips import tooltip_text


class ScreenMoverShortcutEdit(QKeySequenceEdit):
    """Shortcut editor with a theme-aware in-field validation message."""

    capture_state_changed = Signal(bool)

    _MODIFIER_KEYS = {
        Qt.Key.Key_Control,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Meta,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._capture_active = False
        self.setProperty("shortcutConflict", False)
        self.duplicate_message = QLabel(self)
        self.duplicate_message.setObjectName("ScreenMoverDuplicateMessage")
        self.duplicate_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.duplicate_message.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.duplicate_message.hide()
        self.refresh_conflict_style()

    def show_duplicate_message(self, text: str) -> None:
        self.setProperty("shortcutConflict", True)
        self.duplicate_message.setText(text)
        self.duplicate_message.setToolTip(text)
        self.duplicate_message.show()
        self.duplicate_message.raise_()
        self._position_duplicate_message()
        self._refresh_style()

    def clear_duplicate_message(self) -> None:
        self.setProperty("shortcutConflict", False)
        self.duplicate_message.clear()
        self.duplicate_message.setToolTip("")
        self.duplicate_message.hide()
        self._refresh_style()

    def refresh_conflict_style(self) -> None:
        self.duplicate_message.setStyleSheet(
            styles.hotkey_conflict_message_style(9)
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_duplicate_message()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._set_capture_active(True)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._set_capture_active(False)

    def keyPressEvent(self, event) -> None:
        super().keyPressEvent(event)
        if event.key() not in self._MODIFIER_KEYS:
            # Each shortcut is limited to one chord. Finalizing it here avoids
            # QKeySequenceEdit's built-in one-second completion delay.
            self.clearFocus()

    def _set_capture_active(self, active: bool) -> None:
        active = bool(active)
        if active == self._capture_active:
            return
        self._capture_active = active
        self.capture_state_changed.emit(active)

    def _position_duplicate_message(self) -> None:
        self.duplicate_message.setGeometry(
            3,
            3,
            max(0, self.width() - 6),
            max(0, self.height() - 6),
        )

    def _refresh_style(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class ScreenMoverSettingsPage(PageControls):
    settings_changed = Signal(dict)
    reset_confirmation_requested = Signal()
    shortcut_capture_changed = Signal(bool)

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

        self._hotkey_edits: dict[str, ScreenMoverShortcutEdit] = {}
        labels = []
        hotkeys = self._settings["screen_mover_keyboard_hotkeys"]
        for row, (action, label_text) in enumerate(ACTION_LABELS.items()):
            label = QLabel(label_text, self.shortcuts_container)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            label.setStyleSheet(styles.label_style(font_size=12))
            labels.append(label)
            edit = ScreenMoverShortcutEdit(self.shortcuts_container)
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
            edit.capture_state_changed.connect(self.shortcut_capture_changed.emit)
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
        self.reset_button.clicked.connect(self.reset_confirmation_requested.emit)
        shortcuts_layout.addWidget(self.reset_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.register_tooltip(self.reset_button, tooltip_text("screen_mover_reset"))
        self._sync_reset_button_enabled()

    @staticmethod
    def _normalized_settings(settings: dict) -> dict:
        values = settings.get("screen_mover_keyboard_hotkeys", {})
        if not isinstance(values, dict):
            values = {}
        return {
            "screen_mover_keyboard_hotkeys": normalize_unique_hotkeys(values),
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
            edit.clear_duplicate_message()
        self._sync_reset_button_enabled()
        self.settings_changed.emit(self.settings())

    def _sync_reset_button_enabled(self) -> None:
        hotkeys = self._settings["screen_mover_keyboard_hotkeys"]
        self.reset_button.setEnabled(any(hotkeys.values()))

    def refresh_shortcut_styles(self) -> None:
        for edit in self._hotkey_edits.values():
            internal_edits = edit.findChildren(QLineEdit)
            for internal in internal_edits:
                internal.setStyleSheet("")
            edit.setStyleSheet(styles.hotkey_edit_style(13))
            edit.refresh_conflict_style()
            for widget in (edit, *internal_edits):
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()
            edit.setFixedHeight(styles.PAGE_CONTROL_HEIGHT)

    def _save_hotkey(self, action: str, edit: QKeySequenceEdit) -> None:
        portable = edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        normalized = normalize_hotkey(portable)
        hotkeys = self._settings["screen_mover_keyboard_hotkeys"]
        conflict = next(
            (
                other_action
                for other_action in VALID_ACTIONS
                if other_action != action and normalized and hotkeys[other_action] == normalized
            ),
            None,
        )
        if conflict is not None:
            previous_display = hotkey_to_display(hotkeys[action])
            edit.blockSignals(True)
            edit.setKeySequence(QKeySequence(previous_display))
            edit.blockSignals(False)
            edit.show_duplicate_message(
                f"{hotkey_to_display(normalized)} is already assigned to "
                f"{ACTION_LABELS[conflict]}."
            )
            QTimer.singleShot(0, edit.clearFocus)
            return

        edit.clear_duplicate_message()
        hotkeys[action] = normalized
        display = hotkey_to_display(normalized)
        if portable != display:
            edit.blockSignals(True)
            edit.setKeySequence(QKeySequence(display))
            edit.blockSignals(False)
        self._sync_reset_button_enabled()
        self.settings_changed.emit(self.settings())
        QTimer.singleShot(0, edit.clearFocus)

    def _clear_hotkey(self, action: str) -> None:
        self._settings["screen_mover_keyboard_hotkeys"][action] = ""
        edit = self._hotkey_edits[action]
        edit.blockSignals(True)
        edit.clear()
        edit.blockSignals(False)
        edit.clear_duplicate_message()
        self._sync_reset_button_enabled()
        self.settings_changed.emit(self.settings())

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from folder_creator.ui import styles


class TemplateSaveDialog(QDialog):
    """Collect a user-template name without exposing a folder picker."""

    CORNER_RADIUS = 12
    FRAME_WIDTH = 2
    FORMATS = (
        ("JSON (.json)", ".json"),
        ("Text outline (.txt)", ".txt"),
        ("Markdown outline (.md)", ".md"),
    )
    INVALID_FILENAME_CHARACTERS = frozenset('<>:"/\\|?*')
    RESERVED_WINDOWS_NAMES = frozenset(
        {"CON", "PRN", "AUX", "NUL"}
        | {f"COM{number}" for number in range(1, 10)}
        | {f"LPT{number}" for number in range(1, 10)}
    )

    def __init__(self, parent, user_dir: Path) -> None:
        super().__init__(parent if isinstance(parent, QWidget) else None)
        self.user_dir = Path(user_dir)
        self._destination: Path | None = None

        self.setWindowTitle("Save Template")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setSizeGripEnabled(False)
        self.setStyleSheet(self._dialog_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title = QLabel("Save Template")
        title.setStyleSheet(styles.title_label_style())
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)
        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("Template name")
        self.filename_input.setClearButtonEnabled(True)
        self.format_selector = QComboBox()
        self.format_selector.addItems([label for label, _suffix in self.FORMATS])
        self.destination_display = QLineEdit(str(self.user_dir))
        self.destination_display.setReadOnly(True)
        self.destination_display.setToolTip(str(self.user_dir))
        form.addRow("Name", self.filename_input)
        form.addRow("Format", self.format_selector)
        form.addRow("Save to", self.destination_display)
        layout.addLayout(form)

        self.error_label = QLabel()
        self.error_label.setObjectName("templateSaveError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._accept_if_valid)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        for button in self.button_box.buttons():
            button.setStyleSheet(styles.organizing_button_style(14))

        self.setFixedWidth(500)
        self.filename_input.setFocus()

    @property
    def destination(self) -> Path | None:
        return self._destination

    def selected_suffix(self) -> str:
        return self.FORMATS[self.format_selector.currentIndex()][1]

    def _accept_if_valid(self) -> None:
        filename = self.filename_input.text().strip()
        error = self._filename_error(filename)
        if error:
            self.error_label.setText(error)
            self.error_label.show()
            return

        candidate = (self.user_dir / f"{filename}{self.selected_suffix()}").resolve()
        try:
            candidate.relative_to(self.user_dir.resolve())
        except ValueError:
            self.error_label.setText("Template names must save inside User Templates.")
            self.error_label.show()
            return

        self._destination = candidate
        self.accept()

    def _filename_error(self, filename: str) -> str | None:
        if not filename:
            return "Enter a template name."
        if filename in {".", ".."} or Path(filename).name != filename:
            return "Template names cannot contain folders."
        if any(character in self.INVALID_FILENAME_CHARACTERS for character in filename):
            return "Template names contain characters Windows cannot use."
        if filename[-1] in {" ", "."}:
            return "Template names cannot end with a space or period."
        if filename.split(".", 1)[0].upper() in self.RESERVED_WINDOWS_NAMES:
            return "Template names cannot use reserved Windows device names."
        return None

    def _dialog_style(self) -> str:
        return f"""
            QDialog {{
                background-color: {styles.qcolor_css(styles.SURFACE_BG)};
                border: {self.FRAME_WIDTH}px solid {styles.qcolor_css(styles.SURFACE_BORDER)};
                border-radius: {self.CORNER_RADIUS}px;
            }}
            QLabel#templateSaveError {{
                color: #f06a6a;
            }}
        """

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(styles.SURFACE_BORDER)
        pen.setWidth(self.FRAME_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inset = self.FRAME_WIDTH / 2
        painter.drawRoundedRect(
            self.rect().adjusted(inset, inset, -inset, -inset),
            self.CORNER_RADIUS - inset,
            self.CORNER_RADIUS - inset,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        path = QPainterPath()
        path.addRoundedRect(self.rect(), self.CORNER_RADIUS, self.CORNER_RADIUS)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

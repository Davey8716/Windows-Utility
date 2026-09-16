from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRegion
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

    def __init__(
        self,
        parent,
        user_dir: Path,
        *,
        is_dark: bool | None = None,
        theme_resolver=None,
    ) -> None:
        super().__init__(parent if isinstance(parent, QWidget) else None)
        self.user_dir = Path(user_dir)
        self._destination: Path | None = None
        # Capture the host theme when the dialog opens. This avoids a mixed
        # palette when another window refreshes the shared stylesheet.
        self._is_dark = (
            bool(is_dark)
            if is_dark is not None
            else bool(styles.resurface_styles.THEME_IS_DARK)
        )
        self._theme_resolver = theme_resolver

        self.setWindowTitle("Save Template")
        self.setObjectName("TemplateSaveDialog")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizeGripEnabled(False)
        self.setStyleSheet(self._dialog_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        self.title_label = QLabel("Save Template")
        self.title_label.setObjectName("templateSaveTitle")
        layout.addWidget(self.title_label)

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

        self.setFixedWidth(500)
        self.filename_input.setFocus()

        self._theme_timer = QTimer(self)
        self._theme_timer.setInterval(250)
        self._theme_timer.timeout.connect(self._sync_theme)
        self.finished.connect(self._theme_timer.stop)
        if callable(self._theme_resolver):
            self._theme_timer.start()

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
        colors = self._colors()
        chevron_path = self._chevron_path().as_posix()
        frame_radius = self._outer_frame_radius()
        field_border_width = 1 if self._is_dark else 2
        field_radius = 2 if self._is_dark else 6
        return f"""
            QDialog#TemplateSaveDialog {{
                background: transparent;
                border: none;
                border-radius: {frame_radius}px;
            }}
            QDialog#TemplateSaveDialog QLabel {{
                background: transparent;
                border: none;
                color: {colors['text']};
                font-family: {styles.resurface_styles.FONT_FAMILY};
                font-size: {styles.resurface_styles.FONT_SIZE_STANDARD}px;
                font-weight: 700;
            }}
            QDialog#TemplateSaveDialog QLabel#templateSaveTitle {{
                color: {colors['title']};
                font-size: {styles.resurface_styles.FONT_SIZE_DIALOG_TITLE}px;
                font-weight: 1000;
            }}
            QDialog#TemplateSaveDialog QLineEdit {{
                font-family: {styles.resurface_styles.FONT_FAMILY};
                font-size: {styles.resurface_styles.FONT_SIZE_STANDARD}px;
                color: {colors['field_text']};
                background-color: {colors['field_bg']};
                border: {field_border_width}px solid {colors['field_border']};
                border-radius: {field_radius}px;
                padding: 4px 8px;
                selection-background-color: {colors['selection']};
            }}
            QDialog#TemplateSaveDialog QComboBox {{
                color: {colors['combo_text']};
                background-color: {colors['combo_bg']};
                border: 1px solid {colors['combo_border']};
                border-radius: 6px;
                padding: 6px 34px 6px 10px;
                font-family: {styles.resurface_styles.FONT_FAMILY};
                font-size: {styles.resurface_styles.FONT_SIZE_STANDARD}px;
                font-weight: 700;
            }}
            QDialog#TemplateSaveDialog QComboBox:hover {{
                background-color: {colors['combo_hover']};
            }}
            QDialog#TemplateSaveDialog QComboBox::drop-down {{
                width: 28px;
                background-color: {colors['combo_bg']};
                border: none;
                border-left: 1px solid {colors['combo_border']};
                border-top-right-radius: 5px;
                border-bottom-right-radius: 5px;
            }}
            QDialog#TemplateSaveDialog QComboBox::down-arrow {{
                image: url("{chevron_path}");
                width: 10px;
                height: 6px;
            }}
            QDialog#TemplateSaveDialog QComboBox QAbstractItemView {{
                font-family: {styles.resurface_styles.FONT_FAMILY};
                font-size: {styles.resurface_styles.FONT_SIZE_STANDARD}px;
                color: {colors['field_text']};
                background-color: {colors['field_bg']};
                border: 1px solid {colors['field_border']};
                selection-background-color: {colors['selection']};
                selection-color: {colors['field_text']};
            }}
            QDialog#TemplateSaveDialog QPushButton {{
                color: {colors['button_text']};
                background-color: {colors['button_bg']};
                border: 1px solid {colors['button_border']};
                border-radius: 6px;
                padding: 4px 8px;
                font-family: {styles.resurface_styles.FONT_FAMILY};
                font-size: {styles.resurface_styles.FONT_SIZE_STANDARD}px;
                font-weight: bold;
            }}
            QDialog#TemplateSaveDialog QPushButton:hover {{
                background-color: {colors['button_hover']};
            }}
            QDialog#TemplateSaveDialog QPushButton:pressed {{
                background-color: {colors['button_pressed']};
            }}
            QLabel#templateSaveError {{
                color: {colors['error']};
            }}
        """

    def _colors(self) -> dict[str, str]:
        """Return an explicit, self-contained palette for this popup."""
        if self._is_dark:
            return {
                "dialog_bg": "#3a4860", "border": "#5d6b7d", "text": "#ffffff",
                "title": "#ffffff", "field_bg": "#171b24", "field_text": "#ffffff",
                "field_border": "#5d6b7d", "selection": "#4a6fa8", "combo_bg": "#1c66c4",
                "combo_hover": "#2a78da", "combo_border": "#8ac6f6", "combo_text": "#ffffff",
                "button_bg": "#1c66c4", "button_hover": "#2a78da", "button_pressed": "#144e9a",
                "button_border": "#8ac6f6", "button_text": "#ffffff", "error": "#ffb4b4",
            }
        return {
            "dialog_bg": "#eef2f6", "border": "#7e8ea0", "text": "#111820",
            "title": "#111820", "field_bg": "#f5f5f0", "field_text": "#111820",
            "field_border": "#7e8ea0", "selection": "#cbd8e7", "combo_bg": "#2d73c8",
            "combo_hover": "#3e86dc", "combo_border": "#194f87", "combo_text": "#111820",
            "button_bg": "#2d73c8", "button_hover": "#3e86dc", "button_pressed": "#215ba0",
            "button_border": "#194f87", "button_text": "#111820", "error": "#7e1919",
        }

    def _chevron_path(self) -> Path:
        """Choose the chevron that matches this popup's captured theme."""
        bundle_root = getattr(sys, "_MEIPASS", None)
        root = Path(bundle_root) if bundle_root else Path(__file__).resolve().parents[3]
        name = "Dropdown Chevron.svg" if self._is_dark else "Dropdown Chevron Light.svg"
        return root / "App Icons" / "Light Theme" / name

    def _outer_frame_width(self) -> int:
        return 1 if self._is_dark else self.FRAME_WIDTH

    def _outer_frame_radius(self) -> int:
        return self.CORNER_RADIUS

    def _sync_theme(self) -> None:
        """Refresh this modal popup when the shared application theme changes."""
        if not callable(self._theme_resolver):
            return
        try:
            is_dark = bool(self._theme_resolver())
        except Exception:
            return
        if is_dark == self._is_dark:
            return
        self._is_dark = is_dark
        self.setStyleSheet(self._dialog_style())
        self._apply_window_mask()
        self.update()

    def _apply_window_mask(self) -> None:
        path = QPainterPath()
        radius = self._outer_frame_radius()
        path.addRoundedRect(self.rect(), radius, radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = self._colors()
        pen = QPen(QColor(colors["border"]))
        frame_width = self._outer_frame_width()
        radius = self._outer_frame_radius()
        pen.setWidth(frame_width)
        painter.setPen(pen)
        painter.setBrush(QColor(colors["dialog_bg"]))
        inset = frame_width / 2
        painter.drawRoundedRect(
            self.rect().adjusted(inset, inset, -inset, -inset),
            radius - inset,
            radius - inset,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_window_mask()

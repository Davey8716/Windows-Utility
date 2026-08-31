from typing import Callable

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from resurface.ui import styles
from resurface.ui.window_chrome import CenteredTitleComboBox


class PageControls(QWidget):
    """Shared presentation helpers for the small settings-page widgets."""

    LEFT_CONTROL_COLUMN_WIDTH = styles.PAGE_CONTROL_WIDTH
    RIGHT_CONTROL_COLUMN_WIDTH = styles.PAGE_CONTROL_WIDTH
    CONTROL_COLUMN_GAP = styles.PAGE_CONTROL_GAP
    CONTROL_ROW_WIDTH = (
        LEFT_CONTROL_COLUMN_WIDTH + CONTROL_COLUMN_GAP + RIGHT_CONTROL_COLUMN_WIDTH
    )

    def __init__(self, section_id: str, register_tooltip: Callable, parent=None):
        super().__init__(parent)
        self.section_id = section_id
        self.content = self
        self._register_tooltip = register_tooltip
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(10, 10, 10, 10)

    def register_tooltip(self, widget, text: str) -> None:
        self._register_tooltip(widget, text)

    def make_toggle_button(self, text: str, checked: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(button)
        button.setProperty("styleFontSize", 14)
        button.setStyleSheet(styles.toggle_button_style(font_size=14))
        return button

    def make_compact_toggle_button(
        self, text: str, checked: bool, *, width: int, font_size: int = 11
    ) -> QPushButton:
        button = self.make_toggle_button(text, checked)
        styles.apply_page_control_size(button, width=width, role="compact")
        button.setProperty("styleFontSize", font_size)
        button.setStyleSheet(styles.toggle_button_style(font_size=font_size))
        return button

    def make_two_column_control_row(self) -> tuple[QWidget, QGridLayout]:
        row = QWidget()
        row.setProperty("centeredControlGrid", True)
        row.setFixedWidth(self.CONTROL_ROW_WIDTH)
        row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QGridLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(self.CONTROL_COLUMN_GAP)
        layout.setVerticalSpacing(0)
        layout.setColumnMinimumWidth(0, self.LEFT_CONTROL_COLUMN_WIDTH)
        layout.setColumnMinimumWidth(1, self.RIGHT_CONTROL_COLUMN_WIDTH)
        return row, layout

    def add_two_column_control_row(
        self, parent_layout: QVBoxLayout, left_widget: QWidget, right_widget: QWidget
    ) -> QWidget:
        row, layout = self.make_two_column_control_row()
        if left_widget.property("pageControlRole") != "wide":
            left_widget.setFixedWidth(self.LEFT_CONTROL_COLUMN_WIDTH)
        if right_widget.property("pageControlRole") != "wide":
            right_widget.setFixedWidth(self.RIGHT_CONTROL_COLUMN_WIDTH)
        left_width, right_width = left_widget.width(), right_widget.width()
        row.setFixedWidth(left_width + self.CONTROL_COLUMN_GAP + right_width)
        layout.setColumnMinimumWidth(0, left_width)
        layout.setColumnMinimumWidth(1, right_width)
        layout.addWidget(left_widget, 0, 0)
        layout.addWidget(right_widget, 0, 1)
        parent_layout.addWidget(row, 0, Qt.AlignmentFlag.AlignHCenter)
        return row

    @staticmethod
    def bind_toggle_state_text(
        button: QPushButton, label: str, *, on_text: str = "On", off_text: str = "Off"
    ) -> None:
        def update_text(checked: bool) -> None:
            button.setText(f"{label} {on_text}" if checked else f"{label} {off_text}")
        update_text(button.isChecked())
        button.toggled.connect(update_text)

    def bind_toggle_icon_only(
        self, button: QPushButton, *, checked_glyph: str, unchecked_glyph: str
    ) -> None:
        button.setIconSize(QSize(16, 16))
        def update(checked: bool) -> None:
            button.setText("")
            button.setIcon(self.create_fluent_icon(checked_glyph if checked else unchecked_glyph))
        update(button.isChecked())
        button._refresh_toggle_icon = lambda: update(button.isChecked())
        button.toggled.connect(update)

    @staticmethod
    def create_fluent_icon(glyph: str, icon_size: int = 16) -> QIcon:
        pixmap = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont("Segoe Fluent Icons")
        font.setPixelSize(icon_size)
        painter.setFont(font)
        painter.setPen(styles.button_text_color())
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def install_green_flash(button: QPushButton) -> QPushButton:
        def clear() -> None:
            button.setProperty("flashActive", False)
            button.style().unpolish(button)
            button.style().polish(button)
        def flash() -> None:
            button.setProperty("flashActive", True)
            button.style().unpolish(button)
            button.style().polish(button)
            QTimer.singleShot(180, clear)
        button.clicked.connect(flash)
        return button

    def style_action_button(self, button: QPushButton) -> QPushButton:
        button.setCheckable(False)
        button.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(button)
        button.setProperty("styleFontSize", 14)
        button.setStyleSheet(styles.organizing_button_style(14))
        return self.install_green_flash(button)

    def make_action_dropdown(
        self,
        placeholder: str,
        action_names: list[str],
        on_action: Callable[[str], None],
        *,
        power_action_style: bool = False,
        severity_map: dict[str, str] | None = None,
        style_power_action: Callable[[QComboBox], None] | None = None,
    ) -> QComboBox:
        combo = CenteredTitleComboBox() if power_action_style else QComboBox()
        combo.addItem(placeholder)
        combo.addItems(action_names)
        combo.view().setRowHidden(0, True)
        combo.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(combo)
        combo.setProperty("styleFontSize", 14)
        if power_action_style:
            combo.setProperty("powerActionStyle", True)
            combo.setProperty("powerActionPlaceholder", placeholder)
            combo.setProperty("powerActionSeverityMap", severity_map or {})
            if style_power_action:
                style_power_action(combo)
        else:
            combo.setStyleSheet(styles.organizing_combo_style(14))
        styles.fit_page_combo_width(combo, placeholder=placeholder, font_size=14)
        def selected(text: str) -> None:
            if text != placeholder:
                on_action(text)
                combo.setCurrentText(placeholder)
        combo.currentTextChanged.connect(selected)
        return combo

    @staticmethod
    def make_value_dropdown(values: list[str], current_value: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(values)
        combo.setCurrentText(current_value if current_value in values else values[0])
        combo.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(combo)
        combo.setProperty("styleFontSize", 14)
        combo.setStyleSheet(styles.organizing_combo_style(14))
        styles.fit_page_combo_width(combo, font_size=14)
        return combo

"""Live and cached caption-button calibration dialogs."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCloseEvent,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from resurface.ui import styles
from resurface.features.hover_window_controls.core.hover_controller import CaptionAction
from resurface.features.hover_window_controls.vision.detection import (
    TrackedApplication,
    TrackedAsset,
    rects_overlap,
)

_ACTION_LABELS = {
    CaptionAction.MINIMIZE: "Minimize",
    CaptionAction.MAXIMIZE_RESTORE: "Maximize / Restore",
    CaptionAction.CLOSE: "Close",
}
_ACTION_ORDER = (
    CaptionAction.MINIMIZE,
    CaptionAction.MAXIMIZE_RESTORE,
    CaptionAction.CLOSE,
)
_TARGET_COLOR = QColor("#ff4050")
_DARK_STYLESHEET = """
QDialog#CalibrationDialog {
    background-color: #1e1e1e;
    color: #f2f2f2;
}
QDialog#CalibrationDialog QLabel,
QDialog#CalibrationDialog QCheckBox {
    color: #f2f2f2;
}
QDialog#CalibrationDialog QComboBox,
QDialog#CalibrationDialog QPushButton {
    background-color: #333333;
    color: #f2f2f2;
    border: 1px solid #5f5f5f;
    border-radius: 4px;
    padding: 4px 7px;
}
QDialog#CalibrationDialog QComboBox:hover,
QDialog#CalibrationDialog QPushButton:hover {
    border-color: #3d8bfd;
}
QDialog#CalibrationDialog QComboBox:disabled,
QDialog#CalibrationDialog QPushButton:disabled {
    background-color: #292929;
    color: #888888;
}
QDialog#CalibrationDialog QComboBox QAbstractItemView {
    background-color: #252526;
    color: #f2f2f2;
    selection-background-color: #3d6f9f;
    border: 1px solid #5f5f5f;
}
QDialog#CalibrationDialog QScrollArea {
    background-color: #151515;
    border: 1px solid #555555;
}
QDialog#CalibrationDialog QScrollBar:vertical,
QDialog#CalibrationDialog QScrollBar:horizontal {
    background: #202020;
    border: none;
}
QDialog#CalibrationDialog QScrollBar::handle:vertical,
QDialog#CalibrationDialog QScrollBar::handle:horizontal {
    background: #5a5a5a;
    border-radius: 4px;
    min-height: 20px;
    min-width: 20px;
}
"""


def _themed_stylesheet() -> str:
    """Map the companion dialog palette onto the active Resurface theme."""
    replacements = {
        "#1e1e1e": styles.qcolor_css(styles.WINDOW_BG),
        "#f2f2f2": styles.qcolor_css(styles.CURRENT_TEXT),
        "#252526": styles.qcolor_css(styles.SURFACE_BG),
        "#555555": styles.qcolor_css(styles.SURFACE_BORDER),
        "#333333": styles.qcolor_css(styles.themed_button_bg()),
        "#3d8bfd": styles.qcolor_css(styles.STATUS_ACCENT),
        "#76a9ff": styles.qcolor_css(styles.STATUS_ACCENT),
        "#3d6f9f": styles.qcolor_css(styles.PANEL_HOVER),
        "#292929": styles.qcolor_css(styles.SURFACE_HOVER),
        "#888888": styles.qcolor_css(styles.theme_muted_text_color()),
        "#b8b8b8": styles.qcolor_css(styles.theme_muted_text_color()),
    }
    sheet = _DARK_STYLESHEET
    for source, destination in replacements.items():
        sheet = sheet.replace(source, destination)
    return sheet


def validate_assignments(
    assignments: dict[CaptionAction, tuple[int, int, int, int]],
    image_size: tuple[int, int],
) -> Optional[str]:
    width, height = image_size
    if not assignments:
        return "Label at least one caption button."
    rectangles = list(assignments.items())
    for action, rect in rectangles:
        if not (
            0 <= rect[0] < rect[2] <= width
            and 0 <= rect[1] < rect[3] <= height
        ):
            return f"{_ACTION_LABELS[action]} is outside the captured image."
    for index, (action, rect) in enumerate(rectangles):
        for other_action, other_rect in rectangles[index + 1 :]:
            if rects_overlap(rect, other_rect):
                return (
                    f"{_ACTION_LABELS[action]} overlaps "
                    f"{_ACTION_LABELS[other_action]}."
                )
    return None


def action_glyph_geometry(
    action: CaptionAction,
    target: QRect,
) -> tuple[tuple[tuple[int, int, int, int], ...], Optional[QRect]]:
    available = max(2, min(target.width(), target.height()) - 8)
    size = min(12, available)
    half = max(1, size // 2)
    center = target.center()
    left, right = center.x() - half, center.x() + half
    top, bottom = center.y() - half, center.y() + half
    if action is CaptionAction.MINIMIZE:
        y = center.y() + max(1, half // 2)
        return ((left, y, right, y),), None
    if action is CaptionAction.MAXIMIZE_RESTORE:
        return (), QRect(left, top, max(2, right - left), max(2, bottom - top))
    return ((left, top, right, bottom), (right, top, left, bottom)), None


class CalibrationCanvas(QLabel):
    rectChanged = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #151515; color: #b8b8b8;")
        self._pixmap = QPixmap()
        self.reference_rect: Optional[tuple[int, int, int, int]] = None
        self.working_rect: Optional[tuple[int, int, int, int]] = None
        self._action: Optional[CaptionAction] = None
        self._drag_start: Optional[QPoint] = None
        self._drag_current: Optional[QPoint] = None
        self.clear_asset()

    def set_asset(self, asset: TrackedAsset) -> bool:
        pixmap = QPixmap(str(asset.image_path))
        if pixmap.isNull():
            self.clear_asset()
            return False
        self._pixmap = pixmap
        self.reference_rect = asset.reference_rect
        self.working_rect = asset.rect
        self._action = asset.action
        self.setText("")
        self.setEnabled(True)
        self.setFixedSize(*asset.crop_size)
        self.update()
        return True

    def set_live_image(
        self,
        image: QImage,
        action: CaptionAction,
        rect: Optional[tuple[int, int, int, int]],
    ) -> bool:
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            self.clear_asset()
            return False
        self._pixmap = pixmap
        self.reference_rect = (0, 0, image.width(), image.height())
        self.working_rect = rect
        self._action = action
        self.setText("")
        self.setEnabled(True)
        self.setFixedSize(image.width(), image.height())
        self.update()
        return True

    def clear_asset(self) -> None:
        self._pixmap = QPixmap()
        self.reference_rect = None
        self.working_rect = None
        self._action = None
        self.setEnabled(False)
        self.setText("Select a tracked application and action.")
        self.setFixedSize(480, 120)
        self.update()

    def set_working_rect(
        self,
        rect: tuple[int, int, int, int],
    ) -> None:
        self.working_rect = rect
        self.update()

    def commit_asset(self, asset: TrackedAsset) -> None:
        self.reference_rect = asset.reference_rect
        self.working_rect = asset.rect
        self.update()

    def _bounded_point(self, point: QPoint) -> QPoint:
        return QPoint(
            min(max(point.x(), 0), max(self.width() - 1, 0)),
            min(max(point.y(), 0), max(self.height() - 1, 0)),
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            self.isEnabled()
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._drag_start = self._bounded_point(
                event.position().toPoint()
            )
            self._drag_current = self._drag_start
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is not None:
            self._drag_current = self._bounded_point(
                event.position().toPoint()
            )
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is None:
            return
        current = self._bounded_point(event.position().toPoint())
        rect = QRect(self._drag_start, current).normalized().intersected(
            self.rect()
        )
        self._drag_start = None
        self._drag_current = None
        if rect.width() >= 1 and rect.height() >= 1:
            value = (
                rect.left(),
                rect.top(),
                rect.right() + 1,
                rect.bottom() + 1,
            )
            self.working_rect = value
            self.rectChanged.emit(value)
        self.update()

    @staticmethod
    def _qrect(rect: tuple[int, int, int, int]) -> QRect:
        return QRect(
            rect[0],
            rect[1],
            rect[2] - rect[0],
            rect[3] - rect[1],
        )

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.reference_rect is None or self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.drawPixmap(
            self._qrect(self.reference_rect),
            self._pixmap,
            self._pixmap.rect(),
        )
        display_rect = self.working_rect
        if self._drag_start is not None and self._drag_current is not None:
            dragged = QRect(
                self._drag_start,
                self._drag_current,
            ).normalized()
            display_rect = (
                dragged.left(),
                dragged.top(),
                dragged.right() + 1,
                dragged.bottom() + 1,
            )
        if display_rect is None:
            return
        target = self._qrect(display_rect)
        painter.setPen(QPen(_TARGET_COLOR, 2))
        painter.drawRect(target)
        if self._action is not None:
            lines, square = action_glyph_geometry(self._action, target)
            for line in lines:
                painter.drawLine(*line)
            if square is not None:
                painter.drawRect(square)


class CalibrationDialog(QDialog):
    def __init__(
        self,
        application_provider: Callable[[], list[TrackedApplication]],
        asset_provider: Callable[
            [TrackedApplication],
            list[TrackedAsset],
        ],
        update_provider: Callable[
            [TrackedAsset, tuple[int, int, int, int]],
            TrackedAsset,
        ],
        *,
        delete_provider: Optional[Callable[[TrackedApplication], None]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CalibrationDialog")
        self.setStyleSheet(_themed_stylesheet())
        self.setWindowTitle("Calibration Explorer")
        self.setModal(True)
        self._application_provider = application_provider
        self._asset_provider = asset_provider
        self._update_provider = update_provider
        self._delete_provider = delete_provider
        self._selected_application: Optional[TrackedApplication] = None
        self._selected_asset: Optional[TrackedAsset] = None
        self._assets_by_action: dict[
            CaptionAction,
            list[TrackedAsset],
        ] = {}
        self._updating = False
        self._dirty = False
        self._application_refresh_timer = QTimer(self)
        self._application_refresh_timer.setInterval(2_000)
        self._application_refresh_timer.timeout.connect(
            self._poll_applications
        )

        layout = QVBoxLayout(self)
        instruction = QLabel(
            "Select a tracked application and action, then drag the red "
            "box on the JPEG preview to adjust its position."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        app_row = QHBoxLayout()
        app_row.addWidget(QLabel("Tracked application:"))
        self.application_selector = QComboBox()
        self.application_selector.setObjectName("trackedApplicationSelector")
        self.application_selector.setMinimumContentsLength(28)
        app_row.addWidget(self.application_selector, 1)
        self.delete_button = QPushButton("Delete application")
        self.delete_button.setObjectName("deleteTrackedApplicationButton")
        self.delete_button.clicked.connect(self._delete_selected_application)
        app_row.addWidget(self.delete_button)
        layout.addLayout(app_row)

        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("Button action:"))
        self.action_selector = QComboBox()
        self.action_selector.setObjectName("trackedActionSelector")
        action_row.addWidget(self.action_selector, 1)
        layout.addLayout(action_row)

        variant_row = QHBoxLayout()
        variant_row.addWidget(QLabel("JPEG variant:"))
        self.variant_selector = QComboBox()
        self.variant_selector.setObjectName("trackedVariantSelector")
        variant_row.addWidget(self.variant_selector, 1)
        layout.addLayout(variant_row)

        self.status_label = QLabel()
        self.status_label.setObjectName("calibrationStatus")
        self.status_label.setStyleSheet(
            f"color: {styles.qcolor_css(styles.theme_muted_text_color())};"
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.canvas = CalibrationCanvas()
        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(False)
        layout.addWidget(scroll)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Close
        )
        self.save_button = button_box.button(
            QDialogButtonBox.StandardButton.Save
        )
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(lambda: self._save_current())
        button_box.button(
            QDialogButtonBox.StandardButton.Close
        ).clicked.connect(self.close)
        layout.addWidget(button_box)

        self.application_selector.currentIndexChanged.connect(
            self._application_changed
        )
        self.action_selector.currentIndexChanged.connect(
            self._action_changed
        )
        self.variant_selector.currentIndexChanged.connect(
            self._variant_changed
        )
        self.canvas.rectChanged.connect(self._canvas_changed)
        self.refresh_applications(prompt=False)
        self._application_refresh_timer.start()

    @staticmethod
    def _find_key(combo: QComboBox, key) -> int:
        for index in range(combo.count()):
            item = combo.itemData(index)
            if item is not None and item.key == key:
                return index
        return -1

    @staticmethod
    def _find_action(combo: QComboBox, action: CaptionAction) -> int:
        for index in range(combo.count()):
            if combo.itemData(index) is action:
                return index
        return -1

    def _restore_selection(self) -> None:
        self._updating = True
        try:
            if self._selected_application is not None:
                index = self._find_key(
                    self.application_selector,
                    self._selected_application.key,
                )
                self.application_selector.setCurrentIndex(index)
            if self._selected_asset is not None:
                action_index = self._find_action(
                    self.action_selector,
                    self._selected_asset.action,
                )
                self.action_selector.setCurrentIndex(action_index)
                variant_index = self._find_key(
                    self.variant_selector,
                    self._selected_asset.key,
                )
                self.variant_selector.setCurrentIndex(variant_index)
        finally:
            self._updating = False

    def _confirm_transition(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Save position changes?",
            "Save the current action position before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self._save_current(show_success=False)
        if answer == QMessageBox.StandardButton.Discard:
            self._dirty = False
            return True
        return False

    def refresh_applications(self, *, prompt: bool = True) -> None:
        if prompt and not self._confirm_transition():
            return
        app_key = (
            self._selected_application.key
            if self._selected_application is not None
            else None
        )
        asset_key = (
            self._selected_asset.key
            if self._selected_asset is not None
            else None
        )
        try:
            applications = self._application_provider()
        except Exception as error:
            self._clear_editor(
                f"Could not read tracked applications: {error}"
            )
            return
        self._updating = True
        try:
            self.application_selector.clear()
            for application in applications:
                self.application_selector.addItem(
                    application.label,
                    application,
                )
            index = self._find_key(self.application_selector, app_key)
            self.application_selector.setCurrentIndex(
                index if index >= 0 else (0 if applications else -1)
            )
        finally:
            self._updating = False
        if not applications:
            self._selected_application = None
            self._clear_editor("No tracked application JPEGs are available.")
            self.delete_button.setEnabled(False)
            return
        self.delete_button.setEnabled(self._delete_provider is not None)
        self._load_application(asset_key)

    def _application_signature(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (
                self.application_selector.itemData(index).key,
                self.application_selector.itemText(index),
            )
            for index in range(self.application_selector.count())
            if self.application_selector.itemData(index) is not None
        )

    def _poll_applications(self) -> None:
        """Refresh learned applications without interrupting an edit."""
        if self._dirty:
            return
        try:
            applications = self._application_provider()
        except Exception:
            return
        signature = tuple(
            (application.key, application.label)
            for application in applications
        )
        if signature != self._application_signature():
            self.refresh_applications(prompt=False)

    def _delete_selected_application(self) -> None:
        application = self.application_selector.currentData()
        if application is None or self._delete_provider is None:
            return
        if not self._confirm_transition():
            return
        answer = QMessageBox.question(
            self,
            "Delete tracked application?",
            (
                f"Delete all saved caption-button data for "
                f"{application.friendly_name}? This application will be "
                "learned again when you use its caption controls."
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._delete_provider(application)
        except Exception as error:
            QMessageBox.warning(
                self,
                "Could not delete tracked application",
                str(error),
            )
            return
        self._selected_application = None
        self._selected_asset = None
        self.refresh_applications(prompt=False)

    def _application_changed(self, _index: int) -> None:
        if self._updating:
            return
        if not self._confirm_transition():
            self._restore_selection()
            return
        self._load_application(None)

    def _load_application(self, preferred_asset_key) -> None:
        application = self.application_selector.currentData()
        if application is None:
            self._selected_application = None
            self._clear_editor("Select a tracked application.")
            return
        try:
            assets = self._asset_provider(application)
        except Exception as error:
            self._selected_application = application
            self._clear_editor(f"Could not read tracked actions: {error}")
            return
        self._selected_application = application
        self._assets_by_action = {
            action: [
                asset for asset in assets if asset.action is action
            ]
            for action in _ACTION_ORDER
        }
        preferred_asset = next(
            (
                asset
                for asset in assets
                if asset.key == preferred_asset_key
            ),
            None,
        )
        self._updating = True
        try:
            self.action_selector.clear()
            for action in _ACTION_ORDER:
                available = bool(self._assets_by_action[action])
                label = _ACTION_LABELS[action]
                if not available:
                    label += " (No JPEG)"
                self.action_selector.addItem(label, action)
                item = self.action_selector.model().item(
                    self.action_selector.count() - 1
                )
                item.setEnabled(available)
            selected_action = (
                preferred_asset.action
                if preferred_asset is not None
                else next(
                    (
                        action
                        for action in _ACTION_ORDER
                        if self._assets_by_action[action]
                    ),
                    None,
                )
            )
            self.action_selector.setCurrentIndex(
                self._find_action(
                    self.action_selector,
                    selected_action,
                )
                if selected_action is not None
                else -1
            )
        finally:
            self._updating = False
        if not assets:
            self._clear_editor(
                "This application has no available tracked JPEGs."
            )
            return
        self._load_action(preferred_asset_key)

    def _action_changed(self, _index: int) -> None:
        if self._updating:
            return
        if not self._confirm_transition():
            self._restore_selection()
            return
        self._load_action(None)

    def _load_action(self, preferred_asset_key) -> None:
        action = self.action_selector.currentData()
        assets = self._assets_by_action.get(action, [])
        self._updating = True
        try:
            self.variant_selector.clear()
            for asset in assets:
                self.variant_selector.addItem(asset.label, asset)
            index = self._find_key(
                self.variant_selector,
                preferred_asset_key,
            )
            self.variant_selector.setCurrentIndex(
                index if index >= 0 else (0 if assets else -1)
            )
        finally:
            self._updating = False
        if not assets:
            self._clear_editor(
                "The selected action does not have a tracked JPEG."
            )
            return
        self._load_asset(self.variant_selector.currentData())

    def _variant_changed(self, _index: int) -> None:
        if self._updating:
            return
        if not self._confirm_transition():
            self._restore_selection()
            return
        self._load_asset(self.variant_selector.currentData())

    def _load_asset(self, asset: Optional[TrackedAsset]) -> None:
        if asset is None:
            self._clear_editor("Select a tracked action.")
            return
        if not self.canvas.set_asset(asset):
            self._selected_asset = None
            self._clear_editor(
                "The selected JPEG is missing or cannot be decoded. "
                "Refresh or choose another action."
            )
            return
        self._selected_asset = asset
        self._dirty = False
        if asset.rect is None:
            self.save_button.setEnabled(False)
            self.status_label.setText(
                "No detected box is available. Draw this button on the grouped JPEG."
            )
        else:
            self.save_button.setEnabled(True)
            self.status_label.setText(
                "Suggested neighboring position. Adjust it if needed, then Save."
                if asset.configuration_state == "suggested"
                else f"Loaded {asset.image_path.name}."
            )
        self.setWindowTitle(
            f"Calibration Explorer — {asset.application.friendly_name}"
        )

    def _clear_editor(self, message: str) -> None:
        self._selected_asset = None
        self._dirty = False
        self.canvas.clear_asset()
        self.save_button.setEnabled(False)
        self.status_label.setText(message)
        self.setWindowTitle("Calibration Explorer")

    def current_rect(self) -> Optional[tuple[int, int, int, int]]:
        if self._selected_asset is None:
            return None
        return self.canvas.working_rect

    def _canvas_changed(
        self,
        rect: tuple[int, int, int, int],
    ) -> None:
        if self._selected_asset is not None:
            self._dirty = rect != self._selected_asset.rect
            self.save_button.setEnabled(True)
            self.status_label.setText(
                "Position changed. Save to update the tracked manifest."
                if self._dirty
                else f"Loaded {self._selected_asset.image_path.name}."
            )

    def _save_current(self, *, show_success: bool = True) -> bool:
        if self._selected_asset is None:
            return False
        rect = self.current_rect()
        if rect is None:
            return False
        width, height = self._selected_asset.crop_size
        error = validate_assignments(
            {self._selected_asset.action: rect},
            (width, height),
        )
        if error is not None:
            QMessageBox.warning(self, "Invalid position", error)
            return False
        try:
            updated = self._update_provider(self._selected_asset, rect)
        except Exception as error:
            self.status_label.setText(
                f"Could not save the tracked position: {error}"
            )
            return False
        self._selected_asset = updated
        self.variant_selector.setItemData(
            self.variant_selector.currentIndex(),
            updated,
        )
        self.canvas.commit_asset(updated)
        self._dirty = False
        self.status_label.setText(
            f"Saved {updated.image_path.name}."
            if show_success
            else f"Updated {updated.image_path.name}."
        )
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_transition():
            self._application_refresh_timer.stop()
            event.accept()
        else:
            event.ignore()

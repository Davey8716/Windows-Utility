"""Live and cached caption-button calibration dialogs."""

from __future__ import annotations

import ctypes
from typing import Callable, Optional

from PySide6.QtCore import QPoint, QRect, Qt, Signal
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
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from resurface.features.hover_window_controls.core.hover_controller import CaptionAction
from resurface.features.hover_window_controls.vision.detection import (
    TrackedApplication,
    TrackedAsset,
    VisionProfile,
    VisionSnapshot,
    rects_overlap,
)
from resurface.ui import styles
from resurface.ui.app_notifications import WindowMessageMixin

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
CALIBRATION_DIALOG_SIZE = (650, 438)
_CLOSE_ONLY_DIALOG_FLAGS = (
    Qt.WindowType.Dialog
    | Qt.WindowType.CustomizeWindowHint
    | Qt.WindowType.WindowTitleHint
    | Qt.WindowType.WindowCloseButtonHint
)
HOVER_CONTROLS_PROMPT_CORNER_RADIUS = 12


def _color(value: QColor) -> str:
    return value.name(QColor.NameFormat.HexRgb)


def _calibration_stylesheet() -> str:
    window_bg = _color(styles.WINDOW_BG)
    surface_bg = _color(styles.SURFACE_BG)
    surface_hover = _color(styles.SURFACE_HOVER)
    surface_border = _color(styles.SURFACE_BORDER)
    text = _color(styles.theme_text_color())
    muted = _color(styles.theme_muted_text_color())
    field_bg = _color(styles.themed_surface_field_bg())
    field_text = _color(styles.themed_surface_field_text())
    field_border = _color(styles.themed_surface_field_border())
    button_bg = _color(styles.themed_button_bg())
    button_hover = _color(styles.themed_button_hover())
    button_pressed = _color(styles.themed_button_pressed())
    button_border = _color(styles.themed_button_border())
    button_text = _color(styles.button_text_color())
    disabled_bg = _color(styles.themed_button_disabled_bg())
    disabled_text = _color(styles.themed_button_disabled_text())
    return f"""
QDialog#CalibrationDialog {{
    background-color: {window_bg};
    color: {text};
    border-radius: 10px;
}}
QDialog#CalibrationDialog QLabel,
QDialog#CalibrationDialog QGroupBox,
QDialog#CalibrationDialog QCheckBox {{
    color: {text};
}}
QDialog#CalibrationDialog QGroupBox {{
    background-color: {surface_bg};
    border: 1px solid {surface_border};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
}}
QDialog#CalibrationDialog QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}
QDialog#CalibrationDialog QComboBox {{
    background-color: {field_bg};
    color: {field_text};
    border: 1px solid {field_border};
    border-radius: 6px;
    padding: 4px 7px;
}}
QDialog#CalibrationDialog QPushButton {{
    background-color: {button_bg};
    color: {button_text};
    border: 1px solid {button_border};
    border-radius: 6px;
    padding: 5px 10px;
    font-weight: bold;
}}
QDialog#CalibrationDialog QComboBox:hover {{
    background-color: {surface_hover};
    border-color: {field_border};
}}
QDialog#CalibrationDialog QPushButton:hover {{
    background-color: {button_hover};
}}
QDialog#CalibrationDialog QPushButton:pressed {{
    background-color: {button_pressed};
}}
QDialog#CalibrationDialog QComboBox:disabled {{
    background-color: {surface_bg};
    color: {muted};
}}
QDialog#CalibrationDialog QPushButton:disabled {{
    background-color: {disabled_bg};
    color: {disabled_text};
}}
QDialog#CalibrationDialog QComboBox QAbstractItemView {{
    background-color: {surface_bg};
    color: {text};
    selection-background-color: {surface_hover};
    border: 1px solid {surface_border};
}}
QDialog#CalibrationDialog QScrollArea {{
    background-color: {surface_bg};
    border: 1px solid {surface_border};
    border-radius: 6px;
}}
QDialog#CalibrationDialog QScrollBar:vertical,
QDialog#CalibrationDialog QScrollBar:horizontal {{
    background: {surface_bg};
    border: none;
}}
QDialog#CalibrationDialog QScrollBar::handle:vertical,
QDialog#CalibrationDialog QScrollBar::handle:horizontal {{
    background: {surface_hover};
    border-radius: 4px;
    min-height: 20px;
    min-width: 20px;
}}
QDialog#CalibrationDialog QLabel#calibrationStatus,
QDialog#CalibrationDialog QLabel#liveCalibrationStatus {{
    color: {muted};
}}
"""


def _apply_native_window_appearance(dialog: QDialog) -> None:
    """Use close-only native chrome with Windows 11 rounded corners."""
    try:
        hwnd = int(dialog.winId())
        corner_preference = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            33,  # DWMWA_WINDOW_CORNER_PREFERENCE
            ctypes.byref(corner_preference),
            ctypes.sizeof(corner_preference),
        )
        dark_title_bar = ctypes.c_int(1 if styles.THEME_IS_DARK else 0)
        for attribute in (20, 19):  # Current and older immersive-dark-mode ids.
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                attribute,
                ctypes.byref(dark_title_bar),
                ctypes.sizeof(dark_title_bar),
            )
            if result == 0:
                break
    except (AttributeError, OSError, TypeError, ValueError):
        pass


def _apply_frameless_window_style(dialog: QDialog) -> None:
    """Remove the native Windows caption and fixed-window frame."""
    try:
        hwnd = int(dialog.winId())
        if not hwnd:
            return

        user32 = ctypes.windll.user32
        get_window_long = user32.GetWindowLongW
        set_window_long = user32.SetWindowLongW
        set_window_pos = user32.SetWindowPos

        GWL_STYLE = -16
        WS_CAPTION = 0x00C00000
        WS_SYSMENU = 0x00080000
        WS_MINIMIZEBOX = 0x00020000
        WS_MAXIMIZEBOX = 0x00010000
        WS_THICKFRAME = 0x00040000
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020

        style = get_window_long(hwnd, GWL_STYLE)
        style &= ~(
            WS_CAPTION
            | WS_SYSMENU
            | WS_MINIMIZEBOX
            | WS_MAXIMIZEBOX
            | WS_THICKFRAME
        )
        set_window_long(hwnd, GWL_STYLE, style)
        set_window_pos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    _apply_native_window_appearance(dialog)


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


class CalibrationCanvas(QLabel):
    rectChanged = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.apply_theme()
        self._pixmap = QPixmap()
        self.reference_rect: Optional[tuple[int, int, int, int]] = None
        self.working_rect: Optional[tuple[int, int, int, int]] = None
        self._action: Optional[CaptionAction] = None
        self._drag_start: Optional[QPoint] = None
        self._drag_current: Optional[QPoint] = None
        self.clear_asset()

    def apply_theme(self) -> None:
        self.setStyleSheet(
            "background-color: "
            f"{_color(styles.SURFACE_BG)}; "
            f"color: {_color(styles.theme_muted_text_color())};"
        )

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


def action_glyph_geometry(
    action: CaptionAction,
    target: QRect,
) -> tuple[tuple[tuple[int, int, int, int], ...], Optional[QRect]]:
    available = max(2, min(target.width(), target.height()) - 8)
    size = min(12, available)
    half = max(1, size // 2)
    center = target.center()
    left = center.x() - half
    right = center.x() + half
    top = center.y() - half
    bottom = center.y() + half
    if action is CaptionAction.MINIMIZE:
        y = center.y() + max(1, half // 2)
        return ((left, y, right, y),), None
    if action is CaptionAction.MAXIMIZE_RESTORE:
        return (), QRect(left, top, max(2, right - left), max(2, bottom - top))
    return (
        (left, top, right, bottom),
        (right, top, left, bottom),
    ), None


class LiveCalibrationDialog(QDialog):
    def __init__(
        self,
        snapshot: VisionSnapshot,
        save_provider: Callable[
            [
                VisionSnapshot,
                dict[CaptionAction, tuple[int, int, int, int]],
            ],
            VisionProfile,
        ],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CalibrationDialog")
        self.setWindowFlags(_CLOSE_ONLY_DIALOG_FLAGS)
        _apply_native_window_appearance(self)
        self.setStyleSheet(_calibration_stylesheet())
        self.setWindowTitle("Calibrate open application")
        self.setModal(True)
        self.snapshot = snapshot
        self._save_provider = save_provider
        self._rects = dict(snapshot.proposals)
        self._included: set[CaptionAction] = set()
        self._updating = False
        self.saved_profile: Optional[VisionProfile] = None

        layout = QVBoxLayout(self)
        instruction = QLabel(
            "Choose an action, then explicitly include its suggested box "
            "or draw a missing box on the in-memory caption preview. "
            "Unchecked actions are skipped."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("Button action:"))
        self.action_selector = QComboBox()
        for action in _ACTION_ORDER:
            self.action_selector.addItem(_ACTION_LABELS[action], action)
        action_row.addWidget(self.action_selector, 1)
        self.include_checkbox = QCheckBox("Include this action")
        action_row.addWidget(self.include_checkbox)
        layout.addLayout(action_row)

        self.status_label = QLabel()
        self.status_label.setObjectName("liveCalibrationStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.canvas = CalibrationCanvas()
        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(False)
        layout.addWidget(scroll)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(
            QDialogButtonBox.StandardButton.Save
        ).clicked.connect(self._save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.action_selector.currentIndexChanged.connect(
            self._action_changed
        )
        self.include_checkbox.toggled.connect(self._include_changed)
        self.canvas.rectChanged.connect(self._canvas_changed)
        self._load_action()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        _apply_native_window_appearance(self)

    @property
    def current_action(self) -> CaptionAction:
        return self.action_selector.currentData()

    @property
    def assignments(
        self,
    ) -> dict[CaptionAction, tuple[int, int, int, int]]:
        return {
            action: self._rects[action]
            for action in self._included
            if action in self._rects
        }

    def _action_changed(self, _index: int) -> None:
        if not self._updating:
            self._load_action()

    def _load_action(self) -> None:
        action = self.current_action
        rect = self._rects.get(action)
        self._updating = True
        try:
            self.include_checkbox.setChecked(action in self._included)
            self.include_checkbox.setEnabled(rect is not None)
            self.canvas.set_live_image(
                self.snapshot.image,
                action,
                rect,
            )
        finally:
            self._updating = False
        self.status_label.setText(
            (
                "Suggested box available. Check Include or adjust/draw it."
                if rect is not None
                else "No suggestion is available. Draw the button box."
            )
        )

    def _include_changed(self, checked: bool) -> None:
        if self._updating:
            return
        action = self.current_action
        if checked and action in self._rects:
            self._included.add(action)
        else:
            self._included.discard(action)

    def _canvas_changed(
        self,
        rect: tuple[int, int, int, int],
    ) -> None:
        self._rects[self.current_action] = rect
        self.canvas.set_working_rect(rect)
        self._included.add(self.current_action)
        self._updating = True
        try:
            self.include_checkbox.setEnabled(True)
            self.include_checkbox.setChecked(True)
        finally:
            self._updating = False
        self.status_label.setText("Manual box included.")

    def _save(self) -> None:
        assignments = self.assignments
        error = validate_assignments(
            assignments,
            (self.snapshot.image.width(), self.snapshot.image.height()),
        )
        if error is not None:
            QMessageBox.warning(self, "Invalid calibration", error)
            return
        try:
            self.saved_profile = self._save_provider(
                self.snapshot,
                assignments,
            )
        except Exception as error:
            QMessageBox.warning(
                self,
                "Could not save calibration",
                str(error),
            )
            return
        self.accept()


class CalibrationDialog(WindowMessageMixin, QDialog):
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
        target_provider: Optional[Callable[[], list[object]]] = None,
        capture_provider: Optional[Callable[[int], object]] = None,
        save_provider: Optional[
            Callable[
                [
                    VisionSnapshot,
                    dict[CaptionAction, tuple[int, int, int, int]],
                ],
                VisionProfile,
            ]
        ] = None,
        clear_provider: Optional[Callable[[], None]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CalibrationDialog")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        _apply_frameless_window_style(self)
        self.setStyleSheet(_calibration_stylesheet())
        self.setFixedSize(*CALIBRATION_DIALOG_SIZE)
        self.setWindowTitle("Calibration Explorer")
        self.setModal(True)
        self._application_provider = application_provider
        self._asset_provider = asset_provider
        self._update_provider = update_provider
        self._target_provider = target_provider
        self._capture_provider = capture_provider
        self._save_provider = save_provider
        self._clear_provider = clear_provider
        self._selected_application: Optional[TrackedApplication] = None
        self._selected_asset: Optional[TrackedAsset] = None
        self._assets_by_action: dict[
            CaptionAction,
            list[TrackedAsset],
        ] = {}
        self._updating = False
        self._dirty = False

        layout = QVBoxLayout(self)
        instruction = QLabel(
            "Select a tracked application and action. Align the red target "
            "with the fixed JPEG using the labelled position fields or drag "
            "on the preview."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        self.live_group: Optional[QGroupBox] = None
        self.live_target_selector: Optional[QComboBox] = None
        self.live_status_label: Optional[QLabel] = None
        if (
            target_provider is not None
            and capture_provider is not None
            and save_provider is not None
        ):
            self.live_group = QGroupBox("Open windows")
            live_layout = QVBoxLayout(self.live_group)
            live_row = QHBoxLayout()
            self.live_target_selector = QComboBox()
            self.live_target_selector.setObjectName(
                "liveCalibrationTargetSelector"
            )
            self.live_target_selector.setMinimumContentsLength(28)
            live_row.addWidget(self.live_target_selector, 1)
            refresh_live_button = QPushButton("Refresh windows")
            refresh_live_button.clicked.connect(
                self.refresh_live_targets
            )
            live_row.addWidget(refresh_live_button)
            capture_button = QPushButton("Capture and calibrate")
            capture_button.setObjectName("captureLiveApplicationButton")
            capture_button.clicked.connect(self._capture_live_target)
            live_row.addWidget(capture_button)
            live_layout.addLayout(live_row)
            self.live_status_label = QLabel(
                "Select an open application to bootstrap a calibration."
            )
            self.live_status_label.setWordWrap(True)
            live_layout.addWidget(self.live_status_label)
            layout.addWidget(self.live_group)

        app_row = QHBoxLayout()
        app_row.addWidget(QLabel("Tracked application:"))
        self.application_selector = QComboBox()
        self.application_selector.setObjectName("trackedApplicationSelector")
        self.application_selector.setMinimumContentsLength(28)
        app_row.addWidget(self.application_selector, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("refreshTrackedApplicationsButton")
        app_row.addWidget(self.refresh_button)
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
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.canvas = CalibrationCanvas()
        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(False)
        layout.addWidget(scroll)

        footer = QHBoxLayout()
        self.clear_button: Optional[QPushButton] = None
        if self._clear_provider is not None:
            self.clear_button = QPushButton("Clear Learned Buttons")
            self.clear_button.setObjectName("clearLearnedButtonsButton")
            self.clear_button.clicked.connect(self._clear_learned_buttons)
            footer.addWidget(self.clear_button)
        footer.addStretch()
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
        footer.addWidget(button_box)
        layout.addLayout(footer)

        self.application_selector.currentIndexChanged.connect(
            self._application_changed
        )
        self.action_selector.currentIndexChanged.connect(
            self._action_changed
        )
        self.variant_selector.currentIndexChanged.connect(
            self._variant_changed
        )
        self.refresh_button.clicked.connect(
            lambda: self.refresh_applications()
        )
        self.canvas.rectChanged.connect(self._canvas_changed)
        self.refresh_live_targets()
        self.refresh_applications(prompt=False)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        _apply_frameless_window_style(self)

    def _clear_learned_buttons(self) -> None:
        if self._clear_provider is None:
            return
        answer = self._show_modal_message(
            QMessageBox.Icon.NoIcon,
            "Clear all learned buttons?",
            "This permanently \n caption-button images and\n "
            "calibration data.\nHover preferences are kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
            fixed_popup_width=360,
            center_text_block=True,
            popup_corner_radius=HOVER_CONTROLS_PROMPT_CORNER_RADIUS,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._clear_provider()
        except OSError as error:
            QMessageBox.warning(
                self,
                "Could not clear learned buttons",
                str(error),
            )
            return
        self._dirty = False
        self.refresh_applications(prompt=False)
        self.status_label.setText("All learned buttons were cleared.")

    def refresh_live_targets(self) -> None:
        if self.live_target_selector is None or self._target_provider is None:
            return
        current = self.live_target_selector.currentData()
        current_hwnd = getattr(current, "hwnd", None)
        try:
            targets = self._target_provider()
        except Exception as error:
            self.live_target_selector.clear()
            if self.live_status_label is not None:
                self.live_status_label.setText(
                    f"Could not list open windows: {error}"
                )
            return
        self.live_target_selector.clear()
        selected_index = -1
        for index, target in enumerate(targets):
            self.live_target_selector.addItem(target.label, target)
            if target.hwnd == current_hwnd:
                selected_index = index
        if targets:
            self.live_target_selector.setCurrentIndex(
                selected_index if selected_index >= 0 else 0
            )
            if self.live_status_label is not None:
                self.live_status_label.setText(
                    "Select an open application to bootstrap a calibration."
                )
        elif self.live_status_label is not None:
            self.live_status_label.setText(
                "No eligible open application windows were found."
            )

    def _capture_live_target(self) -> None:
        if (
            self.live_target_selector is None
            or self._capture_provider is None
            or self._save_provider is None
        ):
            return
        target = self.live_target_selector.currentData()
        if target is None:
            if self.live_status_label is not None:
                self.live_status_label.setText(
                    "Select an open application first."
                )
            return
        try:
            result = self._capture_provider(target.hwnd)
        except Exception as error:
            if self.live_status_label is not None:
                self.live_status_label.setText(
                    f"Could not capture the selected window: {error}"
                )
            return
        snapshot = getattr(result, "snapshot", None)
        if snapshot is None:
            if self.live_status_label is not None:
                self.live_status_label.setText(
                    getattr(
                        result,
                        "error",
                        "The selected window could not be captured.",
                    )
                )
            return
        dialog = LiveCalibrationDialog(
            snapshot,
            self._save_provider,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        profile = dialog.saved_profile
        self.refresh_applications(prompt=False)
        if profile is not None:
            application_key = profile.identity.executable_hash
            index = self._find_key(
                self.application_selector,
                application_key,
            )
            if index >= 0:
                self.application_selector.setCurrentIndex(index)
                self._load_application(None)
        if self.live_status_label is not None:
            self.live_status_label.setText(
                "Calibration saved. The learned profile is selected below."
            )

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
        answer = self._show_modal_message(
            QMessageBox.Icon.NoIcon,
            "Save position changes?",
            "Save the current action position before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
            popup_corner_radius=HOVER_CONTROLS_PROMPT_CORNER_RADIUS,
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
            return
        self._load_application(asset_key)

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
        self.save_button.setEnabled(True)
        self.status_label.setText(f"Loaded {asset.image_path.name}.")
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
        self.canvas.set_working_rect(rect)
        if self._selected_asset is not None:
            self._dirty = rect != self._selected_asset.rect
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
            event.accept()
        else:
            event.ignore()

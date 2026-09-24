"""Tracked caption-button calibration dialog."""

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

from resurface.features.hover_window_controls.core.hover_controller import CaptionAction
from resurface.features.hover_window_controls.vision.detection import (
    ApplicationIdentity,
    TrackedApplication,
    TrackedAsset,
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
CALIBRATION_DIALOG_SIZE = (650, 478)
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
QDialog#CalibrationDialog QLabel {{
    color: {text};
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
QDialog#CalibrationDialog QLabel#calibrationStatus {{
    color: {muted};
}}
QDialog#CalibrationDialog QLabel#calibrationTitle {{
    font-size: 18px;
    font-weight: bold;
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
        refresh_provider: Optional[
            Callable[
                [Callable[[int, list[TrackedApplication], int, str], None]],
                bool,
            ]
        ] = None,
        clear_provider: Optional[Callable[[], None]] = None,
        clear_available: bool = True,
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
        self._refresh_provider = refresh_provider
        self._asset_provider = asset_provider
        self._update_provider = update_provider
        self._clear_provider = clear_provider
        self._clear_available = bool(clear_available)
        self._selected_application: Optional[TrackedApplication] = None
        self._selected_asset: Optional[TrackedAsset] = None
        self._assets_for_application: list[TrackedAsset] = []
        self._assets_by_action: dict[
            CaptionAction,
            list[TrackedAsset],
        ] = {}
        self._updating = False
        self._dirty = False
        self._refresh_in_progress = False

        layout = QVBoxLayout(self)
        title = QLabel("Calibration Explorer")
        title.setObjectName("calibrationTitle")
        layout.addWidget(title)
        instruction = QLabel(
            "Select a tracked application and action. Align the red target "
            "with the fixed JPEG using the labelled position fields or drag "
            "on the preview."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

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

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Build & window profile:"))
        self.profile_selector = QComboBox()
        self.profile_selector.setObjectName("trackedProfileSelector")
        self.profile_selector.setMinimumContentsLength(28)
        profile_row.addWidget(self.profile_selector, 1)
        layout.addLayout(profile_row)
        self.profile_path_label = QLabel()
        self.profile_path_label.setObjectName("trackedProfilePath")
        self.profile_path_label.setWordWrap(True)
        layout.addWidget(self.profile_path_label)

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
            self.clear_button.setEnabled(self._clear_available)
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
        self.profile_selector.currentIndexChanged.connect(
            self._profile_changed
        )
        self.action_selector.currentIndexChanged.connect(
            self._action_changed
        )
        self.variant_selector.currentIndexChanged.connect(
            self._variant_changed
        )
        self.refresh_button.clicked.connect(
            self._refresh_tracked_applications
        )
        self.canvas.rectChanged.connect(self._canvas_changed)
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
            "This permanently removes all learned caption-button images and "
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
        self.set_clear_available(False)
        self.status_label.setText(
            "All learned buttons were cleared. Click Refresh to scan open "
            "applications."
        )

    def set_clear_available(self, available: bool) -> None:
        self._clear_available = bool(available)
        if self.clear_button is not None:
            self.clear_button.setEnabled(self._clear_available)

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

    @staticmethod
    def _find_profile(
        combo: QComboBox,
        fingerprint: str,
    ) -> int:
        for index in range(combo.count()):
            identity = combo.itemData(index)
            if (
                identity is not None
                and identity.fingerprint == fingerprint
            ):
                return index
        return -1

    @staticmethod
    def _profile_label(identity: ApplicationIdentity) -> str:
        version = identity.executable_version.strip() or "Version unavailable"
        if (
            version != "Version unavailable"
            and not version.casefold().startswith("v")
        ):
            version = f"v{version}"
        return " · ".join(
            (
                version,
                identity.window_state.title(),
                f"{identity.dpi} DPI",
                identity.theme.title(),
                f"{identity.caption_side.title()} captions",
                identity.window_class,
            )
        )

    def _set_profile_path(self, identity: Optional[ApplicationIdentity]) -> None:
        path = identity.executable_path if identity is not None else ""
        self.profile_selector.setToolTip(path)
        self.profile_path_label.setText(
            f"Executable: {path}" if path else ""
        )

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
                profile_index = self._find_profile(
                    self.profile_selector,
                    self._selected_asset.identity.fingerprint,
                )
                self.profile_selector.setCurrentIndex(profile_index)
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

    def refresh_applications(
        self,
        *,
        prompt: bool = True,
        applications: Optional[list[TrackedApplication]] = None,
    ) -> None:
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
            if applications is None:
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
            self._assets_for_application = []
            self._set_empty_tracking_controls()
            self._clear_editor("No tracked application JPEGs are available.")
            return
        self._load_application(asset_key)

    def _refresh_tracked_applications(self) -> None:
        if self._refresh_in_progress or not self._confirm_transition():
            return
        if self._refresh_provider is None:
            self.refresh_applications(prompt=False)
            self.status_label.setText("Tracked applications refreshed.")
            return
        self._refresh_in_progress = True
        self.refresh_button.setEnabled(False)
        self.status_label.setText("Scanning open applications…")
        try:
            started = self._refresh_provider(self._tracked_refresh_completed)
        except Exception as error:
            self._tracked_refresh_completed(
                0,
                [],
                0,
                f"Could not scan open applications: {error}",
            )
            return
        if not started and self._refresh_in_progress:
            self._tracked_refresh_completed(
                0,
                [],
                0,
                "A tracked application refresh is already in progress.",
            )

    def _tracked_refresh_completed(
        self,
        scanned_count: int,
        applications: list[TrackedApplication],
        tracked_count: int,
        error: str,
    ) -> None:
        self._refresh_in_progress = False
        self.refresh_button.setEnabled(True)
        if error:
            self.status_label.setText(error)
            return
        self.refresh_applications(prompt=False, applications=applications)
        self.set_clear_available(True)
        if scanned_count:
            self.status_label.setText(
                f"Scanned {scanned_count} open application(s); "
                f"{len(applications)} application(s) shown, "
                f"{tracked_count} with tracked JPEGs."
            )
        else:
            self.status_label.setText(
                "No eligible open applications were found."
            )

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
        self._assets_for_application = assets
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
            self.profile_selector.setEnabled(True)
            self.action_selector.setEnabled(True)
            self.variant_selector.setEnabled(True)
            self.profile_selector.clear()
            profiles = {
                asset.identity.fingerprint: asset.identity
                for asset in assets
            }
            for identity in sorted(
                profiles.values(),
                key=lambda item: (
                    item.executable_version,
                    item.executable_path.casefold(),
                    0 if item.window_state == "normal" else 1,
                    item.window_state,
                    item.dpi,
                    item.theme,
                    item.caption_side,
                    item.window_class,
                ),
            ):
                self.profile_selector.addItem(
                    self._profile_label(identity),
                    identity,
                )
            preferred_profile = (
                preferred_asset.identity.fingerprint
                if preferred_asset is not None
                else None
            )
            profile_index = self._find_profile(
                self.profile_selector,
                preferred_profile,
            ) if preferred_profile is not None else -1
            self.profile_selector.setCurrentIndex(
                profile_index if profile_index >= 0 else (0 if profiles else -1)
            )
        finally:
            self._updating = False
        if not assets:
            self._set_empty_tracking_controls()
            self._clear_editor(
                "No tracked JPEGs yet. Use Hover Window Controls on this "
                "application, then Refresh."
                if application.manifest_path is None
                else "This application has no available tracked JPEGs."
            )
            return
        self._load_profile(preferred_asset_key)

    def _set_empty_tracking_controls(self) -> None:
        self._updating = True
        try:
            self.profile_selector.clear()
            self.action_selector.clear()
            self.variant_selector.clear()
            self.profile_selector.setEnabled(False)
            self.action_selector.setEnabled(False)
            self.variant_selector.setEnabled(False)
            self._set_profile_path(None)
        finally:
            self._updating = False

    def _profile_changed(self, _index: int) -> None:
        if self._updating:
            return
        if not self._confirm_transition():
            self._restore_selection()
            return
        self._load_profile(None)

    def _load_profile(self, preferred_asset_key) -> None:
        identity = self.profile_selector.currentData()
        self._set_profile_path(identity)
        profile_assets = [
            asset
            for asset in self._assets_for_application
            if identity is not None
            and asset.identity.fingerprint == identity.fingerprint
        ]
        self._assets_by_action = {
            action: [
                asset for asset in profile_assets if asset.action is action
            ]
            for action in _ACTION_ORDER
        }
        preferred_asset = next(
            (
                asset
                for asset in profile_assets
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
        if not profile_assets:
            self._clear_editor("Select a build and window profile.")
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

"""Reusable widgets for the frameless application window chrome."""

from resurface.ui import styles
from resurface.ui.tooltips import tooltip_text
from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionComboBox,
    QStylePainter,
    QToolButton,
    QWidget,
)


class CenteredTitleComboBox(QComboBox):
    """Combo box with a centered, accented closed-state title."""

    def paintEvent(self, _event):
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = ""
        option.currentIcon = option.currentIcon.__class__()
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)

        text_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        painter.setPen(styles.power_action_title_color())
        font = self.font()
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignCenter,
            self.currentText(),
        )


class SeverityComboItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        background = index.data(Qt.ItemDataRole.BackgroundRole)
        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        bg_color = background.color() if hasattr(background, "color") else (
            background if isinstance(background, QColor) else None
        )
        fg_color = foreground.color() if hasattr(foreground, "color") else (
            foreground if isinstance(foreground, QColor) else styles.theme_text_color()
        )
        painter.save()
        if bg_color is not None:
            fill_color = bg_color.lighter(112) if option.state & QStyle.StateFlag.State_Selected else bg_color
            painter.fillRect(option.rect, fill_color)
        painter.setPen(fg_color)
        font = option.font
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(
            option.rect.adjusted(10, 0, -8, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            index.data(Qt.ItemDataRole.DisplayRole) or "",
        )
        painter.restore()


class RecycleBinActionsItemDelegate(QStyledItemDelegate):
    """Paint enabled, destructive Recycle Bin actions with an unambiguous red."""

    _DESTRUCTIVE_ACTIONS = frozenset({"Run Auto-Clean Now", "Empty Recycle Bin"})
    _OPEN_ACTION = "Open Recycle Bin"

    def __init__(self, combo: QComboBox):
        super().__init__(combo.view())
        self._combo = combo

    def paint(self, painter, option, index):
        label = index.data(Qt.ItemDataRole.DisplayRole) or ""
        is_enabled = bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
        if label == self._OPEN_ACTION:
            background = styles.power_action_color("blue")
        elif (
            self._combo.property("recycleBinAutoCleanEnabled")
            and is_enabled
            and label in self._DESTRUCTIVE_ACTIONS
        ):
            background = styles.power_action_color("red")
        else:
            return super().paint(painter, option, index)

        is_hovered = self._combo.property("recycleBinHoveredRow") == index.row()
        if is_hovered or option.state & (
            QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver
        ):
            background = background.lighter(112)
        painter.save()
        painter.fillRect(option.rect, background)
        painter.setPen(styles.dropdown_text_color())
        font = option.font
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(
            option.rect.adjusted(10, 0, -8, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            label,
        )
        painter.restore()


class RecycleBinPopupHoverTracker(QObject):
    """Request a repaint when the Recycle Bin popup hover row changes."""

    def __init__(self, combo: QComboBox):
        super().__init__(combo.view())
        self._combo = combo
        self._view = combo.view()
        self._hovered_row = -1
        self._view.setMouseTracking(True)
        self._view.viewport().setMouseTracking(True)
        self._view.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self._view.viewport():
            if event.type() == QEvent.Type.MouseMove:
                index = self._view.indexAt(event.position().toPoint())
                self._set_hovered_row(index.row() if index.isValid() else -1)
            elif event.type() == QEvent.Type.Leave:
                self._set_hovered_row(-1)
        return super().eventFilter(watched, event)

    def _set_hovered_row(self, row: int) -> None:
        if row == self._hovered_row:
            return
        self._repaint_row(self._hovered_row)
        self._hovered_row = row
        self._combo.setProperty("recycleBinHoveredRow", row)
        self._repaint_row(row)

    def _repaint_row(self, row: int) -> None:
        if row < 0:
            return
        rect = self._view.visualRect(self._combo.model().index(row, 0))
        if rect.isValid():
            self._view.viewport().update(rect)


class TitleBarDragRegion(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._drag_offset = None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        window_handle = self._window.windowHandle()
        self._drag_offset = None if window_handle is not None and window_handle.startSystemMove() else (
            event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
        )
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class WindowChrome:
    """Build and maintain the custom title bar for an application window."""

    def __init__(self, app):
        self.app = app

    def build(self) -> None:
        app = self.app
        title_bar = QFrame(app.root_container)
        title_bar.setObjectName("WindowTitleBar")
        title_bar.setFixedHeight(app.TITLE_BAR_HEIGHT)
        drag_region = TitleBarDragRegion(app)
        drag_region.setParent(title_bar)
        title = QLabel("Windows Resurface", title_bar)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        minimize_btn = QToolButton(title_bar)
        minimize_btn.setProperty("titleBarMinimizeButton", True)
        minimize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        minimize_btn.setIconSize(QSize(16, 16))
        minimize_btn.setFixedSize(42, app.TITLE_TEXT_ROW_HEIGHT)
        minimize_btn.clicked.connect(app.showMinimized)
        close_btn = QToolButton(title_bar)
        close_btn.setProperty("titleBarCloseButton", True)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setIconSize(QSize(16, 16))
        close_btn.setFixedSize(42, app.TITLE_TEXT_ROW_HEIGHT)
        close_btn.clicked.connect(app.close)
        app.window_title_bar = title_bar
        app.window_drag_region = drag_region
        app.window_title_label = title
        app.window_minimize_btn = minimize_btn
        app.window_close_btn = close_btn
        app.register_tooltip(minimize_btn, tooltip_text("window_minimize"))
        app.register_tooltip(close_btn, tooltip_text("window_close"))
        self.apply_theme()
        self.position_controls()

    def position_controls(self) -> None:
        app = self.app
        if not hasattr(app, "window_title_label"):
            return
        title_control_width = app.window_minimize_btn.width() + app.window_close_btn.width()
        app.window_drag_region.setGeometry(0, 0, max(0, app.width() - title_control_width), app.TITLE_TEXT_ROW_HEIGHT)
        app.window_title_label.setGeometry(app.SIDEBAR_WIDTH, app.TITLE_TEXT_TOP_PADDING, max(0, app.width() - app.SIDEBAR_WIDTH), app.TITLE_TEXT_ROW_HEIGHT - app.TITLE_TEXT_TOP_PADDING)
        close_x = app.width() - app.window_close_btn.width()
        app.window_minimize_btn.move(close_x - app.window_minimize_btn.width(), 0)
        app.window_close_btn.move(close_x, 0)
        app.window_drag_region.lower()
        app.window_title_label.raise_()
        app.window_minimize_btn.raise_()
        app.window_close_btn.raise_()

    def apply_theme(self) -> None:
        app = self.app
        app.window_title_bar.setStyleSheet("QFrame#WindowTitleBar " f"{{ background-color: {styles.qcolor_css(styles.WINDOW_BG)}; }}")
        app.window_title_label.setStyleSheet(
            styles.label_style(font_size=25, color=styles.TEXT_LIGHT)
        )
        app.window_minimize_btn.setStyleSheet(styles.title_bar_control_style())
        app.window_minimize_btn.setIcon(app._title_bar_icon("minimize"))
        app.window_close_btn.setStyleSheet(styles.title_bar_control_style(close_button=True))
        app.window_close_btn.setIcon(app._title_bar_icon("close"))

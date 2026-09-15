import ctypes

from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from folder_creator.core.app_service import AppService
from folder_creator.ui import styles
from folder_creator.ui.nested_ui_controller import NestedUIController
from folder_creator.ui.output_options_panel import OutputOptionsPanel
from folder_creator.ui.post_build_panel import PostBuildPanel
from folder_creator.ui.smart_tree_widget import SmartTreeWidget
from folder_creator.ui.status_controller import StatusController
from folder_creator.ui.template_panel import TemplatePanel
from folder_creator.ui.tree_editor_panel import TreeEditorPanel
from folder_creator.ui.ui_state_controller import UIStateController


MAX_NESTED_FOLDER_NAME_LENGTH = 64
WINDOWS_RESURFACE_EXPANDED_WIDTH = 985
WINDOWS_RESURFACE_HEIGHT = 875


class TitleBarDragRegion(QWidget):
    """Provide native-feeling window dragging for the frameless title bar."""

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._drag_offset = None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        window_handle = self._window.windowHandle()
        self._drag_offset = (
            None
            if window_handle is not None and window_handle.startSystemMove()
            else event.globalPosition().toPoint()
            - self._window.frameGeometry().topLeft()
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


class MainWindow(QMainWindow):
    """Compose Folder Creator panels, controllers, state, and lifecycle behavior."""

    TITLE_BAR_HEIGHT = 50
    TITLE_TEXT_ROW_HEIGHT = 40
    TITLE_TEXT_TOP_PADDING = 10
    TITLE_CONTROL_WIDTH = 42

    def __init__(self):
        super().__init__()
        self.tree = SmartTreeWidget()
        self.service = AppService(self.tree)
        self._theme_dark = bool(self.service.state.get("theme_dark", True))
        self._shared_state_path = self.service.state_manager.get_config_path()
        self._shared_state_mtime_ns = None
        styles.set_theme(self._theme_dark)
        self.status = StatusController(self, self.service)

        self.window_width = WINDOWS_RESURFACE_EXPANDED_WIDTH
        self.window_height = WINDOWS_RESURFACE_HEIGHT
        self.tree_default_height = 360
        self.tree_expanded_height = 485
        self.tree_width = 925
        self.tree_frame_padding = 2
        self.setWindowTitle("Folder Generator")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setFixedSize(self.window_width, self.window_height)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)

        metrics = {
            "outer_margin": 8,
            "section_gap": 8,
            "frame_padding": 6,
            "control_gap": 8,
            "tight_gap": 4,
            "top_frame_inset": 1,
            "controls_to_tree_gap": 2,
            "tree_to_controls_gap": 2,
            "find_input_width": 230,
            "expand_width": 120,
            "collapse_width": 160,
            "sort_width": 110,
            "find_width": 80,
        }
        self._create_panels(metrics)
        self._compose_window(metrics)

        self.ui_state = UIStateController(self)
        self.nested_ui = NestedUIController(self)
        self.nested_ui.connect_signals()
        self._restore_ui_state()
        self._start_theme_sync()

    def _create_panels(self, metrics):
        frame_padding = metrics["frame_padding"]
        control_gap = metrics["control_gap"]
        tight_gap = metrics["tight_gap"]

        self.template_panel = TemplatePanel(frame_padding, control_gap, tight_gap)
        self.tree_editor_panel = TreeEditorPanel(
            self.tree,
            frame_padding,
            control_gap,
            self.tree_width,
            self.tree_default_height,
            self.tree_frame_padding,
            metrics["expand_width"],
            metrics["collapse_width"],
            metrics["sort_width"],
            metrics["find_width"],
            metrics["find_input_width"],
        )
        self.output_options_panel = OutputOptionsPanel(
            frame_padding, control_gap, tight_gap
        )
        self.post_build_panel = PostBuildPanel(frame_padding, control_gap)
        for panel in (
            self.template_panel,
            self.tree_editor_panel,
            self.output_options_panel,
            self.post_build_panel,
        ):
            panel.bind_to(self)

    def _compose_window(self, metrics):
        outer_margin = metrics["outer_margin"]
        section_gap = metrics["section_gap"]
        frame_padding = metrics["frame_padding"]
        control_gap = metrics["control_gap"]

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self._create_title_bar()
        root_layout.addWidget(self.window_title_bar)

        content_widget = QWidget()
        root_layout.addWidget(content_widget)
        main_layout = QVBoxLayout(content_widget)
        main_layout.setAlignment(Qt.AlignTop)
        main_layout.setContentsMargins(
            outer_margin, outer_margin, outer_margin, outer_margin
        )
        main_layout.setSpacing(section_gap)

        content_height = (
            self.window_height
            - self.TITLE_BAR_HEIGHT
            - (outer_margin * 2)
        )
        self.smart_folder_creator_frame = QFrame()
        self.smart_folder_creator_frame.setFrameShape(QFrame.NoFrame)
        self.smart_folder_creator_frame.setStyleSheet("border: none;")
        self.smart_folder_creator_frame.setFixedSize(
            self.window_width - 25, content_height
        )
        self.smart_layout = QVBoxLayout(self.smart_folder_creator_frame)
        self.smart_layout.setSpacing(0)
        self.smart_layout.setContentsMargins(
            frame_padding,
            metrics["top_frame_inset"],
            frame_padding,
            frame_padding,
        )

        controls_layout = QGridLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setHorizontalSpacing(section_gap)
        controls_layout.setVerticalSpacing(section_gap)
        controls_layout.setSizeConstraint(QLayout.SetFixedSize)
        top_frames = (
            self.folder_buttons_frame,
            self.date_controls_frame,
            self.post_build_frame,
            self.template_controls_frame,
            self.build_buttons_frame,
        )
        for column, frame in enumerate(top_frames):
            controls_layout.addWidget(frame, 0, column)
            controls_layout.setColumnStretch(column, 1)
        self.smart_layout.addLayout(controls_layout)
        self.smart_layout.addSpacing(metrics["controls_to_tree_gap"])
        self.smart_layout.addWidget(self.tree_frame, alignment=Qt.AlignHCenter)
        self.smart_layout.addSpacing(metrics["tree_to_controls_gap"])
        self.smart_layout.addLayout(self.tree_controls_layout)
        self.smart_layout.addSpacing(section_gap)

        self.bottom_info_frame = QFrame()
        self.bottom_info_frame.setFrameShape(QFrame.NoFrame)
        self.bottom_info_frame.setFixedWidth(self.smart_folder_creator_frame.width())
        self.bottom_info_frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.bottom_info_frame.setStyleSheet("border: none;")
        bottom_layout = QVBoxLayout(self.bottom_info_frame)
        bottom_layout.setContentsMargins(
            frame_padding, frame_padding, frame_padding, frame_padding
        )
        bottom_layout.setSpacing(section_gap)
        bottom_layout.addLayout(self._create_paths_layout(metrics))
        self._create_status_frame(frame_padding, control_gap)
        bottom_layout.addWidget(self.smart_status_frame, alignment=Qt.AlignLeft)
        self.smart_layout.addWidget(self.bottom_info_frame, alignment=Qt.AlignLeft)
        main_layout.addWidget(self.smart_folder_creator_frame, alignment=Qt.AlignHCenter)

    def _create_title_bar(self):
        self.window_title_bar = QFrame()
        self.window_title_bar.setObjectName("FolderCreatorTitleBar")
        self.window_title_bar.setFixedHeight(self.TITLE_BAR_HEIGHT)
        self.window_drag_region = TitleBarDragRegion(self)
        self.window_drag_region.setParent(self.window_title_bar)

        self.title_label = QLabel("Nested Folder Creator", self.window_title_bar)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.window_minimize_btn = QToolButton(self.window_title_bar)
        self.window_minimize_btn.setProperty("titleBarMinimizeButton", True)
        self.window_minimize_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self.window_minimize_btn.setIconSize(QSize(16, 16))
        self.window_minimize_btn.setFixedSize(
            self.TITLE_CONTROL_WIDTH, self.TITLE_TEXT_ROW_HEIGHT
        )
        self.window_minimize_btn.clicked.connect(self.showMinimized)
        self.window_close_btn = QToolButton(self.window_title_bar)
        self.window_close_btn.setProperty("titleBarCloseButton", True)
        self.window_close_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self.window_close_btn.setIconSize(QSize(16, 16))
        self.window_close_btn.setFixedSize(
            self.TITLE_CONTROL_WIDTH, self.TITLE_TEXT_ROW_HEIGHT
        )
        self.window_close_btn.clicked.connect(self.close)
        self._position_title_bar_controls()

    def _position_title_bar_controls(self):
        title_control_width = (
            self.window_minimize_btn.width() + self.window_close_btn.width()
        )
        self.window_drag_region.setGeometry(
            0,
            0,
            max(0, self.width() - title_control_width),
            self.TITLE_TEXT_ROW_HEIGHT,
        )
        self.title_label.setGeometry(
            0,
            self.TITLE_TEXT_TOP_PADDING,
            self.width(),
            self.TITLE_TEXT_ROW_HEIGHT - self.TITLE_TEXT_TOP_PADDING,
        )
        close_x = self.width() - self.window_close_btn.width()
        self.window_minimize_btn.move(close_x - self.window_minimize_btn.width(), 0)
        self.window_close_btn.move(close_x, 0)
        self.window_drag_region.lower()
        self.title_label.raise_()
        self.window_minimize_btn.raise_()
        self.window_close_btn.raise_()

    def _title_bar_icon(self, action: str) -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(styles.theme_text_color(), 2))
        if action == "minimize":
            painter.drawLine(3, 11, 13, 11)
        else:
            painter.drawLine(4, 4, 12, 12)
            painter.drawLine(12, 4, 4, 12)
        painter.end()
        return QIcon(pixmap)

    def _create_paths_layout(self, metrics):
        paths_layout = QGridLayout()
        paths_layout.setContentsMargins(0, metrics["frame_padding"], 0, metrics["frame_padding"])
        paths_layout.setHorizontalSpacing(0)
        paths_layout.setVerticalSpacing(metrics["tight_gap"])
        paths_layout.setColumnMinimumWidth(0, metrics["expand_width"])
        paths_layout.setColumnMinimumWidth(1, metrics["control_gap"])
        paths_layout.setColumnMinimumWidth(2, metrics["collapse_width"])
        paths_layout.setColumnStretch(3, 1)
        paths_layout.setColumnMinimumWidth(4, metrics["sort_width"])
        paths_layout.setColumnMinimumWidth(5, metrics["control_gap"])
        paths_layout.setColumnMinimumWidth(6, metrics["find_width"])
        paths_layout.setColumnMinimumWidth(7, metrics["control_gap"])
        paths_layout.setColumnMinimumWidth(8, metrics["find_input_width"])
        paths_layout.addWidget(
            self.template_path_column, 0, 0, 1, 3, alignment=Qt.AlignLeft
        )
        paths_layout.addWidget(
            self.base_path_column, 0, 4, 1, 1, alignment=Qt.AlignLeft
        )
        return paths_layout

    def _create_status_frame(self, frame_padding, control_gap):
        self.smart_status_frame = QFrame()
        self.smart_status_frame.setObjectName("statusFrame")
        self.smart_status_frame.setFrameShape(QFrame.NoFrame)
        self.smart_status_frame.setFixedHeight(50)
        self.smart_status_frame.setFixedWidth(
            self.bottom_info_frame.width() - (frame_padding * 2)
        )
        self.smart_status_frame.setStyleSheet("border: none;")
        layout = QHBoxLayout(self.smart_status_frame)
        layout.setContentsMargins(
            frame_padding, frame_padding, frame_padding, frame_padding
        )
        layout.setSpacing(control_gap)
        self.smart_status_icon = QLabel(">")
        self.smart_status_text = QLabel("")
        self.smart_status_text.setMaximumWidth(700)
        layout.addWidget(self.smart_status_icon)
        layout.addWidget(self.smart_status_text)
        layout.addStretch()
        self.smart_status_frame.hide()

    def _restore_ui_state(self):
        state = self.service.state
        styles.apply_app_theme(QApplication.instance())
        self.smart_status_icon.setStyleSheet(styles.status_label_style())
        self.smart_status_text.setStyleSheet(styles.status_label_style())
        self.restore_timestamp_state(
            self.nested_date_toggle,
            self.nested_date_config,
            "nested_date_stamp_enabled",
            "nested_date_stamp_mode",
        )
        user_dir = self.service.template_paths.user_dir
        self.template_path_line.setText(
            str(user_dir) if user_dir is not None else "Master Backup Path unavailable"
        )
        self.base_path_line.setText(state.get("last_base_dir", ""))
        self.auto_enumerate_folders.setChecked(
            state.get("nested_auto_number_enabled", False)
        )
        self.open_folder_build_toggle.setChecked(
            state.get("open_folder_after_build", False)
        )
        self.minimize_after_build_toggle.setChecked(
            state.get("minimize_after_build", False)
        )
        self.close_app_after_build_toggle.setChecked(
            state.get("close_after_build", False)
        )
        self.close_app_after_build_toggle.setEnabled(
            not self.minimize_after_build_toggle.isChecked()
        )
        self.minimize_after_build_toggle.setEnabled(
            not self.close_app_after_build_toggle.isChecked()
        )

        self.nested_ui.template_controller.refresh_user_templates_dropdown()
        self.update_expand_button_text()
        self.ui_state.update_build_button_state()
        self.ui_state.update_nested_build_state()
        styles.apply_standard_button_styles(self)
        for toggle in (
            self.open_folder_build_toggle,
            self.minimize_after_build_toggle,
            self.close_app_after_build_toggle,
        ):
            toggle.setStyleSheet(styles.organizing_button_style(font_size=11))
        self.apply_theme(self._theme_dark)

    def _start_theme_sync(self):
        self._shared_state_mtime_ns = self._get_shared_state_mtime_ns()
        self._shared_state_watch_timer = QTimer(self)
        self._shared_state_watch_timer.timeout.connect(
            self._sync_theme_from_shared_state
        )
        self._shared_state_watch_timer.start(500)

    def _get_shared_state_mtime_ns(self):
        try:
            return self._shared_state_path.stat().st_mtime_ns
        except OSError:
            return None

    def _sync_theme_from_shared_state(self):
        current_mtime_ns = self._get_shared_state_mtime_ns()
        if current_mtime_ns == self._shared_state_mtime_ns:
            return
        self._shared_state_mtime_ns = current_mtime_ns
        state = self.service.state_manager.load_state()
        self.service.state = state
        theme_dark = bool(state.get("theme_dark", True))
        if theme_dark != self._theme_dark:
            self.apply_theme(theme_dark)

    def apply_theme(self, is_dark: bool):
        self._theme_dark = bool(is_dark)
        styles.set_theme(self._theme_dark)
        styles.apply_app_theme(QApplication.instance())
        self.title_label.setStyleSheet(styles.title_label_style())
        self.window_title_bar.setStyleSheet(
            "QFrame#FolderCreatorTitleBar "
            f"{{ background-color: {styles.qcolor_css(styles.WINDOW_BG)}; }}"
        )
        self.window_minimize_btn.setStyleSheet(styles.title_bar_control_style())
        self.window_minimize_btn.setIcon(self._title_bar_icon("minimize"))
        self.window_close_btn.setStyleSheet(
            styles.title_bar_control_style(close_button=True)
        )
        self.window_close_btn.setIcon(self._title_bar_icon("close"))
        self.tree_frame.setStyleSheet(styles.tree_outer_frame_style())
        self.tree.setStyleSheet(styles.surfaced_tree_widget_style())
        self.find_output_line.setStyleSheet(
            styles.frameless_surfaced_line_edit_style(15)
        )
        self.smart_status_icon.setStyleSheet(styles.status_label_style())
        self.smart_status_text.setStyleSheet(styles.status_label_style())
        for label in self.findChildren(QLabel):
            if label.property("surfaceLabelStyle"):
                font_size = styles.resurface_styles.coerce_font_size(
                    label.property("styleFontSize"), 14
                ) or 14
                label.setStyleSheet(styles.surfaced_label_style(font_size))
            elif label.property("plainThemeLabelStyle"):
                label.setStyleSheet(styles.plain_theme_label_style(15))
        for combo in self.findChildren(QComboBox):
            font_size = styles.resurface_styles.coerce_font_size(
                combo.property("styleFontSize"), 14
            ) or 14
            combo.setStyleSheet(styles.organizing_combo_style(font_size))
        for button in self.findChildren(QPushButton):
            font_size = styles.resurface_styles.coerce_font_size(
                button.property("styleFontSize"), 14
            ) or 14
            button.setStyleSheet(styles.organizing_button_style(font_size))

    def _apply_native_window_corner_preference(self):
        """Request the standard Windows 11 rounding for this native window."""
        hwnd = int(self.winId())
        if not hwnd:
            return

        try:
            corner_preference = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                33,  # DWMWA_WINDOW_CORNER_PREFERENCE
                ctypes.byref(corner_preference),
                ctypes.sizeof(corner_preference),
            )
        except Exception:
            return

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_native_window_corner_preference()

    def resizeEvent(self, event):
        self._position_title_bar_controls()
        super().resizeEvent(event)

    def update_build_button_state(self):
        self.ui_state.update_build_button_state()

    def update_nested_build_state(self):
        self.ui_state.update_nested_build_state()

    def enforce_tree_name_limit(self, item, _column):
        name = item.text(0)
        if len(name) > MAX_NESTED_FOLDER_NAME_LENGTH:
            item.setText(0, name[:MAX_NESTED_FOLDER_NAME_LENGTH])
            self.status.set(
                f"Folder names limited to {MAX_NESTED_FOLDER_NAME_LENGTH} characters.",
                target="nested",
                status_type="error",
                dedupe_key="folder_name_limit_enforced",
            )

    def restore_timestamp_state(self, toggle, combo, enabled_key, mode_key):
        enabled = self.service.state.get(enabled_key, False)
        toggle.setChecked(enabled)
        combo.setEnabled(enabled)
        mode = self.service.state.get(mode_key, "ISO")
        combo.setCurrentIndex({"ISO": 0, "UK": 1, "US": 2}.get(mode, 0))

    def toggle_tree_expand(self):
        if self.ui_state.tree_has_collapsed_nodes():
            self.tree.expandAll()
        else:
            self.tree.collapseAll()
        self.update_expand_button_text()

    def _set_tree_frame_height(self, tree_height):
        self.tree_frame.setFixedHeight(tree_height + (self.tree_frame_padding * 2))

    def tree_gui_stretch(self):
        is_visible = self.bottom_info_frame.isVisible()
        if is_visible:
            self.bottom_info_frame.hide()
            self.tree.setFixedHeight(self.tree_expanded_height)
            self._set_tree_frame_height(self.tree_expanded_height)
            self.expand_tree_btn.setText("COLLAPSE 🌳")
        else:
            self.bottom_info_frame.show()
            self.tree.setFixedHeight(self.tree_default_height)
            self._set_tree_frame_height(self.tree_default_height)
            self.expand_tree_btn.setText("EXPAND 🌳")
        QTimer.singleShot(0, self.ui_state.update_build_button_state)
        self.tree.setVisible(True)

    def update_expand_button_text(self):
        if self.ui_state.tree_has_collapsed_nodes():
            self.expand_folders_collapse_btn.setText("EXPAND FOLDERS")
        else:
            self.expand_folders_collapse_btn.setText("COLLAPSE FOLDERS")

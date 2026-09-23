import ctypes

from PySide6.QtCore import QRectF, QSize, QTimer, Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from folder_creator.core.app_service import AppService
from folder_creator.core.system_paths import get_desktop_path
from folder_creator.core.windows_resurface_window import focus_windows_resurface
from folder_creator.ui import styles
from folder_creator.ui.nested_ui_controller import NestedUIController
from folder_creator.ui.output_options_panel import OutputOptionsPanel
from folder_creator.ui.post_build_panel import PostBuildPanel
from folder_creator.ui.smart_tree_widget import SmartTreeWidget
from folder_creator.ui.status_controller import StatusController
from folder_creator.ui.template_panel import TemplatePanel
from folder_creator.ui.tree_editor_panel import TreeEditorPanel
from folder_creator.ui.ui_state_controller import UIStateController
from folder_creator.resurface_dependency import ensure_resurface_importable

ensure_resurface_importable()

from resurface.ui.app_notifications import WindowMessageMixin
from resurface.ui.tooltips import (
    install_tooltip_router,
    refresh_visible_tooltip,
    set_tooltip,
)


MAX_NESTED_FOLDER_NAME_LENGTH = 64
WINDOWS_RESURFACE_EXPANDED_WIDTH = 1000
WINDOWS_RESURFACE_HEIGHT = 880


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


class RoundedControlPageBorder(QWidget):
    """Paint the control-page outline above the scroll area viewport."""

    BORDER_WIDTH = 1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(styles.SURFACE_BORDER)
        pen.setWidthF(self.BORDER_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        border_rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = styles.resurface_styles.BUTTON_CORNER_RADIUS
        painter.drawRoundedRect(border_rect, radius, radius)


class RoundedControlPage(QScrollArea):
    """Scrollable control page with an unbroken, theme-aware outer border."""

    BORDER_WIDTH = 1

    def __init__(self):
        super().__init__()
        # Keep the viewport inside the painted outline.  A scroll area's
        # viewport otherwise reaches the widget edge and can cover the
        # anti-aliased pixels at the top-left rounded corner.
        self.setViewportMargins(
            self.BORDER_WIDTH,
            self.BORDER_WIDTH,
            self.BORDER_WIDTH,
            self.BORDER_WIDTH,
        )
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.viewport().setAutoFillBackground(False)
        self._border_overlay = RoundedControlPageBorder(self)
        self._border_overlay.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.setProperty("continuousRoundedBorder", True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._border_overlay.setGeometry(self.rect())
        self._border_overlay.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self._border_overlay.raise_()

    def refresh_rounded_border(self):
        self._border_overlay.update()


class MainWindow(WindowMessageMixin, QMainWindow):
    """Compose Folder Creator panels, controllers, state, and lifecycle behavior."""

    TITLE_BAR_HEIGHT = 50
    TITLE_TEXT_ROW_HEIGHT = 40
    TITLE_TEXT_TOP_PADDING = 10
    TITLE_CONTROL_WIDTH = 42
    CONTROL_FONT_SIZE = 12
    NAVIGATION_WIDTH = 205
    CONTROL_STACK_HEIGHT = 244
    TEMPLATE_CONTROL_STACK_HEIGHT = 250
    CONTROL_STACK_TO_TREE_GAP = 8
    TEMPLATE_STACK_TO_TREE_GAP = 8

    SECTION_DEFINITIONS = (
        ("folders", "Folders", "\ue8b7", "Create and edit folders and files."),
        (
            "date_numbering",
            "Date & Numbering",
            "\ue787",
            "Configure automatic numbering and parent-folder dates.",
        ),
        (
            "after_build",
            "After Build",
            "\ue945",
            "Choose what Folder Creator does after a successful build.",
        ),
        (
            "templates",
            "Templates",
            "\ue8a5",
            "Load, save, and manage reusable folder templates.",
        ),
        (
            "output_build",
            "Output & Build",
            "\ue896",
            "Choose the output location and build the folder structure.",
        ),
    )

    def __init__(self):
        super().__init__()
        self.tree = SmartTreeWidget()
        self.service = AppService(self.tree)
        # WindowMessageMixin reads ``state`` from the window hierarchy for its
        # confirmation-suppression policy. Keep it pointed at the shared state
        # used by Windows Resurface so Folder Creator follows that preference.
        self.state = self.service.state
        self._theme_dark = bool(self.service.state.get("theme_dark", True))
        # Folder Creator follows the same preference as its Windows Resurface
        # host, including when that preference changes while it is open.
        self.tooltips_enabled = bool(self.service.state.get("tooltips_enabled", True))
        self._shared_state_path = self.service.state_manager.get_config_path()
        self._shared_state_mtime_ns = None
        styles.set_theme(self._theme_dark)
        self.status = StatusController(self, self.service)

        self.window_width = WINDOWS_RESURFACE_EXPANDED_WIDTH
        self.window_height = WINDOWS_RESURFACE_HEIGHT
        self.tree_default_height = 475
        self.tree_expanded_height = 725
        self.tree_frame_padding = 2
        self._tree_view_expanded = False
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
            # Keep the editor visually separated from both its top actions and
            # its toolbar, without stealing meaningful space from the tree.
            "controls_to_tree_gap": 8,
            "tree_to_controls_gap": 16,
            "tree_toolbar_bottom_inset": 25,
            "find_input_width": 180,
            "expand_width": 120,
            "collapse_width": 160,
            "sort_width": 110,
            "find_width": 80,
        }
        smart_frame_width = self.window_width - 25
        smart_content_width = smart_frame_width - (metrics["frame_padding"] * 2)
        self.right_pane_width = (
            smart_content_width - self.NAVIGATION_WIDTH - metrics["section_gap"]
        )
        self.tree_width = self.right_pane_width - 6
        self._create_panels(metrics)
        self._compose_window(metrics)
        self._configure_tooltips()
        self._tooltip_router = install_tooltip_router()
        styles.opt_in_light_mode_black_disabled_text(self)

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
        self.smart_layout = QHBoxLayout(self.smart_folder_creator_frame)
        self.smart_layout.setSpacing(section_gap)
        self.smart_layout.setContentsMargins(
            frame_padding,
            metrics["top_frame_inset"],
            frame_padding,
            frame_padding,
        )

        self._create_section_navigation()
        self.smart_layout.addWidget(self.sidebar)

        self.right_pane = QWidget()
        self.right_pane.setObjectName("FolderCreatorRightPane")
        self.right_pane.setFixedWidth(self.right_pane_width)
        right_layout = QVBoxLayout(self.right_pane)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.controls_stack)
        self.controls_to_tree_spacer = QWidget()
        self.controls_to_tree_spacer.setFixedHeight(metrics["controls_to_tree_gap"])
        self._update_control_stack_geometry(self.section_navigation.currentRow())
        right_layout.addWidget(self.controls_to_tree_spacer)
        right_layout.addWidget(self.tree_frame, alignment=Qt.AlignHCenter)
        # Keep a visible, fixed gap between the tree surface and the toolbar
        # in both normal and expanded-tree modes.
        self.tree_toolbar_top_padding = QWidget()
        self.tree_toolbar_top_padding.setObjectName("TreeToolbarTopPadding")
        self.tree_toolbar_top_padding.setFixedHeight(
            metrics["tree_to_controls_gap"]
        )
        self.tree_toolbar_top_padding.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        right_layout.addWidget(self.tree_toolbar_top_padding)
        # Let the tree use the available vertical space above the toolbar while
        # keeping the toolbar fixed near the application edge in either tree
        # view mode.
        right_layout.addStretch()
        right_layout.addLayout(self.tree_controls_layout)
        # The app's outer and frame margins, plus the toolbar layout's own
        # bottom margin, already account for 20 px. Reserve the remaining
        # space so the search field ends exactly 25 px above the window edge.
        toolbar_bottom_spacer_height = max(
            0,
            metrics["tree_toolbar_bottom_inset"]
            - outer_margin
            - frame_padding
            - self.tree_controls_layout.contentsMargins().bottom(),
        )
        self.tree_toolbar_bottom_spacer = QWidget()
        self.tree_toolbar_bottom_spacer.setObjectName("TreeToolbarBottomSpacer")
        self.tree_toolbar_bottom_spacer.setFixedHeight(toolbar_bottom_spacer_height)
        right_layout.addWidget(self.tree_toolbar_bottom_spacer)
        self.smart_layout.addWidget(self.right_pane)
        main_layout.addWidget(self.smart_folder_creator_frame, alignment=Qt.AlignHCenter)

    def _create_section_navigation(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("FolderCreatorSidebar")
        self.sidebar.setFixedWidth(self.NAVIGATION_WIDTH)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(6, 6, 6, 6)
        sidebar_layout.setSpacing(8)

        self.section_navigation = QListWidget()
        self.section_navigation.setObjectName("FolderCreatorNavigationList")
        self.section_navigation.setFixedWidth(self.NAVIGATION_WIDTH - 12)
        self.section_navigation.setIconSize(QSize(22, 22))
        self.section_navigation.setSpacing(2)
        self.section_navigation.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.section_navigation.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.section_navigation.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.section_navigation.setAccessibleName("Folder Creator sections")

        sidebar_layout.addWidget(self.section_navigation)

        self.controls_stack = QStackedWidget()
        self.controls_stack.setObjectName("FolderCreatorControlsStack")
        self.controls_stack.setFixedSize(
            self.right_pane_width, self.CONTROL_STACK_HEIGHT
        )

        pages = (
            self._create_control_page(self.folder_buttons_frame),
            self._create_control_page(self.date_controls_frame),
            self._create_control_page(self.post_build_frame),
            self._create_control_page(
                self.template_controls_frame,
                self.template_path_column,
                vertical_scrollbar_policy=Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            ),
            self._create_control_page(self.build_buttons_frame, self.base_path_column),
        )
        for definition, page in zip(self.SECTION_DEFINITIONS, pages):
            section_id, label, _glyph, description = definition
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, section_id)
            item.setSizeHint(QSize(self.NAVIGATION_WIDTH - 16, 48))
            item.setToolTip(description)
            self.section_navigation.addItem(item)
            self.controls_stack.addWidget(page)

        navigation_height = (len(self.SECTION_DEFINITIONS) * 50) + 16
        self.section_navigation.setFixedHeight(navigation_height)
        sidebar_layout.addStretch()

        self.sidebar_separator = QFrame()
        self.sidebar_separator.setObjectName("FolderCreatorSidebarSeparator")
        self.sidebar_separator.setFrameShape(QFrame.Shape.HLine)
        self.sidebar_separator.setFixedHeight(1)
        sidebar_layout.addWidget(self.sidebar_separator)

        self.return_to_resurface_btn = QPushButton("Windows Resurface")
        self.return_to_resurface_btn.setAccessibleName("Return to Windows Resurface")
        self.return_to_resurface_btn.setProperty("styleFontSize", self.CONTROL_FONT_SIZE)
        self.return_to_resurface_btn.setFixedHeight(40)
        styles.apply_fluent_icon(self.return_to_resurface_btn, "\ue72b")
        self.return_to_resurface_btn.clicked.connect(self._return_to_windows_resurface)
        sidebar_layout.addWidget(self.return_to_resurface_btn)

        self._refresh_section_navigation_icons()
        self.section_navigation.currentRowChanged.connect(
            self._on_section_changed
        )
        self.section_navigation.itemClicked.connect(self._on_section_clicked)
        self.section_navigation.setCurrentRow(0)

    def _return_to_windows_resurface(self):
        """Restore the host application before hiding this companion window."""
        if focus_windows_resurface():
            self.showMinimized()
            return
        self.status.show_action_result(
            "Windows Resurface is not currently open.", status_type="error"
        )

    def _create_control_page(
        self,
        *widgets,
        vertical_scrollbar_policy=Qt.ScrollBarPolicy.ScrollBarAsNeeded,
    ):
        page = RoundedControlPage()
        page.setObjectName("FolderCreatorControlPage")
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page.setVerticalScrollBarPolicy(vertical_scrollbar_policy)

        content = QWidget()
        content.setObjectName("FolderCreatorControlPageContent")
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        content.setMinimumHeight(max(widget.height() for widget in widgets))
        layout = QHBoxLayout(content)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        for widget in widgets:
            layout.addWidget(widget, alignment=Qt.AlignTop | Qt.AlignLeft)
        page.setWidget(content)
        return page

    def _on_section_changed(self, row):
        if row < 0 or row >= self.controls_stack.count():
            return
        self.controls_stack.setCurrentIndex(row)
        self._update_control_stack_geometry(row)
        if self._tree_view_expanded:
            self._set_tree_view_expanded(False)

    def _update_control_stack_geometry(self, row):
        """Keep each tab's action frame at its established distance from the tree."""
        is_templates_tab = row == 3
        self.controls_stack.setFixedHeight(
            self.TEMPLATE_CONTROL_STACK_HEIGHT
            if is_templates_tab
            else self.CONTROL_STACK_HEIGHT
        )
        if hasattr(self, "controls_to_tree_spacer"):
            self.controls_to_tree_spacer.setFixedHeight(
                self.TEMPLATE_STACK_TO_TREE_GAP
                if is_templates_tab
                else self.CONTROL_STACK_TO_TREE_GAP
            )

    def _on_section_clicked(self, item):
        """Restore a hidden current page when its selected item is clicked."""
        if self._tree_view_expanded:
            self._on_section_changed(self.section_navigation.row(item))

    def _refresh_section_navigation_icons(self):
        for row, (_section_id, _label, glyph, _description) in enumerate(
            self.SECTION_DEFINITIONS
        ):
            item = self.section_navigation.item(row)
            if item is not None:
                item.setIcon(styles.create_navigation_icon(glyph))

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

    def _configure_tooltips(self):
        """Give Folder Creator controls the shared rounded, themed tooltips."""
        tooltips = {
            self.window_minimize_btn: "Minimize Nested Folder Creator.",
            self.window_close_btn: "Close Nested Folder Creator.",
            self.return_to_resurface_btn: "Return to the Windows Resurface main window.",
            self.add_folder_btn: "Add a top-level folder to the structure.",
            self.add_subfolder_btn: "Add a subfolder beneath the selected folder.",
            self.remove_btn: "Remove the selected folder and its contents from the structure.",
            self.remove_all_btn: "Remove every folder from the current structure.",
            self.file_dropdown: "Add a blank file of the selected type to the selected folder.",
            self.expand_tree_btn: "Expand the editing area and hide the output details.",
            self.expand_folders_collapse_btn: "Expand or collapse every folder in the structure.",
            self.sort_btn: "Sort folders alphabetically at every level.",
            self.find_btn: "Find folders matching the text entered beside this button.",
            self.load_template_btn: "Load a saved folder-structure template from a file.",
            self.save_template_btn: "Save the current folder structure as a reusable template.",
            self.delete_template_btn: "Delete the selected user template.",
            self.delete_all_templates_btn: "Permanently delete every saved user template.",
            self.load_user_template_dropdown: "Choose one of your saved folder-structure templates.",
            self.load_default_template_dropdown: "Choose one of the included folder-structure templates.",
            self.auto_enumerate_folders: "Add a number to duplicate folder and subfolder names created with the Add controls.",
            self.nested_date_toggle: "Add the selected date format to parent folder names when building.",
            self.nested_date_config: "Choose the date format used for parent folder names.",
            self.default_to_desktop_btn: "Set the output location to your Desktop.",
            self.output_location_btn: "Choose where the completed folder structure will be created.",
            self.build_folders_btn: "Create the folder structure in the selected output location.",
            self.open_folder_build_toggle: "Open the output folder after the structure is created.",
            self.minimize_after_build_toggle: "Minimize Folder Creator after the structure is created.",
            self.close_app_after_build_toggle: "Close Folder Creator after the structure is created.",
        }
        for widget, text in tooltips.items():
            set_tooltip(widget, text)

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

    def _restore_ui_state(self):
        state = self.service.state
        styles.apply_app_theme(QApplication.instance())
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
        # A first-time build should have a useful, easy-to-find destination.
        # Keep any location the user has explicitly chosen on later launches.
        saved_base_dir = str(state.get("last_base_dir") or "").strip()
        self.base_path_line.setText(
            saved_base_dir or str(get_desktop_path())
        )
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
        self._configure_control_font_sizes()
        styles.apply_standard_button_styles(self)
        self.apply_theme(self._theme_dark)

    def _configure_control_font_sizes(self) -> None:
        """Keep the primary controls at one explicit, theme-stable size."""
        top_control_buttons = (
            self.add_folder_btn,
            self.add_subfolder_btn,
            self.remove_btn,
            self.remove_all_btn,
            self.auto_enumerate_folders,
            self.nested_date_toggle,
            self.open_folder_build_toggle,
            self.minimize_after_build_toggle,
            self.close_app_after_build_toggle,
            self.load_template_btn,
            self.save_template_btn,
            self.delete_template_btn,
            self.delete_all_templates_btn,
            self.default_to_desktop_btn,
            self.output_location_btn,
            self.build_folders_btn,
        )
        tree_toolbar_buttons = (
            self.expand_tree_btn,
            self.expand_folders_collapse_btn,
            self.sort_btn,
            self.find_btn,
        )
        for button in (*top_control_buttons, *tree_toolbar_buttons):
            button.setProperty("styleFontSize", self.CONTROL_FONT_SIZE)
        self.find_output_line.setProperty("styleFontSize", self.CONTROL_FONT_SIZE)

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
        self.state = state
        self.tooltips_enabled = bool(state.get("tooltips_enabled", True))
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
        self.section_navigation.setStyleSheet(styles.navigation_list_style())
        self.sidebar.setStyleSheet(styles.sidebar_style())
        self.sidebar_separator.setStyleSheet(styles.sidebar_separator_style())
        for page_index in range(self.controls_stack.count()):
            page = self.controls_stack.widget(page_index)
            page.setStyleSheet(
                styles.control_page_style()
            )
            page.refresh_rounded_border()
        self._refresh_section_navigation_icons()
        self.window_close_btn.setIcon(self._title_bar_icon("close"))
        self.tree_frame.setStyleSheet(styles.tree_outer_frame_style())
        self.tree.setStyleSheet(styles.surfaced_tree_widget_style())
        find_font_size = styles.resurface_styles.coerce_font_size(
            self.find_output_line.property("styleFontSize"), 15
        ) or 15
        self.find_output_line.setStyleSheet(
            styles.frameless_surfaced_line_edit_style(find_font_size)
        )
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
        styles.refresh_fluent_icons(self)
        refresh_visible_tooltip()

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
        self._set_tree_view_expanded(not self._tree_view_expanded)

    def _set_tree_view_expanded(self, expanded):
        self._tree_view_expanded = bool(expanded)
        self.controls_stack.setVisible(not self._tree_view_expanded)
        self.controls_to_tree_spacer.setVisible(not self._tree_view_expanded)
        tree_height = (
            self.tree_expanded_height
            if self._tree_view_expanded
            else self.tree_default_height
        )
        self.tree.setFixedHeight(tree_height)
        self._set_tree_frame_height(tree_height)
        self.tree.setPlaceholderFontSize(
            self.tree.EXPANDED_PLACEHOLDER_FONT_SIZE
            if self._tree_view_expanded
            else self.tree.COMPACT_PLACEHOLDER_FONT_SIZE
        )
        self.expand_tree_btn.setText(
            "Collapse" if self._tree_view_expanded else "Expand"
        )
        QTimer.singleShot(0, self.ui_state.update_build_button_state)
        self.tree.setVisible(True)

    def update_expand_button_text(self):
        if self.ui_state.tree_has_collapsed_nodes():
            self.expand_folders_collapse_btn.setText("Expand Folders")
            self.expand_folders_collapse_btn.setFixedWidth(160)
        else:
            self.expand_folders_collapse_btn.setText("Collapse Folders")
            self.expand_folders_collapse_btn.setFixedWidth(175)

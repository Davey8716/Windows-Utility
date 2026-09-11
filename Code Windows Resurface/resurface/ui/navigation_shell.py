"""Navigation sidebar, page hosts, and page-selection behavior."""

from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from resurface.ui import styles


@dataclass(frozen=True)
class PageDefinition:
    page_id: str
    label: str
    glyph: str
    description: str


class NavigationShell(QWidget):
    """Own the main navigation controls and the final hosts for page content."""

    page_changed = Signal(str)

    PAGE_DEFINITIONS = (
        PageDefinition("overview", "Overview", "\ue80f", "Quick view of Windows Resurface."),
        PageDefinition("quick_actions", "Quick Actions", "\ue945", "Your pinned Windows Resurface actions."),
        PageDefinition("user_interface", "User Interface", "\ue790", "Choose how Windows Resurface looks and behaves."),
        PageDefinition("screen_mover", "Screen Mover", "\ue7f4", "Move and manage the foreground window with global keyboard shortcuts."),
        PageDefinition(
            "monitor_rules",
            "Monitor Rules",
            "\ue8a7",
            "Automatically place chosen applications on chosen monitors.\n"
            "Rules are checked from top to bottom. The first complete match wins.",
        ),
        PageDefinition(
            "clipboard_provenance",
            "Clipboard Provenance",
            "\ue8a5",
            "Record copied text and files, with the source window captured at copy time.",
        ),
        PageDefinition("external_drives", "External Drives", "\ue88e", "Manage drive reminders, storage usage, and removable drives."),
        PageDefinition("organising_utilities", "Organising Utilities", "\ue74c", "Back up desktop items, bookmarks, layouts, and screenshots."),
        PageDefinition("folder_utilities", "Folder Utilities", "\ue8b7", "Create desktop folders or open the Folder Creator companion."),
        PageDefinition("recycle_bin", "Recycle Bin", "\ue74d", "Open, empty, and automatically clean the Recycle Bin."),
        PageDefinition("windows_utilities", "Windows Utilities", "\ue770", "Open useful Windows settings and management tools."),
        PageDefinition("maintenance", "Maintenance", "\ue90f", "Run quick maintenance, repair, and networking actions."),
        PageDefinition(
            "hover_window_controls",
            "Hover Window Controls",
            "\ue7f4",
            "Dwell over window buttons or a taskbar icon to activate its action.",
        ),
    )

    def __init__(
        self,
        *,
        app_version: str,
        sidebar_width: int,
        page_title_top_inset: int,
        parent=None,
    ):
        super().__init__(parent)
        self.sidebar_width = sidebar_width
        self.page_title_top_inset = page_title_top_inset
        self.page_registry = []
        self.page_by_id = {}
        self.page_content_layouts = {}
        self.page_content_widgets = {}
        self.page_scroll_areas = {}

        body_layout = QHBoxLayout(self)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.navigation_sidebar = QWidget(self)
        self.navigation_sidebar.setObjectName("NavigationSidebar")
        self.navigation_sidebar.setFixedWidth(sidebar_width)
        navigation_layout = QVBoxLayout(self.navigation_sidebar)
        navigation_layout.setContentsMargins(0, page_title_top_inset, 0, 0)
        navigation_layout.setSpacing(0)

        self.navigation_list = QListWidget(self.navigation_sidebar)
        self.navigation_list.setObjectName("NavigationList")
        self.navigation_list.setFixedWidth(sidebar_width)
        self.navigation_list.setIconSize(QSize(22, 22))
        self.navigation_list.setSpacing(2)
        self.navigation_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.navigation_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.navigation_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.navigation_list.setAccessibleName("Sections")
        navigation_layout.addWidget(self.navigation_list, 1)

        self.version_label = QLabel(
            f"Windows Resurface  ·  v{app_version}", self.navigation_sidebar
        )
        self.version_label.setObjectName("SidebarVersionLabel")
        self.version_label.setAccessibleName("Application version")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        navigation_layout.addWidget(self.version_label)
        body_layout.addWidget(self.navigation_sidebar)

        self.page_stack = QStackedWidget(self)
        self.page_stack.setObjectName("PageStack")
        body_layout.addWidget(self.page_stack, 1)

        self._create_page_hosts()
        self._populate_navigation()
        self.navigation_list.currentRowChanged.connect(self._selection_changed)

    def _create_page_hosts(self) -> None:
        for definition in self.PAGE_DEFINITIONS:
            page, content, layout, scroll = self._create_page_host(definition)
            self.page_stack.addWidget(page)
            self.page_registry.append(
                {
                    "id": definition.page_id,
                    "label": definition.label,
                    "glyph": definition.glyph,
                    "description": definition.description,
                    "widget": page,
                }
            )
            self.page_by_id[definition.page_id] = page
            self.page_content_widgets[definition.page_id] = content
            self.page_content_layouts[definition.page_id] = layout
            self.page_scroll_areas[definition.page_id] = scroll

    def _create_page_host(self, definition: PageDefinition):
        page = QWidget(self.page_stack)
        page.setObjectName("ContentPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QScrollArea(page)
        scroll.setObjectName("PageScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        page_layout.addWidget(scroll)

        content = QWidget()
        content.setObjectName("PageContent")
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(38, self.page_title_top_inset, 38, 32)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel(definition.label, content)
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet(styles.page_title_style())
        layout.addWidget(title)
        scroll.setWidget(content)
        return page, content, layout, scroll

    def _populate_navigation(self) -> None:
        self.navigation_list.clear()
        for entry in self.page_registry:
            item = QListWidgetItem(entry["label"])
            item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            item.setSizeHint(QSize(self.sidebar_width - 18, 46))
            item.setToolTip(entry["description"])
            self.navigation_list.addItem(item)
        self._refresh_navigation_icons()

    def content_parent(self, page_id: str) -> QWidget:
        return self.page_content_widgets[page_id]

    def mount_content(self, page_id: str, content: QWidget) -> None:
        """Mount content that was constructed with this page's final parent."""
        if content.parentWidget() is not self.content_parent(page_id):
            raise ValueError(f"Content for {page_id!r} was not built with its final parent")
        content.setMaximumWidth(16777215)
        content.setMinimumWidth(0)
        content.setVisible(True)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        content_layout = content.layout()
        if content_layout is not None:
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.page_content_layouts[page_id].addWidget(content)

    def add_subheading(self, page_id: str, text: str) -> None:
        label = QLabel(text, self.content_parent(page_id))
        label.setObjectName("PageSectionHeading")
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        label.setStyleSheet(styles.page_section_heading_style())
        layout = self.page_content_layouts[page_id]
        layout.addSpacing(8)
        layout.addWidget(label)

    def finish_page_layouts(self) -> None:
        for layout in self.page_content_layouts.values():
            layout.addStretch(1)

    def _selection_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.page_registry):
            return
        entry = self.page_registry[row]
        self.page_stack.setCurrentWidget(entry["widget"])
        self.page_changed.emit(entry["id"])

    def navigate_to(self, page_id: str, *, emit_signal: bool = True) -> str:
        valid_ids = [entry["id"] for entry in self.page_registry]
        resolved_id = page_id if page_id in valid_ids else "overview"
        row = valid_ids.index(resolved_id)
        row_changed = self.navigation_list.currentRow() != row
        if emit_signal:
            self.navigation_list.setCurrentRow(row)
            if not row_changed:
                self.page_changed.emit(resolved_id)
        else:
            self.navigation_list.blockSignals(True)
            self.navigation_list.setCurrentRow(row)
            self.page_stack.setCurrentIndex(row)
            self.navigation_list.blockSignals(False)
        return resolved_id

    def _navigation_icon(self, glyph: str) -> QIcon:
        icon = QIcon()
        for mode, color in (
            (QIcon.Mode.Normal, styles.theme_muted_text_color()),
            (QIcon.Mode.Selected, styles.STATUS_ACCENT),
        ):
            pixmap = QPixmap(24, 24)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            font = QFont("Segoe Fluent Icons")
            font.setPixelSize(18)
            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
            painter.end()
            icon.addPixmap(pixmap, mode)
        return icon

    def _refresh_navigation_icons(self) -> None:
        for row, entry in enumerate(self.page_registry):
            item = self.navigation_list.item(row)
            if item is not None:
                item.setIcon(self._navigation_icon(entry["glyph"]))

    def apply_theme(self) -> None:
        self.navigation_list.setStyleSheet(styles.navigation_list_style())
        self.version_label.setStyleSheet(styles.sidebar_version_label_style())
        self._refresh_navigation_icons()
        for button in self.findChildren(QToolButton, "MonitorRulesHelpButton"):
            button.setStyleSheet(styles.monitor_rules_help_button_style())
        for name in (
            "OverviewSummary",
            "MonitorRulesEmptyState",
        ):
            for frame in self.findChildren(QFrame, name):
                frame.setStyleSheet(styles.summary_frame_style())

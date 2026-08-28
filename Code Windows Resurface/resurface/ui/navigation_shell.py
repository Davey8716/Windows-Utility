"""Navigation registry and page-selection behavior for the main window."""

from resurface.ui import styles
from resurface.core.state_manager import save_state
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QListWidgetItem


class NavigationShell:
    PAGE_DEFINITIONS = (
        ("overview", "Overview", "\ue80f", "Common actions and a quick view of Windows Resurface."),
        ("quick_actions", "Quick Actions", "\ue945", "Frequently used Windows Resurface actions."),
        ("user_interface", "User Interface", "\ue790", "Choose how Windows Resurface looks and behaves."),
        ("screen_mover", "Screen Mover", "\ue7f4", "Move and manage windows with the title-bar dock and keyboard shortcuts."),
        ("monitor_rules", "Monitor Rules", "\ue8a7", "Automatically place chosen applications on chosen monitors."),
        ("external_drives", "External Drives", "\ue88e", "Manage drive reminders, storage usage, and removable drives."),
        ("organising_utilities", "Organising Utilities", "\ue74c", "Back up desktop items, bookmarks, layouts, and screenshots."),
        ("folder_utilities", "Folder Utilities", "\ue8b7", "Create desktop folders or open the Folder Creator companion."),
        ("recycle_bin", "Recycle Bin", "\ue74d", "Open, empty, and automatically clean the Recycle Bin."),
        ("windows_utilities", "Windows Utilities", "\ue770", "Open useful Windows settings and management tools."),
        ("maintenance", "Maintenance", "\ue90f", "Run quick maintenance, repair, and networking actions."),
        (
            "hover_window_controls",
            "Hover Window Controls",
            "\ue7f4",
            "Coming soon — configure floating window controls and hover actions.",
        ),
    )

    def __init__(self, app):
        self.app = app

    def create_page_registry(self) -> None:
        app = self.app
        app.page_registry = []
        app.page_by_id = {}
        app.page_content_layouts = {}
        app.page_scroll_areas = {}
        for page_id, label, glyph, description in self.PAGE_DEFINITIONS:
            page, content_layout, scroll = app._create_page(label, description)
            app.page_stack.addWidget(page)
            app.page_registry.append({"id": page_id, "label": label, "glyph": glyph, "description": description, "widget": page})
            app.page_by_id[page_id] = page
            app.page_content_layouts[page_id] = content_layout
            app.page_scroll_areas[page_id] = scroll

    def populate(self) -> None:
        app = self.app
        app.navigation_list.clear()
        for entry in app.page_registry:
            item = QListWidgetItem(entry["label"])
            item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            item.setSizeHint(QSize(app.SIDEBAR_WIDTH - 18, 46))
            item.setToolTip(entry["description"])
            app.navigation_list.addItem(item)
        app._refresh_navigation_icons()

    def selection_changed(self, row: int) -> None:
        app = self.app
        if row < 0 or row >= len(app.page_registry):
            return
        entry = app.page_registry[row]
        app.page_stack.setCurrentWidget(entry["widget"])
        app.state["last_opened_page"] = entry["id"]
        save_state(app.state)
        if entry["id"] == "overview":
            app.refresh_overview()

    def navigate_to(self, page_id: str, *, persist: bool = True) -> None:
        app = self.app
        valid_ids = [entry["id"] for entry in app.page_registry]
        if page_id not in valid_ids:
            page_id = "overview"
        row = valid_ids.index(page_id)
        if persist:
            app.navigation_list.setCurrentRow(row)
        else:
            app.navigation_list.blockSignals(True)
            app.navigation_list.setCurrentRow(row)
            app.page_stack.setCurrentIndex(row)
            app.navigation_list.blockSignals(False)
            app.state["last_opened_page"] = page_id
        if page_id == "overview":
            app.refresh_overview()

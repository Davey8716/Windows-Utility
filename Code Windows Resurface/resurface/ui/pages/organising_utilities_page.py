from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton

from resurface.ui import styles
from resurface.ui.pages.page_controls import PageControls
from resurface.ui.tooltips import set_tooltip, tooltip_text


ORGANISING_UTILITIES_HELP_TEXT = (
    "Desktop Screenshot saves a visual record of your screens and Taskbar. "
    "It cannot restore pinned Taskbar apps automatically.\n\n"
    "Taskbar Actions backs up compatible pinned desktop-app shortcuts. Some "
    "Windows and Microsoft Store apps, such as Settings and modern Notepad, "
    "use Windows-managed app identities instead of shortcut files and are not "
    "included in that backup.\n\n"
    "Use the screenshot as a reference when manually restoring the arrangement "
    "of those apps."
)


class OrganisingUtilitiesPage(PageControls):
    action_requested = Signal(str)
    master_backup_path_requested = Signal()

    AUTO_EXPORT_LABELS = {
        "off": "Auto-Export: Off",
        "daily": "Auto-Export: Daily",
        "weekly": "Auto-Export: Weekly",
        "monthly": "Auto-Export: Monthly",
    }
    AUTO_EXPORT_NOW_LABEL = "Auto-Export: Now"

    def __init__(self, backup_path: str, register_tooltip, parent=None, *, auto_export_interval="off"):
        super().__init__("organising_utilities", register_tooltip, parent)
        screenshot = self.style_action_button(QPushButton("Desktop Screenshot"))
        screenshot.clicked.connect(lambda: self.action_requested.emit("desktop_screenshot"))
        self.register_tooltip(screenshot, tooltip_text("desktop_screenshot"))
        self.screenshot_button = screenshot
        desktop = self.make_action_dropdown(
            " Desktop Actions ", ["Capture Layout", "Restore Layout", "Alphabetise Groups"],
            lambda name: self.action_requested.emit({
                "Capture Layout": "capture_layout",
                "Restore Layout": "restore_layout",
                "Alphabetise Groups": "alphabetise_groups",
            }[name]),
        )
        self.register_tooltip(desktop, tooltip_text("capture_desktop_layout"))
        self.desktop_actions_combo = desktop
        self.add_two_column_control_row(self.content_layout, screenshot, desktop)
        bookmarks = self.style_action_button(QPushButton("Export Bookmarks"))
        bookmarks.clicked.connect(lambda: self.action_requested.emit("export_bookmarks"))
        self._bookmarks_tooltip_manager = self.register_tooltip(
            bookmarks, tooltip_text("export_bookmarks")
        )
        self.bookmarks_button = bookmarks
        auto_export = self.make_value_dropdown(
            [self.AUTO_EXPORT_NOW_LABEL, *self.AUTO_EXPORT_LABELS.values()],
            self.AUTO_EXPORT_LABELS.get(auto_export_interval, self.AUTO_EXPORT_LABELS["off"]),
        )
        auto_export.currentTextChanged.connect(self._auto_export_selected)
        self.register_tooltip(auto_export, tooltip_text("bookmark_auto_export"))
        self.auto_export_combo = auto_export
        taskbar = self.make_action_dropdown(
            " Taskbar Actions ", ["Backup Taskbar", "Open Backup Folder"],
            lambda name: self.action_requested.emit({"Backup Taskbar": "backup_taskbar", "Open Backup Folder": "open_backup_folder"}[name]),
        )
        self.register_tooltip(taskbar, tooltip_text("backup_taskbar"))
        self.taskbar_actions_combo = taskbar
        self.add_two_column_control_row(self.content_layout, bookmarks, taskbar)
        self.content_layout.addWidget(auto_export, 0, Qt.AlignmentFlag.AlignLeft)
        choose = self.style_action_button(QPushButton("Master Backup Path"))
        choose.clicked.connect(self.master_backup_path_requested.emit)
        self.register_tooltip(choose, tooltip_text("master_backup_path"))
        self.master_backup_button = choose
        self._path_label = QLabel()
        self._path_label.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        self._path_label.setProperty("surfaceLabelStyle", True)
        self._path_label.setProperty("whiteSurfaceLabelStyle", True)
        self._path_label.setProperty("styleFontSize", 15)
        self._path_label.setStyleSheet(
            styles.surfaced_label_style(15, text_color=styles.TEXT_LIGHT)
        )
        self._path_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.add_two_column_control_row(self.content_layout, choose, self._path_label)
        self.set_backup_path(backup_path)
        self.set_auto_export_status(auto_export_interval, None)

    def set_backup_path(self, path: str, *, unavailable: bool = False) -> None:
        self._path_label.setText(path)
        self._path_label.setToolTip("")
        self._path_label.setStyleSheet(
            styles.surfaced_label_style(15, text_color=styles.TEXT_LIGHT)
            + ("QLabel { color: #c53030; }" if unavailable else "")
        )

    def set_alphabetise_groups_available(self, available: bool) -> None:
        """Enable or disable only the Alphabetise Groups dropdown entry."""
        row = self.desktop_actions_combo.findText("Alphabetise Groups")
        item = self.desktop_actions_combo.model().item(row)
        if item is not None:
            item.setEnabled(available)
        self.desktop_actions_combo.setProperty("alphabetiseGroupsApplied", not available)
        self.desktop_actions_combo.style().unpolish(self.desktop_actions_combo)
        self.desktop_actions_combo.style().polish(self.desktop_actions_combo)

    def path_display_width(self) -> int:
        return self._path_label.width()

    def path_display_font(self):
        return self._path_label.font()

    def set_auto_export_status(self, interval: str, last_success: str | None) -> None:
        self.auto_export_combo.blockSignals(True)
        self.auto_export_combo.setCurrentText(
            self.AUTO_EXPORT_LABELS.get(interval, self.AUTO_EXPORT_LABELS["off"])
        )
        self.auto_export_combo.blockSignals(False)
        detail = "No automatic export has completed yet."
        if last_success:
            detail = f"Last successful automatic export: {last_success}"
        self.auto_export_combo.setToolTip(
            tooltip_text("bookmark_auto_export") + "\n\n" + detail
        )
        automatic_export_enabled = interval in {"daily", "weekly", "monthly"}
        self.bookmarks_button.setEnabled(not automatic_export_enabled)
        bookmark_tooltip = (
            "Manual bookmark export is disabled while Auto-Export is active. "
            "Choose Auto-Export: Now to create a forced test snapshot."
            if automatic_export_enabled
            else tooltip_text("export_bookmarks")
        )
        manager = self._bookmarks_tooltip_manager
        if manager is not None and hasattr(manager, "set_text"):
            manager.set_text(bookmark_tooltip)
        else:
            self.bookmarks_button.setToolTip(bookmark_tooltip)

    def _auto_export_selected(self, text: str) -> None:
        if text == self.AUTO_EXPORT_NOW_LABEL:
            self.action_requested.emit("run_bookmark_auto_export_now")
            return
        interval = next(
            key for key, label in self.AUTO_EXPORT_LABELS.items() if label == text
        )
        self.action_requested.emit("set_bookmark_auto_export:" + interval)

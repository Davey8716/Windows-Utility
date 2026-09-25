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

    def __init__(self, backup_path: str, register_tooltip, parent=None):
        super().__init__("organising_utilities", register_tooltip, parent)
        screenshot = self.style_action_button(QPushButton("Desktop Screenshot"))
        screenshot.clicked.connect(lambda: self.action_requested.emit("desktop_screenshot"))
        self.register_tooltip(screenshot, tooltip_text("desktop_screenshot"))
        self.screenshot_button = screenshot
        desktop = self.make_action_dropdown(
            " Desktop Actions ", ["Capture Layout", "Restore Layout"],
            lambda name: self.action_requested.emit({"Capture Layout": "capture_layout", "Restore Layout": "restore_layout"}[name]),
        )
        self.register_tooltip(desktop, tooltip_text("capture_desktop_layout"))
        self.desktop_actions_combo = desktop
        self.add_two_column_control_row(self.content_layout, screenshot, desktop)
        bookmarks = self.style_action_button(QPushButton("Export Bookmarks"))
        bookmarks.clicked.connect(lambda: self.action_requested.emit("export_bookmarks"))
        self.register_tooltip(bookmarks, tooltip_text("export_bookmarks"))
        self.bookmarks_button = bookmarks
        taskbar = self.make_action_dropdown(
            " Taskbar Actions ", ["Backup Taskbar", "Open Backup Folder"],
            lambda name: self.action_requested.emit({"Backup Taskbar": "backup_taskbar", "Open Backup Folder": "open_backup_folder"}[name]),
        )
        self.register_tooltip(taskbar, tooltip_text("backup_taskbar"))
        self.taskbar_actions_combo = taskbar
        self.add_two_column_control_row(self.content_layout, bookmarks, taskbar)
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

    def set_backup_path(self, path: str, *, unavailable: bool = False) -> None:
        self._path_label.setText(path)
        self._path_label.setToolTip("")
        self._path_label.setStyleSheet(
            styles.surfaced_label_style(15, text_color=styles.TEXT_LIGHT)
            + ("QLabel { color: #c53030; }" if unavailable else "")
        )

    def path_display_width(self) -> int:
        return self._path_label.width()

    def path_display_font(self):
        return self._path_label.font()

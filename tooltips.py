from PySide6.QtCore import QObject, QTimer, QPoint, QEvent
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QToolTip


TOOLTIP_TEXT = {
    "dark_mode": "Switches the app between dark and light appearance.",
    "always_on_top": "Keeps the main window above other windows.",
    "enable_tooltips": "Enables or disables delayed hover tooltips across the app.",
    "maximize_all": "Controls whether the minimize-all utility is enabled.",
    "power_options": "Choose a power action such as sleep, lock, restart, log out, or shutdown.",
    "title_bar_dock": "Shows a small left/right mover dock when you hover an app window's title bar.",
    "screen_move_button": "Chooses which mouse button activates moving a window from the tracked title-bar dock.",
    "idle_plugged_reminder": "Controls warnings when you lock, log out, restart, shut down, or use this app's power actions with an external drive still connected.",
    "download_done_reminder": "Controls the finished-download drive reminder.",
    "plug_unplug_notify": "Controls notifications for drive plug and unplug events.",
    "desktop_screenshot": "Captures the desktop and saves it to the master backup folder.",
    "folder_to_desktop": "Creates a desktop folder using the name entered beside it.",
    "folder_name_input": "Enter the name of the folder to create on the desktop.",
    "backup_taskbar": "Backs up pinned taskbar shortcuts into the TaskBarApps folder.",
    "open_backup_folder": "Opens the TaskBarApps backup folder inside the master backup path, or closes it if already open.",
    "capture_desktop_layout": "Saves the current desktop icon layout to the master backup location.",
    "restore_desktop_layout": "Restores the saved desktop icon layout from the master backup location.",
    "export_bookmarks": "Exports Brave bookmarks into the Bookmarks folder inside the master backup path.",
    "desktop_zen_mode": "Hides desktop icons and sends the app to the system tray in Zen Mode, then shows icons again when toggled back.",
    "master_backup_path": "Chooses the base folder used by backup and layout utilities.",
    "backup_path_input": "Shows the current master backup folder path.",
    "master_collapse_right": "Master collapse toggle for all of these regions.",
    "windows_utilities_toggle": "Shows windows utilities grouped by type and quick actions.",
    "maintenance_quick_actions_toggle": "Shows maintenance, cleanup, repair, and quick-access action menus.",
    "drive_space_display_toggle": "Shows disk usage for all detected drives.",
    "open_this_pc": "Opens This PC in File Explorer, or closes it if already open.",
    "windows_dropdown_system": "Opens system-focused Windows tools such as Control Panel, Settings, System Information, and Task Manager.",
    "windows_dropdown_hardware": "Opens hardware and device management tools such as Device Manager, Disk Management, Services, and Event Viewer.",
    "windows_dropdown_network": "Opens network-related tools such as adapter settings, firewall controls, IP configuration, and router login.",
    "windows_dropdown_startup_power": "Opens startup app controls and Windows power options.",
    "sidebar_dropdown_network_fix": "Runs quick network and system repair actions such as flushing DNS, renewing IP, restarting Explorer, or restarting Bluetooth service.",
    "sidebar_dropdown_cleanup": "Runs cleanup and quick utility actions such as clearing temp files or clearing the clipboard.",
    "sidebar_dropdown_quick_open": "Opens common locations and tools such as Downloads, the Startup folder, and Clipboard History settings.",
    "sidebar_dropdown_integrity": "Runs system integrity and disk health tools such as SFC and CHKDSK.",
}


def tooltip_text(key: str) -> str:
    return TOOLTIP_TEXT[key]


class QtTooltipManager(QObject):
    def __init__(self, widget, text, delay=250):
        super().__init__(widget)

        self.widget = widget
        self.text = text
        self.delay = delay

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show_tooltip)

        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        etype = event.type()

        if etype == QEvent.Type.Enter:
            self._schedule()

        elif etype == QEvent.Type.ToolTip:
            return True

        elif etype in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress):
            self._hide()
        return False

    def _schedule(self):
        self._timer.start(self.delay)

    def _show_tooltip(self):
        app = self.widget.window()
        if hasattr(app, "tooltips_enabled") and not app.tooltips_enabled:
            return

        QToolTip.setFont(self._build_tooltip_font())
        pos = self.widget.mapToGlobal(QPoint(20, self.widget.height()))
        QToolTip.showText(pos, self.text, self.widget)

    def _hide(self):
        self._timer.stop()
        QToolTip.hideText()

    def _build_tooltip_font(self) -> QFont:
        font = QFont(self.widget.font())
        style_font_size = self.widget.property("styleFontSize")

        pixel_size = None
        if style_font_size is not None:
            try:
                pixel_size = max(12, int(style_font_size) + 1)
            except (TypeError, ValueError):
                pixel_size = None

        if pixel_size is None:
            widget_pixel_size = font.pixelSize()
            if widget_pixel_size > 0:
                pixel_size = max(12, widget_pixel_size)
            else:
                point_size = font.pointSizeF()
                if point_size > 0:
                    font.setPointSizeF(max(10.5, point_size))

        if pixel_size is not None:
            font.setPixelSize(pixel_size)

        font.setBold(True)
        return font

import html
import textwrap

from PySide6.QtCore import QObject, QTimer, QPoint, QEvent
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QToolTip

TOOLTIP_TEXT = {
    "dark_mode": "Switches the app between dark and light appearance.",
    "always_on_top": "Keeps the main window above other windows.",
    "enable_tooltips": "Enables or disables delayed hover tooltips across the app.",
    "maximize_all": "Controls whether the maximize-all utility is enabled.",
    "minimize_after_use": "Controls whether launcher-style utilities minimize the app before opening or running.",
    "power_options": "Choose a power action such as sleep, lock, restart, log out, or shutdown.",
    "title_bar_dock": "Shows a small left/right mover dock when you hover an app window's title bar.",
    "screen_mover_enabled": "Enables the title-bar dock, mouse trigger, and configured keyboard shortcuts.",
    "screen_move_button": "Chooses which mouse button activates moving a window from the tracked title-bar dock.",
    "screen_mover_hotkey": "Sets a global keyboard shortcut for this window action.",
    "screen_mover_hotkey_clear": "Removes this keyboard shortcut.",
    "screen_mover_reset": "Restores the Screen Mover defaults without changing other Windows Resurface settings.",
    "idle_plugged_reminder": "Controls warnings when you lock, log out, restart, shut down, or use this app's power actions with an external drive still connected.",
    "plug_unplug_notify": "Controls notifications for drive plug and unplug events.",
    "desktop_screenshot": "Captures each detected screen into separate images and saves them to the Desktop Screenshots backup folder.",
    "folder_to_desktop": "Creates a desktop folder using the name entered beside it.",
    "folder_creator_launcher": "Opens the external Folder Creator tool from its main.py launcher.",
    "folder_name_input": "Enter the name of the folder to create on the desktop.",
    "backup_taskbar": "Backs up pinned taskbar shortcuts into the TaskBarApps folder.",
    "open_backup_folder": "Opens the TaskBarApps backup folder inside the master backup path, or closes it if already open.",
    "capture_desktop_layout": "Saves the current desktop icon layout to the master backup location.",
    "restore_desktop_layout": "Restores the saved desktop icon layout from the master backup location.",
    "export_bookmarks": "Exports supported browser bookmarks into separate HTML files inside the Bookmarks folder in the master backup path.",
    "cleanup_actions": "Opens Recycle Bin cleanup actions such as emptying the bin, opening it, or cleaning older items.",
    "recycle_bin_auto_clean": "Automatically cleans Recycle Bin items using the selected age rule each time the app starts.",
    "recycle_bin_age_rule": "Chooses how old Recycle Bin items must be before the startup cleanup deletes them.",
    "desktop_zen_mode": "Hides desktop icons and sends the app to the system tray in Zen Mode, then shows icons again when toggled back.",
    "master_backup_path": "Chooses the base folder used by backup and layout utilities.",
    "backup_path_input": "Shows the current master backup folder path.",
    "window_minimize": "Minimizes Windows Resurface.",
    "window_close": "Hides Windows Resurface to the system tray.",
    "open_this_pc": "Opens This PC, closes it if it is already open, or maximizes it if it is minimized.",
    "open_storage_sense": "Opens Storage Sense, closes it if it is already open, or maximizes it if it is minimized.",
    "windows_dropdown_system": "Opens system-focused Windows tools such as Control Panel, Credential Manager, Settings, and System Information.",
    "windows_dropdown_monitoring_security": "Opens monitoring and security tools such as Reliability Monitor, Resource Monitor, Task Manager, and Windows Security.",
    "windows_dropdown_devices_storage": "Opens device and storage tools such as Device Manager, Disk Cleanup, and Disk Management.",
    "windows_dropdown_services_logs": "Opens service and logging tools such as Services and Event Viewer.",
    "windows_dropdown_network": "Opens network-related tools such as adapter settings, firewall controls, IP configuration, and router login.",
    "windows_dropdown_startup_power": "Opens startup app controls and Windows power options.",
    "sidebar_dropdown_network_fix": "Runs quick network and system repair actions such as flushing DNS, renewing the local DHCP lease, restarting Explorer, or restarting Bluetooth service. This does not change the public IP address shown by websites.",
    "sidebar_dropdown_cleanup": "Runs cleanup and quick utility actions such as clearing temp files or clearing the clipboard.",
    "sidebar_dropdown_quick_open": "Opens common locations and tools such as Downloads, the Startup folder, and Clipboard History settings.",
    "sidebar_dropdown_integrity": "Runs system integrity and disk health tools such as SFC and CHKDSK.",
}

def tooltip_text(key: str) -> str:
    return TOOLTIP_TEXT[key]


def format_tooltip_text(text: str, wrap_width: int = 62) -> str:
    paragraphs: list[str] = []
    for raw_line in text.splitlines():
        stripped = " ".join(raw_line.split())
        if not stripped:
            paragraphs.append("")
            continue

        wrapped_lines = textwrap.wrap(
            stripped,
            width=wrap_width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        paragraphs.append("<br>".join(html.escape(line) for line in wrapped_lines))

    wrapped_html = "<br>".join(paragraphs).strip("<br>")
    return (
        "<div style='padding: 10px; margin: 0px;'>"
        f"{wrapped_html}"
        "</div>"
    )

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
        QToolTip.showText(pos, format_tooltip_text(self.text), self.widget)

    def _hide(self):
        self._timer.stop()
        QToolTip.hideText()

    def _safe_tooltip_font(
        self,
        pixel_size: int = 14,
        bold: bool = True,
    ) -> QFont:
        source_font = self.widget.font()
        family = source_font.family().strip() if source_font is not None else ""
        font = QFont(family or "Segoe UI")
        font.setPixelSize(pixel_size)
        font.setBold(bold)
        return font

    def _build_tooltip_font(self) -> QFont:
        return self._safe_tooltip_font(pixel_size=14, bold=True)

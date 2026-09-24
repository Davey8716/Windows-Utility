import html
import textwrap

from PySide6.QtCore import QObject, QTimer, QPoint, QEvent, QRectF, Qt
from PySide6.QtGui import QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from resurface.ui import style_tokens as styles

REGISTERED_TOOLTIP_PROPERTY = "resurfaceRegisteredTooltip"
_TOOLTIP_POPUPS: dict[int, "RoundedTooltipPopup"] = {}
_TOOLTIP_ROUTERS: dict[int, "TooltipEventRouter"] = {}
TOOLTIP_CONTENT_INSET = 10
TOOLTIP_SCREEN_INSET = 8

TOOLTIP_TEXT = {
    "dark_mode": "Switches the app between dark and light appearance.",
    "always_on_top": "Keeps the main window above other windows.",
    "enable_tooltips": "Enables or disables delayed hover tooltips across the app.",
    "disable_all_confirmations": "Disables every app confirmation after a final danger warning. Errors, warnings, information, file pickers, and editor dialogs still appear.",
    "maximize_all": "Controls whether the maximize-all utility is enabled.",
    "minimize_after_use": "Controls whether launcher-style utilities minimize the app before opening or running.",
    "power_options": "Choose a power action such as sleep, lock, restart, log out, or shutdown.",
    "screen_mover_hotkey": "Sets a global keyboard shortcut for this window action.",
    "screen_mover_hotkey_clear": "Removes this keyboard shortcut.",
    "screen_mover_reset": "Clears all Screen Mover keyboard shortcuts without changing other Windows Resurface settings.",
    "hover_controls_enabled": "Runs a window action after the pointer rests on a supported minimize, maximize, restore, or close button.",
    "hover_controls_taskbar_restore": "Restores a minimized window after the pointer rests over its taskbar icon. Requires AutoHotkey v2.",
    "hover_controls_dwell": "Chooses how long the pointer must remain over a supported window control before it activates.",
    "hover_controls_calibrate": "Captures and adjusts learned button positions for applications with custom title bars.",
    "hover_controls_export": "Exports Hover Window Controls settings and learned profiles to the Hover Window Controls folder inside the master backup path.",
    "hover_controls_import": "Imports Hover Window Controls settings and learned profiles from a validated backup.",
    "hover_controls_clear": "Permanently removes learned caption images and manual calibration data without changing preferences.",
    "idle_plugged_reminder": "Controls warnings when you lock, log out, restart, shut down, or use this app's power actions with an external drive still connected.",
    "plug_unplug_notify": "Controls notifications for drive plug and unplug events.",
    "desktop_screenshot": "Captures each detected screen into separate images and saves them to the Desktop Screenshots backup folder.",
    "folder_to_desktop": "Creates a desktop folder using the name entered beside it.",
    "quick_actions_reset_defaults": "Restores the default Quick Actions and their original order.",
    "folder_creator_launcher": "Opens the external Folder Creator tool from its main.py launcher.",
    "folder_name_input": "Enter the name of the folder to create on the desktop.",
    "delete_name": "Deletes whichever the chosen drop down save folder name item is. ",
    "delete_all_names": "Deletes every saved folder name from the list.",
    "backup_taskbar": "Backs up compatible pinned desktop-app shortcuts into the TaskBarApps folder.",
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
    "maintenance_clear_log": "Clears the Maintenance page output log without undoing any completed actions.",
    "clipboard_provenance_export": "Exports the recorded clipboard provenance history to the Clipboard Provenance folder in the master backup path.",
    "clipboard_provenance_clear": "Permanently clears every locally recorded clipboard provenance entry. Exported backup files are kept.",
}

def tooltip_text(key: str) -> str:
    return TOOLTIP_TEXT[key]


def registered_tooltip_text(widget) -> str:
    """Return the delayed-tooltip text previously registered for a widget."""
    value = widget.property(REGISTERED_TOOLTIP_PROPERTY)
    return "" if value is None else str(value)


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
        "<div style='margin: 0px; text-align: center;'>"
        f"{wrapped_html}"
        "</div>"
    )


def set_tooltip(widget, text: str | None) -> None:
    """Assign the standard roomy tooltip markup to a widget."""
    value = "" if text is None else str(text)
    widget.setToolTip(format_tooltip_text(value) if value.strip() else "")


class RoundedTooltipPopup(QWidget):
    """A transparent tooltip window that paints one continuous rounded surface."""

    def __init__(self) -> None:
        flags = (
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.BypassWindowManagerHint
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

        self.label = QLabel(self)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            TOOLTIP_CONTENT_INSET,
            TOOLTIP_CONTENT_INSET,
            TOOLTIP_CONTENT_INSET,
            TOOLTIP_CONTENT_INSET,
        )
        layout.addWidget(self.label)
        self._anchor_pos = QPoint()

    def _apply_theme(self) -> None:
        self.label.setStyleSheet(
            "background: transparent; border: none; "
            f"color: {styles.tooltip_text_color().name()};"
        )

    @staticmethod
    def _available_screen_geometry(pos: QPoint):
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if screen is None:
            return None
        return screen.availableGeometry()

    def _resize_for_text(self, pos: QPoint) -> None:
        geometry = self._available_screen_geometry(pos)
        max_content_width = 16_384
        if geometry is not None:
            max_content_width = max(
                1,
                geometry.width() - (2 * TOOLTIP_SCREEN_INSET) - (2 * TOOLTIP_CONTENT_INSET),
            )

        self.label.setMinimumSize(0, 0)
        self.label.setMaximumSize(16_384, 16_384)
        self.label.adjustSize()
        content_width = min(self.label.sizeHint().width(), max_content_width)
        self.label.setFixedWidth(max(1, content_width))
        self.label.setFixedHeight(max(1, self.label.heightForWidth(content_width)))
        self.layout().activate()
        self.adjustSize()

    def _move_inside_screen(self, pos: QPoint) -> None:
        geometry = self._available_screen_geometry(pos)
        if geometry is None:
            self.move(pos)
            return
        min_x = geometry.left() + TOOLTIP_SCREEN_INSET
        min_y = geometry.top() + TOOLTIP_SCREEN_INSET
        max_x = max(min_x, geometry.right() - self.width() - TOOLTIP_SCREEN_INSET + 1)
        max_y = max(min_y, geometry.bottom() - self.height() - TOOLTIP_SCREEN_INSET + 1)
        self.move(
            max(min_x, min(pos.x(), max_x)),
            max(min_y, min(pos.y(), max_y)),
        )

    def show_tooltip(self, pos: QPoint, text: str, font: QFont | None = None) -> None:
        self.label.setFont(font or QApplication.font())
        self.label.setText(text)
        self._anchor_pos = QPoint(pos)
        self._apply_theme()
        self._resize_for_text(pos)
        self._move_inside_screen(pos)
        self.show()
        self.raise_()

    def refresh_theme(self) -> None:
        self._apply_theme()
        self._resize_for_text(self._anchor_pos)
        self._move_inside_screen(self._anchor_pos)
        self.update()

    def paintEvent(self, event) -> None:
        del event
        inset = styles.POPUP_BORDER_WIDTH / 2
        rect = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        if rect.isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(styles.tooltip_border(), styles.POPUP_BORDER_WIDTH))
        painter.setBrush(styles.tooltip_bg())
        radius = max(0, styles.BUTTON_CORNER_RADIUS - inset)
        painter.drawRoundedRect(rect, radius, radius)


def tooltip_popup() -> RoundedTooltipPopup:
    """Return the one tooltip surface shared by the current QApplication."""
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("A QApplication is required before showing a tooltip")
    app_key = id(app)
    popup = _TOOLTIP_POPUPS.get(app_key)
    if popup is None:
        popup = RoundedTooltipPopup()
        _TOOLTIP_POPUPS[app_key] = popup
    return popup


def show_tooltip(pos: QPoint, text: str, font: QFont | None = None) -> None:
    if text.strip():
        tooltip_popup().show_tooltip(pos, text, font)


def hide_tooltip() -> None:
    app = QApplication.instance()
    if app is None:
        return
    popup = _TOOLTIP_POPUPS.get(id(app))
    if popup is not None:
        popup.hide()


def refresh_visible_tooltip() -> None:
    """Repaint the shared popup after the mutable theme palette changes."""
    app = QApplication.instance()
    if app is None:
        return
    popup = _TOOLTIP_POPUPS.get(id(app))
    if popup is not None and popup.isVisible():
        popup.refresh_theme()


class TooltipEventRouter(QObject):
    """Routes standard Qt tooltip events into the rounded app tooltip surface."""

    _HIDE_EVENTS = {
        QEvent.Type.Leave,
        QEvent.Type.MouseButtonPress,
        QEvent.Type.WindowDeactivate,
        QEvent.Type.FocusOut,
    }

    @staticmethod
    def _tooltip_text_for(obj: QWidget, event) -> str:
        text = obj.toolTip()
        if text.strip():
            return text

        view = obj if isinstance(obj, QAbstractItemView) else obj.parentWidget()
        if not isinstance(view, QAbstractItemView):
            return ""
        index = view.indexAt(event.pos())
        if not index.isValid():
            return view.toolTip()
        value = view.model().data(index, Qt.ItemDataRole.ToolTipRole)
        return "" if value is None else str(value)

    def eventFilter(self, obj, event):
        if isinstance(obj, RoundedTooltipPopup):
            return False
        if event.type() == QEvent.Type.ToolTip and isinstance(obj, QWidget):
            text = self._tooltip_text_for(obj, event)
            if not text.strip():
                return False
            window = obj.window()
            if not (
                hasattr(window, "tooltips_enabled") and not window.tooltips_enabled
            ):
                show_tooltip(event.globalPos(), text, obj.font())
            else:
                hide_tooltip()
            return True
        if event.type() in self._HIDE_EVENTS:
            hide_tooltip()
        return False


def install_tooltip_router() -> TooltipEventRouter:
    """Install the application-wide router once and return it for test access."""
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("A QApplication is required before installing tooltip routing")
    app_key = id(app)
    router = _TOOLTIP_ROUTERS.get(app_key)
    if router is None:
        router = TooltipEventRouter(app)
        app.installEventFilter(router)
        _TOOLTIP_ROUTERS[app_key] = router
    return router


class QtTooltipManager(QObject):
    def __init__(self, widget, text, delay=250):
        super().__init__(widget)

        self.widget = widget
        self.text = "" if text is None else str(text)
        self.delay = delay
        self.widget.setProperty(REGISTERED_TOOLTIP_PROPERTY, self.text)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show_tooltip)

        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        etype = event.type()

        if etype == QEvent.Type.Enter:
            self._schedule()

        elif etype in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress):
            self._hide()
        return False

    def _schedule(self):
        if not self.text.strip():
            self._hide()
            return
        self._timer.start(self.delay)

    def _show_tooltip(self):
        if not self.text.strip():
            self._hide()
            return
        app = self.widget.window()
        if hasattr(app, "tooltips_enabled") and not app.tooltips_enabled:
            return

        pos = self.widget.mapToGlobal(QPoint(20, self.widget.height()))
        show_tooltip(pos, format_tooltip_text(self.text), self._build_tooltip_font())

    def set_text(self, text) -> None:
        self.text = "" if text is None else str(text)
        self.widget.setProperty(REGISTERED_TOOLTIP_PROPERTY, self.text)
        if not self.text.strip():
            self._hide()

    def _hide(self):
        self._timer.stop()
        hide_tooltip()

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

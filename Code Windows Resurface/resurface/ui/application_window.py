
import ctypes
from ctypes import wintypes
from resurface.ui import styles
import win32gui
import win32con
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from resurface.core.app_paths import MasterBackupPathsMixin
from resurface.core.instance_runtime import WM_APP_RESTORE_INSTANCE
from resurface.core.state_manager import load_state, save_state
from resurface.core.tray_toggles import TrayIconManager, resolve_application_icon
from resurface.features.desktop.folder_service import DesktopFolderService
from resurface.features.desktop.screenshot_service import ScreenshotService
from resurface.features.desktop.zen_mode import ZenModeService
from resurface.features.folder_creator.launcher import FolderCreatorLauncher
from resurface.features.drives.drive_service import DriveService
from resurface.features.drives.drive_reminder_logic import DriveReminderPolicy
from resurface.features.drives.external_drive_mixin import ExternalDriveMixin
from resurface.features.screen_mover.hotkeys import GlobalHotkeyManager, VALID_ACTIONS, active_hotkeys
from resurface.features.screen_mover.service import ScreenMover
from resurface.features.screen_mover.window_actions import perform_window_action
from resurface.features.monitor_rules import MonitorRuleWatcher, normalize_monitor_rules
from resurface.features.explorer.window_service import ExplorerWindowService
from resurface.features.recycle_bin.service import RecycleBinService
from resurface.features.system.utility_toggles import UtilityActionsManager
from resurface.features.system.router_service import RouterService
from resurface.features.taskbar.backup_service import TaskbarBackupService
from resurface.features.windows.window_management import WindowManagementService
from resurface.features.system.command_runner import CommandRunner
from resurface.features.system.maintenance_actions import MaintenanceActions
from resurface.ui.app_notifications import WindowMessageMixin
from resurface.ui.application_pages import ApplicationPageComposer
from resurface.ui.controllers import (
    FolderActionsController,
    OrganisingActionsController,
    RecycleBinActionsController,
)
from resurface.ui.tooltips import QtTooltipManager
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from resurface.ui.navigation_shell import NavigationShell
from resurface.ui.window_chrome import SeverityComboItemDelegate, WindowChrome

from PySide6.QtWidgets import (
    QWidget,
    QMainWindow,
    QComboBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QLineEdit,
    QApplication,
    QKeySequenceEdit,
)

WM_QUERYENDSESSION = 0x0011
ENDSESSION_LOGOFF = 0x80000000
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
NOTIFY_FOR_THIS_SESSION = 0


class ScreenMoverActionBridge(QObject):
    action_requested = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.action_requested.connect(window.handle_screen_mover_self_action)

    def dispatch(self, action: str) -> None:
        self.action_requested.emit(action)


class UtilityControlApp(
    MasterBackupPathsMixin,
    WindowMessageMixin,
    ExternalDriveMixin,
    QMainWindow,
):
    APP_VERSION = "0.1.0"
    WINDOW_WIDTH = 1000
    WINDOW_HEIGHT = 800
    SIDEBAR_WIDTH = 220
    TITLE_TEXT_ROW_HEIGHT = 40
    TITLE_TEXT_TOP_PADDING = 20
    TITLE_CONTROL_ROW_HEIGHT = 0
    TITLE_BAR_HEIGHT = 40
    PAGE_TITLE_TOP_INSET = 43
    PREFERRED_WINDOW_HEIGHT = WINDOW_HEIGHT
    def __init__(self):
        super().__init__()

        self.state = load_state()
        self.saved_state = self.state
        styles.set_theme(bool(self.state.get("theme_dark", True)))
        self.setWindowTitle("Windows Resurface")
        self.setStyleSheet(styles.window_style() + styles.tooltip_style())
        self.setWindowIcon(resolve_application_icon(self))
        self.COLLAPSED_WIDTH = self.WINDOW_WIDTH
        self.EXPANDED_WIDTH = self.WINDOW_WIDTH
        self.ADVANCED_PANEL_WIDTH = 0
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        
        self.tooltips_enabled = bool(self.state.get("tooltips_enabled", True))
        self._tooltip_managers = []
        self._active_message_boxes = []
        self._grouped_timed_message_boxes = {}
        self._session_notification_registered = False
        self._pending_end_session_warning = False
        self._taskbar_backup_folder_open = False
        self._quit_requested = False
        self._shutdown_complete = False
        self.window_management = WindowManagementService()
        self.explorer_windows = ExplorerWindowService(self.window_management)
        self.recycle_bin_service = RecycleBinService(self.window_management)
        self.taskbar_backup_service = TaskbarBackupService()
        self.screenshot_service = ScreenshotService()
        self.desktop_folder_service = DesktopFolderService()
        self.folder_creator_launcher = FolderCreatorLauncher()
        self.zen_mode_service = ZenModeService()
        self.router_service = RouterService()
        self.organising_actions = OrganisingActionsController(
            self,
            self.screenshot_service,
            self.taskbar_backup_service,
            self.explorer_windows,
        )
        self.recycle_bin_actions = RecycleBinActionsController(
            self,
            self.recycle_bin_service,
            self.organising_actions.run_with_optional_minimize,
        )
        self.folder_actions = FolderActionsController(
            self,
            self.desktop_folder_service,
            self.folder_creator_launcher,
            self.organising_actions,
        )
        self.actions = UtilityActionsManager(
            self,
            windows=self.window_management,
            explorer=self.explorer_windows,
            recycle_bin=self.recycle_bin_service,
            taskbar_backup=self.taskbar_backup_service,
            zen_mode=self.zen_mode_service,
            router=self.router_service,
        )
        self.drive_service = DriveService()
        self.drive_reminder_policy = DriveReminderPolicy()
        self.command_runner = CommandRunner(self)
        self.maintenance_actions = MaintenanceActions(
            self.command_runner,
            self.explorer_windows,
            self.window_management,
            self,
        )
        self.tray_manager = TrayIconManager(self)
        self._screen_mover_bridge = ScreenMoverActionBridge(self)
        self.screen_mover = ScreenMover(name="WindowsResurfaceMain")
        self.monitor_rule_watcher = MonitorRuleWatcher(name="WindowsResurfaceMonitorRules")
        self.hotkey_manager = GlobalHotkeyManager(self.screen_mover.request_action)
        self.window_chrome = WindowChrome(self)

        self._build_ui()
        self.drive_reminder_policy.reset(self._current_external_drives())
        self._drive_change_timer = QTimer(self)
        self._drive_change_timer.timeout.connect(self._check_external_drive_changes)
        self._drive_change_timer.start(3000)
        self.tray_manager.create_tray_icon()
        self.screen_mover.configure(
            app_hwnd=int(self.winId()),
            self_action_dispatch=self._screen_mover_bridge.dispatch,
            settings=self.state,
        )
        self.apply_screen_mover_settings()
        self.apply_monitor_rule_settings(apply_existing=True)
        
        self._set_main_window_topmost_state(True)
        self._apply_fixed_window_style()
        self._register_session_notifications()
        QTimer.singleShot(0, self.recycle_bin_actions.run_auto_cleanup)

    def _apply_fixed_window_style(self):
        hwnd = int(self.winId())
        if not hwnd:
            return

        user32 = ctypes.windll.user32
        get_window_long = user32.GetWindowLongW
        set_window_long = user32.SetWindowLongW
        set_window_pos = user32.SetWindowPos

        GWL_STYLE = -16
        WS_MAXIMIZEBOX = 0x00010000
        WS_THICKFRAME = 0x00040000
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020

        style = get_window_long(hwnd, GWL_STYLE)
        style &= ~WS_MAXIMIZEBOX
        style &= ~WS_THICKFRAME
        set_window_long(hwnd, GWL_STYLE, style)
        set_window_pos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )
        self._apply_native_window_corner_preference()

    def _apply_native_window_corner_preference(self):
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
        self._apply_fixed_window_style()
        self._register_session_notifications()

    def _set_main_window_topmost_state(self, enabled: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()

        hwnd = int(self.winId())
        if not hwnd:
            return

        insert_after = -1 if enabled else -2
        try:
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                insert_after,
                0,
                0,
                0,
                0,
                0x0003,
            )
        except Exception as exc:
            print(f"[TOPMOST] Failed to apply topmost={enabled}: {exc}")

    def nativeEvent(self, eventType, message):
        try:
            event_name = bytes(eventType).decode(errors="ignore")
        except Exception:
            event_name = str(eventType)

        if event_name == "windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_WTSSESSION_CHANGE and msg.wParam == WTS_SESSION_LOCK:
                QTimer.singleShot(0, self._handle_session_lock_reminder)
            elif msg.message == WM_QUERYENDSESSION:
                end_session_reason = (
                    "Log Out" if (msg.lParam & ENDSESSION_LOGOFF) else "Shutdown or Restart"
                )
                if self._block_end_session_for_connected_drives(end_session_reason):
                    return True, 0
            elif msg.message == WM_APP_RESTORE_INSTANCE:
                QTimer.singleShot(0, self.restore_from_activation)
                return True, 0

        return False, 0

    def restore_from_activation(self):
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.repaint()
        self.update()

        try:
            hwnd = int(self.winId())
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def apply_screen_mover_settings(self) -> None:
        enabled = bool(self.state.get("title_bar_dock_enabled", True))
        hotkeys = active_hotkeys(
            self.state.get("screen_mover_keyboard_hotkeys", {})
        )
        activation_button = (
            self.state.get("screen_mover_activation_button", "middle")
            if enabled
            else "off"
        )

        self.screen_mover.update_settings(
            title_bar_dock_enabled=enabled,
            activation_button=activation_button,
            force_running=enabled and bool(hotkeys),
        )
        self.hotkey_manager.update_hotkeys(hotkeys, enabled=enabled)

        tray_manager = getattr(self, "tray_manager", None)
        if tray_manager is not None:
            tray_manager.sync_screen_mover_action()

    def apply_monitor_rule_settings(self, *, apply_existing=False) -> None:
        self.monitor_rule_watcher.update_rules(
            self.state.get("monitor_rules", []),
            app_hwnd=int(self.winId()),
            apply_existing=apply_existing,
        )

    def set_monitor_rules(self, rules) -> None:
        self.state["monitor_rules"] = normalize_monitor_rules(rules)
        save_state(self.state)
        self.apply_monitor_rule_settings()
        tray_manager = getattr(self, "tray_manager", None)
        sync_tray = getattr(tray_manager, "sync_monitor_rules_action", None)
        if callable(sync_tray):
            sync_tray()

    def set_monitor_rules_enabled(self, enabled: bool) -> None:
        page = getattr(self, "monitor_rules_page", None)
        if page is not None:
            page.set_all_enabled(enabled)
            return

        rules = normalize_monitor_rules(self.state.get("monitor_rules", []))
        for rule in rules:
            rule["enabled"] = bool(enabled)
        self.set_monitor_rules(rules)

    def set_screen_mover_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.state["title_bar_dock_enabled"] = enabled
        page = getattr(self, "screen_mover_settings_page", None)
        if page is not None:
            page.set_enabled(enabled)
        else:
            toggle = getattr(self, "screen_mover_enabled_btn", None)
            if toggle is not None and toggle.isChecked() != enabled:
                toggle.blockSignals(True)
                toggle.setChecked(enabled)
                toggle.blockSignals(False)
                toggle.setText("Screen Mover On" if enabled else "Screen Mover Off")

        save_state(self.state)
        self.apply_screen_mover_settings()
        refresh_overview = getattr(self, "refresh_overview", None)
        if refresh_overview is not None:
            refresh_overview()

    def reset_screen_mover_settings(self) -> None:
        page = getattr(self, "screen_mover_settings_page", None)
        if page is not None:
            page.reset_settings()
            return

        self.state["title_bar_dock_enabled"] = True
        self.state["screen_mover_activation_button"] = "middle"
        self.state["mmb_activation_enabled"] = True
        self.state["screen_mover_keyboard_hotkeys"] = {
            action: "" for action in VALID_ACTIONS
        }

        combo = getattr(self, "screen_move_button_combo", None)
        if combo is not None:
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData("middle"))
            combo.blockSignals(False)
            combo.setProperty("persistPressed", True)
            combo.style().unpolish(combo)
            combo.style().polish(combo)
        for edit in getattr(self, "screen_mover_hotkey_edits", {}).values():
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)

        self.set_screen_mover_enabled(True)

    def handle_screen_mover_self_action(self, action: str) -> None:
        if action == "MAXIMIZE":
            return

        hwnd = int(self.winId())
        if not hwnd:
            return

        try:
            perform_window_action(hwnd, action)
        except Exception as exc:
            print(f"[SCREEN_MOVER] Failed self-window action {action}: {exc}")

    def prepare_for_shutdown(self):
        if self._shutdown_complete:
            return

        self._shutdown_complete = True
        self._unregister_session_notifications()

        try:
            self.hotkey_manager.stop()
        except Exception:
            pass

        try:
            self.screen_mover.stop()
        except Exception:
            pass

        try:
            self.monitor_rule_watcher.stop()
        except Exception:
            pass

        self.command_runner.reset()

        tray = getattr(getattr(self, "tray_manager", None), "tray", None)
        if tray:
            try:
                tray.hide()
            except Exception:
                pass

    def _register_session_notifications(self):
        if self._session_notification_registered:
            return

        hwnd = int(self.winId())
        if not hwnd:
            return

        try:
            registered = bool(
                ctypes.windll.wtsapi32.WTSRegisterSessionNotification(
                    hwnd,
                    NOTIFY_FOR_THIS_SESSION,
                )
            )
        except Exception as exc:
            print(f"[SESSION] Failed to register session notifications: {exc}")
            return

        if registered:
            self._session_notification_registered = True

    def _unregister_session_notifications(self):
        if not self._session_notification_registered:
            return

        hwnd = int(self.winId())
        if not hwnd:
            return

        try:
            ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification(hwnd)
        except Exception as exc:
            print(f"[SESSION] Failed to unregister session notifications: {exc}")
        finally:
            self._session_notification_registered = False

    def _build_ui(self):
        self.root_container = QWidget()
        self.setCentralWidget(self.root_container)
        root_layout = QVBoxLayout(self.root_container)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self._build_title_bar()
        root_layout.addWidget(self.window_title_bar)

        self.navigation_shell = NavigationShell(
            app_version=self.APP_VERSION,
            sidebar_width=self.SIDEBAR_WIDTH,
            page_title_top_inset=self.PAGE_TITLE_TOP_INSET,
            parent=self.root_container,
        )
        root_layout.addWidget(self.navigation_shell, 1)

        self.page_composer = ApplicationPageComposer(self, self.navigation_shell)
        self.pages = self.page_composer.compose()

        # Transitional aliases keep mixins and callers stable during extraction.
        self.navigation_sidebar = self.navigation_shell.navigation_sidebar
        self.navigation_list = self.navigation_shell.navigation_list
        self.version_label = self.navigation_shell.version_label
        self.page_stack = self.navigation_shell.page_stack
        self.page_registry = self.navigation_shell.page_registry
        self.page_by_id = self.navigation_shell.page_by_id
        self.page_content_layouts = self.navigation_shell.page_content_layouts
        self.page_scroll_areas = self.navigation_shell.page_scroll_areas

        self.sidebar_navigation_mode = True
        self.navigation_shell.page_changed.connect(self._on_page_changed)
        saved_page = self.state.get("last_opened_page", "overview")
        self.navigate_to_page(saved_page, persist=False)
        self.navigation_shell.apply_theme()
        self._refresh_screen_mover_shortcut_field_styles()
        QTimer.singleShot(0, self._refresh_screen_mover_shortcut_field_styles)

    def _build_title_bar(self) -> None:
        self.window_chrome.build()

    def _position_title_bar_controls(self) -> None:
        self.window_chrome.position_controls()

    def _apply_title_bar_theme(self) -> None:
        self.window_chrome.apply_theme()

    def _refresh_screen_mover_shortcut_field_styles(self) -> None:
        """Restore shortcut-field styling after Qt reparents or repolishes it."""
        page = getattr(self, "screen_mover_settings_page", None)
        if page is not None:
            page.refresh_shortcut_styles()
            return
        for hotkey_edit in self.findChildren(QKeySequenceEdit):
            if hotkey_edit.objectName() != "ScreenMoverShortcutEdit":
                continue

            internal_edits = hotkey_edit.findChildren(QLineEdit)
            for internal_edit in internal_edits:
                internal_edit.setStyleSheet("")
            hotkey_edit.setStyleSheet(styles.hotkey_edit_style(13))
            widgets = (hotkey_edit, *internal_edits)
            for widget in widgets:
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()
            hotkey_edit.setFixedHeight(styles.PAGE_CONTROL_HEIGHT)

    @staticmethod
    def _is_screen_mover_shortcut_internal_field(line_edit: QLineEdit) -> bool:
        parent = line_edit.parentWidget()
        return (
            isinstance(parent, QKeySequenceEdit)
            and parent.objectName() == "ScreenMoverShortcutEdit"
        )

    def navigate_to_page(self, page_id: str, *, persist: bool = True) -> None:
        resolved_id = self.navigation_shell.navigate_to(
            page_id, emit_signal=persist
        )
        if not persist:
            self._on_page_changed(resolved_id)

    def _on_page_changed(self, page_id: str) -> None:
        self.state["last_opened_page"] = page_id
        if page_id == "overview":
            self.refresh_overview()

    def _open_folder_utilities(self) -> None:
        self.navigate_to_page("folder_utilities")
        page = getattr(self, "folder_utilities_page", None)
        if page is not None:
            page.focus_name_input()

    def refresh_overview(self) -> None:
        page = getattr(self, "overview_page", None)
        if page is None:
            return
        page.refresh(
            self.state, getattr(self, "_overview_connected_drives", set())
        )

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

    @classmethod
    def _height_for_available_height(cls, available_height: int | None) -> int:
        """Return the preferred height unless the work area is shorter."""
        if available_height is None or available_height <= 0:
            return cls.PREFERRED_WINDOW_HEIGHT
        return min(cls.PREFERRED_WINDOW_HEIGHT, int(available_height))

    def _resolve_window_height(self) -> int:
        screen = self.screen() or QApplication.primaryScreen()
        available_height = (
            screen.availableGeometry().height() if screen is not None else None
        )
        return self._height_for_available_height(available_height)

    def resizeEvent(self, event):
        self._position_title_bar_controls()
        self._refresh_master_backup_path_display()
        super().resizeEvent(event)

    def _power_action_item_colors(self) -> dict[str, QColor]:
        return {
            "placeholder": QColor(26, 118, 214) if styles.THEME_IS_DARK else QColor(42, 134, 230),
            "blue": QColor(36, 104, 196) if styles.THEME_IS_DARK else QColor(68, 142, 236),
            "yellow": QColor(196, 162, 32) if styles.THEME_IS_DARK else QColor(224, 196, 74),
            "amber": QColor(207, 132, 30) if styles.THEME_IS_DARK else QColor(230, 154, 56),
            "orange": QColor(210, 95, 26) if styles.THEME_IS_DARK else QColor(234, 118, 42),
            "orange_red": QColor(198, 67, 35) if styles.THEME_IS_DARK else QColor(220, 88, 48),
            "red": QColor(176, 38, 38) if styles.THEME_IS_DARK else QColor(204, 52, 52),
        }

    def _power_action_item_foreground(self, label: str, background: QColor) -> QColor:
        if styles.THEME_IS_DARK and label in {"Sleep", "Log out"}:
            return styles.TEXT_LIGHT
        if not styles.THEME_IS_DARK and label == "Shutdown":
            return QColor(0, 0, 0)
        return styles.contrasting_text_color(background)

    def _apply_power_action_dropdown_style(self, combo: QComboBox) -> None:
        font_size = styles.coerce_font_size(
            combo.property("styleFontSize"),
            14,
        ) or 14
        combo.setStyleSheet(styles.power_combo_style(font_size))

        severity_map = combo.property("powerActionSeverityMap") or {}
        placeholder_text = combo.property("powerActionPlaceholder") or ""
        color_map = self._power_action_item_colors()

        for row in range(combo.count()):
            label = combo.itemText(row)
            severity = "placeholder" if label == placeholder_text else severity_map.get(label)
            if not severity:
                continue
            background = color_map[severity]
            combo.setItemData(row, background, Qt.ItemDataRole.BackgroundRole)
            combo.setItemData(
                row,
                self._power_action_item_foreground(label, background),
                Qt.ItemDataRole.ForegroundRole,
            )

        if not isinstance(combo.itemDelegate(), SeverityComboItemDelegate):
            combo.setItemDelegate(SeverityComboItemDelegate(combo))

    def apply_theme(self, is_dark: bool):
        styles.set_theme(is_dark)
        self.setStyleSheet(styles.window_style() + styles.tooltip_style())
        self._apply_title_bar_theme()

        for line_edit in self.findChildren(QLineEdit):
            if self._is_screen_mover_shortcut_internal_field(line_edit):
                continue
            if line_edit.property("emphasizedSurfaceFieldStyle"):
                line_edit.setStyleSheet(styles.emphasized_surface_line_edit_style(15))
            elif line_edit.property("framelessSurfaceFieldStyle"):
                line_edit.setStyleSheet(styles.frameless_surfaced_line_edit_style(15))
            elif line_edit.property("plainThemeFieldStyle"):
                line_edit.setStyleSheet(styles.plain_theme_line_edit_style(15))
            elif line_edit.property("surfaceFieldStyle"):
                line_edit.setStyleSheet(styles.surfaced_line_edit_style(15))
            else:
                line_edit.setStyleSheet(styles.line_edit_style(15))

        self._refresh_screen_mover_shortcut_field_styles()

        for label in self.findChildren(QLabel):
            if label.property("surfaceLabelStyle"):
                font_size = styles.coerce_font_size(
                    label.property("styleFontSize"),
                    14,
                ) or 14
                label.setStyleSheet(styles.surfaced_label_style(font_size))

        self._refresh_master_backup_path_display()

        for button in self.findChildren(QPushButton):
            font_size = styles.coerce_font_size(
                button.property("styleFontSize"),
                14,
            ) or 14
            button.setStyleSheet(styles.organizing_button_style(font_size=font_size))

        user_interface_page = getattr(self, "user_interface_page", None)
        if user_interface_page is not None:
            user_interface_page.refresh_icons()

        for combo in self.findChildren(QComboBox):
            font_size = styles.coerce_font_size(
                combo.property("styleFontSize"),
                14,
            ) or 14
            if combo.property("connectedDrivesFieldStyle"):
                self._apply_connected_drives_field_style()
            elif combo.property("powerActionStyle"):
                self._apply_power_action_dropdown_style(combo)
            elif combo.property("surfaceFieldStyle"):
                combo.setStyleSheet(styles.surfaced_combo_style(font_size=font_size))
            else:
                combo.setStyleSheet(styles.organizing_combo_style(font_size=font_size))

        if hasattr(self, "maintenance_page"):
            self.maintenance_page.apply_theme()
        if hasattr(self, "drive_space_page"):
            self.drive_space_page.apply_theme()

        for label in self.findChildren(QLabel, "PageTitle"):
            label.setStyleSheet(styles.page_title_style())
        for label in self.findChildren(QLabel, "PageDescription"):
            label.setStyleSheet(styles.page_description_style())
        for label in self.findChildren(QLabel, "PageSectionHeading"):
            label.setStyleSheet(styles.page_section_heading_style())
        for label in self.findChildren(QLabel, "OverviewSummaryLabel"):
            label.setStyleSheet(styles.summary_label_style())
        for key, label in getattr(self, "overview_status_labels", {}).items():
            label.setStyleSheet(styles.summary_value_style())
        self.navigation_shell.apply_theme()

    def register_tooltip(self, widget: QWidget, text: str, delay: int = 10):
        manager = QtTooltipManager(widget, text, delay=delay)
        self._tooltip_managers.append(manager)
        return manager

    def save_all_settings(self):
        self.state["main_always_on_top_enabled"] = bool(
            self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        )
        save_state(self.state)

    def closeEvent(self, event):
        self.save_all_settings()
        if self._quit_requested:
            self.prepare_for_shutdown()
            event.accept()
            return

        event.ignore()
        self.hide()
        if getattr(self, "tray_manager", None) and self.tray_manager.tray:
            self.tray_manager.tray.showMessage(
                "Windows Resurface",
                "Still running in the system tray.",
                self.tray_manager.tray.icon(),
                2000
            )



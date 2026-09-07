
import ctypes
from ctypes import wintypes
from resurface.ui import styles
import win32gui
import win32con
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap

from resurface.core.app_paths import MasterBackupPathsMixin
from resurface.core.instance_runtime import WM_APP_RESTORE_INSTANCE
from resurface.core.state_manager import load_state, save_state
from resurface.core.tray_toggles import TrayIconManager, resolve_application_icon
from resurface.features.desktop.folder_service import DesktopFolderService
from resurface.features.desktop.screenshot_service import ScreenshotService
from resurface.features.desktop.zen_mode import ZenModeService
from resurface.features.folder_creator.launcher import FolderCreatorLauncher
from resurface.features.hover_window_controls.migration import import_standalone_data
from resurface.features.hover_window_controls.service import HoverWindowControlsService
from resurface.features.drives.drive_monitor import DriveMonitor
from resurface.features.drives.drive_service import DriveService
from resurface.features.drives.drive_reminder_logic import DriveReminderPolicy
from resurface.features.drives.windows_session_adapter import WindowsSessionEventAdapter
from resurface.features.screen_mover.hotkeys import GlobalHotkeyManager
from resurface.features.screen_mover.service import ScreenMover
from resurface.features.monitor_rules import MonitorRuleWatcher
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
    ApplicationThemeController,
    ExternalDriveController,
    FolderActionsController,
    MonitorRulesController,
    OrganisingActionsController,
    RecycleBinActionsController,
    ScreenMoverSettingsController,
)
from resurface.ui.tooltips import QtTooltipManager
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from resurface.ui.navigation_shell import NavigationShell
from resurface.ui.window_chrome import WindowChrome

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

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
    QMainWindow,
):
    APP_VERSION = "0.1.0"
    WINDOW_WIDTH = 1000
    WINDOW_HEIGHT = 800
    SIDEBAR_WIDTH = 220
    TITLE_TEXT_ROW_HEIGHT = 40
    TITLE_TEXT_TOP_PADDING = 10
    TITLE_CONTROL_ROW_HEIGHT = 0
    TITLE_BAR_HEIGHT = 50
    PAGE_TITLE_TOP_INSET = 40
    PREFERRED_WINDOW_HEIGHT = WINDOW_HEIGHT
    def __init__(self):
        super().__init__()

        self.state = load_state()
        if import_standalone_data(self.state):
            save_state(self.state)
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
        self._overview_connected_drives = set()
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
        self.drive_monitor = DriveMonitor(self.drive_service, parent=self)
        self.command_runner = CommandRunner(self)
        self.maintenance_actions = MaintenanceActions(
            self.command_runner,
            self.explorer_windows,
            self.window_management,
            self,
        )
        self.hover_window_controls = HoverWindowControlsService(
            self.state,
            save_state,
            self,
        )
        self.tray_manager = TrayIconManager(self)
        self._screen_mover_bridge = ScreenMoverActionBridge(self)
        self.screen_mover = ScreenMover(name="WindowsResurfaceMain")
        self.monitor_rule_watcher = MonitorRuleWatcher(name="WindowsResurfaceMonitorRules")
        self.hotkey_manager = GlobalHotkeyManager(self.screen_mover.request_action)
        self.window_chrome = WindowChrome(self)
        self.external_drive_controller = ExternalDriveController(
            window=self,
            state=self.state,
            drive_service=self.drive_service,
            monitor=self.drive_monitor,
            policy=self.drive_reminder_policy,
            page=lambda: getattr(
                getattr(self, "pages", None), "external_drives_page", None
            ),
            drive_space_page=lambda: getattr(
                getattr(self, "pages", None), "drive_space_page", None
            ),
            refresh_overview=self.refresh_overview,
            run_with_optional_minimize=(
                self.organising_actions.run_with_optional_minimize
            ),
        )
        self.session_event_adapter = WindowsSessionEventAdapter(
            window_handle=lambda: int(self.winId()),
            on_session_lock=self.external_drive_controller.handle_session_lock,
            on_end_session=self.external_drive_controller.block_end_session,
        )

        self._build_ui()
        self.theme_controller = ApplicationThemeController(
            root=self,
            window_chrome=self.window_chrome,
            navigation_shell=self.navigation_shell,
            refresh_master_backup_path=self._refresh_master_backup_path_display,
            refresh_connected_drives_style=(
                self.external_drive_controller.apply_connected_drives_style
            ),
            screen_mover_settings_page=self.pages.screen_mover_settings_page,
            hover_window_controls_page=self.pages.hover_window_controls_page,
            user_interface_page=self.pages.user_interface_page,
            maintenance_page=self.pages.maintenance_page,
            drive_space_page=self.pages.drive_space_page,
            overview_status_labels=self.pages.overview_page.status_labels,
        )
        self.screen_mover_settings_controller = ScreenMoverSettingsController(
            state=self.state,
            screen_mover=self.screen_mover,
            hotkey_manager=self.hotkey_manager,
            save_state=save_state,
            window_handle=lambda: int(self.winId()),
            settings_page=lambda: getattr(
                getattr(self, "pages", None), "screen_mover_settings_page", None
            ),
            legacy_toggle=lambda: getattr(self, "screen_mover_enabled_btn", None),
            legacy_activation_combo=lambda: getattr(self, "screen_move_button_combo", None),
            legacy_hotkey_edits=lambda: getattr(self, "screen_mover_hotkey_edits", {}),
            refresh_overview=self.refresh_overview,
            sync_tray=self.tray_manager.sync_screen_mover_action,
        )
        self.monitor_rules_controller = MonitorRulesController(
            state=self.state,
            watcher=self.monitor_rule_watcher,
            save_state=save_state,
            window_handle=lambda: int(self.winId()),
            rules_page=lambda: getattr(
                getattr(self, "pages", None), "monitor_rules_page", None
            ),
            sync_tray=lambda: getattr(
                self.tray_manager, "sync_monitor_rules_action", lambda: None
            )(),
        )
        self.theme_controller.refresh_screen_mover_shortcut_styles()
        QTimer.singleShot(
            0, self.theme_controller.refresh_screen_mover_shortcut_styles
        )
        self.external_drive_controller.start()
        self.tray_manager.create_tray_icon()
        self.hover_window_controls.settings_changed.connect(
            lambda _enabled, _dwell: self.tray_manager.sync_hover_controls_action()
        )
        self.hover_window_controls.start()
        self.screen_mover.configure(
            app_hwnd=int(self.winId()),
            self_action_dispatch=self._screen_mover_bridge.dispatch,
            settings=self.state,
        )
        self.apply_screen_mover_settings()
        self.apply_monitor_rule_settings(apply_existing=True)
        
        self._set_main_window_topmost_state(True)
        self._apply_fixed_window_style()
        self.session_event_adapter.register()
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
        self.session_event_adapter.register()

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
        handled, result = self.session_event_adapter.handle_native_event(
            eventType,
            message,
        )
        if handled:
            return True, result

        try:
            event_name = bytes(eventType).decode(errors="ignore")
        except Exception:
            event_name = str(eventType)

        if event_name == "windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_APP_RESTORE_INSTANCE:
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
        self.screen_mover_settings_controller.apply_settings()

    def apply_monitor_rule_settings(self, *, apply_existing=False) -> None:
        self.monitor_rules_controller.apply_settings(apply_existing=apply_existing)

    def set_monitor_rules(self, rules, *, apply_rule_ids=None) -> None:
        self.monitor_rules_controller.set_rules(rules, apply_rule_ids=apply_rule_ids)

    def set_monitor_rules_enabled(self, enabled: bool) -> None:
        self.monitor_rules_controller.set_enabled(enabled)

    def set_screen_mover_enabled(self, enabled: bool) -> None:
        self.screen_mover_settings_controller.set_enabled(enabled)

    def set_hover_window_controls_enabled(self, enabled: bool) -> None:
        self.hover_window_controls.set_enabled(enabled)

    def reset_screen_mover_settings(self) -> None:
        self.screen_mover_settings_controller.reset_settings()

    def handle_screen_mover_self_action(self, action: str) -> None:
        self.screen_mover_settings_controller.handle_self_action(action)

    def prepare_for_shutdown(self):
        if self._shutdown_complete:
            return

        self._shutdown_complete = True
        self.session_event_adapter.unregister()
        self.external_drive_controller.shutdown()

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

        try:
            self.hover_window_controls.stop()
        except Exception:
            pass

        self.command_runner.reset()

        tray = getattr(getattr(self, "tray_manager", None), "tray", None)
        if tray:
            try:
                tray.hide()
            except Exception:
                pass

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
        self._refresh_taskbar_backup_folder_button()
        self._refresh_master_backup_path_display()

        self.sidebar_navigation_mode = True
        self.navigation_shell.page_changed.connect(self._on_page_changed)
        saved_page = self.state.get("last_opened_page", "overview")
        self.navigate_to_page(saved_page, persist=False)
        self.navigation_shell.apply_theme()

    def _build_title_bar(self) -> None:
        self.window_chrome.build()

    def _position_title_bar_controls(self) -> None:
        self.window_chrome.position_controls()

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
        self.pages.folder_utilities_page.focus_name_input()

    def refresh_overview(self) -> None:
        pages = getattr(self, "pages", None)
        if pages is None:
            return
        pages.overview_page.refresh(
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

    def apply_theme(self, is_dark: bool) -> None:
        self.theme_controller.apply_theme(is_dark)

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

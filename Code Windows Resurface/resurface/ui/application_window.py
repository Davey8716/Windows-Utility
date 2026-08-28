
import sys
import ctypes
from ctypes import wintypes
from resurface.ui import styles
import win32gui
import win32con
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

from resurface.core.app_paths import MasterBackupPathsMixin
from resurface.core.instance_runtime import WM_APP_RESTORE_INSTANCE
from resurface.core.state_manager import load_state, save_state
from resurface.core.tray_toggles import TrayIconManager, resolve_application_icon
from resurface.features.desktop.desktop_operations import DesktopOperationsMixin
from resurface.features.drives.external_drive_mixin import ExternalDriveMixin
from resurface.features.screen_mover.hotkeys import GlobalHotkeyManager, VALID_ACTIONS, active_hotkeys
from resurface.features.screen_mover.screen_mover import ScreenMover, perform_window_action
from resurface.features.monitor_rules import MonitorRuleWatcher, normalize_monitor_rules
from resurface.features.system.utility_toggles import UtilityActionsManager
from resurface.ui.app_notifications import WindowMessageMixin
from resurface.ui.left_panel_gui import LeftPanelBuilder
from resurface.ui.right_utility_gui import (
    AdvancedToolsPanel as RightAdvancedToolsPanel,
    get_drive_info,
)
from resurface.ui.tooltips import QtTooltipManager, tooltip_text
from PySide6.QtCore import QObject, Qt, QTimer, Signal, QSize
from resurface.ui.navigation_shell import NavigationShell
from resurface.ui.monitor_rules_ui import MonitorRulesPage
from resurface.ui.window_chrome import SeverityComboItemDelegate, WindowChrome

from PySide6.QtWidgets import (
    QWidget,
    QMainWindow,
    QComboBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QScrollArea,
    QLineEdit,
    QApplication,
    QFrame,
    QKeySequenceEdit,
    QSizePolicy,
    QHBoxLayout,
    QGridLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QAbstractItemView,
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
    DesktopOperationsMixin,
    QMainWindow,
):
    APP_VERSION = "0.1.0"
    WINDOW_WIDTH = 1000
    WINDOW_HEIGHT = 800
    SIDEBAR_WIDTH = 220
    TITLE_TEXT_ROW_HEIGHT = 40
    TITLE_TEXT_TOP_PADDING = 6
    TITLE_CONTROL_ROW_HEIGHT = 0
    TITLE_BAR_HEIGHT = 40
    PAGE_TITLE_TOP_INSET = 28
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
        self._known_external_drives = set()
        self._session_notification_registered = False
        self._pending_end_session_warning = False
        self._taskbar_backup_folder_open = False
        self._quit_requested = False
        self._shutdown_complete = False
        self._folder_creator_title_candidates = (
            "Folder Generator",
            "Folder Creator",
            "Code Folder Creator",
        )
        self._folder_creator_z_order_managed = False
        self._folder_creator_restore_topmost = False
        self.actions = UtilityActionsManager(self)
        self.tray_manager = TrayIconManager(self)
        self._screen_mover_bridge = ScreenMoverActionBridge(self)
        self.screen_mover = ScreenMover(name="WindowsResurfaceMain")
        self.monitor_rule_watcher = MonitorRuleWatcher(name="WindowsResurfaceMonitorRules")
        self.hotkey_manager = GlobalHotkeyManager(self.screen_mover.request_action)
        self.navigation_shell = NavigationShell(self)
        self.window_chrome = WindowChrome(self)

        self._build_ui()
        self._folder_creator_monitor_timer = QTimer(self)
        self._folder_creator_monitor_timer.timeout.connect(
            self._monitor_folder_creator_window
        )
        self._known_external_drives = self._current_external_drives()
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
        QTimer.singleShot(0, self.run_recycle_bin_auto_cleanup)

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

    def _begin_folder_creator_z_order_handoff(
        self,
        title_candidates: list[str] | tuple[str, ...],
    ) -> None:
        self._folder_creator_title_candidates = tuple(title_candidates)
        self._folder_creator_restore_topmost = bool(
            self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        )
        self._folder_creator_z_order_managed = True

        if self._folder_creator_restore_topmost:
            self._set_main_window_topmost_state(False)

        if not self._folder_creator_monitor_timer.isActive():
            self._folder_creator_monitor_timer.start(250)

    def _focus_folder_creator_window(
        self,
        title_candidates: list[str] | tuple[str, ...] | None = None,
        *,
        attempt: int = 0,
        max_attempts: int = 20,
    ) -> None:
        candidates = tuple(title_candidates or self._folder_creator_title_candidates)
        if self.actions.focus_window_titles(candidates):
            return

        if attempt >= max_attempts:
            return

        QTimer.singleShot(
            150,
            lambda: self._focus_folder_creator_window(
                candidates,
                attempt=attempt + 1,
                max_attempts=max_attempts,
            ),
        )

    def _restore_folder_creator_parent_topmost(self) -> None:
        if self._folder_creator_monitor_timer.isActive():
            self._folder_creator_monitor_timer.stop()

        should_restore = bool(self._folder_creator_restore_topmost)
        self._folder_creator_z_order_managed = False
        self._folder_creator_restore_topmost = False

        if should_restore:
            self._set_main_window_topmost_state(True)

    def _monitor_folder_creator_window(self) -> None:
        if not self._folder_creator_z_order_managed:
            if self._folder_creator_monitor_timer.isActive():
                self._folder_creator_monitor_timer.stop()
            return

        window_state = self.actions.get_window_titles_state(
            self._folder_creator_title_candidates
        )
        if window_state == "closed":
            self._restore_folder_creator_parent_topmost()

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

    def set_screen_mover_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.state["title_bar_dock_enabled"] = enabled

        toggle = getattr(self, "screen_mover_enabled_btn", None)
        if toggle is not None and toggle.isChecked() != enabled:
            toggle.blockSignals(True)
            toggle.setChecked(enabled)
            toggle.blockSignals(False)
            toggle.setText(
                "Screen Mover On" if enabled else "Screen Mover Off"
            )

        save_state(self.state)
        self.apply_screen_mover_settings()
        refresh_overview = getattr(self, "refresh_overview", None)
        if refresh_overview is not None:
            refresh_overview()

    def reset_screen_mover_settings(self) -> None:
        self.state["title_bar_dock_enabled"] = True
        self.state["screen_mover_activation_button"] = "middle"
        self.state["mmb_activation_enabled"] = True
        self.state["screen_mover_keyboard_hotkeys"] = {
            action: "" for action in VALID_ACTIONS
        }

        combo = getattr(self, "screen_move_button_combo", None)
        if combo is not None:
            combo_index = combo.findData("middle")
            combo.blockSignals(True)
            combo.setCurrentIndex(combo_index)
            combo.blockSignals(False)
            combo.setProperty("persistPressed", True)
            combo.style().unpolish(combo)
            combo.style().polish(combo)
            sync_screen_mover_widths = getattr(
                self,
                "_sync_screen_mover_control_widths",
                None,
            )
            if callable(sync_screen_mover_widths):
                sync_screen_mover_widths()

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

        body = QWidget(self.root_container)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        root_layout.addWidget(body, 1)

        self.navigation_sidebar = QWidget(body)
        self.navigation_sidebar.setObjectName("NavigationSidebar")
        self.navigation_sidebar.setFixedWidth(self.SIDEBAR_WIDTH)
        navigation_layout = QVBoxLayout(self.navigation_sidebar)
        navigation_layout.setContentsMargins(0, self.PAGE_TITLE_TOP_INSET, 0, 0)
        navigation_layout.setSpacing(0)

        self.navigation_list = QListWidget(self.navigation_sidebar)
        self.navigation_list.setObjectName("NavigationList")
        self.navigation_list.setFixedWidth(self.SIDEBAR_WIDTH)
        self.navigation_list.setIconSize(QSize(22, 22))
        self.navigation_list.setSpacing(2)
        self.navigation_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.navigation_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.navigation_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.navigation_list.setAccessibleName("Sections")
        navigation_layout.addWidget(self.navigation_list, 1)

        self.version_label = QLabel(
            f"Windows Resurface  ·  v{self.APP_VERSION}",
            self.navigation_sidebar,
        )
        self.version_label.setObjectName("SidebarVersionLabel")
        self.version_label.setAccessibleName("Application version")
        self.version_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        navigation_layout.addWidget(self.version_label)
        body_layout.addWidget(self.navigation_sidebar)

        self.page_stack = QStackedWidget(body)
        self.page_stack.setObjectName("PageStack")
        body_layout.addWidget(self.page_stack, 1)

        self.navigation_shell.create_page_registry()

        self.sidebar_navigation_mode = True
        # Build the existing wired controls in staging containers, then mount their
        # content on the new pages. This keeps all action callbacks in one place.
        self.right_tools_panel = RightAdvancedToolsPanel(self)
        self.right_tools_panel.hide()

        LeftPanelBuilder(self).build()

        left_page_map = {
            "user_interface": "user_interface",
            "screen_mover": "screen_mover",
            "drive_reminder_options": "external_drives",
            "organising_utilities": "organising_utilities",
            "folder_utilities": "folder_utilities",
            "recycle_bin_actions": "recycle_bin",
        }
        for section_id, content in self.left_page_contents.items():
            self._mount_page_content(
                left_page_map[section_id],
                content,
            )

        self._add_page_subheading("external_drives", "Storage")
        self._mount_page_content(
            "external_drives",
            self.right_tools_panel.drive_space_content,
        )
        self._mount_page_content(
            "windows_utilities",
            self.right_tools_panel.windows_utilities_content,
        )
        self._mount_page_content(
            "maintenance",
            self.right_tools_panel.maintenance_content,
        )
        self._build_overview_page()
        self._build_monitor_rules_page()

        for layout in self.page_content_layouts.values():
            layout.addStretch(1)

        self._populate_navigation()
        self.navigation_list.currentRowChanged.connect(self._on_navigation_changed)
        saved_page = self.state.get("last_opened_page", "overview")
        self.navigate_to_page(saved_page, persist=False)
        self._apply_navigation_theme()
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

    @staticmethod
    def _is_screen_mover_shortcut_internal_field(line_edit: QLineEdit) -> bool:
        parent = line_edit.parentWidget()
        return (
            isinstance(parent, QKeySequenceEdit)
            and parent.objectName() == "ScreenMoverShortcutEdit"
        )

    def _create_page(self, title_text: str, description: str):
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
        layout.setContentsMargins(38, self.PAGE_TITLE_TOP_INSET, 38, 32)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel(title_text, content)
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet(styles.page_title_style())
        description_label = QLabel(description, content)
        description_label.setObjectName("PageDescription")
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        description_label.setStyleSheet(styles.page_description_style())
        layout.addWidget(title)
        layout.addWidget(description_label)
        layout.addSpacing(6)
        scroll.setWidget(content)
        return page, layout, scroll

    def _mount_page_content(self, page_id: str, content: QWidget) -> None:
        content.setParent(self.page_by_id[page_id])
        content.setMaximumWidth(16777215)
        content.setMinimumWidth(0)
        content.setVisible(True)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        content_layout = content.layout()
        if content_layout is not None:
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
            )
        self.page_content_layouts[page_id].addWidget(content)

    def _add_page_subheading(self, page_id: str, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("PageSectionHeading")
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        label.setStyleSheet(styles.page_section_heading_style())
        self.page_content_layouts[page_id].addSpacing(8)
        self.page_content_layouts[page_id].addWidget(label)

    def _build_overview_page(self) -> None:
        layout = self.page_content_layouts["overview"]
        overview_content_width = (
            styles.PAGE_CONTROL_WIDTH * 2
        ) + styles.PAGE_CONTROL_GAP
        summary = QFrame()
        summary.setObjectName("OverviewSummary")
        summary.setFixedWidth(overview_content_width)
        summary_layout = QGridLayout(summary)
        summary_layout.setContentsMargins(20, 18, 20, 18)
        summary_layout.setHorizontalSpacing(24)
        summary_layout.setVerticalSpacing(12)

        self.overview_status_labels = {}
        for row, (key, label_text) in enumerate(
            (
                ("screen_mover", "Screen Mover"),
                ("drives", "Connected drives"),
                ("backup_path", "Master backup path"),
                ("recycle", "Recycle Bin auto-clean"),
            )
        ):
            label = QLabel(label_text)
            label.setObjectName("OverviewSummaryLabel")
            label.setStyleSheet(styles.summary_label_style())
            value = QLabel()
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setStyleSheet(styles.summary_value_style())
            summary_layout.addWidget(label, row, 0)
            summary_layout.addWidget(value, row, 1)
            self.overview_status_labels[key] = value
        summary_layout.setColumnStretch(1, 1)
        layout.addWidget(summary, 0, Qt.AlignmentFlag.AlignHCenter)

        self._add_page_subheading("overview", "Quick actions")
        quick_row = QWidget()
        quick_row.setProperty("centeredControlGrid", True)
        quick_row.setFixedWidth(overview_content_width)
        quick_row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        quick_layout = QGridLayout(quick_row)
        quick_layout.setContentsMargins(0, 0, 0, 0)
        quick_layout.setHorizontalSpacing(styles.PAGE_CONTROL_GAP)
        quick_layout.setVerticalSpacing(12)
        actions = (
            ("Desktop Screenshot", self.take_desktop_screenshot),
            ("Export Bookmarks", self.export_bookmarks),
            ("Create Desktop Folder", self._open_folder_utilities),
            ("Open Recycle Bin", self.open_recycle_bin),
        )
        for index, (text, callback) in enumerate(actions):
            button = QPushButton(text)
            styles.apply_page_control_size(button)
            button.setProperty("styleFontSize", 13)
            button.setStyleSheet(styles.organizing_button_style(13))
            button.clicked.connect(callback)
            quick_layout.addWidget(button, index // 2, index % 2)
        layout.addWidget(quick_row, 0, Qt.AlignmentFlag.AlignHCenter)
        self.refresh_overview()

    def _build_monitor_rules_page(self) -> None:
        layout = self.page_content_layouts["monitor_rules"]
        self.monitor_rules_page = MonitorRulesPage(
            self.page_by_id["monitor_rules"],
            rules=self.state.get("monitor_rules", []),
            app_hwnd=int(self.winId()),
            on_rules_changed=self.set_monitor_rules,
        )
        self.monitor_rules_add_button = self.monitor_rules_page.add_button
        layout.addWidget(self.monitor_rules_page)

    def _populate_navigation(self) -> None:
        self.navigation_shell.populate()

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

    def _apply_navigation_theme(self) -> None:
        if hasattr(self, "navigation_list"):
            self.navigation_list.setStyleSheet(styles.navigation_list_style())
            self._refresh_navigation_icons()
        if hasattr(self, "version_label"):
            self.version_label.setStyleSheet(styles.sidebar_version_label_style())
        for name in ("OverviewSummary", "MonitorRulesEmptyState"):
            for frame in self.findChildren(QFrame, name):
                frame.setStyleSheet(styles.summary_frame_style())

    def _on_navigation_changed(self, row: int) -> None:
        self.navigation_shell.selection_changed(row)

    def navigate_to_page(self, page_id: str, *, persist: bool = True) -> None:
        self.navigation_shell.navigate_to(page_id, persist=persist)

    def _open_folder_utilities(self) -> None:
        self.navigate_to_page("folder_utilities")
        folder_input = getattr(self, "folder_input", None)
        if folder_input is not None:
            folder_input.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def refresh_overview(self) -> None:
        labels = getattr(self, "overview_status_labels", None)
        if not labels:
            return
        labels["screen_mover"].setText(
            "On" if self.state.get("title_bar_dock_enabled", True) else "Off"
        )
        drive_count = len(getattr(self, "_overview_connected_drives", set()))
        labels["drives"].setText(
            f"{drive_count} connected" if drive_count else "None connected"
        )
        labels["backup_path"].setText(
            str(self.state.get("master_backup_output_path", "Not set"))
        )
        labels["recycle"].setText(
            "On" if self.state.get("recycle_bin_auto_clean_enabled", False) else "Off"
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

        for button_name in ("dark_mode_btn", "desktop_zen_btn"):
            refresh_icon = getattr(
                getattr(self, button_name, None), "_refresh_toggle_icon", None
            )
            if callable(refresh_icon):
                refresh_icon()

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

        if hasattr(self, "right_tools_panel"):
            if hasattr(self.right_tools_panel, "sidebar_output"):
                self.right_tools_panel._apply_sidebar_output_theme()
            if hasattr(self.right_tools_panel, "drive_space_list"):
                self.right_tools_panel._apply_drive_space_list_style()

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
        self._apply_navigation_theme()

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



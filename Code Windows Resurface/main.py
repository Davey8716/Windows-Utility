
import sys
import ctypes
from ctypes import wintypes
from pathlib import Path
import styles
import win32gui
import win32con
from PySide6.QtGui import QColor

from app_notifications import WindowMessageMixin
from app_paths import MasterBackupPathsMixin
from desktop_operations import DesktopOperationsMixin
from external_drive_mixin import ExternalDriveMixin
from left_panel_gui import LeftPanelBuilder
from right_utility_gui import (
    AdvancedToolsPanel as RightAdvancedToolsPanel,
    get_drive_info,
)
from screen_mover import ScreenMover, perform_window_action
from tray_toggles import TrayIconManager, resolve_application_icon
from utility_toggles import  UtilityActionsManager 
from state_manager import load_state, save_state
from tooltips import QtTooltipManager, tooltip_text
from PySide6.QtCore import QObject, Qt, QTimer, Signal

from PySide6.QtWidgets import (
    QWidget,
    QComboBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QScrollArea,
    QLineEdit,
    QApplication,
    QFrame,
    QMessageBox,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
)

MUTEX_NAME = "Windows Resurface"
WM_QUERYENDSESSION = 0x0011
ENDSESSION_LOGOFF = 0x80000000
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
NOTIFY_FOR_THIS_SESSION = 0
WM_APP_RESTORE_INSTANCE = 0x8001


class SeverityComboItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        background = index.data(Qt.ItemDataRole.BackgroundRole)
        foreground = index.data(Qt.ItemDataRole.ForegroundRole)

        bg_color = (
            background.color()
            if hasattr(background, "color")
            else background
            if isinstance(background, QColor)
            else None
        )
        fg_color = (
            foreground.color()
            if hasattr(foreground, "color")
            else foreground
            if isinstance(foreground, QColor)
            else styles.theme_text_color()
        )

        painter.save()

        if bg_color is not None:
            fill_color = bg_color.lighter(112) if option.state & QStyle.StateFlag.State_Selected else bg_color
            painter.fillRect(option.rect, fill_color)

        text_rect = option.rect.adjusted(10, 0, -8, 0)
        painter.setPen(fg_color)
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            index.data(Qt.ItemDataRole.DisplayRole) or "",
        )
        painter.restore()


class ScreenMoverActionBridge(QObject):
    action_requested = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.action_requested.connect(window.handle_screen_mover_self_action)

    def dispatch(self, action: str) -> None:
        self.action_requested.emit(action)


def bring_existing_instance_to_front():
    target_hwnd = None

    def enum_handler(hwnd, _):
        nonlocal target_hwnd
        try:
            title = win32gui.GetWindowText(hwnd)
        except Exception:
            return True

        if "Windows Resurface" in title and hwnd != 0:
            target_hwnd = hwnd

        return True

    try:
        ctypes.windll.kernel32.SetLastError(0)
        win32gui.EnumWindows(enum_handler, None)
    except Exception as e:
        print("[RESTORE] enumeration failed:", e)
        return

    if not target_hwnd:
        return

    try:
        win32gui.PostMessage(target_hwnd, WM_APP_RESTORE_INSTANCE, 0, 0)
    except Exception as e:
        print("[RESTORE] failed:", e)

def ensure_single_instance():
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_error = kernel32.GetLastError()

    ERROR_ALREADY_EXISTS = 183
    if last_error == ERROR_ALREADY_EXISTS:
        bring_existing_instance_to_front()
        sys.exit(0)

    return mutex

class UtilityControlApp(
    MasterBackupPathsMixin,
    WindowMessageMixin,
    ExternalDriveMixin,
    DesktopOperationsMixin,
    QWidget,
):
    MAIN_PANEL_WIDTH = 450
    RIGHT_PANEL_WIDTH = MAIN_PANEL_WIDTH + 65
    MAIN_SECTION_SIDE_PADDING = 14
    LEFT_TOGGLE_RIGHT_INSET = 14
    LEFT_SECTION_TOP_MARGIN = 5
    LEFT_SECTION_BOTTOM_MARGIN = 12
    LEFT_SECTION_COLLAPSED_TOP_MARGIN = 10
    LEFT_SECTION_COLLAPSED_BOTTOM_MARGIN = 0
    LEFT_SECTION_COLLAPSED_SPACER = 0
    USER_INTERFACE_TOP_SPACER = 0
    SCREEN_MOVER_TOP_SPACER = 0
    DRIVE_REMINDER_TOP_SPACER = 0
    ORGANISING_SECTION_TOP_SPACER = 0
    FOLDER_UTILITIES_TOP_SPACER = 0
    RECYCLE_BIN_ACTIONS_TOP_SPACER = 0
    MAIN_SECTION_FRAME_WIDTH = 405
    LEFT_SECTION_VISIBLE_FRAME_WIDTH = MAIN_SECTION_FRAME_WIDTH - 4
    MAIN_SECTION_OUTER_WIDTH = (
        MAIN_SECTION_FRAME_WIDTH + (MAIN_SECTION_SIDE_PADDING * 2)
    )

    def __init__(self):
        super().__init__()

        self.state = load_state()
        self.saved_state = self.state
        styles.set_theme(bool(self.state.get("theme_dark", True)))
        self.setWindowTitle("Windows Resurface")
        self.setStyleSheet(styles.window_style() + styles.tooltip_style())
        self.setWindowIcon(resolve_application_icon(self))
        self.COLLAPSED_WIDTH = 470
        self.EXPANDED_WIDTH = self.COLLAPSED_WIDTH + self.RIGHT_PANEL_WIDTH
        self.ADVANCED_PANEL_WIDTH = self.EXPANDED_WIDTH - self.COLLAPSED_WIDTH
        self.WINDOW_WIDTH = self.COLLAPSED_WIDTH
        self.WINDOW_HEIGHT = 875
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
        self.advanced_settings_open = bool(self.state.get("advanced_panel_open", False))
        self.collapsible_sections = []
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
        )
        self.screen_mover.start()
        
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

    def handle_screen_mover_self_action(self, action: str) -> None:
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
            self.screen_mover.stop()
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

        self.root_container = QWidget(self)
        self.root_container.setGeometry(0, 0, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

        self.main_scroll = QScrollArea(self.root_container)
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.main_scroll.setFixedWidth(self.MAIN_PANEL_WIDTH)
        self.main_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.main_scroll.setViewportMargins(0, 0, 0, 0)

        self.advanced_settings_panel = QFrame(self.root_container)
        self.advanced_settings_panel.setFixedWidth(self.ADVANCED_PANEL_WIDTH)

        self.advanced_settings_layout = QVBoxLayout(self.advanced_settings_panel)
        self.advanced_settings_layout.setContentsMargins(0, 0, 0, 0)
        self.advanced_settings_layout.setSpacing(10)
        self.advanced_settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.right_tools_panel = RightAdvancedToolsPanel(self)
        self.advanced_settings_layout.addWidget(self.right_tools_panel)
        self.advanced_settings_panel.hide()

        self.advanced_settings_toggle = QToolButton(self.root_container)
        self.advanced_settings_toggle.setProperty("sidePanelToggleButton", True)
        self.advanced_settings_toggle.setCursor(Qt.CursorShape.ArrowCursor)
        self.advanced_settings_toggle.setArrowType(Qt.ArrowType.NoArrow)
        self.advanced_settings_toggle.setText(
            styles.arrow_glyph(Qt.ArrowType.RightArrow)
        )
        self.advanced_settings_toggle.setStyleSheet(
            styles.side_panel_toggle_style(
                styles.theme_text_color(),
                styles.SURFACE_DARK,
            )
        )
        side_panel_slot_width, side_panel_slot_height = (
            styles.side_panel_toggle_slot_size()
        )
        self.advanced_settings_toggle.setFixedSize(
            side_panel_slot_width,
            side_panel_slot_height,
        )
        self.register_tooltip(
            self.advanced_settings_toggle,
            tooltip_text("side_panel_toggle"),
        )
        self.advanced_settings_toggle.clicked.connect(
            self.toggle_advanced_settings_panel
        )
        self.advanced_settings_toggle.raise_()

        self.main_frame = QWidget()
        self.main_frame.setMinimumWidth(self.MAIN_SECTION_OUTER_WIDTH)
        self.main_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.main_scroll.setWidget(self.main_frame)

        self.main_layout = QVBoxLayout(self.main_frame)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)
        self.main_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        
        LeftPanelBuilder(self).build()

        if self.advanced_settings_open:
            self.WINDOW_WIDTH = self.EXPANDED_WIDTH
            self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
            self.advanced_settings_panel.show()
            self.advanced_settings_toggle.setText(
                styles.arrow_glyph(Qt.ArrowType.LeftArrow)
            )

        self._update_panel_geometries()
        self._position_advanced_settings_toggle()

    def toggle_advanced_settings_panel(self):
        self.advanced_settings_open = not self.advanced_settings_open
        self.state["advanced_panel_open"] = self.advanced_settings_open

        if self.advanced_settings_open:
            self.WINDOW_WIDTH = self.EXPANDED_WIDTH
            self.advanced_settings_panel.show()
            self.advanced_settings_toggle.setText(
                styles.arrow_glyph(Qt.ArrowType.LeftArrow)
            )
        else:
            self.WINDOW_WIDTH = self.COLLAPSED_WIDTH
            self.advanced_settings_panel.hide()
            self.advanced_settings_toggle.setText(
                styles.arrow_glyph(Qt.ArrowType.RightArrow)
            )

        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self._update_panel_geometries()
        self._position_advanced_settings_toggle()
        save_state(self.state)

    def _update_panel_geometries(self):
        self.root_container.setGeometry(0, 0, self.width(), self.height())
        self.main_scroll.setGeometry(0, 0, self.MAIN_PANEL_WIDTH, self.height())
        self.advanced_settings_panel.setGeometry(
            self.MAIN_PANEL_WIDTH,
            0,
            self.ADVANCED_PANEL_WIDTH,
            self.height(),
        )

    def _position_advanced_settings_toggle(self):
        x = self.MAIN_PANEL_WIDTH - self.advanced_settings_toggle.width() + 14
        y = (self.height() - self.advanced_settings_toggle.height()) // 2
        self.advanced_settings_toggle.move(x, y)

    def _set_left_section_open(self, section, is_open: bool):
        section.is_open = bool(is_open)
        section.content.setVisible(is_open)
        if hasattr(section, "frame"):
            section.frame.setVisible(is_open)
        if hasattr(section, "toggle_btn"):
            section.toggle_btn.setText(
                styles.arrow_glyph(
                    Qt.ArrowType.DownArrow if is_open else Qt.ArrowType.UpArrow
                )
            )
        self._sync_left_section_spacing(section)

    def _sync_left_section_spacing(self, section):
        if hasattr(section, "is_open"):
            is_open = bool(section.is_open)
        else:
            is_open = bool(section.content.isVisible())

        top_spacer = getattr(section, "top_spacer", None)
        if top_spacer is not None:
            spacer_height = (
                getattr(section, "expanded_spacer_height", self.LEFT_SECTION_COLLAPSED_SPACER)
                if is_open
                else self.LEFT_SECTION_COLLAPSED_SPACER
            )
            top_spacer.changeSize(
                0,
                spacer_height,
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed,
            )

        section_layout = getattr(section, "section_layout", None)
        if section_layout is not None:
            section_layout.setContentsMargins(
                self.MAIN_SECTION_SIDE_PADDING,
                self.LEFT_SECTION_TOP_MARGIN,
                self.MAIN_SECTION_SIDE_PADDING,
                self.LEFT_SECTION_BOTTOM_MARGIN,
            )

        main_layout = getattr(self, "main_layout", None)
        if main_layout is not None:
            main_layout.invalidate()

    def resizeEvent(self, event):
        self._update_panel_geometries()
        self._position_advanced_settings_toggle()
        self._refresh_master_backup_path_display()
        super().resizeEvent(event)

    def _get_arrow_colors(self):
        return {
            "text": styles.theme_text_color(),
            "hover": styles.SURFACE_HOVER_DARK,
        }

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

    def _apply_power_action_dropdown_style(self, combo: QComboBox) -> None:
        font_size = styles.coerce_font_size(
            combo.property("styleFontSize"),
            14,
        ) or 14
        combo.setStyleSheet(styles.power_combo_style(font_size))

        severity_map = combo.property("powerActionSeverityMap") or {}
        placeholder_text = combo.property("powerActionPlaceholder") or ""
        color_map = self._power_action_item_colors()
        text_color = styles.theme_text_color()

        for row in range(combo.count()):
            label = combo.itemText(row)
            severity = "placeholder" if label == placeholder_text else severity_map.get(label)
            if not severity:
                continue
            combo.setItemData(row, color_map[severity], Qt.ItemDataRole.BackgroundRole)
            combo.setItemData(row, text_color, Qt.ItemDataRole.ForegroundRole)

        if not isinstance(combo.itemDelegate(), SeverityComboItemDelegate):
            combo.setItemDelegate(SeverityComboItemDelegate(combo))

    def apply_theme(self, is_dark: bool):
        styles.set_theme(is_dark)
        self.setStyleSheet(styles.window_style() + styles.tooltip_style())

        for frame in self.findChildren(QFrame, "CollapsibleSectionFrame"):
            frame.setStyleSheet(styles.collapsible_section_frame_style())

        for line_edit in self.findChildren(QLineEdit):
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

        backup_path_label = getattr(self, "backup_path_input", None)
        if (
            backup_path_label is not None
            and backup_path_label.property("plainThemeLabelStyle")
        ):
            backup_path_label.setStyleSheet(styles.plain_theme_label_style(15))

        self._refresh_master_backup_path_display()

        for button in self.findChildren(QPushButton):
            font_size = styles.coerce_font_size(
                button.property("styleFontSize"),
                14,
            ) or 14
            button.setStyleSheet(styles.organizing_button_style(font_size=font_size))

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

        empty_label = getattr(self, "connected_drives_empty_label", None)
        if empty_label is not None:
            empty_label.setStyleSheet(
                styles.label_style(font_size=14, color=styles.theme_text_color())
            )

        if hasattr(self, "right_tools_panel"):
            if hasattr(self.right_tools_panel, "sidebar_output"):
                self.right_tools_panel._apply_sidebar_output_theme()
            if hasattr(self.right_tools_panel, "drive_space_list"):
                self.right_tools_panel._apply_drive_space_list_style()

        self.update_collapsible_arrow_colours()

    def update_collapsible_arrow_colours(self):
        colors = self._get_arrow_colors()

        for btn in self.findChildren(QToolButton):
            if btn.property("leftMasterToggleButton"):
                btn.setStyleSheet(
                    styles.left_master_toggle_style(
                        colors["text"],
                        colors["hover"],
                    )
                )
            elif btn.property("rightMasterToggleButton"):
                btn.setStyleSheet(
                    styles.right_master_toggle_style(
                        colors["text"],
                        colors["hover"],
                    )
                )
            elif btn.property("sidePanelToggleButton"):
                btn.setStyleSheet(
                    styles.side_panel_toggle_style(
                        colors["text"],
                        colors["hover"],
                    )
                )
            else:
                btn.setStyleSheet(
                    styles.section_toggle_style(
                        colors["text"],
                        colors["hover"],
                    )
                )

    def register_tooltip(self, widget: QWidget, text: str, delay: int = 10):
        manager = QtTooltipManager(widget, text, delay=delay)
        self._tooltip_managers.append(manager)
        return manager

    def save_section_states(self):
        left_states = {}
        for section in self.left_sections:
            section_id = getattr(section, "section_id", None)
            if section_id and hasattr(section, "content"):
                left_states[section_id] = bool(
                    getattr(section, "is_open", section.content.isVisible())
                )

        if left_states:
            self.state["left_section_states"] = left_states
            self.state["master_toggle_left"] = all(left_states.values())
            self.master_toggle_left_state = self.state["master_toggle_left"]

        right_states = {}
        for section in self.collapsible_sections:
            section_id = getattr(section, "section_id", None)
            is_open = getattr(section, "is_open", None)
            if section_id and is_open is not None:
                right_states[section_id] = bool(is_open)

        if right_states:
            self.state["right_section_states"] = right_states
            self.state["master_toggle_right"] = all(right_states.values())
            self.master_toggle_right_state = self.state["master_toggle_right"]

        self._refresh_master_toggle_buttons()

    def _refresh_master_toggle_buttons(self):
        if hasattr(self, "master_collapse_btn_left"):
            self.master_collapse_btn_left.setText(
                styles.arrow_glyph(
                    Qt.ArrowType.DownArrow
                    if self.state.get("master_toggle_left", True)
                    else Qt.ArrowType.UpArrow
                )
            )

        right_button = getattr(self, "right_tools_panel", None)
        if right_button and hasattr(right_button, "master_collapse_btn_right"):
            right_button.master_collapse_btn_right.setText(
                styles.arrow_glyph(
                    Qt.ArrowType.DownArrow
                    if self.state.get("master_toggle_right", False)
                    else Qt.ArrowType.UpArrow
                )
            )

    def save_all_settings(self):
        self.save_section_states()
        self.state["main_always_on_top_enabled"] = bool(
            self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        )
        self.state["advanced_panel_open"] = self.advanced_settings_open
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

def main():
    mutex = ensure_single_instance()
    app = QApplication(sys.argv)
    window = UtilityControlApp()   
    window._instance_mutex = mutex
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()


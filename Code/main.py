
import sys
import ctypes
from ctypes import wintypes
from pathlib import Path
import styles
import win32gui
import win32con
from PySide6.QtGui import QColor, QIcon

from app_notifications import WindowMessageMixin
from app_paths import MasterBackupPathsMixin
from desktop_operations import DesktopOperationsMixin
from external_drive_mixin import ExternalDriveMixin
from right_utility_gui import (
    AdvancedToolsPanel as RightAdvancedToolsPanel,
    get_drive_info,
)
from screen_mover import SCREEN_MOVER
from tray_toggles import TrayIconManager, resolve_application_icon
from utility_toggles import  UtilityActionsManager 
from state_manager import load_state, save_state
from tooltips import QtTooltipManager, left_section_toggle_tooltip, tooltip_text
from PySide6.QtCore import Qt, QTimer, QSize

from PySide6.QtWidgets import (
    QWidget,
    QComboBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QScrollArea,
    QHBoxLayout,
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
        self.actions = UtilityActionsManager(self)
        self.tray_manager = TrayIconManager(self)

        self._build_ui()
        self._known_external_drives = self._current_external_drives()
        self._drive_change_timer = QTimer(self)
        self._drive_change_timer.timeout.connect(self._check_external_drive_changes)
        self._drive_change_timer.start(3000)
        self.tray_manager.create_tray_icon()
        SCREEN_MOVER.configure(app_hwnd=int(self.winId()))
        SCREEN_MOVER.start()
        
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.show()
        self._apply_fixed_window_style()
        self._register_session_notifications()
        QTimer.singleShot(0, self.run_recycle_bin_auto_cleanup)

        ctypes.windll.user32.SetWindowPos(
            int(self.winId()),
            -1,
            0, 0, 0, 0,
            0x0003
        )

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

    def prepare_for_shutdown(self):
        if self._shutdown_complete:
            return

        self._shutdown_complete = True
        self._unregister_session_notifications()

        try:
            SCREEN_MOVER.stop()
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
        
        state = self.state
        
        header = QWidget(self.main_frame)
        header.setFixedWidth(self.MAIN_SECTION_OUTER_WIDTH)
        header.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(
            self.MAIN_SECTION_SIDE_PADDING,
            10,
            self.MAIN_SECTION_SIDE_PADDING + (
                self.MAIN_SECTION_FRAME_WIDTH - self.LEFT_SECTION_VISIBLE_FRAME_WIDTH
            ) + self.LEFT_TOGGLE_RIGHT_INSET,
            10,
        )

        title = QLabel("Windows Resurface", header)
        title.setStyleSheet(styles.label_style(font_size=20))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        master_btn = QToolButton(header)
        master_btn.setProperty("leftMasterToggleButton", True)
        master_btn.setCursor(Qt.CursorShape.ArrowCursor)
        master_btn.setArrowType(Qt.ArrowType.NoArrow)
        master_btn.setText(styles.arrow_glyph(Qt.ArrowType.DownArrow))
        master_btn.setStyleSheet(
            styles.left_master_toggle_style(
                styles.theme_text_color(),
                styles.SURFACE_DARK,
            )
        )
        left_master_slot_width, left_master_slot_height = (
            styles.left_master_toggle_slot_size()
        )
        master_btn.setFixedSize(
            left_master_slot_width,
            left_master_slot_height,
        )
        self.master_collapse_btn_left = master_btn
        self.register_tooltip(master_btn, tooltip_text("master_collapse_left"))

        header_spacer = QWidget(header)
        header_spacer.setFixedSize(
            left_master_slot_width,
            left_master_slot_height,
        )

        header_layout.addWidget(header_spacer)
        header_layout.addStretch()
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(master_btn)

        self.main_layout.addWidget(header, 0, Qt.AlignmentFlag.AlignLeft)
        
        self.left_sections = []
        self.master_toggle_left_state = bool(state.get("master_toggle_left", True))

        def add_left_section_spacer(height: int):
            self.main_layout.addSpacing(height)
            return self.main_layout.itemAt(self.main_layout.count() - 1).spacerItem()

        def register_left_section(
            section: QWidget,
            *,
            top_spacer,
            expanded_spacer_height: int,
        ) -> None:
            section.top_spacer = top_spacer
            section.expanded_spacer_height = expanded_spacer_height
            self.left_sections.append(section)
            self._sync_left_section_spacing(section)

        def make_section(title_text, section_id: str):
            section = QWidget(self.main_frame)
            section.section_id = section_id
            section.setFixedWidth(self.MAIN_SECTION_OUTER_WIDTH)
            section.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            layout = QVBoxLayout(section)
            section.section_layout = layout
            layout.setContentsMargins(
                self.MAIN_SECTION_SIDE_PADDING,
                self.LEFT_SECTION_TOP_MARGIN,
                self.MAIN_SECTION_SIDE_PADDING,
                self.LEFT_SECTION_BOTTOM_MARGIN,
            )
            layout.setSpacing(4)

            sec_header = QWidget(section)
            sec_header.setMaximumWidth(self.LEFT_SECTION_VISIBLE_FRAME_WIDTH)
            sec_header.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            sec_header_layout = QHBoxLayout(sec_header)
            sec_header_layout.setContentsMargins(
                0,
                0,
                self.LEFT_TOGGLE_RIGHT_INSET,
                0,
            )

            sec_title = QLabel(title_text, sec_header)
            sec_title.setStyleSheet(styles.label_style(font_size=15))

            toggle = QToolButton(sec_header)
            toggle.setCursor(Qt.CursorShape.ArrowCursor)
            toggle.setArrowType(Qt.ArrowType.NoArrow)
            toggle.setText(styles.arrow_glyph(Qt.ArrowType.DownArrow))
            toggle.setStyleSheet(
                styles.section_toggle_style(
                    styles.theme_text_color(),
                    styles.SURFACE_DARK,
                )
            )
            section_toggle_slot_width, section_toggle_slot_height = (
                styles.section_toggle_slot_size()
            )
            toggle.setFixedSize(
                section_toggle_slot_width,
                section_toggle_slot_height,
            )
            section.toggle_btn = toggle
            self.register_tooltip(
                toggle,
                left_section_toggle_tooltip(title_text),
            )

            title_spacer = QWidget(sec_header)
            title_spacer.setFixedSize(
                section_toggle_slot_width,
                section_toggle_slot_height,
            )

            sec_header_layout.addWidget(title_spacer)
            sec_header_layout.addStretch()
            sec_header_layout.addWidget(sec_title)
            sec_header_layout.addStretch()
            sec_header_layout.addWidget(toggle)

            frame = QFrame(section)
            section.frame = frame
            frame.setObjectName("CollapsibleSectionFrame")
            frame.setMaximumWidth(self.LEFT_SECTION_VISIBLE_FRAME_WIDTH)
            frame.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            frame.setStyleSheet(styles.LEFT_PANEL_FRAME_STYLE)
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(2, 2, 2, 2)
            frame_layout.setSpacing(0)

            section.content = QWidget(frame)
            content = section.content
            content.setMaximumWidth(self.LEFT_SECTION_VISIBLE_FRAME_WIDTH - 4)
            content.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            initial_open = self.state.get("left_section_states", {}).get(section_id, True)
            section.is_open = bool(initial_open)
            content.setVisible(initial_open)
            frame.setVisible(initial_open)

            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(10, 10, 10, 10)

            layout.addWidget(sec_header)
            frame_layout.addWidget(content)
            layout.addWidget(frame)
            

            def toggle_section():
                self._set_left_section_open(section, not bool(section.is_open))
                self.save_all_settings()

            toggle.clicked.connect(toggle_section)
            toggle.setText(
                styles.arrow_glyph(
                    Qt.ArrowType.DownArrow if initial_open else Qt.ArrowType.UpArrow
                )
            )

            return section, content_layout

        def make_toggle_button(text: str, checked: bool = False):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setChecked(checked)
            button.setCursor(Qt.CursorShape.ArrowCursor)
            styles.apply_default_button_size(button)
            button.setProperty("styleFontSize", 14)
            button.setStyleSheet(styles.toggle_button_style(font_size=14))
            return button

        def make_compact_toggle_button(
            text: str,
            checked: bool = False,
            *,
            width: int,
            font_size: int = 11,
        ) -> QPushButton:
            button = make_toggle_button(text, checked)
            styles.apply_default_button_size(button, width=width)
            button.setProperty("styleFontSize", font_size)
            button.setStyleSheet(styles.toggle_button_style(font_size=font_size))
            return button

        def bind_toggle_state_text(
            button: QPushButton,
            label: str,
            *,
            on_text: str = "On",
            off_text: str = "Off",
        ) -> None:
            def update_text(checked: bool) -> None:
                button.setText(f"{label} {on_text}" if checked else f"{label} {off_text}")

            update_text(button.isChecked())
            button.toggled.connect(update_text)

        def bind_toggle_state_icon(
            button: QPushButton,
            *,
            checked_icon_path: Path,
            unchecked_icon_path: Path,
            icon_size: int = 18,
        ) -> None:
            checked_icon = QIcon(str(checked_icon_path))
            unchecked_icon = QIcon(str(unchecked_icon_path))
            button.setIconSize(QSize(icon_size, icon_size))

            def update_icon(checked: bool) -> None:
                button.setIcon(checked_icon if checked else unchecked_icon)

            update_icon(button.isChecked())
            button.toggled.connect(update_icon)

        def bind_toggle_state_text_with_checked_icon(
            button: QPushButton,
            label: str,
            *,
            checked_icon_path: Path,
            checked_text: str = "",
            unchecked_text: str = "Off",
            icon_size: int = 18,
        ) -> None:
            checked_icon = QIcon(str(checked_icon_path))
            button.setIconSize(QSize(icon_size, icon_size))

            def update_state(checked: bool) -> None:
                if checked:
                    button.setText(f"{label} {checked_text}".rstrip())
                    button.setIcon(checked_icon)
                else:
                    button.setText(f"{label} {unchecked_text}")
                    button.setIcon(QIcon())

            update_state(button.isChecked())
            button.toggled.connect(update_state)

        def bind_toggle_icon_only(
            button: QPushButton,
            *,
            checked_icon_path: Path,
            unchecked_icon_path: Path,
            icon_size: int = 18,
        ) -> None:
            checked_icon = QIcon(str(checked_icon_path))
            unchecked_icon = QIcon(str(unchecked_icon_path))
            button.setIconSize(QSize(icon_size, icon_size))

            def update_state(checked: bool) -> None:
                button.setText("")
                button.setIcon(checked_icon if checked else unchecked_icon)

            update_state(button.isChecked())
            button.toggled.connect(update_state)

        def bind_combo_placeholder_icon(
            combo: QComboBox,
            *,
            placeholder: str,
            icon_path: Path,
            icon_size: int = 18,
        ) -> None:
            combo.setIconSize(QSize(icon_size, icon_size))
            placeholder_index = combo.findText(placeholder)
            if placeholder_index >= 0:
                combo.setItemIcon(placeholder_index, QIcon(str(icon_path)))

        def install_green_flash(button: QPushButton):
            def flash_active():
                button.setProperty("flashActive", True)
                button.style().unpolish(button)
                button.style().polish(button)
                QTimer.singleShot(180, clear_flash)

            def clear_flash():
                button.setProperty("flashActive", False)
                button.style().unpolish(button)
                button.style().polish(button)

            button.clicked.connect(flash_active)
            return button

        def style_organizing_button(button: QPushButton):
            button.setCheckable(False)
            button.setAutoExclusive(False)
            button.setCursor(Qt.CursorShape.ArrowCursor)
            styles.apply_default_button_size(button)
            button.setProperty("styleFontSize", 14)
            button.setStyleSheet(styles.organizing_button_style(font_size=14))
            install_green_flash(button)
            return button

        def make_action_dropdown(
            placeholder: str,
            actions_map: dict[str, callable],
            *,
            power_action_style: bool = False,
            severity_map: dict[str, str] | None = None,
        ):
            combo = QComboBox()
            combo.addItem(placeholder)
            combo.addItems(actions_map.keys())
            combo.setCurrentText(placeholder)
            combo.view().setRowHidden(0, True)
            combo.setCursor(Qt.CursorShape.ArrowCursor)
            styles.apply_default_button_size(combo)
            combo.setProperty("styleFontSize", 14)
            if power_action_style:
                combo.setProperty("powerActionStyle", True)
                combo.setProperty("powerActionPlaceholder", placeholder)
                combo.setProperty("powerActionSeverityMap", severity_map or {})
                self._apply_power_action_dropdown_style(combo)
            else:
                combo.setStyleSheet(styles.organizing_combo_style(14))

            def run_action(text: str):
                if text == placeholder:
                    return
                action = actions_map.get(text)
                if action:
                    action()
                combo.setCurrentText(placeholder)

            combo.currentTextChanged.connect(run_action)
            return combo

        def make_value_dropdown(values: list[str], current_value: str) -> QComboBox:
            combo = QComboBox()
            combo.addItems(values)
            combo.setCurrentText(current_value if current_value in values else values[0])
            combo.setCursor(Qt.CursorShape.ArrowCursor)
            styles.apply_default_button_size(combo)
            combo.setProperty("styleFontSize", 14)
            combo.setStyleSheet(styles.organizing_combo_style(14))
            return combo

        ui_section, ui_layout = make_section("User Interface", "user_interface")
        ui_section_spacer = add_left_section_spacer(self.USER_INTERFACE_TOP_SPACER)
        self.main_layout.addWidget(ui_section)
        register_left_section(
            ui_section,
            top_spacer=ui_section_spacer,
            expanded_spacer_height=self.USER_INTERFACE_TOP_SPACER,
        )

        compact_toggle_width = (styles.DEFAULT_BUTTON_WIDTH - 10) // 2

        ui_top_row = QWidget(ui_section.content)
        ui_top_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ui_top_row_layout = QHBoxLayout(ui_top_row)
        ui_top_row_layout.setContentsMargins(0, 0, 0, 0)
        ui_top_row_layout.setSpacing(10)
        ui_layout.addWidget(ui_top_row)

        dark_mode_btn = make_compact_toggle_button(
            "",
            state.get("theme_dark", True),
            width=compact_toggle_width,
            font_size=10,
        )
        bind_toggle_icon_only(
            dark_mode_btn,
            checked_icon_path=Path(__file__).resolve().parent.parent / "App Icons" / "Dark Theme" / "Dark Mode.png",
            unchecked_icon_path=Path(__file__).resolve().parent.parent / "App Icons" / "Dark Theme" / "Light Mode.png",
            icon_size=18,
        )
        ui_top_row_layout.addWidget(dark_mode_btn)
        self.register_tooltip(dark_mode_btn, tooltip_text("dark_mode"))

        desktop_zen_mode_enabled = bool(state.get("desktop_zen_mode_enabled", False))
        current_icons_visible = self.actions.desktop_icons_visible()
        if current_icons_visible is not None:
            desktop_zen_mode_enabled = not current_icons_visible
            state["desktop_zen_mode_enabled"] = desktop_zen_mode_enabled
            save_state(state)

        desktop_zen_btn = make_compact_toggle_button(
            "Zen Mode",
            desktop_zen_mode_enabled,
            width=compact_toggle_width,
            font_size=10,
        )
        self.desktop_zen_btn = desktop_zen_btn
        bind_toggle_state_text_with_checked_icon(
            desktop_zen_btn,
            "Zen Mode",
            checked_icon_path=Path(__file__).resolve().parent.parent / "App Icons" / "Zen Mode On.png",
            unchecked_text="Off",
            icon_size=18,
        )
        ui_top_row_layout.addWidget(desktop_zen_btn)
        self.register_tooltip(desktop_zen_btn, tooltip_text("desktop_zen_mode"))

        power_dropdown = make_action_dropdown(
            " Power and Session ",
            {
                "Lock PC": lambda: self._confirm_power_action("Lock PC", self.right_tools_panel.run_lock_pc),
                "Sleep": lambda: self._confirm_power_action("Sleep", self.right_tools_panel.run_sleep),
                "Log out": lambda: self._confirm_power_action("Log out", self.right_tools_panel.run_logout),
                "Restart": lambda: self._confirm_power_action("Restart", self.right_tools_panel.run_restart),
                "Shutdown": lambda: self._confirm_power_action("Shutdown", self.right_tools_panel.run_shutdown),
            },
            power_action_style=True,
            severity_map={
                "Lock PC": "blue",
                "Sleep": "yellow",
                "Restart": "orange_red",
                "Log out": "orange",
                "Shutdown": "red",
            },
        )
        ui_top_row_layout.addWidget(power_dropdown)
        ui_top_row_layout.setStretch(2, 1)
        self.register_tooltip(power_dropdown, tooltip_text("power_options"))

        ui_middle_row = QWidget(ui_section.content)
        ui_middle_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ui_middle_row_layout = QHBoxLayout(ui_middle_row)
        ui_middle_row_layout.setContentsMargins(0, 0, 0, 0)
        ui_middle_row_layout.setSpacing(10)
        ui_layout.addWidget(ui_middle_row)

        always_on_top_btn = make_toggle_button("Always on Top", state.get("main_always_on_top_enabled", True))
        bind_toggle_state_text(always_on_top_btn, "Always on Top")
        ui_middle_row_layout.addWidget(always_on_top_btn)
        self.register_tooltip(always_on_top_btn, tooltip_text("always_on_top"))

        tooltips_btn = make_toggle_button("Tooltips", state.get("tooltips_enabled", True))
        bind_toggle_state_text(tooltips_btn, "Tooltips")
        ui_middle_row_layout.addWidget(tooltips_btn)
        self.register_tooltip(tooltips_btn, tooltip_text("enable_tooltips"))

        ui_bottom_row = QWidget(ui_section.content)
        ui_bottom_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ui_bottom_row_layout = QHBoxLayout(ui_bottom_row)
        ui_bottom_row_layout.setContentsMargins(0, 0, 0, 0)
        ui_bottom_row_layout.setSpacing(10)
        ui_layout.addWidget(ui_bottom_row)

        maximize_all_enabled = bool(
            state.get(
                "maximize_all_enabled",
                not state.get("minimize_all_enabled", False),
            )
        )
        max_all_btn = make_toggle_button("Maximize All", maximize_all_enabled)
        bind_toggle_state_text(max_all_btn, "Maximize All")
        ui_bottom_row_layout.addWidget(max_all_btn)
        self.register_tooltip(max_all_btn, tooltip_text("maximize_all"))

        minimize_after_use_btn = make_toggle_button(
            "Minimize After Use",
            bool(state.get("minimize_after_use_enabled", True)),
        )
        bind_toggle_state_text(
            minimize_after_use_btn,
            "Minimize After Use",
            on_text="On",
            off_text="Off",
        )
        minimize_after_use_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        styles.apply_default_button_size(minimize_after_use_btn)
        ui_bottom_row_layout.addWidget(minimize_after_use_btn)
        self.register_tooltip(
            minimize_after_use_btn,
            tooltip_text("minimize_after_use"),
        )

        def on_dark_mode_changed(checked: bool):
            state["theme_dark"] = checked
            self.apply_theme(checked)
            save_state(state)

        dark_mode_btn.toggled.connect(on_dark_mode_changed)

        def on_always_on_top_changed(checked):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
            self.show() 

            state["main_always_on_top_enabled"] = checked
            save_state(state)

        always_on_top_btn.toggled.connect(on_always_on_top_changed)
        
        def on_tooltips_changed(checked):
            state["tooltips_enabled"] = checked
            self.actions.tooltips_toggle(checked)
            save_state(state)

        tooltips_btn.toggled.connect(on_tooltips_changed)
        
        def on_max_all_changed(checked: bool):
            state["maximize_all_enabled"] = checked
            state.pop("minimize_all_enabled", None)
            save_state(state)

            if hasattr(self.actions, "maximize_all_toggle"):
                self.actions.maximize_all_toggle(checked)
            elif hasattr(self.actions, "minimize_all_toggle"):
                self.actions.minimize_all_toggle(checked)
            elif hasattr(self.actions, "maximize_all"):
                self.actions.maximize_all(checked)
            elif hasattr(self.actions, "minimize_all"):
                self.actions.minimize_all(checked)

        max_all_btn.toggled.connect(on_max_all_changed)

        def on_minimize_after_use_changed(checked: bool):
            state["minimize_after_use_enabled"] = checked
            save_state(state)

        minimize_after_use_btn.toggled.connect(on_minimize_after_use_changed)

        def on_desktop_zen_mode_changed(checked: bool):
            state["desktop_zen_mode_enabled"] = checked

            if self.actions.desktop_zen_mode_toggle(checked) is not None:
                save_state(state)
                if checked and getattr(self, "tray_manager", None):
                    self._minimize_self_if_configured()
                return

            desktop_zen_btn.blockSignals(True)
            desktop_zen_btn.setChecked(not checked)
            desktop_zen_btn.blockSignals(False)
            state["desktop_zen_mode_enabled"] = not checked
            save_state(state)
            self._show_timed_message(
                QMessageBox.Icon.Warning,
                "Desktop Icons",
                "Could not change desktop icon visibility.",
            )

        desktop_zen_btn.toggled.connect(on_desktop_zen_mode_changed)

        screen_section, screen_layout = make_section("Screen Mover", "screen_mover")

        screen_row = QWidget(screen_section.content)
        screen_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        screen_row_layout = QHBoxLayout(screen_row)
        screen_row_layout.setContentsMargins(0, 0, 0, 0)
        screen_row_layout.setSpacing(10)
        screen_layout.addWidget(screen_row)

        title_bar_dock_btn = make_toggle_button("Title Bar Dock", state.get("title_bar_dock_enabled", True))
        bind_toggle_state_text(title_bar_dock_btn, "Title Bar Dock")
        screen_row_layout.addWidget(title_bar_dock_btn)
        self.register_tooltip(title_bar_dock_btn, tooltip_text("title_bar_dock"))

        def on_title_bar_dock_changed(checked: bool):
            state["title_bar_dock_enabled"] = checked
            save_state(state)
            SCREEN_MOVER.title_bar_dock_enabled = checked

        title_bar_dock_btn.toggled.connect(on_title_bar_dock_changed)

        screen_move_button_combo = QComboBox()
        screen_move_button_combo.addItem("Move Button: Off", "off")
        screen_move_button_combo.addItem("Left Mouse Button", "left")
        screen_move_button_combo.addItem("Middle Mouse Button", "middle")
        screen_move_button_combo.addItem("Right Mouse Button", "right")
        screen_move_button_combo.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_default_button_size(screen_move_button_combo)
        screen_move_button_combo.setStyleSheet(styles.organizing_combo_style(14))

        def update_screen_move_combo_state() -> None:
            screen_move_button_combo.setProperty(
                "persistPressed",
                screen_move_button_combo.currentData() != "off",
            )
            screen_move_button_combo.style().unpolish(screen_move_button_combo)
            screen_move_button_combo.style().polish(screen_move_button_combo)

        stored_move_button = str(state.get("screen_mover_activation_button", "")).strip().lower()
        if stored_move_button not in {"left", "middle", "right", "off"}:
            stored_move_button = "middle" if state.get("mmb_activation_enabled", True) else "off"
        combo_index = screen_move_button_combo.findData(stored_move_button)
        if combo_index >= 0:
            screen_move_button_combo.setCurrentIndex(combo_index)
        update_screen_move_combo_state()

        screen_row_layout.addWidget(screen_move_button_combo)
        self.register_tooltip(screen_move_button_combo, tooltip_text("screen_move_button"))
        screen_row_layout.addStretch()

        def on_screen_move_button_changed(_text: str):
            button_value = screen_move_button_combo.currentData()
            state["screen_mover_activation_button"] = button_value
            state["mmb_activation_enabled"] = button_value == "middle"
            save_state(state)
            SCREEN_MOVER.activation_button = button_value
            update_screen_move_combo_state()

        screen_move_button_combo.currentTextChanged.connect(on_screen_move_button_changed)
        screen_section_spacer = add_left_section_spacer(self.SCREEN_MOVER_TOP_SPACER)
        self.main_layout.addWidget(screen_section)
        register_left_section(
            screen_section,
            top_spacer=screen_section_spacer,
            expanded_spacer_height=self.SCREEN_MOVER_TOP_SPACER,
        )

        usb_section, usb_layout = make_section("External Drive Reminder Options", "drive_reminder_options")

        def create_drive_reminder_combo(
            tooltip_key: str,
            state_key: str,
            legacy_enabled_key: str,
            items: list[tuple[str, str]],
        ) -> QComboBox:
            combo = QComboBox()
            for text, value in items:
                combo.addItem(text, value)
            combo.setCursor(Qt.CursorShape.ArrowCursor)
            combo.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
            combo.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            combo.setStyleSheet(styles.organizing_combo_style(14))

            def update_combo_state() -> None:
                combo.setProperty("persistPressed", combo.currentData() != "off")
                combo.style().unpolish(combo)
                combo.style().polish(combo)

            stored_value = str(state.get(state_key, "")).strip().lower()
            valid_values = {value for _, value in items}
            if stored_value not in valid_values:
                stored_value = items[1][1] if state.get(legacy_enabled_key, True) else "off"

            combo_index = combo.findData(stored_value)
            if combo_index >= 0:
                combo.setCurrentIndex(combo_index)
            update_combo_state()

            def on_combo_changed(_text: str):
                selected_value = combo.currentData()
                state[state_key] = selected_value
                state[legacy_enabled_key] = selected_value != "off"
                save_state(state)
                update_combo_state()

            combo.currentTextChanged.connect(on_combo_changed)
            self.register_tooltip(combo, tooltip_text(tooltip_key))
            return combo

        leave_reminder_row = QWidget()
        leave_reminder_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        leave_reminder_row_layout = QHBoxLayout(leave_reminder_row)
        leave_reminder_row_layout.setContentsMargins(0, 0, 0, 0)
        leave_reminder_row_layout.setSpacing(10)

        leave_reminder_btn = make_toggle_button(
            "Drive Leave Reminder Off",
            state.get("usb_idle_enabled", True),
        )
        bind_toggle_state_text(leave_reminder_btn, "Drive Leave Reminder")
        leave_reminder_btn.setFixedSize(
            190,
            styles.DEFAULT_BUTTON_HEIGHT,
        )
        leave_reminder_row_layout.addWidget(leave_reminder_btn)
        self.register_tooltip(leave_reminder_btn, tooltip_text("idle_plugged_reminder"))

        self.connected_drives_field = QComboBox()
        self.connected_drives_field.setEditable(False)
        self.connected_drives_field.setCursor(Qt.CursorShape.ArrowCursor)
        self.connected_drives_field.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        self.connected_drives_field.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.connected_drives_field.setMinimumContentsLength(
            len("No Drives Connected")
        )
        self.connected_drives_field.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.connected_drives_field.setProperty("connectedDrivesFieldStyle", True)
        self.connected_drives_field.setProperty("surfaceFieldStyle", True)
        self.connected_drives_field.setProperty("styleFontSize", 15)
        self.connected_drives_field.setStyleSheet(
            styles.connected_drives_combo_style(15)
        )
        self.connected_drives_field.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.connected_drives_field.view().viewport().installEventFilter(self)
        self.connected_drives_field.customContextMenuRequested.connect(
            self._show_connected_drives_context_menu
        )
        self.connected_drives_empty_label = QLabel("No Drives Connected")
        self.connected_drives_empty_label.setStyleSheet(
            styles.label_style(font_size=14, color=styles.theme_text_color())
        )
        self.connected_drives_empty_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self.connected_drives_empty_label.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        self.connected_drives_empty_label.hide()
        leave_reminder_row_layout.addWidget(self.connected_drives_field)
        leave_reminder_row_layout.addWidget(self.connected_drives_empty_label)
        usb_layout.addWidget(leave_reminder_row)
        self._refresh_connected_drive_status_label()

        def on_leave_reminder_changed(checked: bool):
            state["usb_idle_enabled"] = checked
            save_state(state)

        leave_reminder_btn.toggled.connect(on_leave_reminder_changed)

        plug_combo = create_drive_reminder_combo(
            "plug_unplug_notify",
            "usb_plug_notify_mode",
            "usb_plug_enabled",
            [
                ("Plug / Unplug Notify: Off", "off"),
                ("Show plug and unplug notifications", "on"),
            ],
        )
        usb_layout.addWidget(plug_combo)

        usb_section_spacer = add_left_section_spacer(self.DRIVE_REMINDER_TOP_SPACER)
        self.main_layout.addWidget(usb_section)
        register_left_section(
            usb_section,
            top_spacer=usb_section_spacer,
            expanded_spacer_height=self.DRIVE_REMINDER_TOP_SPACER,
        )

        org_section, org_layout = make_section("Organising Utilities", "organising_utilities")
        self.backup_path = self._get_master_backup_dir()

        desktop_actions_row = QWidget()
        desktop_actions_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        desktop_actions_row_layout = QHBoxLayout(desktop_actions_row)
        desktop_actions_row_layout.setContentsMargins(0, 0, 0, 0)
        desktop_actions_row_layout.setSpacing(10)

        screenshot_btn = QPushButton("Desktop Screenshot")
        style_organizing_button(screenshot_btn)
        desktop_actions_row_layout.addWidget(screenshot_btn)
        screenshot_btn.clicked.connect(self.take_desktop_screenshot)
        self.register_tooltip(screenshot_btn, tooltip_text("desktop_screenshot"))

        layout_actions_combo = make_action_dropdown(
            " Desktop Actions ",
            {
                "Capture Layout": self.capture_desktop_layout,
                "Restore Layout": self.restore_desktop_layout,
            },
        )
        desktop_actions_row_layout.addWidget(layout_actions_combo)
        org_layout.addWidget(desktop_actions_row)
        self.register_tooltip(layout_actions_combo, tooltip_text("capture_desktop_layout"))

        folder_row = QWidget()
        folder_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        folder_row_layout = QHBoxLayout(folder_row)
        folder_row_layout.setContentsMargins(0, 0, 0, 0)
        folder_row_layout.setSpacing(10)

        folder_btn = QPushButton("Folder → Desktop")
        style_organizing_button(folder_btn)
        self.register_tooltip(folder_btn, tooltip_text("folder_to_desktop"))

        folder_input = QLineEdit()
        folder_input.setPlaceholderText("Folder name")
        folder_input.setText(state.get("folder_to_desktop_name", ""))
        folder_input.setReadOnly(False)
        folder_input.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        folder_input.setProperty("framelessSurfaceFieldStyle", True)
        folder_input.setStyleSheet(styles.frameless_surfaced_line_edit_style(15))
        self.register_tooltip(folder_input, tooltip_text("folder_name_input"))

        folder_row_layout.addWidget(folder_btn)
        folder_row_layout.addWidget(folder_input)

        org_layout.addWidget(folder_row)

        def on_folder_name_changed(text: str):
            state["folder_to_desktop_name"] = text
            folder_btn.setEnabled(bool(text.strip()))
            save_state(state)

        def on_create_folder_clicked():
            self._create_desktop_folder(folder_input)

        folder_btn.setEnabled(bool(folder_input.text().strip()))
        folder_btn.clicked.connect(on_create_folder_clicked)
        folder_input.textChanged.connect(on_folder_name_changed)

        bookmarks_taskbar_row = QWidget()
        bookmarks_taskbar_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bookmarks_taskbar_row_layout = QHBoxLayout(bookmarks_taskbar_row)
        bookmarks_taskbar_row_layout.setContentsMargins(0, 0, 0, 0)
        bookmarks_taskbar_row_layout.setSpacing(10)

        brave_export_btn = QPushButton("Export Bookmarks")
        style_organizing_button(brave_export_btn)
        bookmarks_taskbar_row_layout.addWidget(brave_export_btn)
        brave_export_btn.clicked.connect(self.export_bookmarks)
        self.register_tooltip(brave_export_btn, tooltip_text("export_bookmarks"))

        taskbar_actions_combo = make_action_dropdown(
            " Taskbar Actions ",
            {
                "Backup Taskbar": self.backup_taskbar_apps,
                "Open Backup Folder": self.open_taskbar_backup_folder,
            },
        )
        bookmarks_taskbar_row_layout.addWidget(taskbar_actions_combo)
        org_layout.addWidget(bookmarks_taskbar_row)
        self.register_tooltip(taskbar_actions_combo, tooltip_text("backup_taskbar"))

        master_backup_row = QWidget()
        master_backup_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        master_backup_row_layout = QHBoxLayout(master_backup_row)
        master_backup_row_layout.setContentsMargins(0, 0, 0, 0)
        master_backup_row_layout.setSpacing(10)

        master_backup_btn = QPushButton("Master Backup Path")
        style_organizing_button(master_backup_btn)
        master_backup_row_layout.addWidget(master_backup_btn)
        self.register_tooltip(master_backup_btn, tooltip_text("master_backup_path"))

        self.backup_path_input = QLabel()
        self.backup_path_input.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        self.backup_path_input.setProperty("plainThemeLabelStyle", True)
        self.backup_path_input.setStyleSheet(styles.plain_theme_label_style(15))
        self.backup_path_input.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        master_backup_row_layout.addWidget(self.backup_path_input)
        self._refresh_master_backup_path_display()

        org_layout.addWidget(master_backup_row)

        master_backup_btn.clicked.connect(self._choose_master_backup_dir)
        self._taskbar_backup_folder_timer = QTimer(self)
        self._taskbar_backup_folder_timer.timeout.connect(
            self._refresh_taskbar_backup_folder_button
        )
        self._taskbar_backup_folder_timer.start(1000)
        self._refresh_taskbar_backup_folder_button()

        org_section_spacer = add_left_section_spacer(self.ORGANISING_SECTION_TOP_SPACER)
        self.main_layout.addWidget(org_section)
        register_left_section(
            org_section,
            top_spacer=org_section_spacer,
            expanded_spacer_height=self.ORGANISING_SECTION_TOP_SPACER,
        )

        recycle_bin_section, recycle_bin_layout = make_section(
            "Recycle Bin Actions",
            "recycle_bin_actions",
        )

        recycle_bin_controls = QWidget()
        recycle_bin_controls.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        recycle_bin_controls_layout = QGridLayout(recycle_bin_controls)
        recycle_bin_controls_layout.setContentsMargins(0, 0, 0, 0)
        recycle_bin_controls_layout.setHorizontalSpacing(10)
        recycle_bin_controls_layout.setVerticalSpacing(10)

        cleanup_actions_combo = make_action_dropdown(
            " Cleanup Actions ",
            {
                "Open Recycle Bin": self.open_recycle_bin,
                "Run Auto-Clean Now": self.run_recycle_bin_cleanup_now,
                "Empty Recycle Bin": self.empty_recycle_bin,
            },
        )
        recycle_bin_controls_layout.addWidget(cleanup_actions_combo, 0, 0)
        self.register_tooltip(cleanup_actions_combo, tooltip_text("cleanup_actions"))

        recycle_bin_auto_clean_enabled = bool(
            state.get("recycle_bin_auto_clean_enabled", False)
        )
        recycle_bin_auto_clean_btn = make_toggle_button(
            "Auto-clean On",
            recycle_bin_auto_clean_enabled,
        )
        bind_toggle_state_text(recycle_bin_auto_clean_btn, "Auto-clean")
        recycle_bin_controls_layout.addWidget(recycle_bin_auto_clean_btn, 0, 1)
        self.register_tooltip(
            recycle_bin_auto_clean_btn,
            tooltip_text("recycle_bin_auto_clean"),
        )

        age_rule_values = ["7 days", "14 days", "30 days"]
        current_age_rule_days = int(state.get("recycle_bin_age_rule_days", 30))
        current_age_rule_text = f"{current_age_rule_days} days"
        recycle_bin_age_rule_combo = make_value_dropdown(
            age_rule_values,
            current_age_rule_text,
        )
        self.register_tooltip(
            recycle_bin_age_rule_combo,
            tooltip_text("recycle_bin_age_rule"),
        )

        cleanup_rule_label = QLabel("Delete items older than:")
        cleanup_rule_label.setStyleSheet(styles.label_style(font_size=14))
        recycle_bin_age_rule_slot = QWidget()
        recycle_bin_age_rule_slot.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        recycle_bin_age_rule_row = QWidget()
        recycle_bin_age_rule_row_layout = QGridLayout(recycle_bin_age_rule_row)
        recycle_bin_age_rule_row_layout.setContentsMargins(0, 0, 0, 0)
        recycle_bin_age_rule_row_layout.setHorizontalSpacing(10)
        recycle_bin_age_rule_row_layout.setVerticalSpacing(0)
        recycle_bin_age_rule_row_layout.addWidget(cleanup_rule_label, 0, 0)
        recycle_bin_age_rule_row_layout.addWidget(recycle_bin_age_rule_combo, 0, 1)
        recycle_bin_age_rule_row_layout.setColumnStretch(0, 1)
        recycle_bin_age_rule_row_layout.setColumnStretch(1, 1)
        recycle_bin_age_rule_row_height = recycle_bin_age_rule_row.sizeHint().height()
        recycle_bin_age_rule_slot.setFixedHeight(recycle_bin_age_rule_row_height)
        recycle_bin_age_rule_slot_layout = QVBoxLayout(recycle_bin_age_rule_slot)
        recycle_bin_age_rule_slot_layout.setContentsMargins(0, 0, 0, 0)
        recycle_bin_age_rule_slot_layout.setSpacing(0)
        recycle_bin_age_rule_slot_layout.addWidget(recycle_bin_age_rule_row)
        recycle_bin_controls_layout.addWidget(recycle_bin_age_rule_slot, 1, 0, 1, 2)

        def set_recycle_bin_age_rule_row_visible(is_visible: bool):
            recycle_bin_age_rule_row.setVisible(is_visible)

        set_recycle_bin_age_rule_row_visible(recycle_bin_auto_clean_enabled)
        recycle_bin_controls_layout.setColumnStretch(0, 1)
        recycle_bin_controls_layout.setColumnStretch(1, 1)
        recycle_bin_layout.addWidget(recycle_bin_controls)

        def on_recycle_bin_auto_clean_changed(checked: bool):
            state["recycle_bin_auto_clean_enabled"] = checked
            set_recycle_bin_age_rule_row_visible(checked)
            save_state(state)

        def on_recycle_bin_age_rule_changed(text: str):
            try:
                days = int(text.split()[0])
            except (IndexError, ValueError):
                return
            if state.get("recycle_bin_age_rule_days") != days:
                state["recycle_bin_last_auto_clean_popup_days"] = None
            state["recycle_bin_age_rule_days"] = days
            save_state(state)

        recycle_bin_auto_clean_btn.toggled.connect(on_recycle_bin_auto_clean_changed)
        recycle_bin_age_rule_combo.currentTextChanged.connect(
            on_recycle_bin_age_rule_changed
        )

        recycle_bin_section_spacer = add_left_section_spacer(
            self.RECYCLE_BIN_ACTIONS_TOP_SPACER
        )
        self.main_layout.addWidget(recycle_bin_section)
        register_left_section(
            recycle_bin_section,
            top_spacer=recycle_bin_section_spacer,
            expanded_spacer_height=self.RECYCLE_BIN_ACTIONS_TOP_SPACER,
        )

        self.main_layout.addStretch(1)
        
        def toggle_all():
            any_visible = any(
                bool(getattr(section, "is_open", False))
                for section in self.left_sections
            )

            new_state = not any_visible
            self.master_toggle_left_state = new_state
            self.state["master_toggle_left"] = new_state

            master_btn.setText(
                styles.arrow_glyph(
                    Qt.ArrowType.DownArrow if new_state else Qt.ArrowType.UpArrow
                )
            )

            for section in self.left_sections:
                self._set_left_section_open(section, new_state)

            self.save_all_settings()
            
        master_btn.clicked.connect(toggle_all)
        master_btn.setText(
            styles.arrow_glyph(
                Qt.ArrowType.DownArrow
                if self.master_toggle_left_state
                else Qt.ArrowType.UpArrow
            )
        )

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
        font_size = int(combo.property("styleFontSize") or 14)
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
            font_size = int(button.property("styleFontSize") or 14)
            button.setStyleSheet(styles.organizing_button_style(font_size=font_size))

        for combo in self.findChildren(QComboBox):
            font_size = int(combo.property("styleFontSize") or 14)
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
                if self.right_tools_panel.sidebar_output.property("surfaceFieldStyle"):
                    self.right_tools_panel.sidebar_output.setStyleSheet(
                        styles.surfaced_text_edit_style("Consolas", 15)
                    )
                else:
                    self.right_tools_panel.sidebar_output.setStyleSheet(
                        styles.text_edit_style("Consolas", 15)
                    )
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



import sys
import ctypes
from pathlib import Path
from datetime import datetime
import styles
from PIL import ImageGrab
import win32gui
import win32con

from collapsible_section import SECTION_FRAME_MAX_WIDTH
from right_utility_gui import AdvancedToolsPanel as RightAdvancedToolsPanel
from screen_mover import SCREEN_MOVER
from tray_toggles import TrayIconManager
from utility_toggles import  UtilityActionsManager 
from state_manager import load_state, save_state
from tooltips import QtTooltipManager
from PySide6.QtCore import Qt, QTimer

from PySide6.QtWidgets import (
    QWidget,
    QGridLayout,
    QComboBox,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QScrollArea,
    QHBoxLayout,
    QLineEdit,
    QApplication,
    QFrame,
    QFileDialog,
    QMessageBox,
    QSizePolicy
)

MUTEX_NAME = "Windows Resurface"

def bring_existing_instance_to_front():
    target_hwnd = None

    def enum_handler(hwnd, _):
        nonlocal target_hwnd
        title = win32gui.GetWindowText(hwnd)

        if "Windows Resurface" in title and hwnd != 0:
            target_hwnd = hwnd

        return True

    try:
        win32gui.EnumWindows(enum_handler, None)
    except Exception as e:
        print("[RESTORE] enumeration failed:", e)
        return

    if not target_hwnd:
        return

    try:
        win32gui.ShowWindow(target_hwnd, win32con.SW_SHOW)
        win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(target_hwnd)
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

class UtilityControlApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Windows Resurface")
        self.setStyleSheet(styles.window_style())
        self.COLLAPSED_WIDTH = 485
        self.EXPANDED_WIDTH = 935
        self.ADVANCED_PANEL_WIDTH = self.EXPANDED_WIDTH - self.COLLAPSED_WIDTH
        self.WINDOW_WIDTH = self.COLLAPSED_WIDTH
        self.WINDOW_HEIGHT = 875
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        
        self.state = load_state()
        self.saved_state = self.state
        self.tooltips_enabled = bool(self.state.get("tooltips_enabled", True))
        self._tooltip_managers = []
        self._active_message_boxes = []
        self._taskbar_backup_folder_open = False
        self.advanced_settings_open = bool(self.state.get("advanced_panel_open", False))
        self.collapsible_sections = []
        self._quit_requested = False
        self.actions = UtilityActionsManager(self)
        self.tray_manager = TrayIconManager(self)

        self._build_ui()
        self.tray_manager.create_tray_icon()
        SCREEN_MOVER.configure(app_hwnd=int(self.winId()))
        SCREEN_MOVER.start()
        
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.show()
        self._apply_fixed_window_style()

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

    def _build_ui(self):

        self.root_container = QWidget(self)
        self.root_container.setGeometry(0, 0, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

        self.root_layout = QGridLayout(self.root_container)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.root_layout.setColumnMinimumWidth(0, 425)
        self.root_layout.setColumnStretch(0, 0)
        self.root_layout.setColumnStretch(1, 0)
        self.root_layout.setRowStretch(0, 1)

        self.main_scroll = QScrollArea(self.root_container)
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.main_scroll.setFixedWidth(450)
        self.main_scroll.setViewportMargins(0, 0, 12, 0)

        self.root_layout.addWidget(self.main_scroll, 0, 0)

        self.advanced_settings_panel = QFrame(self.root_container)
        self.advanced_settings_panel.setFixedWidth(self.ADVANCED_PANEL_WIDTH)

        self.advanced_settings_layout = QVBoxLayout(self.advanced_settings_panel)
        self.advanced_settings_layout.setContentsMargins(0, 0, 0, 0)
        self.advanced_settings_layout.setSpacing(10)
        self.advanced_settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.right_tools_panel = RightAdvancedToolsPanel(self)
        self.advanced_settings_layout.addWidget(self.right_tools_panel)

        self.root_layout.addWidget(self.advanced_settings_panel, 0, 1)
        self.advanced_settings_panel.hide()

        self.advanced_settings_toggle = QToolButton(self.root_container)
        self.advanced_settings_toggle.setFixedSize(
            styles.ICON_BUTTON_WIDTH,
            styles.ICON_BUTTON_HEIGHT
        )
        self.advanced_settings_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.advanced_settings_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_settings_toggle.setStyleSheet(
            styles.arrow_button_style(styles.TEXT_LIGHT, styles.SURFACE_DARK)
        )
        self.advanced_settings_toggle.clicked.connect(
            self.toggle_advanced_settings_panel
        )
        self.advanced_settings_toggle.raise_()

        self.main_frame = QWidget()
        self.main_scroll.setWidget(self.main_frame)

        self.main_layout = QVBoxLayout(self.main_frame)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(10)
        
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        state = self.state
        
        header = QWidget(self.main_frame)
        header.setMaximumWidth(SECTION_FRAME_MAX_WIDTH)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("Windows Resurface", header)
        title.setStyleSheet(styles.label_style(font_size=20))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header_spacer = QWidget(header)
        header_spacer.setFixedSize(styles.ICON_BUTTON_WIDTH, styles.ICON_BUTTON_HEIGHT)

        master_btn = QToolButton(header)
        master_btn.setFixedSize(styles.ICON_BUTTON_WIDTH, styles.ICON_BUTTON_HEIGHT)
        master_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        master_btn.setArrowType(Qt.ArrowType.DownArrow)
        master_btn.setStyleSheet(
            styles.arrow_button_style(styles.TEXT_LIGHT, styles.SURFACE_DARK)
        )
        self.master_collapse_btn_left = master_btn

        header_layout.addWidget(header_spacer)
        header_layout.addStretch()
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(master_btn)

        self.main_layout.addWidget(header)
        
        self.left_sections = []
        self.master_toggle_left_state = bool(state.get("master_toggle_left", True))

        def make_section(title_text, section_id: str):
            section = QWidget(self.main_frame)
            section.section_id = section_id
            section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            section.setMaximumWidth(405)
            layout = QVBoxLayout(section)
            layout.setContentsMargins(10, 5, 10, 5)
            layout.setSpacing(4)

            sec_header = QWidget(section)
            sec_header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            sec_header.setMaximumWidth(405)
            sec_header_layout = QHBoxLayout(sec_header)
            sec_header_layout.setContentsMargins(0, 0, 0, 0)

            sec_title = QLabel(title_text, sec_header)
            sec_title.setStyleSheet(styles.label_style(font_size=15))

            toggle = QToolButton(sec_header)
            toggle.setFixedSize(styles.SECTION_TOGGLE_WIDTH, styles.SECTION_TOGGLE_HEIGHT)
            toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle.setArrowType(Qt.ArrowType.DownArrow)
            toggle.setStyleSheet(
                styles.arrow_button_style(styles.TEXT_LIGHT, styles.SURFACE_DARK, font_size=16)
            )
            section.toggle_btn = toggle

            sec_header_layout.addWidget(sec_title)
            sec_header_layout.addStretch()
            sec_header_layout.addWidget(toggle)

            frame = QFrame(section)
            section.frame = frame
            frame.setObjectName("CollapsibleSectionFrame")
            frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            frame.setMaximumWidth(405)
            frame.setStyleSheet(styles.collapsible_section_frame_style())
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(2, 2, 2, 2)
            frame_layout.setSpacing(0)

            section.content = QWidget(frame)
            content = section.content
            content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            content.setMaximumWidth(405)
            initial_open = self.state.get("left_section_states", {}).get(section_id, True)
            content.setVisible(initial_open)
            frame.setVisible(initial_open)

            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(10, 10, 10, 10)

            layout.addWidget(sec_header)
            frame_layout.addWidget(content)
            layout.addWidget(frame)
            

            def toggle_section():
                visible = content.isVisible()
                content.setVisible(not visible)
                frame.setVisible(not visible)
                toggle.setArrowType(
                    Qt.ArrowType.DownArrow if not visible else Qt.ArrowType.UpArrow
                )
                self.save_all_settings()

            toggle.clicked.connect(toggle_section)
            toggle.setArrowType(
                Qt.ArrowType.DownArrow if initial_open else Qt.ArrowType.UpArrow
            )

            return section, content_layout

        def make_toggle_button(text: str, checked: bool = False):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setChecked(checked)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            styles.apply_default_button_size(button)
            button.setStyleSheet(styles.toggle_button_style(font_size=14))
            install_green_flash(button)
            return button

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
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            styles.apply_default_button_size(button)
            button.setStyleSheet(styles.organizing_button_style(font_size=14))
            install_green_flash(button)
            return button

        def make_action_dropdown(placeholder: str, actions_map: dict[str, callable]):
            combo = QComboBox()
            combo.addItem(placeholder)
            combo.addItems(actions_map.keys())
            combo.setCurrentText(placeholder)
            combo.setCursor(Qt.CursorShape.PointingHandCursor)
            styles.apply_default_button_size(combo)
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

        ui_section, ui_layout = make_section("User Interface", "user_interface")
        self.main_layout.addWidget(ui_section)
        self.left_sections.append(ui_section)

        ui_rows = QWidget(ui_section.content)
        ui_rows.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ui_rows_layout = QHBoxLayout(ui_rows)
        ui_rows_layout.setContentsMargins(0, 0, 0, 0)
        ui_rows_layout.setSpacing(10)
        ui_layout.addWidget(ui_rows)

        ui_left_col = QWidget(ui_rows)
        ui_left_col.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ui_left_layout = QVBoxLayout(ui_left_col)
        ui_left_layout.setContentsMargins(0, 0, 0, 0)
        ui_left_layout.setSpacing(10)

        ui_right_col = QWidget(ui_rows)
        ui_right_col.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ui_right_layout = QVBoxLayout(ui_right_col)
        ui_right_layout.setContentsMargins(0, 0, 0, 0)
        ui_right_layout.setSpacing(10)

        ui_rows_layout.addWidget(ui_left_col)
        ui_rows_layout.addWidget(ui_right_col)
        ui_rows_layout.setStretch(0, 1)
        ui_rows_layout.setStretch(1, 1)
        ui_rows_layout.setAlignment(ui_left_col, Qt.AlignmentFlag.AlignTop)
        ui_rows_layout.setAlignment(ui_right_col, Qt.AlignmentFlag.AlignTop)

        dark_mode_btn = make_toggle_button("Dark Mode", state.get("theme_dark", True))
        ui_left_layout.addWidget(dark_mode_btn)
        self.register_tooltip(dark_mode_btn, "Switches the app between dark and light appearance.")

        always_on_top_btn = make_toggle_button("Always on Top", state.get("main_always_on_top_enabled", True))
        ui_left_layout.addWidget(always_on_top_btn)
        self.register_tooltip(always_on_top_btn, "Keeps the main window above other windows.")

        tooltips_btn = make_toggle_button("Enable Tooltips", state.get("tooltips_enabled", True))
        ui_left_layout.addWidget(tooltips_btn)
        self.register_tooltip(tooltips_btn, "Enables or disables delayed hover tooltips across the app.")

        min_all_btn = make_toggle_button("Minimize All On", state.get("minimize_all_enabled", False))
        ui_left_layout.addWidget(min_all_btn)
        self.register_tooltip(min_all_btn, "Controls whether the minimize-all utility is enabled.")

        power_dropdown = make_action_dropdown(
            " Power Options ",
            {
                "Sleep": self.right_tools_panel.run_sleep,
                "Lock PC": self.right_tools_panel.run_lock_pc,
                "Restart": self.right_tools_panel.run_restart,
                "Log out": self.right_tools_panel.run_logout,
                "Shutdown": self.right_tools_panel.run_shutdown,
            },
        )
        ui_right_layout.addWidget(power_dropdown)
        self.register_tooltip(
            power_dropdown,
            "Choose a power action such as sleep, lock, restart, log out, or shutdown.",
        )

        def on_dark_mode_changed(checked: bool):
            state["theme_dark"] = checked
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
        
        def on_min_all_changed(checked: bool):
            state["minimize_all_enabled"] = checked
            save_state(state)

            if hasattr(self.actions, "minimize_all_toggle"):
                self.actions.minimize_all_toggle(checked)
            elif hasattr(self.actions, "minimize_all"):
                self.actions.minimize_all(checked)

        min_all_btn.toggled.connect(on_min_all_changed)
        screen_section, screen_layout = make_section("Screen Mover", "screen_mover")

        screen_row = QWidget(screen_section.content)
        screen_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        screen_row_layout = QHBoxLayout(screen_row)
        screen_row_layout.setContentsMargins(0, 0, 0, 0)
        screen_row_layout.setSpacing(10)
        screen_layout.addWidget(screen_row)

        title_bar_dock_btn = make_toggle_button("Title Bar Dock", state.get("title_bar_dock_enabled", True))
        screen_row_layout.addWidget(title_bar_dock_btn)
        self.register_tooltip(
            title_bar_dock_btn,
            "Shows a small left/right mover dock when you hover an app window's title bar.",
        )

        def on_title_bar_dock_changed(checked: bool):
            state["title_bar_dock_enabled"] = checked
            save_state(state)
            SCREEN_MOVER.title_bar_dock_enabled = checked

        title_bar_dock_btn.toggled.connect(on_title_bar_dock_changed)

        mmb_btn = make_toggle_button("Middle Mouse Move", state.get("mmb_activation_enabled", True))
        screen_row_layout.addWidget(mmb_btn)
        self.register_tooltip(mmb_btn, "Lets you move a window by middle-clicking the tracked title-bar dock.")
        screen_row_layout.addStretch()

        def on_mmb_changed(checked: bool):
            state["mmb_activation_enabled"] = checked
            save_state(state)
            SCREEN_MOVER.enable_mmb = checked

        mmb_btn.toggled.connect(on_mmb_changed)
        self.main_layout.addWidget(screen_section)
        self.left_sections.append(screen_section)

        usb_section, usb_layout = make_section("Drive Reminder Options", "drive_reminder_options")

        idle_btn = make_toggle_button("Idle Plugged Reminder", state.get("usb_idle_enabled", True))
        usb_layout.addWidget(idle_btn)
        self.register_tooltip(idle_btn, "Controls the idle plugged-in drive reminder.")

        def on_idle_changed(checked: bool):
            state["usb_idle_enabled"] = checked
            save_state(state)

        idle_btn.toggled.connect(on_idle_changed)

        download_btn = make_toggle_button("Download Done Remind", state.get("usb_download_enabled", True))
        usb_layout.addWidget(download_btn)
        self.register_tooltip(download_btn, "Controls the finished-download drive reminder.")

        def on_download_changed(checked: bool):
            state["usb_download_enabled"] = checked
            save_state(state)

        download_btn.toggled.connect(on_download_changed)

        plug_btn = make_toggle_button("Plug / Unplug Notify", state.get("usb_plug_enabled", True))
        usb_layout.addWidget(plug_btn)
        self.register_tooltip(plug_btn, "Controls notifications for drive plug and unplug events.")

        def on_plug_changed(checked: bool):
            state["usb_plug_enabled"] = checked
            save_state(state)

        plug_btn.toggled.connect(on_plug_changed)

        self.main_layout.addWidget(usb_section)
        self.left_sections.append(usb_section)

        org_section, org_layout = make_section("Organising Utilities", "organising_utilities")
        self.backup_path = self._get_master_backup_dir()

        screenshot_btn = QPushButton("Desktop Screenshot")
        style_organizing_button(screenshot_btn)
        org_layout.addWidget(screenshot_btn)
        screenshot_btn.clicked.connect(self.take_desktop_screenshot)
        self.register_tooltip(screenshot_btn, "Captures the desktop and saves it to the master backup folder.")

        folder_row = QWidget()
        folder_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        folder_row_layout = QHBoxLayout(folder_row)
        folder_row_layout.setContentsMargins(0, 0, 0, 0)
        folder_row_layout.setSpacing(10)

        folder_btn = QPushButton("Folder → Desktop")
        style_organizing_button(folder_btn)
        self.register_tooltip(folder_btn, "Creates a desktop folder using the name entered beside it.")

        folder_input = QLineEdit()
        folder_input.setPlaceholderText("Folder name")
        folder_input.setText(state.get("folder_to_desktop_name", ""))
        folder_input.setReadOnly(False)
        folder_input.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        folder_input.setStyleSheet(styles.line_edit_style(15))
        self.register_tooltip(folder_input, "Enter the name of the folder to create on the desktop.")

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

        taskbar_row = QWidget()
        taskbar_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        taskbar_row_layout = QHBoxLayout(taskbar_row)
        taskbar_row_layout.setContentsMargins(0, 0, 0, 0)
        taskbar_row_layout.setSpacing(10)
        org_layout.addWidget(taskbar_row)

        backup_taskbar_btn = QPushButton("Backup Taskbar")
        style_organizing_button(backup_taskbar_btn)
        taskbar_row_layout.addWidget(backup_taskbar_btn)
        backup_taskbar_btn.clicked.connect(self.backup_taskbar_apps)
        self.register_tooltip(backup_taskbar_btn, "Backs up pinned taskbar shortcuts into the TaskBarApps folder.")

        open_backup_btn = QPushButton("Open Backup Folder")
        style_organizing_button(open_backup_btn)
        taskbar_row_layout.addWidget(open_backup_btn)
        self.open_backup_btn = open_backup_btn
        open_backup_btn.clicked.connect(self.open_taskbar_backup_folder)
        self.register_tooltip(
            open_backup_btn,
            "Opens the TaskBarApps backup folder inside the master backup path, or closes it if already open.",
        )

        layout_row = QWidget()
        layout_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout_row_layout = QHBoxLayout(layout_row)
        layout_row_layout.setContentsMargins(0, 0, 0, 0)
        layout_row_layout.setSpacing(10)
        org_layout.addWidget(layout_row)

        capture_layout_btn = QPushButton("Capture Desktop Layout")
        style_organizing_button(capture_layout_btn)
        layout_row_layout.addWidget(capture_layout_btn)
        capture_layout_btn.clicked.connect(self.capture_desktop_layout)
        self.register_tooltip(capture_layout_btn, "Saves the current desktop icon layout to the master backup location.")

        restore_layout_btn = QPushButton("Restore Desktop Layout")
        style_organizing_button(restore_layout_btn)
        layout_row_layout.addWidget(restore_layout_btn)
        restore_layout_btn.clicked.connect(self.restore_desktop_layout)
        self.register_tooltip(restore_layout_btn, "Restores the saved desktop icon layout from the master backup location.")

        brave_export_btn = QPushButton("Export Bookmarks")
        style_organizing_button(brave_export_btn)
        org_layout.addWidget(brave_export_btn)
        brave_export_btn.clicked.connect(self.export_bookmarks)
        self.register_tooltip(
            brave_export_btn,
            "Exports Brave bookmarks into the Bookmarks folder inside the master backup path.",
        )

        master_backup_row = QWidget()
        master_backup_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        master_backup_row_layout = QHBoxLayout(master_backup_row)
        master_backup_row_layout.setContentsMargins(0, 0, 0, 0)
        master_backup_row_layout.setSpacing(10)

        master_backup_btn = QPushButton("Master Backup Path")
        style_organizing_button(master_backup_btn)
        master_backup_row_layout.addWidget(master_backup_btn)
        self.register_tooltip(master_backup_btn, "Chooses the base folder used by backup and layout utilities.")

        self.backup_path_input = QLineEdit()
        self.backup_path_input.setPlaceholderText("Backup output folder path")
        self.backup_path_input.setText(self._get_master_backup_dir())
        self.backup_path_input.setReadOnly(True)
        self.backup_path_input.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        self.backup_path_input.setStyleSheet(styles.line_edit_style(15))
        master_backup_row_layout.addWidget(self.backup_path_input)
        self.register_tooltip(self.backup_path_input, "Shows the current master backup folder path.")

        org_layout.addWidget(master_backup_row)

        def on_master_backup_path_changed(text: str):
            self._set_master_backup_dir(text)

        master_backup_btn.clicked.connect(self._choose_master_backup_dir)
        self.backup_path_input.textChanged.connect(on_master_backup_path_changed)
        self._taskbar_backup_folder_timer = QTimer(self)
        self._taskbar_backup_folder_timer.timeout.connect(
            self._refresh_taskbar_backup_folder_button
        )
        self._taskbar_backup_folder_timer.start(1000)
        self._refresh_taskbar_backup_folder_button()

        self.main_layout.addWidget(org_section)
        self.left_sections.append(org_section)

        self.main_layout.addStretch(1)
        
        def toggle_all():
            any_visible = any(
                section.content.isVisible()
                for section in self.left_sections
            )

            new_state = not any_visible
            self.master_toggle_left_state = new_state
            self.state["master_toggle_left"] = new_state

            master_btn.setArrowType(
                Qt.ArrowType.DownArrow if new_state else Qt.ArrowType.UpArrow
            )

            for section in self.left_sections:
                section.content.setVisible(new_state)
                if hasattr(section, "frame"):
                    section.frame.setVisible(new_state)
                if hasattr(section, "toggle_btn"):
                    section.toggle_btn.setArrowType(
                        Qt.ArrowType.DownArrow if new_state else Qt.ArrowType.UpArrow
                    )

            self.save_all_settings()
            
        master_btn.clicked.connect(toggle_all)
        master_btn.setArrowType(
            Qt.ArrowType.DownArrow if self.master_toggle_left_state else Qt.ArrowType.UpArrow
        )

        if self.advanced_settings_open:
            self.WINDOW_WIDTH = self.EXPANDED_WIDTH
            self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
            self.root_container.setGeometry(0, 0, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
            self.advanced_settings_panel.show()
            self.advanced_settings_toggle.setArrowType(Qt.ArrowType.LeftArrow)

        self._position_advanced_settings_toggle()

    def _get_master_backup_dir(self) -> str:
        return (
            self.state.get("master_backup_output_path")
            or self.state.get("backup_output_path")
            or self.state.get("backup_folder_path")
            or str(Path.home())
        )

    def _choose_master_backup_dir(self):
        start_dir = self._get_master_backup_dir().strip() or str(Path.home())
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Choose Master Backup Folder",
            start_dir
        )

        if selected_dir:
            self._set_master_backup_dir(selected_dir)

    def toggle_advanced_settings_panel(self):
        self.advanced_settings_open = not self.advanced_settings_open
        self.state["advanced_panel_open"] = self.advanced_settings_open

        if self.advanced_settings_open:
            self.WINDOW_WIDTH = self.EXPANDED_WIDTH
            self.advanced_settings_panel.show()
            self.advanced_settings_toggle.setArrowType(Qt.ArrowType.LeftArrow)
        else:
            self.WINDOW_WIDTH = self.COLLAPSED_WIDTH
            self.advanced_settings_panel.hide()
            self.advanced_settings_toggle.setArrowType(Qt.ArrowType.RightArrow)

        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self.root_container.setGeometry(0, 0, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self._position_advanced_settings_toggle()
        save_state(self.state)

    def _position_advanced_settings_toggle(self):
        x = self.width() - self.advanced_settings_toggle.width() - 6
        y = (self.height() - self.advanced_settings_toggle.height()) // 2
        self.advanced_settings_toggle.move(x, y)

    def resizeEvent(self, event):
        self.root_container.setGeometry(0, 0, self.width(), self.height())
        self._position_advanced_settings_toggle()
        super().resizeEvent(event)

    def _set_master_backup_dir(self, path: str):
        clean_path = path.strip()
        if not clean_path:
            return

        self.backup_path = clean_path
        self.state["master_backup_output_path"] = clean_path
        self.state["backup_output_path"] = clean_path
        self.state["backup_folder_path"] = clean_path

        if hasattr(self, "backup_path_input") and self.backup_path_input.text() != clean_path:
            self.backup_path_input.setText(clean_path)

        save_state(self.state)

    def _build_master_output_path(self, filename: str) -> str:
        base_dir = self._get_master_backup_dir().strip()
        return str(Path(base_dir) / filename) if base_dir else filename

    def get_default_taskbar_backup_dir(self) -> str:
        base_dir = self._get_master_backup_dir().strip() or str(Path.home())
        return str(Path(base_dir) / "TaskBarApps")

    def get_default_bookmarks_export_dir(self) -> str:
        base_dir = self._get_master_backup_dir().strip() or str(Path.home())
        return str(Path(base_dir) / "Bookmarks")

    def get_default_desktop_layout_path(self) -> str:
        return self._build_master_output_path("desktop_icon_layout.json")

    def get_default_screenshot_path(self) -> str:
        return self._build_master_output_path("desktop_screenshot.png")

    def _refresh_taskbar_backup_folder_button(self):
        is_open = self.actions.is_backup_folder_open(
            self.get_default_taskbar_backup_dir()
        )
        self._taskbar_backup_folder_open = is_open

        if hasattr(self, "open_backup_btn"):
            self.open_backup_btn.setText(
                "Close Backup Folder" if is_open else "Open Backup Folder"
            )

    def _show_timed_message(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
        timeout_ms: int = 10_000,
    ) -> QMessageBox:
        timeout_seconds = max(1, timeout_ms // 1000)
        message_box = QMessageBox(self)
        message_box.setIcon(icon)
        message_box.setWindowTitle(title)
        message_box.setText(
            f"{text}\n\nThis message will close in {timeout_seconds} seconds."
        )
        message_box.setStandardButtons(QMessageBox.StandardButton.NoButton)
        message_box.setModal(False)
        self._active_message_boxes.append(message_box)
        close_timer = QTimer(message_box)
        close_timer.setSingleShot(True)

        def cleanup_message_box():
            if message_box in self._active_message_boxes:
                self._active_message_boxes.remove(message_box)
            message_box.deleteLater()

        message_box.finished.connect(lambda _: cleanup_message_box())
        close_timer.timeout.connect(message_box.accept)
        message_box.show()
        close_timer.start(timeout_ms)
        return message_box

    def take_desktop_screenshot(self):
        self.showMinimized()
        QTimer.singleShot(
            250,
            self._capture_desktop_screenshot,
        )

    def _capture_desktop_screenshot(self):
        try:
            img = ImageGrab.grab()

            default_name = f"DesktopScreenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            save_dir = Path(self._get_master_backup_dir())
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / default_name

            img.save(save_path)
            self.state["desktop_screenshot_last_path"] = str(save_path)
            save_state(self.state)
            print(f"[SCREENSHOT] Saved: {save_path}")
            self._show_timed_message(
                QMessageBox.Icon.Information,
                "Desktop Screenshot",
                f"Desktop screenshot saved to:\n{save_path}",
                timeout_ms=5_000,
            )

        except Exception as e:
            print("[SCREENSHOT] Error:", e)
            self._show_timed_message(
                QMessageBox.Icon.Warning,
                "Desktop Screenshot",
                f"Could not save desktop screenshot:\n{e}",
                timeout_ms=5_000,
            )

    def backup_taskbar_apps(self):
        backup_dir = self.get_default_taskbar_backup_dir()
        count = self.actions.backup_pinned_shortcuts(backup_dir)

        if count > 0:
            self._show_timed_message(
                QMessageBox.Icon.Information,
                "Backup Taskbar",
                f"Backed up {count} taskbar shortcut(s) to:\n{backup_dir}",
            )
            return

        self._show_timed_message(
            QMessageBox.Icon.Warning,
            "Backup Taskbar",
            "No taskbar shortcuts were backed up.",
        )

    def open_taskbar_backup_folder(self):
        path = self.get_default_taskbar_backup_dir()
        if self.actions.is_backup_folder_open(path):
            closed = self.actions.close_backup_folder(path)
            self._refresh_taskbar_backup_folder_button()

            if closed:
                return

            QMessageBox.warning(
                self,
                "Close Backup Folder",
                f"Could not close backup folder:\n{path}"
            )
            return

        opened = self.actions.open_backup_folder(path)
        self._refresh_taskbar_backup_folder_button()

        if opened:
            QTimer.singleShot(500, self._refresh_taskbar_backup_folder_button)
            return

        QMessageBox.warning(
            self,
            "Open Backup Folder",
            f"Could not open backup folder:\n{path}"
        )

    def capture_desktop_layout(self):
        out_path = self.get_default_desktop_layout_path()
        count = self.actions.capture_desktop_layout(out_path)

        if count > 0:
            self._show_timed_message(
                QMessageBox.Icon.Information,
                "Desktop Layout",
                f"Captured desktop layout with {count} icon position(s) saved to:\n{out_path}",
            )
            return

        self._show_timed_message(
            QMessageBox.Icon.Warning,
            "Desktop Layout",
            f"Could not capture desktop layout to:\n{out_path}",
        )

    def restore_desktop_layout(self):
        layout_path = self.get_default_desktop_layout_path()
        count = self.actions.restore_desktop_layout(layout_path)

        if count > 0:
            self._show_timed_message(
                QMessageBox.Icon.Information,
                "Desktop Layout",
                f"Desktop icons restored from:\n{layout_path}",
            )
            return

        self._show_timed_message(
            QMessageBox.Icon.Warning,
            "Desktop Layout",
            f"Could not restore desktop layout from:\n{layout_path}",
        )

    def export_bookmarks(self):
        out_path = self.right_tools_panel._run_brave_export()
        if isinstance(out_path, str) and out_path:
            self._show_timed_message(
                QMessageBox.Icon.Information,
                "Export Bookmarks",
                f"Bookmarks exported to:\n{out_path}",
            )
            return

        if out_path is False:
            self._show_timed_message(
                QMessageBox.Icon.Warning,
                "Export Bookmarks",
                "Could not export bookmarks.",
            )

    def _create_desktop_folder(self, folder_input: QLineEdit):
        folder_name = folder_input.text().strip()
        if not folder_name:
            return

        desktop = Path.home() / "Desktop"
        new_path = desktop / folder_name

        try:
            if new_path.exists():
                self._show_timed_message(
                    QMessageBox.Icon.Warning,
                    "Folder to Desktop",
                    "A folder with that name already exists on Desktop.",
                )
                return

            new_path.mkdir(parents=True, exist_ok=False)
            folder_input.clear()
            self.state["folder_to_desktop_name"] = ""
            save_state(self.state)
            self._show_timed_message(
                QMessageBox.Icon.Information,
                "Folder to Desktop",
                f"Created desktop folder:\n{new_path}",
            )

        except Exception as e:
            self._show_timed_message(
                QMessageBox.Icon.Warning,
                "Folder to Desktop",
                f"Could not create folder:\n{e}",
            )

    def _get_arrow_colors(self):
        palette = self.palette()
        bg = palette.color(self.backgroundRole())

        is_dark = (bg.red() + bg.green() + bg.blue()) / 3 < 128

        if is_dark:
            return {
                "text": styles.TEXT_LIGHT,
                "hover": styles.SURFACE_HOVER_DARK,
            }
        else:
            return {
                "text": styles.TEXT_DARK,
                "hover": styles.SURFACE_HOVER_LIGHT,
            }
        
    def update_collapsible_arrow_colours(self):
        colors = self._get_arrow_colors()
        style = styles.arrow_button_style(colors["text"], colors["hover"], font_size=18)

        for btn in getattr(self, "arrow_buttons", []):
            btn.setStyleSheet(style)

    def register_tooltip(self, widget: QWidget, text: str, delay: int = 10):
        manager = QtTooltipManager(widget, text, delay=delay)
        self._tooltip_managers.append(manager)
        return manager

    def save_section_states(self):
        left_states = {}
        for section in self.left_sections:
            section_id = getattr(section, "section_id", None)
            if section_id and hasattr(section, "content"):
                left_states[section_id] = section.content.isVisible()

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
            self.master_collapse_btn_left.setArrowType(
                Qt.ArrowType.DownArrow if self.state.get("master_toggle_left", True) else Qt.ArrowType.UpArrow
            )

        right_button = getattr(self, "right_tools_panel", None)
        if right_button and hasattr(right_button, "master_collapse_btn_right"):
            right_button.master_collapse_btn_right.setArrowType(
                Qt.ArrowType.DownArrow if self.state.get("master_toggle_right", False) else Qt.ArrowType.UpArrow
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



import sys
import ctypes
from pathlib import Path
from datetime import datetime
import styles
from PIL import ImageGrab
import win32gui
import win32con

from right_utility_gui import AdvancedToolsPanel as RightAdvancedToolsPanel
from screen_mover import SCREEN_MOVER
from tray_toggles import TrayIconManager
from utility_toggles import  UtilityActionsManager 
from state_manager import load_state, save_state
from tooltips import QtTooltipManager, tooltip_text
from PySide6.QtCore import Qt, QTimer

from PySide6.QtWidgets import (
    QWidget,
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
    MAIN_PANEL_WIDTH = 450
    RIGHT_PANEL_WIDTH = MAIN_PANEL_WIDTH + 70
    MAIN_SECTION_SIDE_PADDING = 14
    LEFT_SECTION_TOP_MARGIN = 5
    LEFT_SECTION_BOTTOM_MARGIN = 12
    USER_INTERFACE_TOP_SPACER = 6
    ORGANISING_SECTION_TOP_SPACER = 18
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
        self.setStyleSheet(styles.window_style())
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
        self.advanced_settings_toggle.setFixedSize(
            styles.ICON_BUTTON_WIDTH,
            styles.ICON_BUTTON_HEIGHT
        )
        self.advanced_settings_toggle.setCursor(Qt.CursorShape.ArrowCursor)
        self.advanced_settings_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_settings_toggle.setStyleSheet(
            styles.arrow_button_style(styles.theme_text_color(), styles.SURFACE_DARK)
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
        self.main_layout.setSpacing(10)
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
            self.MAIN_SECTION_SIDE_PADDING,
            10,
        )

        title = QLabel("Windows Resurface", header)
        title.setStyleSheet(styles.label_style(font_size=20))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header_spacer = QWidget(header)
        header_spacer.setFixedSize(styles.ICON_BUTTON_WIDTH, styles.ICON_BUTTON_HEIGHT)

        master_btn = QToolButton(header)
        master_btn.setFixedSize(styles.ICON_BUTTON_WIDTH, styles.ICON_BUTTON_HEIGHT)
        master_btn.setCursor(Qt.CursorShape.ArrowCursor)
        master_btn.setArrowType(Qt.ArrowType.DownArrow)
        master_btn.setStyleSheet(
            styles.arrow_button_style(styles.theme_text_color(), styles.SURFACE_DARK)
        )
        self.master_collapse_btn_left = master_btn

        header_layout.addWidget(header_spacer)
        header_layout.addStretch()
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(master_btn)

        self.main_layout.addWidget(header, 0, Qt.AlignmentFlag.AlignLeft)
        
        self.left_sections = []
        self.master_toggle_left_state = bool(state.get("master_toggle_left", True))

        def make_section(title_text, section_id: str):
            section = QWidget(self.main_frame)
            section.section_id = section_id
            section.setFixedWidth(self.MAIN_SECTION_OUTER_WIDTH)
            section.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            layout = QVBoxLayout(section)
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
            sec_header_layout.setContentsMargins(0, 0, 0, 0)

            sec_title = QLabel(title_text, sec_header)
            sec_title.setStyleSheet(styles.label_style(font_size=15))

            title_spacer = QWidget(sec_header)
            title_spacer.setFixedSize(
                styles.SECTION_TOGGLE_WIDTH,
                styles.SECTION_TOGGLE_HEIGHT,
            )

            toggle = QToolButton(sec_header)
            toggle.setFixedSize(styles.SECTION_TOGGLE_WIDTH, styles.SECTION_TOGGLE_HEIGHT)
            toggle.setCursor(Qt.CursorShape.ArrowCursor)
            toggle.setArrowType(Qt.ArrowType.DownArrow)
            toggle.setStyleSheet(
                styles.arrow_button_style(
                    styles.theme_text_color(),
                    styles.SURFACE_DARK,
                    font_size=16,
                )
            )
            section.toggle_btn = toggle

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
            button.setCursor(Qt.CursorShape.ArrowCursor)
            styles.apply_default_button_size(button)
            button.setProperty("styleFontSize", 14)
            button.setStyleSheet(styles.toggle_button_style(font_size=14))
            install_green_flash(button)
            return button

        def bind_toggle_text(
            button: QPushButton,
            checked_text: str,
            unchecked_text: str,
        ) -> None:
            def update_text(checked: bool) -> None:
                button.setText(checked_text if checked else unchecked_text)

            update_text(button.isChecked())
            button.toggled.connect(update_text)

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

        def make_action_dropdown(placeholder: str, actions_map: dict[str, callable]):
            combo = QComboBox()
            combo.addItem(placeholder)
            combo.addItems(actions_map.keys())
            combo.setCurrentText(placeholder)
            combo.setCursor(Qt.CursorShape.ArrowCursor)
            styles.apply_default_button_size(combo)
            combo.setProperty("styleFontSize", 14)
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
        self.main_layout.addSpacing(self.USER_INTERFACE_TOP_SPACER)
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
        bind_toggle_text(dark_mode_btn, "Light Mode", "Dark Mode")
        ui_left_layout.addWidget(dark_mode_btn)
        self.register_tooltip(dark_mode_btn, tooltip_text("dark_mode"))

        always_on_top_btn = make_toggle_button("Always on Top", state.get("main_always_on_top_enabled", True))
        bind_toggle_text(always_on_top_btn, "Always on Top Off", "Always on Top On")
        ui_left_layout.addWidget(always_on_top_btn)
        self.register_tooltip(always_on_top_btn, tooltip_text("always_on_top"))

        tooltips_btn = make_toggle_button("Enable Tooltips", state.get("tooltips_enabled", True))
        bind_toggle_text(tooltips_btn, "Disable Tooltips", "Enable Tooltips")
        ui_left_layout.addWidget(tooltips_btn)
        self.register_tooltip(tooltips_btn, tooltip_text("enable_tooltips"))

        min_all_btn = make_toggle_button("Maximize All On", state.get("minimize_all_enabled", False))
        bind_toggle_text(min_all_btn, "Maximize All Off", "Maximize All On")
        ui_left_layout.addWidget(min_all_btn)
        self.register_tooltip(min_all_btn, tooltip_text("maximize_all"))

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
        self.register_tooltip(power_dropdown, tooltip_text("power_options"))

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
        bind_toggle_text(title_bar_dock_btn, "Title Bar Dock Off", "Title Bar Dock On")
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
        self.main_layout.addWidget(screen_section)
        self.left_sections.append(screen_section)

        usb_section, usb_layout = make_section("Drive Reminder Options", "drive_reminder_options")

        idle_btn = make_toggle_button("Idle Plugged Reminder", state.get("usb_idle_enabled", True))
        usb_layout.addWidget(idle_btn)
        self.register_tooltip(idle_btn, tooltip_text("idle_plugged_reminder"))

        def on_idle_changed(checked: bool):
            state["usb_idle_enabled"] = checked
            save_state(state)

        idle_btn.toggled.connect(on_idle_changed)

        download_btn = make_toggle_button("Download Done Remind", state.get("usb_download_enabled", True))
        usb_layout.addWidget(download_btn)
        self.register_tooltip(download_btn, tooltip_text("download_done_reminder"))

        def on_download_changed(checked: bool):
            state["usb_download_enabled"] = checked
            save_state(state)

        download_btn.toggled.connect(on_download_changed)

        plug_btn = make_toggle_button("Plug / Unplug Notify", state.get("usb_plug_enabled", True))
        usb_layout.addWidget(plug_btn)
        self.register_tooltip(plug_btn, tooltip_text("plug_unplug_notify"))

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
        self.register_tooltip(screenshot_btn, tooltip_text("desktop_screenshot"))

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
        folder_input.setProperty("surfaceFieldStyle", True)
        folder_input.setStyleSheet(styles.surfaced_line_edit_style(15))
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
        self.register_tooltip(backup_taskbar_btn, tooltip_text("backup_taskbar"))

        open_backup_btn = QPushButton("Open Backup Folder")
        style_organizing_button(open_backup_btn)
        taskbar_row_layout.addWidget(open_backup_btn)
        self.open_backup_btn = open_backup_btn
        open_backup_btn.clicked.connect(self.open_taskbar_backup_folder)
        self.register_tooltip(open_backup_btn, tooltip_text("open_backup_folder"))

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
        self.register_tooltip(capture_layout_btn, tooltip_text("capture_desktop_layout"))

        restore_layout_btn = QPushButton("Restore Desktop Layout")
        style_organizing_button(restore_layout_btn)
        layout_row_layout.addWidget(restore_layout_btn)
        restore_layout_btn.clicked.connect(self.restore_desktop_layout)
        self.register_tooltip(restore_layout_btn, tooltip_text("restore_desktop_layout"))

        brave_export_btn = QPushButton("Export Bookmarks")
        style_organizing_button(brave_export_btn)
        org_layout.addWidget(brave_export_btn)
        brave_export_btn.clicked.connect(self.export_bookmarks)
        self.register_tooltip(brave_export_btn, tooltip_text("export_bookmarks"))

        master_backup_row = QWidget()
        master_backup_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        master_backup_row_layout = QHBoxLayout(master_backup_row)
        master_backup_row_layout.setContentsMargins(0, 0, 0, 0)
        master_backup_row_layout.setSpacing(10)

        master_backup_btn = QPushButton("Master Backup Path")
        style_organizing_button(master_backup_btn)
        master_backup_row_layout.addWidget(master_backup_btn)
        self.register_tooltip(master_backup_btn, tooltip_text("master_backup_path"))

        self.backup_path_input = QLineEdit()
        self.backup_path_input.setPlaceholderText("Backup output folder path")
        self.backup_path_input.setText(self._get_master_backup_dir())
        self.backup_path_input.setReadOnly(True)
        self.backup_path_input.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        self.backup_path_input.setProperty("surfaceFieldStyle", True)
        self.backup_path_input.setStyleSheet(styles.surfaced_line_edit_style(15))
        master_backup_row_layout.addWidget(self.backup_path_input)
        self.register_tooltip(self.backup_path_input, tooltip_text("backup_path_input"))

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

        self.main_layout.addSpacing(self.ORGANISING_SECTION_TOP_SPACER)
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
            self.advanced_settings_panel.show()
            self.advanced_settings_toggle.setArrowType(Qt.ArrowType.LeftArrow)

        self._update_panel_geometries()
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

    def resizeEvent(self, event):
        self._update_panel_geometries()
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
        return {
            "text": styles.theme_text_color(),
            "hover": styles.SURFACE_HOVER_DARK,
        }

    def apply_theme(self, is_dark: bool):
        styles.set_theme(is_dark)
        self.setStyleSheet(styles.window_style())

        for frame in self.findChildren(QFrame, "CollapsibleSectionFrame"):
            frame.setStyleSheet(styles.collapsible_section_frame_style())

        for line_edit in self.findChildren(QLineEdit):
            if line_edit.property("surfaceFieldStyle"):
                line_edit.setStyleSheet(styles.surfaced_line_edit_style(15))
            else:
                line_edit.setStyleSheet(styles.line_edit_style(15))

        for button in self.findChildren(QPushButton):
            font_size = int(button.property("styleFontSize") or 14)
            button.setStyleSheet(styles.organizing_button_style(font_size=font_size))

        for combo in self.findChildren(QComboBox):
            font_size = int(combo.property("styleFontSize") or 14)
            combo.setStyleSheet(styles.organizing_combo_style(font_size=font_size))

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
        tool_button_styles = {
            (styles.ICON_BUTTON_WIDTH, styles.ICON_BUTTON_HEIGHT): styles.arrow_button_style(
                colors["text"], colors["hover"], font_size=18
            ),
            (styles.SECTION_TOGGLE_WIDTH, styles.SECTION_TOGGLE_HEIGHT): styles.arrow_button_style(
                colors["text"], colors["hover"], font_size=16
            ),
        }

        for btn in self.findChildren(QToolButton):
            size_key = (btn.width(), btn.height())
            btn.setStyleSheet(
                tool_button_styles.get(
                    size_key,
                    styles.arrow_button_style(colors["text"], colors["hover"], font_size=18),
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


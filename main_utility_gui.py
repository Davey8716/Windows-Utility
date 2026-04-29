# ===================================================================
#  Screen Tab Mover + USB Reminder Control Panel
#  Modern UI using CustomTkinter
# ===================================================================


import sys
import ctypes
from pathlib import Path


from screen_mover import SCREEN_MOVER

import styles
from utility_toggles import  UtilityActionsManager 
from state_manager import load_state, save_state

from PySide6.QtWidgets import (
    QWidget,
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
    QFileDialog
)

from PySide6.QtCore import Qt


# =======================================
# These 3 functions possibly to be moved.
# =======================================

MUTEX_NAME = "Problems Gone"

# def get_drive_info():
#             drives = []
#             for letter in string.ascii_uppercase:
#                 path = f"{letter}:\\"
#                 if os.path.exists(path):
#                     try:
#                         total, used, free = shutil.disk_usage(path)
#                         drives.append({
#                             "drive": path,
#                             "total": total,
#                             "free": free,
#                             "used": used
#                         })
#                     except Exception:
#                         pass
#             return drives

# def bring_existing_instance_to_front():
#     def enum_handler(hwnd, _):
#         title = win32gui.GetWindowText(hwnd)

#         if "Problems Gone" in title:
#             try:
#                 win32gui.ShowWindow(hwnd, win32con.SW_SHOW)     # handles withdrawn
#                 win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)  # handles minimized
#                 win32gui.SetForegroundWindow(hwnd)
#             except Exception as e:
#                 print("[RESTORE] failed:", e)
#             return False  # stop enumerating

#         return True

#     win32gui.EnumWindows(enum_handler, None)

# def ensure_single_instance():
#     kernel32 = ctypes.windll.kernel32
#     mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
#     last_error = kernel32.GetLastError()

#     ERROR_ALREADY_EXISTS = 183
#     if last_error == ERROR_ALREADY_EXISTS:
#         bring_existing_instance_to_front()
#         sys.exit(0)

#     return mutex

# TEMP stub — Qt branch only
class AdvancedToolsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide()


class UtilityControlApp(QWidget):
    def __init__(self):
        super().__init__()

        # ---------------- Window ----------------
        self.setWindowTitle("Problems Gone")
        self.COLLAPSED_WIDTH = 505
        self.EXPANDED_WIDTH = 1045
        self.ADVANCED_PANEL_WIDTH = self.EXPANDED_WIDTH - self.COLLAPSED_WIDTH
        self.WINDOW_WIDTH = self.COLLAPSED_WIDTH
        self.WINDOW_HEIGHT = 800
        self.advanced_settings_open = False
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        
        # ✅ add these
        self.state = load_state()
        self.saved_state = self.state
        self.actions = UtilityActionsManager(self)

        # ---------------- Build UI ----------------
        self._build_ui()
        

        # ---------------- Always on top ----------------
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.show()

        ctypes.windll.user32.SetWindowPos(
            int(self.winId()),
            -1,
            0, 0, 0, 0,
            0x0003
        )

    def _build_ui(self):

        # ==================================================
        # Root container
        # ==================================================
        self.root_container = QWidget(self)
        self.root_container.setGeometry(0, 0, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

        self.root_layout = QGridLayout(self.root_container)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.root_layout.setColumnMinimumWidth(0, 425)
        self.root_layout.setColumnStretch(0, 0)
        self.root_layout.setColumnStretch(1, 0)
        self.root_layout.setRowStretch(0, 1)

        # ==================================================
        # Scroll Area (LEFT)
        # ==================================================
        self.main_scroll = QScrollArea(self.root_container)
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.main_scroll.setFixedWidth(450)
        self.main_scroll.setViewportMargins(0, 0, 12, 0)

        self.root_layout.addWidget(self.main_scroll, 0, 0)

        # ==================================================
        # Advanced Settings panel (RIGHT)
        # ==================================================
        self.advanced_settings_panel = QFrame(self.root_container)
        self.advanced_settings_panel.setFixedWidth(self.ADVANCED_PANEL_WIDTH)

        self.advanced_settings_layout = QVBoxLayout(self.advanced_settings_panel)
        self.advanced_settings_layout.setContentsMargins(0, 0, 0, 0)
        self.advanced_settings_layout.setSpacing(10)
        self.advanced_settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        advanced_header = QWidget(self.advanced_settings_panel)
        advanced_header_layout = QHBoxLayout(advanced_header)
        advanced_header_layout.setContentsMargins(10, 10, 10, 10)

        advanced_title = QLabel("Advanced Settings", advanced_header)
        advanced_title.setStyleSheet(styles.label_style(font_size=20))
        advanced_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        advanced_header_layout.addStretch()
        advanced_header_layout.addWidget(advanced_title)
        advanced_header_layout.addStretch()

        self.advanced_settings_layout.addWidget(advanced_header)
        self.advanced_settings_layout.addStretch(1)

        self.root_layout.addWidget(self.advanced_settings_panel, 0, 1)
        self.advanced_settings_panel.hide()

        # ==================================================
        # Right-edge panel toggle
        # ==================================================
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

        # ==================================================
        # Scroll Contents
        # ==================================================
        self.main_frame = QWidget()
        self.main_scroll.setWidget(self.main_frame)

        self.main_layout = QVBoxLayout(self.main_frame)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(10)
        
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # (later, after you add all sections)
        
        state = load_state()
        

        # ==================================================
        # HEADER — App title + master collapse
        # ==================================================
        header = QWidget(self.main_frame)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("Windows Resurface", header)
        title.setStyleSheet(styles.label_style(font_size=20))

        master_btn = QToolButton(header)
        master_btn.setFixedSize(styles.ICON_BUTTON_WIDTH, styles.ICON_BUTTON_HEIGHT)
        master_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        master_btn.setArrowType(Qt.ArrowType.DownArrow)
        master_btn.setStyleSheet(
            styles.arrow_button_style(styles.TEXT_LIGHT, styles.SURFACE_DARK)
        )

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(master_btn)

        self.main_layout.addWidget(header,alignment= Qt.AlignCenter)
        
        # ✅ MUST exist before you append
        self.left_sections = []
        self._sections_visible = True
        
        # ==================================================
        # Section factory
        # ==================================================
        def make_section(title_text):
            section = QFrame(self.main_frame)
            section.setObjectName("CollapsibleSectionFrame")
            section.setStyleSheet(styles.collapsible_section_frame_style())
            layout = QVBoxLayout(section)
            layout.setContentsMargins(10, 5, 10, 5)

            sec_header = QWidget(section)
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

            sec_header_layout.addWidget(sec_title)
            sec_header_layout.addStretch()
            sec_header_layout.addWidget(toggle)

            # ✅ attach content to section for master toggle
            section.content = QWidget(section)
            content = section.content

            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(10, 5, 10, 5)

            layout.addWidget(sec_header)
            layout.addWidget(content)
            

            def toggle_section():
                visible = content.isVisible()
                content.setVisible(not visible)
                toggle.setArrowType(
                    Qt.ArrowType.DownArrow if not visible else Qt.ArrowType.UpArrow
                )

            toggle.clicked.connect(toggle_section)

            return section, content_layout

        def make_toggle_button(text: str, checked: bool = False):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setChecked(checked)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            styles.apply_default_button_size(button)
            button.setStyleSheet(styles.toggle_button_style())
            return button

        # ==================================================
        # User Interface section (SIMPLE + STABLE)
        # ==================================================
        ui_section, ui_layout = make_section("User Interface")

        self.main_layout.addWidget(ui_section)
        self.left_sections.append(ui_section)

        ui_rows = QWidget(ui_section.content)
        ui_rows_layout = QHBoxLayout(ui_rows)
        ui_rows_layout.setContentsMargins(0, 0, 0, 0)
        ui_rows_layout.setSpacing(12)
        ui_layout.addWidget(ui_rows)

        ui_left_col = QWidget(ui_rows)
        ui_left_layout = QVBoxLayout(ui_left_col)
        ui_left_layout.setContentsMargins(0, 0, 0, 0)
        ui_left_layout.setSpacing(6)

        ui_right_col = QWidget(ui_rows)
        ui_right_layout = QVBoxLayout(ui_right_col)
        ui_right_layout.setContentsMargins(0, 0, 0, 0)
        ui_right_layout.setSpacing(6)

        ui_rows_layout.addWidget(ui_left_col)
        ui_rows_layout.addWidget(ui_right_col)
        ui_rows_layout.setAlignment(ui_left_col, Qt.AlignmentFlag.AlignTop)
        ui_rows_layout.setAlignment(ui_right_col, Qt.AlignmentFlag.AlignTop)

        # ---- Dark Mode ----
        dark_mode_btn = make_toggle_button("Dark Mode", state.get("theme_dark", True))
        ui_left_layout.addWidget(dark_mode_btn)

        always_on_top_btn = make_toggle_button("Always on Top", state.get("main_always_on_top_enabled", True))
        ui_left_layout.addWidget(always_on_top_btn)

        tooltips_btn = make_toggle_button("Enable Tooltips", state.get("tooltips_enabled", True))
        ui_left_layout.addWidget(tooltips_btn)

        min_all_btn = make_toggle_button("Minimize All On", state.get("minimize_all_enabled", False))
        ui_left_layout.addWidget(min_all_btn)

        # ---- Power Options master ----
        power_btn = make_toggle_button("Power Options", state.get("power_options_enabled", False))
        ui_right_layout.addWidget(power_btn)

        # ---- Power Options container (VERTICAL, BELOW) ----
        power_container = QWidget(ui_right_col)
        power_layout = QVBoxLayout(power_container)
        power_layout.setContentsMargins(0, 0, 0, 0)
        power_layout.setSpacing(6)

        ui_right_layout.addWidget(power_container)

        sleep_btn = make_toggle_button("Sleep", state.get("power_sleep_enabled", False))
        power_layout.addWidget(sleep_btn)

        logout_btn = make_toggle_button("Log out", state.get("power_logout_enabled", False))
        power_layout.addWidget(logout_btn)

        shutdown_btn = make_toggle_button("Shutdown", state.get("power_shutdown_enabled", False))
        power_layout.addWidget(shutdown_btn)

        # ---- STATE HANDLERS ----
        def save_sleep(checked: bool):
            state["power_sleep_enabled"] = checked
            save_state(state)

        def save_logout(checked: bool):
            state["power_logout_enabled"] = checked
            save_state(state)

        def save_shutdown(checked: bool):
            state["power_shutdown_enabled"] = checked
            save_state(state)

        def update_power_visibility():
            power_container.setVisible(power_btn.isChecked())

        def on_power_master_changed(checked: bool):
            state["power_options_enabled"] = checked
            save_state(state)
            update_power_visibility()

        power_btn.toggled.connect(on_power_master_changed)
        sleep_btn.toggled.connect(save_sleep)
        logout_btn.toggled.connect(save_logout)
        shutdown_btn.toggled.connect(save_shutdown)

        # Initial state
        update_power_visibility()








        def on_always_on_top_changed(checked):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
            self.show()  # required for flag changes to apply

            state["main_always_on_top_enabled"] = checked
            save_state(state)

        always_on_top_btn.toggled.connect(on_always_on_top_changed)
        
        def on_tooltips_changed(checked):
            state["tooltips_enabled"] = checked
            save_state(state)

        tooltips_btn.toggled.connect(on_tooltips_changed)
        
        def on_min_all_changed(checked: bool):
            state["minimize_all_enabled"] = checked
            save_state(state)

            # call logic if it exists
            if hasattr(self.actions, "minimize_all_toggle"):
                self.actions.minimize_all_toggle(checked)
            elif hasattr(self.actions, "minimize_all"):
                # alt naming
                self.actions.minimize_all(checked)

        min_all_btn.toggled.connect(on_min_all_changed)

        # ==================================================
        # Screen Mover section (visual only)
        # ==================================================
        screen_section, screen_layout = make_section("Screen Mover")

        # -------------------------
        # Screen Mover (placeholders, no logic yet)
        # -------------------------

        # Middle Mouse to Move
        mmb_btn = make_toggle_button("Middle Mouse to Move", state.get("mmb_activation_enabled", True))
        screen_layout.addWidget(mmb_btn)

        def on_mmb_changed(checked: bool):
            state["mmb_activation_enabled"] = checked
            save_state(state)

        mmb_btn.toggled.connect(on_mmb_changed)


        # Windows in Move Zone (auto-align)
        auto_align_btn = make_toggle_button("Windows in Move Zone", state.get("auto_align_enabled", False))
        screen_layout.addWidget(auto_align_btn)

        def on_auto_align_changed(checked: bool):
            state["auto_align_enabled"] = checked
            save_state(state)

        auto_align_btn.toggled.connect(on_auto_align_changed)


        self.main_layout.addWidget(screen_section)
        self.left_sections.append(screen_section)

        
        # ==================================================
        # Drive Reminder Options (visual only)
        # ==================================================
        usb_section, usb_layout = make_section("Drive Reminder Options")


        # Idle-plugged reminder
        idle_btn = make_toggle_button("Idle-plugged Reminder", state.get("usb_idle_enabled", True))
        usb_layout.addWidget(idle_btn)

        def on_idle_changed(checked: bool):
            state["usb_idle_enabled"] = checked
            save_state(state)

        idle_btn.toggled.connect(on_idle_changed)


        # Download-finished reminder
        download_btn = make_toggle_button("Download-finished Reminder", state.get("usb_download_enabled", True))
        usb_layout.addWidget(download_btn)

        def on_download_changed(checked: bool):
            state["usb_download_enabled"] = checked
            save_state(state)

        download_btn.toggled.connect(on_download_changed)

        # Plug / unplug notification
        plug_btn = make_toggle_button("Plug / Unplug Notification", state.get("usb_plug_enabled", True))
        usb_layout.addWidget(plug_btn)

        def on_plug_changed(checked: bool):
            state["usb_plug_enabled"] = checked
            save_state(state)

        plug_btn.toggled.connect(on_plug_changed)

        self.main_layout.addWidget(usb_section)
        self.left_sections.append(usb_section)

        
        # ==================================================
        # Organising Utilities (grouped under one title frame)
        # ==================================================
        org_section, org_layout = make_section("Organising Utilities")

        self.backup_path = self._get_master_backup_dir()
        # -------------------------
        # Desktop Screenshot (placeholder toggle)
        # -------------------------
        screenshot_btn = make_toggle_button("Desktop Screenshot", state.get("desktop_screenshot_enabled", True))
        org_layout.addWidget(screenshot_btn)

        def on_screenshot_changed(checked: bool):
            state["desktop_screenshot_enabled"] = checked
            save_state(state)

        screenshot_btn.toggled.connect(on_screenshot_changed)

        # -------------------------
        # Folder → Desktop (placeholder toggle + input)
        # -------------------------
        folder_row = QWidget()
        folder_row_layout = QHBoxLayout(folder_row)
        folder_row_layout.setContentsMargins(0, 0, 0, 0)
        folder_row_layout.setSpacing(8)

        folder_btn = make_toggle_button("Folder → Desktop", state.get("folder_to_desktop_enabled", False))

        folder_input = QLineEdit()
        folder_input.setPlaceholderText("Folder name")
        folder_input.setText(state.get("folder_to_desktop_name", ""))
        folder_input.setEnabled(folder_btn.isChecked())
        folder_input.setReadOnly(False)

        folder_row_layout.addWidget(folder_btn)
        folder_row_layout.addWidget(folder_input)

        org_layout.addWidget(folder_row)

        def on_folder_toggle(checked: bool):
            state["folder_to_desktop_enabled"] = checked
            folder_input.setEnabled(checked)
            save_state(state)

        def on_folder_name_changed(text: str):
            state["folder_to_desktop_name"] = text
            save_state(state)

        folder_btn.toggled.connect(on_folder_toggle)
        folder_input.textChanged.connect(on_folder_name_changed)

        # -------------------------
        # Backup Taskbar (placeholder)
        # -------------------------
        backup_taskbar_btn = make_toggle_button("Backup Taskbar", state.get("backup_taskbar_enabled", True))
        org_layout.addWidget(backup_taskbar_btn)

        def on_backup_taskbar_changed(checked: bool):
            state["backup_taskbar_enabled"] = checked
            save_state(state)

        backup_taskbar_btn.toggled.connect(on_backup_taskbar_changed)
        
        # -------------------------
        # Open Backup Folder (placeholder)
        # -------------------------
        open_backup_btn = make_toggle_button("Open Backup Folder", state.get("open_backup_enabled", True))
        org_layout.addWidget(open_backup_btn)

        def on_open_backup_changed(checked: bool):
            state["open_backup_enabled"] = checked
            save_state(state)

        open_backup_btn.toggled.connect(on_open_backup_changed)
        
        # -------------------------
        # Change Backup Folder (placeholder)
        # -------------------------
        change_backup_btn = make_toggle_button("Change Backup Folder", state.get("change_backup_folder_enabled", False))
        org_layout.addWidget(change_backup_btn)

        def on_change_backup_changed(checked: bool):
            state["change_backup_folder_enabled"] = checked
            save_state(state)

        change_backup_btn.toggled.connect(on_change_backup_changed)

        # -------------------------
        # Desktop Icon Layout (placeholders)
        # -------------------------

        # Capture desktop layout
        capture_layout_btn = make_toggle_button("Capture Desktop Layout", state.get("capture_desktop_layout_enabled", True))
        org_layout.addWidget(capture_layout_btn)

        def on_capture_layout_changed(checked: bool):
            state["capture_desktop_layout_enabled"] = checked
            save_state(state)

        capture_layout_btn.toggled.connect(on_capture_layout_changed)


        # Restore desktop layout
        restore_layout_btn = make_toggle_button("Restore Desktop Layout", state.get("restore_desktop_layout_enabled", True))
        org_layout.addWidget(restore_layout_btn)

        def on_restore_layout_changed(checked: bool):
            state["restore_desktop_layout_enabled"] = checked
            save_state(state)

        restore_layout_btn.toggled.connect(on_restore_layout_changed)

        master_backup_row = QWidget()
        master_backup_row_layout = QHBoxLayout(master_backup_row)
        master_backup_row_layout.setContentsMargins(0, 0, 0, 0)
        master_backup_row_layout.setSpacing(8)

        master_backup_btn = QPushButton("Master Backup Path")
        styles.apply_default_button_size(master_backup_btn)
        master_backup_btn.setStyleSheet(styles.toggle_button_style())
        master_backup_row_layout.addWidget(master_backup_btn)

        self.backup_path_input = QLineEdit()
        self.backup_path_input.setPlaceholderText("Backup output folder path")
        self.backup_path_input.setText(self._get_master_backup_dir())
        self.backup_path_input.setReadOnly(True)
        master_backup_row_layout.addWidget(self.backup_path_input)

        org_layout.addWidget(master_backup_row)

        def on_master_backup_path_changed(text: str):
            self._set_master_backup_dir(text)

        master_backup_btn.clicked.connect(self._choose_master_backup_dir)
        self.backup_path_input.textChanged.connect(on_master_backup_path_changed)

        self.main_layout.addWidget(org_section)
        self.left_sections.append(org_section)

        
        self.main_layout.addStretch(1)
        
        def toggle_all():
            # If ANY section is visible → collapse all
            any_visible = any(
                section.content.isVisible()
                for section in self.left_sections
            )

            new_state = not any_visible

            master_btn.setArrowType(
                Qt.ArrowType.DownArrow if new_state else Qt.ArrowType.UpArrow
            )

            for section in self.left_sections:
                section.content.setVisible(new_state)
            
        master_btn.clicked.connect(toggle_all)

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
        return self._get_master_backup_dir()

    def get_default_desktop_layout_path(self) -> str:
        return self._build_master_output_path("desktop_icon_layout.json")

    def get_default_screenshot_path(self) -> str:
        return self._build_master_output_path("desktop_screenshot.png")


    def _get_arrow_colors(self):
        palette = self.palette()
        bg = palette.color(self.backgroundRole())

        # Simple luminance check
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


    # def _run_brave_export(self):
    #     default_name = f"Brave_Bookmarks_{datetime.now().strftime('%Y-%m-%d')}.html"

    #     path, _ = QFileDialog.getSaveFileName(
    #         self,  # QWidget parent ✔
    #         "Save Brave Bookmarks As",
    #         default_name,
    #         "HTML files (*.html)"
    #     )

    #     if not path:
    #         return

    #     self.brave_export_path = path
    #     self.save_all_settings()
    #     BraveBookmarksExporter().export_to_file(path)
        
    
        
    # --------------------------------------------------
    # Window close hook (replaces protocol WM_DELETE)
    # --------------------------------------------------
    def closeEvent(self, event):
        """
        Temporary behaviour:
        real tray logic comes later with QSystemTrayIcon
        """
        # event.ignore()  # if you want tray-only close later
        event.accept()

    
        
        



        # def on_auto_align_toggle():
        #     enabled = self.auto_align_switch.isChecked()
        #     self.auto_align_enabled = enabled

        #     self.auto_align_switch.setText(
        #         "Windows In Move Zone On" if enabled else "Windows In Move Zone Off"
        #     )

        #     self.actions.auto_align_toggle()

        # self.auto_align_switch.stateChanged.connect(lambda _: on_auto_align_toggle())

        # self.auto_align_switch.setToolTip(
        #     "Keeps window title bars inside the flick activation zone.\n"
        #     "Only activates after you finish dragging a window.\n"
        #     "Never interferes during movement."
        # )

        # # initial label sync
        # self.auto_align_switch.setText(
        #     "Windows In Move Zone On" if self.auto_align_enabled else "Windows In Move Zone Off"
        # )

        # self.mover_section.content_layout.addWidget(self.auto_align_switch)

        

        # def on_idle_toggle():
        #     enabled = self.opt_idle.isChecked()
        #     self.opt_idle_enabled = enabled
        #     self.opt_idle.setText(
        #         "Idle-plugged Reminder On" if enabled else "Idle-plugged Reminder Off"
        #     )
        #     self.save_all_settings()

        # self.opt_idle.stateChanged.connect(lambda _: on_idle_toggle())

        # # initial label sync
        # self.opt_idle.setText(
        #     "Idle-plugged Reminder On" if self.opt_idle_enabled else "Idle-plugged Reminder Off"
        # )

        # self.usb_section.content_layout.addWidget(self.opt_idle)
        
        # self.opt_download_enabled = self.saved_state.get("usb_download_enabled", True)

        # self.opt_download = QCheckBox(self.usb_section.content)
        # self.opt_download.setChecked(self.opt_download_enabled)

        # def on_download_toggle():
        #     enabled = self.opt_download.isChecked()
        #     self.opt_download_enabled = enabled
        #     self.opt_download.setText(
        #         "Download-finished Reminder On" if enabled else "Download-finished Reminder Off"
        #     )
        #     self.save_all_settings()

        # self.opt_download.stateChanged.connect(lambda _: on_download_toggle())

        # # initial label sync
        # self.opt_download.setText(
        #     "Download-finished Reminder On" if self.opt_download_enabled else "Download-finished Reminder Off"
        # )

        # self.usb_section.content_layout.addWidget(self.opt_download)
        
        
        # self.opt_plug_enabled = self.saved_state.get("usb_plug_enabled", True)

        # self.opt_plug = QCheckBox(self.usb_section.content)
        # self.opt_plug.setChecked(self.opt_plug_enabled)

        # def on_plug_toggle():
        #     enabled = self.opt_plug.isChecked()
        #     self.opt_plug_enabled = enabled
        #     self.opt_plug.setText(
        #         "Plug / Unplug Notification On" if enabled else "Plug / Unplug Notification Off"
        #     )
        #     self.save_all_settings()

        # self.opt_plug.stateChanged.connect(lambda _: on_plug_toggle())

        # # initial label sync
        # self.opt_plug.setText(
        #     "Plug / Unplug Notification On" if self.opt_plug_enabled else "Plug / Unplug Notification Off"
        # )

        # self.usb_section.content_layout.addWidget(self.opt_plug)

        
        # --------------------------------------------------------------
        # Desktop Screenshot Button
        # --------------------------------------------------------------

        # self.btn_desktop_screenshot = QPushButton(
        #     "Desktop Screenshot",
        #     self.organise_frame
        # )
        # self.btn_desktop_screenshot.setFixedWidth(btn_width)
        # self.btn_desktop_screenshot.clicked.connect(self.take_desktop_screenshot)

        # self.btn_desktop_screenshot.setToolTip(
        #     "Minimizes the app, takes a full desktop screenshot.\n"
        #     "Choose a save location, then minimizes the window."
        # )

        # self.organising_section.content_layout.addWidget(
        #     self.btn_desktop_screenshot,
        #     alignment=Qt.AlignmentFlag.AlignLeft
        # )
        
        # # --------------------------------------------------------------
        # # Folder Creator Row
        # # --------------------------------------------------------------

        # folder_row = QWidget(self.organise_frame)
        # folder_row_layout = QHBoxLayout(folder_row)
        # folder_row_layout.setContentsMargins(10, 0, 10, 0)
        # folder_row_layout.setSpacing(5)

        # self.organising_section.content_layout.addWidget(folder_row)
        
        
        # self.btn_create_folder = QPushButton(
        #     "Folder To Desktop",
        #     folder_row
        # )
        # self.btn_create_folder.setFixedWidth(btn_width)
        # self.btn_create_folder.setEnabled(False)
        # self.btn_create_folder.clicked.connect(self._create_desktop_folder)

        # self.btn_create_folder.setToolTip(
        #     "Type a folder name in the box → Click to create.\n"
        #     "A new folder will appear instantly on your Desktop.\n"
        #     "Greyed out if no name entered.\n"
        #     "App self-minimizes after a few seconds."
        # )

        # folder_row_layout.addWidget(self.btn_create_folder)
        
        # entry_group = QWidget(folder_row)
        # entry_layout = QHBoxLayout(entry_group)
        # entry_layout.setContentsMargins(0, 0, 0, 0)
        # entry_layout.setSpacing(5)

        # folder_row_layout.addWidget(entry_group)
        
        # self.folder_name_entry = QLineEdit(entry_group)
        # self.folder_name_entry.setPlaceholderText("Folder name…")
        # self.folder_name_entry.setFixedWidth(250)

        # entry_layout.addWidget(self.folder_name_entry)
        
        # self.folder_status_label = QLabel(" ", entry_group)  # keep width
        # self.folder_status_label.setFixedWidth(300)
        # self.folder_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        # self.folder_status_label.setStyleSheet(
        #     "font-weight: bold; color: #1f6aa5;"
        # )

        # entry_layout.addWidget(self.folder_status_label)
        
        # self.folder_name_entry.textChanged.connect(
        #     self._update_create_folder_button
        # )


        
        # # ==============================================================
        # # Backup Taskbar + Open Backup
        # # ==============================================================

        # backup_buttons_frame = QWidget(self.desktop_backup_frame)
        # backup_buttons_layout = QVBoxLayout(backup_buttons_frame)
        # backup_buttons_layout.setContentsMargins(10, 0, 10, 0)
        # backup_buttons_layout.setSpacing(4)

        # self.desktop_backup_section.content_layout.addWidget(
        #     backup_buttons_frame,
        #     alignment=Qt.AlignmentFlag.AlignLeft
        # )
        
        # backup_row = QWidget(backup_buttons_frame)
        # backup_row_layout = QHBoxLayout(backup_row)
        # backup_row_layout.setContentsMargins(0, 0, 0, 0)
        # backup_row_layout.setSpacing(5)

        # backup_buttons_layout.addWidget(backup_row)
        
        # self.btn_backup_pins = QPushButton(
        #     "Backup Taskbar",
        #     backup_row
        # )
        # self.btn_backup_pins.setFixedWidth(btn_width)
        # self.btn_backup_pins.clicked.connect(
        #     self._backup_taskbar_and_minimize
        # )

        # self.btn_backup_pins.setToolTip(
        #     "Backs up Taskbar icons to a folder chosen\n"
        #     "by the Change Folder button."
        # )

        # backup_row_layout.addWidget(self.btn_backup_pins)
        
        # self.backup_status_label = QLabel(" ", backup_row)  # keep width
        # self.backup_status_label.setFixedWidth(140)
        # self.backup_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        # self.backup_status_label.setStyleSheet(
        #     "font-weight: bold; color: #1f6aa5;"
        # )

        # backup_row_layout.addWidget(self.backup_status_label)


        # # ===================================================================
        # # Backup Folder Path Display + Change Button
        # # ===================================================================

        # path_inner = QWidget(self.desktop_backup_frame)
        # path_inner_layout = QVBoxLayout(path_inner)
        # path_inner_layout.setContentsMargins(10, 0, 10, 0)
        # path_inner_layout.setSpacing(4)

        # self.desktop_backup_section.content_layout.addWidget(path_inner)

        # self.backup_folder_path = self.saved_state.get(
        #     "backup_folder_path",
        #     str(Path.home())
        # )
        
        # self.btn_change_path = QPushButton(
        #     "Change Folder",
        #     path_inner
        # )
        # self.btn_change_path.setFixedWidth(btn_width)
        # self.btn_change_path.clicked.connect(
        #     self.actions.change_backup_folder
        # )

        # self.btn_change_path.setToolTip(
        #     "Chooses folder path for backing up Taskbar icons."
        # )

        # path_inner_layout.addWidget(
        #     self.btn_change_path,
        #     alignment=Qt.AlignmentFlag.AlignLeft
        # )
        
        # self.btn_open_backup = QPushButton(
        #     "Open Backup",
        #     backup_buttons_frame
        # )
        # self.btn_open_backup.setFixedWidth(btn_width)
        # self.btn_open_backup.clicked.connect(
        #     self.actions.open_backup_folder
        # )

        # self.btn_open_backup.setToolTip(
        #     "Opens backed up Taskbar icons folder location."
        # )

        # backup_buttons_layout.addWidget(
        #     self.btn_open_backup,
        #     alignment=Qt.AlignmentFlag.AlignLeft
        # )

        # self.entry_backup_path = QLineEdit(path_inner)
        # self.entry_backup_path.setText(self.backup_folder_path)
        # self.entry_backup_path.setReadOnly(True)
        # self.entry_backup_path.setFixedWidth(420)

        # path_inner_layout.addWidget(self.entry_backup_path)

        
        
        # # ==============================================================
        # # Capture / Restore Desktop Layout
        # # ==============================================================

        # self.icon_buttons_frame = QWidget(self.desktop_icon_frame)
        # icon_buttons_layout = QVBoxLayout(self.icon_buttons_frame)
        # icon_buttons_layout.setContentsMargins(10, 0, 10, 0)
        # icon_buttons_layout.setSpacing(4)

        # self.desktop_icon_layout.content_layout.addWidget(
        #     self.icon_buttons_frame,
        #     alignment=Qt.AlignmentFlag.AlignLeft
        # )
        
        # capture_row = QWidget(self.icon_buttons_frame)
        # capture_row_layout = QHBoxLayout(capture_row)
        # capture_row_layout.setContentsMargins(0, 0, 0, 0)
        # capture_row_layout.setSpacing(6)

        # icon_buttons_layout.addWidget(capture_row)
        
        # self.btn_capture_layout = QPushButton(
        #     "Capture Desktop Layout",
        #     capture_row
        # )
        # self.btn_capture_layout.setFixedWidth(btn_width)
        # self.btn_capture_layout.setFixedHeight(28)
        # self.btn_capture_layout.clicked.connect(
        #     self.actions.capture_desktop_layout
        # )

        # self.btn_capture_layout.setToolTip(
        #     "Captures and restores icon layout on desktops.\n"
        #     "Make sure you right click Desktop → View → turn OFF Auto arrange icons."
        # )

        # capture_row_layout.addWidget(self.btn_capture_layout)
        
        # self.desktop_layout_status = QLabel(" ", capture_row)  # keep width
        # self.desktop_layout_status.setFixedWidth(140)
        # self.desktop_layout_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        # self.desktop_layout_status.setStyleSheet(
        #     "font-weight: bold; color: #1f6aa5;"
        # )

        # capture_row_layout.addWidget(self.desktop_layout_status)
        
        
        # self.btn_restore_layout = QPushButton(
        #     "Restore Layout",
        #     self.icon_buttons_frame
        # )
        # self.btn_restore_layout.setFixedWidth(btn_width)
        # self.btn_restore_layout.setFixedHeight(28)
        # self.btn_restore_layout.clicked.connect(
        #     self.actions.restore_desktop_layout
        # )

        # self.btn_restore_layout.setToolTip(
        #     "Restores a previously saved desktop icon layout.\n"
        #     "Auto arrange icons must be turned OFF."
        # )

        # icon_buttons_layout.addWidget(
        #     self.btn_restore_layout,
        #     alignment=Qt.AlignmentFlag.AlignLeft
        # )

    #  FIX def set_desktop_layout_status(self, text, timeout=2500):
    #     self.desktop_layout_status.configure(text=text)
    #     self.after(timeout, lambda: self.desktop_layout_status.configure(text=" "))

    # ==================================================
    # End of muddafucking initilisation bro
    # ==================================================
    
    # def _backup_taskbar_and_minimize(self):
    #     # run the actual backup
    #     self.actions.backup_pinned_shortcuts()

    # def _set_backup_status_timed(self, text, duration_ms=2000):
    # #  FIX   if hasattr(self, "_backup_status_after_id") and self._backup_status_after_id:
    # #         self.after_cancel(self._backup_status_after_id)

    # #     self.backup_status_label.configure(text=text)
    # #     self._backup_status_after_id = self.after(
    # #         duration_ms,
    # #         lambda: self.backup_status_label.configure(text="")
    # # )   
        
    # def _sync_toggle_label(self, switch, base_text, var):
    #     if var.get():
    #         switch.configure(text=f"{base_text} On")
    #     else:
    #         switch.configure(text=f"{base_text} Off")
        
    
        
    # def take_desktop_screenshot(self):
    #     """
    #     Universal desktop screenshotter:
    #     - Iconifies main GUI
    #     - Iconifies right panel if open
    #     - Takes screenshot
    #     - Prompts for save location
    #     - Ends iconified (both panels)
    #     """

    #     try:
    #         # -------------------------------------------------------
    #         # 2) Capture full desktop
    #         # -------------------------------------------------------
    #         img = ImageGrab.grab()

    #         # -------------------------------------------------------
    #         # 3) Save dialog
    #         # -------------------------------------------------------
    #         default_name = f"DesktopScreenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

    #         save_path = filedialog.asksaveasfilename(
    #             title="Save Desktop Screenshot",
    #             defaultextension=".png",
    #             initialfile=default_name,
    #             filetypes=[("PNG Image", "*.png")],
    #         )

    #         if save_path:
    #             img.save(save_path)
    #             print(f"[SCREENSHOT] Saved: {save_path}")
    #         else:
    #             print("[SCREENSHOT] Cancelled by user")

    #     except Exception as e:
    #         print("[SCREENSHOT] Error:", e)

    #     finally:
    #         pass

    # from PyQt6.QtWidgets import QFileDialog

    # def _choose_brave_export_path(self):
    #     default_name = f"Brave_Bookmarks_Export_{datetime.now().strftime('%Y-%m-%d')}.html"

    #     path, _ = QFileDialog.getSaveFileName(
    #         self,  # QWidget parent
    #         "Save Brave Bookmarks As",
    #         default_name,
    #         "HTML files (*.html)"
    #     )

    #     if not path:
    #         return

    #     self.brave_export_path = path
    #     self.save_all_settings()

    
                    
    # def open_this_pc(self):
    #     os.system("explorer shell:MyComputerFolder")

    # def apply_always_on_top(self, enabled: bool):
    #     """Apply Always-on-Top state using both Tk and WinAPI."""
    #     try:
    #         self.attributes("-topmost", enabled)
    #     except Exception as e:
    #         print("[AlwaysOnTop] Tk error:", e)

    #     try:
    #         hwnd = self.winfo_id()
    #         hWndTopMost = -1 if enabled else -2
    #         ctypes.windll.user32.SetWindowPos(
    #             hwnd,
    #             hWndTopMost,
    #             0, 0, 0, 0,
    #             0x0003  # SWP_NOSIZE | SWP_NOMOVE
    #         )
    #     except Exception as e:
    #         print("[AlwaysOnTop] WinAPI error:", e)

    # def resize_to_fit(self):
    #     """Keep the window height locked; never auto-resize to content."""
    #     self.update_idletasks()  # Recalculate layout

    # ===================================================================
    #  Save ALL toggle states to JSON
    # ===================================================================

    # def save_section_states(self):
    #     """Save expanded/collapsed states of all collapsible sections."""
    #     if not hasattr(self, "collapsible_sections"):
    #         return
        
    #     left_states = {}
    #     right_states = {}

    #     for section in self.collapsible_sections:
    #         if section.parent == self.main_frame:
    #             left_states[section.section_id] = section.open
    #         elif section.parent == self.side_frame:
    #             right_states[section.section_id] = section.open

    #     # Load current JSON
    #     data = load_state()

    #     # Update section states
        
    #     data["left_section_states"] = left_states
    #     data["right_section_states"] = right_states
        
    #     print("collapsible count:", len(self.collapsible_sections))
    #     print("collapsible count:", len(self.collapsible_sections))
    #     for s in self.collapsible_sections:
    #         print("sec:", s.section_id, "parent:", type(s.parent), "toplevel:", s.parent.winfo_toplevel())
            
    #     save_state(data)

    # # ===================================================================
    # #  Create Folder On Desktop
    # # ===================================================================
    
    # def _create_desktop_folder(self):
    #     folder_name = self.folder_name_var.get().strip()

    #     if not folder_name:
    #         return

    #     desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    #     new_path = os.path.join(desktop, folder_name)

    #     try:
    #         if os.path.exists(new_path):
    #             messagebox.showerror(
    #                 "Error",
    #                 "A folder with that name already exists on Desktop."
    #             )
    #             return

    #         os.makedirs(new_path)

    #         # Clear entry
    #         self.folder_name_var.set("")

    #         # Timed success message
    #         self._set_folder_status_timed("Folder Made", 2000)
            
    #         def minimize_both():
    #             if (
    #                 hasattr(self, "advanced_panel")
    #                 and self.advanced_panel
    #                 and self.advanced_panel.winfo_viewable()
    #             ):
    #                 self.advanced_panel.iconify()

    #             # FIX self.iconify

    #         # FIX self.after

    #     except Exception as e:
    #         messagebox.showerror(
    #             "Error",
    #             f"Could not create folder:\n{e}"
    #         )
            
    # def _update_create_folder_button(self, *_):
    #     name = self.folder_name_var.get().strip()
        
    #     if name:
    #         self.btn_create_folder.configure(state="normal")
    #         self.folder_status_label.configure(text="")
    #     else:
    #         self.btn_create_folder.configure(state="disabled")
    #         self.folder_status_label.configure(text="")
            
    # def _set_folder_status_timed(self, text, duration_ms=2000):
    #     # Cancel any existing timer
    #     # FIX if self._folder_status_after_id:
    #     #     self.after_cancel(self._folder_status_after_id)
    #     #     self._folder_status_after_id = None

    #     # Set text immediately
    #     self.folder_status_label.configure(text=text)

    #     # # FIX Schedule clear
    #     # self._folder_status_after_id = self.after(
    #     #     duration_ms,
    #     #     lambda: self.folder_status_label.configure(text="")
    #     # )

    # # ---------------- Helpers that run on Tk main thread ----------------
    
    # def _show_window(self):
        
    #     # FIX deiconify and lift for cute
        
    #     try:
    #         self.focus_force()
    #     except:
    #         pass
    #     self.attributes("-topmost", True)
    #     try:
    #         ctypes.windll.user32.SetWindowPos(
    #             self.winfo_id(),
    #             -1,
    #             0, 0, 0, 0,
    #             0x0003
    #         )
    #     except Exception as e:
    #         print("[TOPMOST] WinAPI failed:", e)
    
# ===================================================================
# Launch App
# ===================================================================
def main():
    app = QApplication(sys.argv)   # ✅ FIRST
    window = UtilityControlApp()   # QWidget created AFTER
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

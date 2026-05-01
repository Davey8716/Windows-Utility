import ctypes
import os
import shutil
import string
import subprocess
from pathlib import Path

import styles
from collapsible_section import CollapsibleSection, SECTION_FRAME_MAX_WIDTH
from state_manager import save_state
from universal_bookmarks_export import BraveBookmarksExporter
from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QListWidget,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)


def get_drive_info():
    drives = []
    for letter in string.ascii_uppercase:
        path = f"{letter}:\\"
        if not os.path.exists(path):
            continue
        try:
            total, used, free = shutil.disk_usage(path)
        except Exception:
            continue
        drives.append(
            {
                "drive": path,
                "total": total,
                "free": free,
                "used": used,
            }
        )
    return drives


class AdvancedToolsPanel(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setViewportMargins(0, 0, 12, 0)
        root_layout.addWidget(self.scroll)

        self.side_frame = QWidget()
        self.side_frame.setFixedWidth(self.app.main_scroll.width())
        self.scroll.setWidget(self.side_frame)

        self.side_layout = QVBoxLayout(self.side_frame)
        self.side_layout.setContentsMargins(10, 5, 10, 5)
        self.side_layout.setSpacing(6)
        self.side_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title_row = QWidget()
        title_row.setMaximumWidth(SECTION_FRAME_MAX_WIDTH)
        title_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        title_row_layout = QHBoxLayout(title_row)
        title_row_layout.setContentsMargins(10, 10, 10, 10)

        title_spacer = QWidget(title_row)
        title_spacer.setFixedSize(styles.ICON_BUTTON_WIDTH, styles.ICON_BUTTON_HEIGHT)

        self.advanced_title = QLabel("Advanced Tools", title_row)
        self.advanced_title.setStyleSheet(styles.label_style(font_size=20))
        self.advanced_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_row_layout.addWidget(title_spacer)
        title_row_layout.addStretch()
        title_row_layout.addWidget(self.advanced_title)
        title_row_layout.addStretch()

        self.master_collapse_btn_right = QToolButton()
        self.master_collapse_btn_right.setFixedSize(
            styles.ICON_BUTTON_WIDTH,
            styles.ICON_BUTTON_HEIGHT,
        )
        self.app.master_toggle_right_state = bool(
            self.app.saved_state.get("master_toggle_right", False)
        )
        self.master_collapse_btn_right.setArrowType(
            Qt.ArrowType.DownArrow
            if self.app.master_toggle_right_state
            else Qt.ArrowType.UpArrow
        )
        self.master_collapse_btn_right.setStyleSheet(
            styles.arrow_button_style(styles.TEXT_LIGHT, styles.SURFACE_DARK)
        )
        self.master_collapse_btn_right.clicked.connect(
            self.toggle_all_right_sections
        )
        self.app.register_tooltip(
            self.master_collapse_btn_right,
            "Master collapse toggle for all of these regions.",
        )
        title_row_layout.addWidget(self.master_collapse_btn_right)
        self.side_layout.addWidget(title_row)

        self.windows_utility_section = CollapsibleSection(
            parent=self.side_frame,
            title_text="Windows Utilities",
            section_id="windows_utilities",
            app=self.app,
            initial_open=self.app.saved_state
            .get("right_section_states", {})
            .get("windows_utilities", False),
        )
        self.side_layout.addWidget(self.windows_utility_section)
        self.app.collapsible_sections.append(self.windows_utility_section)
        self.app.register_tooltip(
            self.windows_utility_section.toggle_btn,
            "Shows windows utilities grouped by type and quick actions.",
        )

        self._build_windows_utilities()

        self.sidebar_utils_section = CollapsibleSection(
            parent=self.side_frame,
            title_text="Side Bar Utilities",
            section_id="sidebar_utils_section",
            app=self.app,
            initial_open=self.app.saved_state
            .get("right_section_states", {})
            .get("sidebar_utils_section", False),
        )
        self.app.collapsible_sections.append(self.sidebar_utils_section)
        self.side_layout.addWidget(self.sidebar_utils_section)
        self.build_sidebar_utilities()
        self.app.register_tooltip(
            self.sidebar_utils_section.toggle_btn,
            "Side bar actions menus.",
        )

        self.sidebar_output = QTextEdit()
        self.sidebar_output.setFixedHeight(285)
        self.sidebar_output.setReadOnly(True)
        self.sidebar_output.setStyleSheet(styles.text_edit_style("Consolas", 15))
        self.sidebar_utils_section.content_layout.addWidget(self.sidebar_output)

        self.display_space_section = CollapsibleSection(
            parent=self.side_frame,
            title_text="Drive Space Display",
            section_id="drive_space_display",
            app=self.app,
            initial_open=self.app.saved_state
            .get("right_section_states", {})
            .get("drive_space_display", False),
        )
        self.side_layout.addWidget(self.display_space_section)
        self.app.collapsible_sections.append(self.display_space_section)
        self.app.register_tooltip(
            self.display_space_section.toggle_btn,
            "Shows disk usage for all detected drives.",
        )
        self._build_drive_space_display()

    def _build_windows_utilities(self):
        parent_layout = self.windows_utility_section.content_layout

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        parent_layout.addWidget(row)

        left_drop_col = QWidget()
        left_drop_layout = QVBoxLayout(left_drop_col)
        left_drop_layout.setContentsMargins(0, 0, 0, 0)
        left_drop_layout.setSpacing(10)

        right_drop_col = QWidget()
        right_drop_layout = QVBoxLayout(right_drop_col)
        right_drop_layout.setContentsMargins(0, 0, 0, 0)
        right_drop_layout.setSpacing(10)

        row_layout.addWidget(left_drop_col)
        row_layout.addWidget(right_drop_col)
        row_layout.setStretch(0, 1)
        row_layout.setStretch(1, 1)
        row_layout.setAlignment(left_drop_col, Qt.AlignmentFlag.AlignTop)
        row_layout.setAlignment(right_drop_col, Qt.AlignmentFlag.AlignTop)

        self._add_windows_dropdown(
            left_drop_layout, "System", self._system_utilities()
        )
        self._add_windows_dropdown(
            left_drop_layout, "Hardware", self._hardware_utilities()
        )
        self._add_windows_dropdown(
            right_drop_layout, "Network", self._network_utilities()
        )
        self._add_windows_dropdown(
            right_drop_layout, "Startup & Power", self._startup_power_utilities()
        )

    def _build_drive_space_display(self):
        drive_parent = self.display_space_section.content_layout

        btn_this_pc = QPushButton("Open This PC")
        styles.apply_default_button_size(btn_this_pc)
        btn_this_pc.setStyleSheet(styles.button_text_style(14))
        self._install_green_flash(btn_this_pc)
        btn_this_pc.clicked.connect(lambda: self._minimize_and_run(self._open_this_pc))
        self.app.register_tooltip(btn_this_pc, "Opens This PC in File Explorer.")
        drive_parent.addWidget(btn_this_pc)

        self.drive_space_list = QListWidget()
        self.drive_space_list.setFixedHeight(120)
        self.drive_space_list.setSpacing(0)
        self.drive_space_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.drive_space_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.drive_space_list.setWordWrap(False)
        self.drive_space_list.setStyleSheet(
            """
            QListWidget {
                %s
                background-color: %s;
                color: %s;
                border: 2px solid %s;
                border-radius: 6px;
                padding: 6px;
            }
            QListWidget::item {
                padding: 1px 6px;
                margin: 0px;
            }
            QListWidget::item:selected {
                background-color: %s;
                color: %s;
            }
            """
            % (
                styles.label_style(font_size=15, bold=True, font_family="Consolas"),
                styles.qcolor_css(styles.PANEL_BG),
                styles.qcolor_css(styles.TEXT_LIGHT),
                styles.qcolor_css(styles.PANEL_BORDER),
                styles.qcolor_css(styles.PANEL_HOVER),
                styles.qcolor_css(styles.TEXT_LIGHT),
            )
        )
        drive_parent.addWidget(self.drive_space_list)

        def refresh_drive_display():
            self.drive_space_list.clear()
            metrics = self.drive_space_list.fontMetrics()
            for d in get_drive_info():
                used_gb = (d["total"] - d["free"]) / (1024 ** 3)
                total_gb = d["total"] / (1024 ** 3)
                free_gb = d["free"] / (1024 ** 3)
                text = (
                    f"{d['drive']}  Used: {used_gb:.1f} GB  Free: {free_gb:.1f} GB  "
                    f"Total: {total_gb:.1f} GB"
                )
                item = QListWidgetItem(text)
                item_width = metrics.horizontalAdvance(text) + 24
                item.setSizeHint(QSize(item_width, 20))
                self.drive_space_list.addItem(item)

        refresh_drive_display()
        self.drive_refresh_timer = QTimer(self)
        self.drive_refresh_timer.timeout.connect(refresh_drive_display)
        self.drive_refresh_timer.start(10_000)

    def _add_action_button(self, parent_layout, label, action):
        button = QPushButton(label)
        styles.apply_default_button_size(button)
        button.setStyleSheet(styles.button_text_style(14))
        self._install_green_flash(button)
        button.clicked.connect(action)
        parent_layout.addWidget(button)
        return button

    def _install_green_flash(self, button: QPushButton):
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

    def run_sleep(self):
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])

    def run_lock_pc(self):
        ctypes.windll.user32.LockWorkStation()

    def run_restart(self):
        subprocess.Popen(["shutdown", "/r", "/t", "0"])

    def run_logout(self):
        subprocess.Popen(["shutdown", "/l"])

    def run_shutdown(self):
        subprocess.Popen(["shutdown", "/s", "/t", "0"])

    def _system_utilities(self):
        return {
            "Control Panel": lambda: subprocess.Popen(["control"]),
            "System Settings": self.open_system_settings,
            "System Information": lambda: subprocess.Popen(["msinfo32"]),
            "Task Manager": lambda: subprocess.Popen(["taskmgr"]),
        }

    def _hardware_utilities(self):
        return {
            "Device Manager": self.open_device_manager,
            "Disk Management": self.open_disk_management,
            "Services": self.open_services,
            "Event Viewer": self.open_event_viewer,
        }

    def open_device_manager(self):
        self._shell_open("devmgmt.msc")

    def open_disk_management(self):
        self._shell_open("diskmgmt.msc")

    def open_services(self):
        self._shell_open("services.msc")

    def open_event_viewer(self):
        self._shell_open("eventvwr.msc")

    def open_system_settings(self):
        self._shell_open("ms-settings:")

    def _shell_open(self, target: str):
        ctypes.windll.shell32.ShellExecuteW(None, "open", target, None, None, 1)

    def _shell_execute(self, target: str, parameters: str | None = None):
        ctypes.windll.shell32.ShellExecuteW(
            None, "open", target, parameters, None, 1
        )

    def _minimize_and_run(self, action):
        self.app.showMinimized()
        self.showMinimized()
        action()

    def _network_utilities(self):
        return {
            "Network Connections": self.open_network_connections,
            "Firewall": self.open_firewall,
            "IP Configuration": lambda: subprocess.Popen(["cmd", "/k", "ipconfig"]),
            "Router Login": self.app.actions.open_router_page,
        }

    def open_network_connections(self):
        self._shell_execute("control.exe", "ncpa.cpl")

    def open_firewall(self):
        self._shell_open("wf.msc")

    def _startup_power_utilities(self):
        return {
            "Startup Apps": self.open_startup_apps,
            "Power Options": self.open_power_options,
        }

    def open_startup_apps(self):
        self._shell_open("ms-settings:startupapps")

    def open_power_options(self):
        self._shell_execute("control.exe", "/name Microsoft.PowerOptions")

    def _add_windows_dropdown(self, parent_layout, label, actions_map):
        placeholder = f" {label} "
        combo = QComboBox()
        combo.setFixedWidth(160)
        combo.addItem(placeholder)
        combo.addItems(sorted(actions_map.keys()))
        combo.setCurrentText(placeholder)
        combo.setStyleSheet(styles.combo_style(15))

        def runner(text: str):
            if text == placeholder:
                return
            action = actions_map.get(text)
            if action:
                self._minimize_and_run(action)
            combo.setCurrentText(placeholder)

        combo.currentTextChanged.connect(runner)
        parent_layout.addWidget(combo)

    def _sidebar_network_actions(self):
        return {
            "Flush DNS": self.flush_dns,
            "Renew IP": self.renew_ip,
            "IP Config": self.show_ip_config,
            "Restart Explorer": self.restart_explorer,
            "Restart Bluetooth Service": self.restart_bluetooth,
        }

    def _sidebar_cleanup_actions(self):
        return {
            "Clear Temp Files": self.clear_temp,
            "Clear Clipboard": self.clear_clipboard,
        }

    def _sidebar_quick_open_actions(self):
        return {
            "Open Downloads Folder": self.open_downloads,
            "Open Startup Folder": self.open_startup_folder,
            "Clipboard History": self.open_clipboard_history,
        }

    def build_sidebar_utilities(self):
        parent_layout = self.sidebar_utils_section.content_layout
        dropdown_grid = QWidget()
        grid_layout = QGridLayout(dropdown_grid)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setVerticalSpacing(10)
        parent_layout.addWidget(dropdown_grid)

        self._add_sidebar_dropdown(
            grid_layout,
            0,
            0,
            "Network / System Quick Fix",
            self._sidebar_network_actions(),
        )
        self._add_sidebar_dropdown(
            grid_layout,
            0,
            1,
            "Cleanup / Quick Actions",
            self._sidebar_cleanup_actions(),
        )
        self._add_sidebar_dropdown(
            grid_layout,
            1,
            0,
            "Quick Open",
            self._sidebar_quick_open_actions(),
        )
        self._add_sidebar_dropdown(
            grid_layout,
            1,
            1,
            "System Integrity & Disk Health",
            self._sidebar_system_integrity_actions(),
        )

    def _sidebar_system_integrity_actions(self):
        return {
            "Run System File Checker (SFC)": self.run_sfc_scannow,
            "Run Check Disk (CHKDSK)": self.run_chkdsk,
        }

    def _ensure_admin(self):
        try:
            if ctypes.windll.shell32.IsUserAnAdmin():
                return True
        except Exception:
            pass

        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            os.sys.executable,
            " ".join(os.sys.argv),
            None,
            1,
        )
        return False

    def _run_and_output(self, cmd, shell=True):
        self.sidebar_output.clear()
        try:
            result = subprocess.run(
                cmd,
                shell=shell,
                capture_output=True,
                text=True,
            )
            output = result.stdout or result.stderr or "[no output]"
        except Exception as e:
            output = str(e)
        self.sidebar_output.append(output)

    def flush_dns(self):
        self._run_and_output("ipconfig /flushdns")

    def renew_ip(self):
        self._run_and_output("ipconfig /renew")

    def show_ip_config(self):
        self._run_and_output("ipconfig")

    def restart_explorer(self):
        self._run_and_output("taskkill /f /im explorer.exe && start explorer")

    def restart_bluetooth(self):
        self._run_and_output("powershell Restart-Service bthserv -Force")

    def clear_temp(self):
        self._run_and_output("del /q /s %temp%\\*", shell=True)

    def clear_clipboard(self):
        self._run_and_output("cmd /c echo off | clip")

    def open_downloads(self):
        self.sidebar_output.clear()
        subprocess.Popen(["explorer", "shell:downloads"])
        self.sidebar_output.append("Opened Downloads folder.")

    def open_startup_folder(self):
        self.sidebar_output.clear()
        subprocess.Popen(["explorer", "shell:startup"])
        self.sidebar_output.append("Opened Startup folder.")

    def open_clipboard_history(self):
        self.sidebar_output.clear()
        subprocess.Popen(["cmd", "/c", "start", "ms-settings:clipboard"])
        self.sidebar_output.append("Opened Clipboard History.")

    def run_sfc_scannow(self):
        if self._ensure_admin():
            self._run_and_output("sfc /scannow")

    def run_chkdsk(self):
        if self._ensure_admin():
            self._run_and_output("chkdsk")

    def _add_sidebar_dropdown(self, parent_layout, row, column, title, actions_map):
        placeholder = f" {title} "
        combo = QComboBox()
        combo.setMinimumWidth(180)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.addItem(placeholder)
        combo.addItems(actions_map.keys())
        combo.setCurrentText(placeholder)
        combo.setStyleSheet(styles.combo_style(14))

        def runner(text: str):
            if text == placeholder:
                return
            action = actions_map.get(text)
            if action:
                action()
            combo.setCurrentText(placeholder)

        combo.currentTextChanged.connect(runner)
        parent_layout.addWidget(combo, row, column)

    def _open_this_pc(self):
        subprocess.Popen(["explorer", "shell:MyComputerFolder"])

    def _run_brave_export(self):
        start_dir = Path(self.app.get_default_bookmarks_export_dir())
        start_dir.mkdir(parents=True, exist_ok=True)
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Bookmarks",
            str(start_dir / "Brave_Bookmarks.html"),
            "HTML Files (*.html)",
        )
        if not out_path:
            return None

        if BraveBookmarksExporter().export_to_file(out_path):
            save_state(self.app.state)
            return out_path

        return False

    def toggle_all_right_sections(self):
        any_open = any(
            section.is_open
            for section in self.app.collapsible_sections
            if getattr(section, "parent", lambda: None)() is self.side_frame
        )
        new_state = not any_open
        self.app.master_toggle_right_state = new_state
        self.app.state["master_toggle_right"] = new_state
        self.master_collapse_btn_right.setArrowType(
            Qt.ArrowType.DownArrow if new_state else Qt.ArrowType.UpArrow
        )

        for section in self.app.collapsible_sections:
            if hasattr(section, "set_open") and section.parent() is self.side_frame:
                if section.is_open != new_state:
                    section.set_open(new_state)

        self.app.save_all_settings()

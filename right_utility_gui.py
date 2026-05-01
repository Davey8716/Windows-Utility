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
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
        self.sidebar_output.setFixedHeight(120)
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

        self.bookmarks_exporter_section = CollapsibleSection(
            parent=self.side_frame,
            title_text="Universal Bookmarks Exporter",
            section_id="bookmarks_exporter",
            app=self.app,
            initial_open=self.app.saved_state
            .get("right_section_states", {})
            .get("bookmarks_exporter", False),
        )
        self.side_layout.addWidget(self.bookmarks_exporter_section)
        self.app.collapsible_sections.append(self.bookmarks_exporter_section)
        self._build_bookmarks_exporter()

    def _build_windows_utilities(self):
        parent_layout = self.windows_utility_section.content_layout

        quick_row = QWidget()
        quick_row_layout = QHBoxLayout(quick_row)
        quick_row_layout.setContentsMargins(0, 0, 0, 10)
        quick_row_layout.setSpacing(10)
        parent_layout.addWidget(quick_row)

        left_col = QWidget()
        left_col_layout = QVBoxLayout(left_col)
        left_col_layout.setContentsMargins(0, 0, 0, 0)
        left_col_layout.setSpacing(10)

        right_col = QWidget()
        right_col_layout = QVBoxLayout(right_col)
        right_col_layout.setContentsMargins(0, 0, 0, 0)
        right_col_layout.setSpacing(10)

        quick_row_layout.addWidget(left_col)
        quick_row_layout.addWidget(right_col)
        quick_row_layout.setStretch(0, 1)
        quick_row_layout.setStretch(1, 1)
        quick_row_layout.setAlignment(left_col, Qt.AlignmentFlag.AlignTop)
        quick_row_layout.setAlignment(right_col, Qt.AlignmentFlag.AlignTop)

        self._add_action_button(
            left_col_layout,
            "System Settings",
            lambda: subprocess.Popen(["cmd", "/c", "start", "ms-settings:"]),
        )
        self._add_action_button(
            left_col_layout,
            "Task Manager",
            lambda: subprocess.Popen(["taskmgr"]),
        )
        self._add_action_button(
            right_col_layout,
            "Device Manager",
            lambda: subprocess.Popen(["devmgmt.msc"]),
        )
        self._add_action_button(
            right_col_layout,
            "Router Login",
            self.app.actions.open_router_page,
        )

        self.power_actions_row = QWidget()
        power_layout = QHBoxLayout(self.power_actions_row)
        power_layout.setContentsMargins(0, 0, 0, 10)
        power_layout.setSpacing(10)
        parent_layout.addWidget(self.power_actions_row)

        self._add_action_button(
            power_layout,
            "Sleep",
            lambda: subprocess.Popen(
                ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
            ),
        )
        self._add_action_button(
            power_layout,
            "Lock PC",
            lambda: ctypes.windll.user32.LockWorkStation(),
        )
        self._add_action_button(
            power_layout,
            "Restart",
            lambda: subprocess.Popen(["shutdown", "/r", "/t", "0"]),
        )
        self._add_action_button(
            power_layout,
            "Shutdown",
            lambda: subprocess.Popen(["shutdown", "/s", "/t", "0"]),
        )
        self.power_actions_row.setVisible(
            bool(self.app.state.get("power_options_enabled", False))
        )

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
        btn_this_pc.clicked.connect(self._open_this_pc)
        self.app.register_tooltip(btn_this_pc, "Opens This PC in File Explorer.")
        drive_parent.addWidget(btn_this_pc)

        self.drive_space_list = QListWidget()
        self.drive_space_list.setFixedHeight(120)
        self.drive_space_list.setStyleSheet(
            """
            QListWidget {
                background-color: %s;
                color: %s;
                border: 2px solid %s;
                border-radius: 6px;
                padding: 6px;
            }
            QListWidget::item {
                padding: 4px 6px;
            }
            QListWidget::item:selected {
                background-color: %s;
                color: %s;
            }
            """
            % (
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
            for d in get_drive_info():
                used_gb = (d["total"] - d["free"]) / (1024 ** 3)
                total_gb = d["total"] / (1024 ** 3)
                free_gb = d["free"] / (1024 ** 3)
                self.drive_space_list.addItem(
                    f"{d['drive']}  Used: {used_gb:.1f} GB  Free: {free_gb:.1f} GB  Total: {total_gb:.1f} GB"
                )

        refresh_drive_display()
        self.drive_refresh_timer = QTimer(self)
        self.drive_refresh_timer.timeout.connect(refresh_drive_display)
        self.drive_refresh_timer.start(10_000)

    def _build_bookmarks_exporter(self):
        self.btn_brave_export = QPushButton("Export Brave Bookmarks")
        styles.apply_default_button_size(self.btn_brave_export, width=210)
        self.btn_brave_export.setStyleSheet(styles.button_text_style(15))
        self._install_green_flash(self.btn_brave_export)
        self.btn_brave_export.clicked.connect(self._run_brave_export)
        self.app.register_tooltip(
            self.btn_brave_export,
            "Exports Brave bookmarks and remembers the last saved path.",
        )
        self.bookmarks_exporter_section.content_layout.addWidget(self.btn_brave_export)

        self.brave_export_entry = QLineEdit()
        self.brave_export_entry.setReadOnly(True)
        self.brave_export_entry.setFixedWidth(365)
        self.brave_export_entry.setStyleSheet(styles.line_edit_style(15))
        self.brave_export_entry.setText(self.app.state.get("brave_export_path", ""))
        self.bookmarks_exporter_section.content_layout.addWidget(self.brave_export_entry)

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

    def _system_utilities(self):
        return {
            "Control Panel": lambda: subprocess.Popen(["control"]),
            "System Settings": lambda: subprocess.Popen(["cmd", "/c", "start", "ms-settings:"]),
            "System Information": lambda: subprocess.Popen(["msinfo32"]),
            "Task Manager": lambda: subprocess.Popen(["taskmgr"]),
        }

    def _hardware_utilities(self):
        return {
            "Device Manager": lambda: subprocess.Popen(["devmgmt.msc"]),
            "Disk Management": lambda: subprocess.Popen(["diskmgmt.msc"]),
            "Services": lambda: subprocess.Popen(["services.msc"]),
            "Event Viewer": lambda: subprocess.Popen(["eventvwr.msc"]),
        }

    def _network_utilities(self):
        return {
            "Network Connections": lambda: subprocess.Popen(["ncpa.cpl"]),
            "Firewall": lambda: subprocess.Popen(["wf.msc"]),
            "IP Configuration": lambda: subprocess.Popen(["cmd", "/k", "ipconfig"]),
            "Router Login": self.app.actions.open_router_page,
        }

    def _startup_power_utilities(self):
        return {
            "Startup Apps": lambda: subprocess.Popen(
                ["cmd", "/c", "start", "ms-settings:startupapps"]
            ),
            "Power Options": lambda: subprocess.Popen(["powercfg.cpl"]),
        }

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
                self.app.showMinimized()
                self.showMinimized()
                action()
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
        self._add_sidebar_dropdown(
            parent_layout,
            "Network / System Quick Fix",
            self._sidebar_network_actions(),
        )
        self._add_sidebar_dropdown(
            parent_layout,
            "Cleanup / Quick Actions",
            self._sidebar_cleanup_actions(),
        )
        self._add_sidebar_dropdown(
            parent_layout,
            "Quick Open",
            self._sidebar_quick_open_actions(),
        )
        self._add_sidebar_dropdown(
            parent_layout,
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

    def _add_sidebar_dropdown(self, parent_layout, title, actions_map):
        placeholder = f" {title} "
        combo = QComboBox()
        combo.setFixedWidth(260)
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
        parent_layout.addWidget(combo)

    def _open_this_pc(self):
        subprocess.Popen(["explorer", "shell:MyComputerFolder"])

    def _run_brave_export(self):
        default_path = self.app.state.get("brave_export_path", "")
        start_dir = str(Path(default_path).parent) if default_path else str(Path.home())
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Brave Bookmarks",
            str(Path(start_dir) / "Brave_Bookmarks.html"),
            "HTML Files (*.html)",
        )
        if not out_path:
            return False

        if BraveBookmarksExporter().export_to_file(out_path):
            self.app.state["brave_export_path"] = out_path
            save_state(self.app.state)
            self.brave_export_entry.setText(out_path)
            return True

        return False

    def toggle_all_right_sections(self):
        new_state = not self.app.master_toggle_right_state
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

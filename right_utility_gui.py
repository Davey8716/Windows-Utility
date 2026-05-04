import ctypes
import os
import shutil
import string
import subprocess
import tempfile
import uuid
from pathlib import Path

import styles
from collapsible_section import CollapsibleSection
from state_manager import save_state
from universal_bookmarks_export import BraveBookmarksExporter
from PySide6.QtCore import QPoint, QSize, Qt, QTimer, QProcess
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QListWidget,
    QMessageBox,
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
    WINDOWS_UTILITIES_FRAME_WIDTH = 370
    WINDOWS_UTILITIES_SECTION_WIDTH = WINDOWS_UTILITIES_FRAME_WIDTH + 8
    WINDOWS_UTILITIES_CONTENT_WIDTH = WINDOWS_UTILITIES_FRAME_WIDTH - 8
    WINDOWS_UTILITIES_ROW_WIDTH = WINDOWS_UTILITIES_CONTENT_WIDTH - 20
    WINDOWS_UTILITIES_COLUMN_WIDTH = (
        WINDOWS_UTILITIES_ROW_WIDTH - 10
    ) // 2

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._sidebar_process = None
        self._sidebar_output_timer = None
        self._sidebar_output_path = None
        self._sidebar_output_offset = 0

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root_layout.addWidget(self.scroll)

        self.side_frame = QWidget()
        self.side_frame.setMinimumWidth(styles.RIGHT_SECTION_MAX_WIDTH)
        self.side_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.scroll.setWidget(self.side_frame)

        self.side_layout = QVBoxLayout(self.side_frame)
        self.side_layout.setContentsMargins(10, 5, 10, 5)
        self.side_layout.setSpacing(6)
        self.side_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title_row = QWidget()
        title_row.setMaximumWidth(styles.RIGHT_SECTION_MAX_WIDTH)
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
        self.windows_utility_section.main_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.windows_utility_section.setFixedWidth(
            self.WINDOWS_UTILITIES_SECTION_WIDTH
        )
        self.windows_utility_section.header.setFixedWidth(
            self.WINDOWS_UTILITIES_FRAME_WIDTH
        )
        self.windows_utility_section.container.setFixedWidth(
            self.WINDOWS_UTILITIES_FRAME_WIDTH
        )
        self.windows_utility_section.content.setFixedWidth(
            self.WINDOWS_UTILITIES_CONTENT_WIDTH
        )

        self._build_windows_utilities()

        self.sidebar_utils_section = CollapsibleSection(
            parent=self.side_frame,
            title_text="Maintenance & Quick Actions",
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
            "Shows maintenance, cleanup, repair, and quick-access action menus.",
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
        row.setFixedWidth(self.WINDOWS_UTILITIES_ROW_WIDTH)
        row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        parent_layout.addWidget(row)

        left_drop_col = QWidget()
        left_drop_col.setFixedWidth(self.WINDOWS_UTILITIES_COLUMN_WIDTH)
        left_drop_layout = QVBoxLayout(left_drop_col)
        left_drop_layout.setContentsMargins(0, 0, 0, 0)
        left_drop_layout.setSpacing(10)

        right_drop_col = QWidget()
        right_drop_col.setFixedWidth(self.WINDOWS_UTILITIES_COLUMN_WIDTH)
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
        self.btn_this_pc = btn_this_pc
        styles.apply_default_button_size(btn_this_pc)
        btn_this_pc.setStyleSheet(styles.button_text_style(14))
        self._install_green_flash(btn_this_pc)
        btn_this_pc.clicked.connect(self.toggle_this_pc)
        self.app.register_tooltip(
            btn_this_pc,
            "Opens This PC in File Explorer, or closes it if already open.",
        )
        drive_parent.addWidget(btn_this_pc)

        self.this_pc_button_timer = QTimer(self)
        self.this_pc_button_timer.timeout.connect(self._refresh_this_pc_button)
        self.this_pc_button_timer.start(1000)
        self._refresh_this_pc_button()

        self.drive_space_list = QListWidget()
        self.drive_space_list.setFixedHeight(120)
        self.drive_space_list.setSpacing(0)
        self.drive_space_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.drive_space_list.setTextElideMode(Qt.TextElideMode.ElideRight)
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
            for d in get_drive_info():
                used_gb = (d["total"] - d["free"]) / (1024 ** 3)
                total_gb = d["total"] / (1024 ** 3)
                free_gb = d["free"] / (1024 ** 3)
                text = (
                    f"{d['drive']}  Used: {used_gb:.1f} GB  Free: {free_gb:.1f} GB  "
                    f"Total: {total_gb:.1f} GB"
                )
                item = QListWidgetItem(text)
                item.setSizeHint(QSize(0, 20))
                self.drive_space_list.addItem(item)

        refresh_drive_display()
        self.drive_refresh_timer = QTimer(self)
        self.drive_refresh_timer.timeout.connect(refresh_drive_display)
        self.drive_refresh_timer.start(10_000)

    def _refresh_this_pc_button(self):
        is_open = self.app.actions.is_this_pc_open()
        if hasattr(self, "btn_this_pc"):
            self.btn_this_pc.setText("Close This PC" if is_open else "Open This PC")

    def toggle_this_pc(self):
        if self.app.actions.is_this_pc_open():
            closed = self.app.actions.close_this_pc()
            self._refresh_this_pc_button()
            if closed:
                return
            self.app._show_timed_message(
                QMessageBox.Icon.Warning,
                "This PC",
                "Could not close This PC.",
            )
            return

        self._minimize_and_run(self._open_this_pc)
        self._refresh_this_pc_button()
        QTimer.singleShot(500, self._refresh_this_pc_button)

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

    def _is_admin(self):
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _stop_sidebar_output_timer(self):
        timer = self._sidebar_output_timer
        if timer is not None:
            timer.stop()
            timer.deleteLater()
            self._sidebar_output_timer = None

    def _reset_sidebar_process(self):
        if self._sidebar_process is not None:
            self._sidebar_process.kill()
            self._sidebar_process.deleteLater()
            self._sidebar_process = None
        self._stop_sidebar_output_timer()
        self._sidebar_output_path = None
        self._sidebar_output_offset = 0

    def _append_sidebar_output(self, text: str):
        if not text:
            return
        cursor = self.sidebar_output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self.sidebar_output.setTextCursor(cursor)
        self.sidebar_output.ensureCursorVisible()

    def _read_process_output(self):
        process = self._sidebar_process
        if not process:
            return

        stdout_text = bytes(process.readAllStandardOutput()).decode(
            "utf-8",
            errors="replace",
        )
        stderr_text = bytes(process.readAllStandardError()).decode(
            "utf-8",
            errors="replace",
        )
        self._append_sidebar_output(stdout_text)
        self._append_sidebar_output(stderr_text)

    def _append_file_output(self, path: str | None):
        if not path or not os.path.exists(path):
            return

        offset = self._sidebar_output_offset
        try:
            with open(path, "rb") as handle:
                handle.seek(offset)
                chunk = handle.read()
        except OSError:
            return

        if not chunk:
            return

        self._sidebar_output_offset = offset + len(chunk)
        self._append_sidebar_output(chunk.decode("utf-8", errors="replace"))

    def _poll_elevated_output(self):
        self._append_file_output(self._sidebar_output_path)

    def _on_process_finished(self, exit_code: int, exit_status):
        self._read_process_output()
        self._poll_elevated_output()

        if self.sidebar_output.toPlainText().strip():
            self._append_sidebar_output(
                f"\n\n[Process finished with exit code {exit_code}]"
            )
        else:
            self.sidebar_output.setPlainText(
                f"[no output]\n\n[Process finished with exit code {exit_code}]"
            )

        self._reset_sidebar_process()

    def _run_and_output(self, cmd, shell=False):
        self.sidebar_output.clear()
        try:
            self._reset_sidebar_process()

            process = QProcess(self)
            process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
            process.readyReadStandardOutput.connect(self._read_process_output)
            process.readyReadStandardError.connect(self._read_process_output)
            process.finished.connect(self._on_process_finished)
            self._sidebar_process = process

            if isinstance(cmd, str):
                if shell:
                    process.start("cmd.exe", ["/c", cmd])
                else:
                    process.startCommand(cmd)
            else:
                process.start(cmd[0], cmd[1:])

            if not process.waitForStarted(3000):
                output = "Could not start process."
                self._sidebar_process = None
                process.deleteLater()
                self.sidebar_output.setPlainText(output)
                return

            self.sidebar_output.setPlainText(f"Running: {process.program()}\n")
        except Exception as e:
            output = str(e)
            self.sidebar_output.setPlainText(output)

    def _run_elevated_and_output(self, command: list[str]):
        self.sidebar_output.clear()
        self._reset_sidebar_process()

        token = uuid.uuid4().hex
        base_dir = Path.home() / "AppData" / "Local" / "Temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        output_path = base_dir / f"windows_resurface_{token}.log"
        output_path.write_text("", encoding="utf-8")

        exe_path = command[0]
        args = command[1:]
        def quote_ps(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"

        cmd_parts = [exe_path, *args]
        cmd_text = subprocess.list2cmdline(cmd_parts)
        log_text = subprocess.list2cmdline([str(output_path)])
        cmd_wrapper = f'{cmd_text} > {log_text} 2>&1'
        quoted_args = ", ".join(
            quote_ps(arg) for arg in ["/c", cmd_wrapper]
        )
        args_expr = f"@({quoted_args})"
        ps_command = (
            f"$p = Start-Process -FilePath 'cmd.exe' "
            f"-ArgumentList {args_expr} -Verb RunAs "
            f"-PassThru -Wait; "
            f"exit $p.ExitCode"
        )

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_process_output)
        process.readyReadStandardError.connect(self._read_process_output)
        process.finished.connect(self._on_process_finished)
        self._sidebar_process = process
        self._sidebar_output_path = str(output_path)

        timer = QTimer(self)
        timer.timeout.connect(self._poll_elevated_output)
        timer.start(250)
        self._sidebar_output_timer = timer

        process.start(
            "powershell.exe",
            ["-NoProfile", "-Command", ps_command],
        )

        if not process.waitForStarted(3000):
            self._reset_sidebar_process()
            self.sidebar_output.setPlainText("Could not start elevated process.")
            return

        command_text = " ".join(command)
        self.sidebar_output.setPlainText(
            f"Running: {command_text}\n"
            "Waiting for administrator approval if prompted...\n\n"
        )

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
        if self._is_admin():
            self._run_and_output(["sfc", "/scannow"])
            return

        self._run_elevated_and_output(["sfc", "/scannow"])

    def run_chkdsk(self):
        system_drive = os.environ.get("SystemDrive", "C:")
        command = ["chkdsk", system_drive]

        if self._is_admin():
            self._run_and_output(command)
            return

        self._run_elevated_and_output(command)

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


import sys
import subprocess
import ctypes

import styles
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QLabel,
    QPushButton,
    QToolButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout
)
from PySide6.QtCore import Qt

from collapsible_section import CollapsibleSection
from main import get_drive_info
from PySide6.QtWidgets import QPushButton, QTextEdit
from PySide6.QtCore import QTimer
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QComboBox
from PySide6.QtWidgets import QComboBox
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QLineEdit


class AdvancedToolsPanel(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.app = app

        # --------------------------------------------------
        # Window config
        # --------------------------------------------------
        self.setWindowTitle("")
        self.setFixedWidth(505)
        self.hide()  # start hidden

        self._desired_topmost = self.app.right_always_on_top_var

        self.setWindowFlag(
            Qt.WindowType.WindowStaysOnTopHint,
            self._desired_topmost
        )

        # --------------------------------------------------
        # Root layout
        # --------------------------------------------------
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # --------------------------------------------------
        # Scrollable content
        # --------------------------------------------------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root_layout.addWidget(self.scroll)

        self.side_frame = QWidget()
        self.scroll.setWidget(self.side_frame)

        self.side_layout = QVBoxLayout(self.side_frame)
        self.side_layout.setContentsMargins(10, 5, 10, 5)
        self.side_layout.setSpacing(6)

        # --------------------------------------------------
        # Title
        # --------------------------------------------------
        self.advanced_title = QLabel("Advanced Tools")
        self.advanced_title.setStyleSheet(styles.label_style(font_size=20))
        self.advanced_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.side_layout.addWidget(self.advanced_title)

        # --------------------------------------------------
        # Title row
        # --------------------------------------------------
        title_row = QWidget()
        title_row_layout = QHBoxLayout(title_row)
        title_row_layout.setContentsMargins(0, 0, 0, 0)

        title_row_layout.addStretch()

        self.master_collapse_btn_right = QToolButton()
        self.master_collapse_btn_right.setFixedSize(
            styles.ICON_BUTTON_WIDTH,
            styles.ICON_BUTTON_HEIGHT
        )
        self.master_collapse_btn_right.setArrowType(Qt.ArrowType.DownArrow)
        self.master_collapse_btn_right.setStyleSheet(
            styles.arrow_button_style(styles.TEXT_LIGHT, styles.SURFACE_DARK)
        )
        self.master_collapse_btn_right.clicked.connect(
            self.toggle_all_right_sections
        )

        self.app.register_tooltip(
            self.master_collapse_btn_right,
            "Master collapse toggle for all of these regions."
        )

        title_row_layout.addWidget(self.master_collapse_btn_right)
        self.side_layout.addWidget(title_row)

        # ==================================================
        # Windows Utilities
        # ==================================================
        self.windows_utility_section = CollapsibleSection(
            title="Windows Utilities",
            section_id="windows_utilities",
            app=self.app,
            initial_open=self.app.saved_state
                .get("right_section_states", {})
                .get("windows_utilities", False)
        )

        self.side_layout.addWidget(self.windows_utility_section)

        self.app.register_tooltip(
            self.windows_utility_section.toggle_btn,
            "Shows windows utilities here instead grouped by type\n"
            "not having to have them all cluttering up your taskbar."
        )

        self.app.collapsible_sections.append(self.windows_utility_section)

        parent = self.windows_utility_section.content

        # ==================================================
        # Side Bar Utilities
        # ==================================================
        self.sidebar_utils_section = CollapsibleSection(
            title="Side Bar Utilities",
            section_id="sidebar_utils_section",
            app=self.app,
            initial_open=self.app.saved_state
                .get("right_section_states", {})
                .get("sidebar_utils_section", False)
        )

        self.app.collapsible_sections.append(self.sidebar_utils_section)
        self.side_layout.addWidget(self.sidebar_utils_section)

        self.build_sidebar_utilities()

        self.app.register_tooltip(
            self.sidebar_utils_section.toggle_btn,
            "Side bar actions menus."
        )

        self.sidebar_output = QTextEdit()
        self.sidebar_output.setFixedHeight(120)
        self.sidebar_output.setStyleSheet(styles.text_edit_style("Consolas", 15))

        self.sidebar_utils_section.content_layout.addWidget(self.sidebar_output)

        # --------------------------------------------------
        # Two-column dropdown container
        # --------------------------------------------------
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 4, 4, 8)

        parent.layout().addWidget(row)

        left_col = QWidget()
        left_col_layout = QVBoxLayout(left_col)
        left_col_layout.setSpacing(6)

        right_col = QWidget()
        right_col_layout = QVBoxLayout(right_col)
        right_col_layout.setSpacing(6)

        row_layout.addWidget(left_col)
        row_layout.addWidget(right_col)

        self._add_windows_dropdown(left_col_layout, "System", self._system_utilities())
        self._add_windows_dropdown(left_col_layout, "Hardware", self._hardware_utilities())

        self._add_windows_dropdown(right_col_layout, "Network", self._network_utilities())
        self._add_windows_dropdown(
            right_col_layout,
            "Startup & Power",
            self._startup_power_utilities()
        )

    
        # ==================================================
        # Drive Space Display
        # ==================================================

        
        self.display_space_section = CollapsibleSection(
            title="Drive Space Display",
            section_id="drive_space_display",
            app=self.app,
            initial_open=self.app.saved_state
                .get("right_section_states", {})
                .get("drive_space_display", False)
        )

        self.side_layout.addWidget(self.display_space_section)

        self.app.register_tooltip(
            self.display_space_section.toggle_btn,
            "Shows disk usage for all detected drives."
        )

        self.app.collapsible_sections.append(self.display_space_section)

        drive_parent = self.display_space_section.content_layout

        # --------------------------------------------------
        # Open This PC button
        # --------------------------------------------------
        btn_this_pc = QPushButton("Open This PC")
        styles.apply_default_button_size(btn_this_pc)
        btn_this_pc.setStyleSheet(styles.button_text_style(14))
        self._install_green_flash(btn_this_pc)
        btn_this_pc.clicked.connect(self.app.open_this_pc)
        self.app.register_tooltip(btn_this_pc, "Takes you to Drives location.")

        drive_parent.addWidget(btn_this_pc)

        # --------------------------------------------------
        # OUTPUT CONSOLE (read-only)
        # --------------------------------------------------
        self.drive_space_output = QTextEdit()
        self.drive_space_output.setFixedHeight(100)
        self.drive_space_output.setReadOnly(True)
        self.drive_space_output.setStyleSheet(styles.text_edit_style("Rubik", 14))

        drive_parent.addWidget(self.drive_space_output)

        # --------------------------------------------------
        # Refresh logic
        # --------------------------------------------------
        def refresh_drive_display():
            self.drive_space_output.clear()

            for d in get_drive_info():
                used_gb = (d["total"] - d["free"]) / (1024 ** 3)
                total_gb = d["total"] / (1024 ** 3)
                free_gb = d["free"] / (1024 ** 3)

                line = (
                    f"{d['drive']:<5} "
                    f"Used: {used_gb:6.1f} GB   "
                    f"Free: {free_gb:6.1f} GB   "
                    f"Total: {total_gb:6.1f} GB"
                )

                self.drive_space_output.append(line)

        # initial render
        refresh_drive_display()

        # --------------------------------------------------
        # Scheduled refresh (10s)
        # --------------------------------------------------
        self.drive_refresh_timer = QTimer(self)
        self.drive_refresh_timer.timeout.connect(refresh_drive_display)
        self.drive_refresh_timer.start(10_000)

        # ==================================================
        # Universal Bookmarks Exporter
        # ==================================================


        self.bookmarks_exporter_section = CollapsibleSection(
            title="Universal Bookmarks Exporter",
            section_id="bookmarks_exporter",
            app=self.app,
            initial_open=self.app.saved_state
                .get("right_section_states", {})
                .get("bookmarks_exporter", False)
        )

        self.side_layout.addWidget(self.bookmarks_exporter_section)
        self.app.collapsible_sections.append(self.bookmarks_exporter_section)

        # --------------------------------------------------
        # Export Brave Bookmarks button
        # --------------------------------------------------
        self.btn_brave_export = QPushButton("Export Brave Bookmarks")
        styles.apply_default_button_size(self.btn_brave_export)
        self.btn_brave_export.setStyleSheet(styles.button_text_style(15))
        self._install_green_flash(self.btn_brave_export)
        self.btn_brave_export.clicked.connect(self.app._run_brave_export)

        self.app.register_tooltip(
            self.btn_brave_export,
            "Exports brave bookmarks to a file path of your choice,\n"
            "remembers last saved location."
        )

        self.bookmarks_exporter_section.content_layout.addWidget(self.btn_brave_export)

        # --------------------------------------------------
        # Output path display (read-only)
        # --------------------------------------------------
        self.brave_export_entry = QLineEdit()
        self.brave_export_entry.setReadOnly(True)
        self.brave_export_entry.setFixedWidth(420)
        self.brave_export_entry.setStyleSheet(styles.line_edit_style(15))

        # If app.brave_export_path_var is a QString/QLineEdit source:
        # call this whenever it changes
        self.brave_export_entry.setText(
            str(self.app.brave_export_path_var)
        )

        self.bookmarks_exporter_section.content_layout.addWidget(self.brave_export_entry)

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


    def _run_elevated(self, command: str):
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",          # triggers UAC
            "cmd.exe",
            f"/k {command}",  # keep window open
            None,
            1
        )


    def _is_admin(self) -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False


    # ==================================================
    # Windows Utilities
    # ==================================================

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

        
    # ==================================================
    # Drop down helper for windows utils
    # ==================================================

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
            if not action:
                return

            # minimize BOTH windows to taskbar
            self.app.showMinimized()
            self.showMinimized()

            action()

            # reset dropdown back to placeholder
            combo.setCurrentText(placeholder)

        combo.currentTextChanged.connect(runner)

        parent_layout.addWidget(combo)
        
    # ==================================================
    # Side Bar Utilities
    # ==================================================

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

    import ctypes

    def _ensure_admin(self):
        try:
            if ctypes.windll.shell32.IsUserAnAdmin():
                return True
        except Exception:
            pass

        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            " ".join(sys.argv),
            None,
            1
        )
        return False

    def build_sidebar_utilities(self):
        parent_layout = self.sidebar_utils_section.content_layout

        self._add_sidebar_dropdown(
            parent_layout,
            "Network / System Quick Fix",
            self._sidebar_network_actions()
        )

        self._add_sidebar_dropdown(
            parent_layout,
            "Cleanup / Quick Actions",
            self._sidebar_cleanup_actions()
        )

        self._add_sidebar_dropdown(
            parent_layout,
            "Quick Open",
            self._sidebar_quick_open_actions()
        )

        # ✅ System integrity section
        self._add_sidebar_dropdown(
            parent_layout,
            "System Integrity & Disk Health",
            self._sidebar_system_integrity_actions()
        )

    def _sidebar_system_integrity_actions(self):
        return {
            "Run System File Checker (SFC)": self.run_sfc_scannow,
            "Run Check Disk (CHKDSK)": self.run_chkdsk,
        }

    def toggle_side_bar_utilities(self):
        section = self.sidebar_utils_section

        new_state = not section.is_open
        section.set_open(new_state)

        self.app.save_all_settings()
        
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

    # ====================================
    # Dropdown calls
    # ====================================

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
        if not self._ensure_admin():
            return
        self._run_and_output("sfc /scannow")


    def run_chkdsk(self):
        if not self._ensure_admin():
            return
        self._run_and_output("chkdsk")

    def _add_sidebar_dropdown(self, parent_layout, title, actions_map):
        placeholder = f" {title} "

        combo = QComboBox()
        combo.setFixedWidth(160)
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

            # reset after run
            combo.setCurrentText(placeholder)

        combo.currentTextChanged.connect(runner)

        parent_layout.addWidget(combo)


    def toggle_all_right_sections(self):
        new_state = not self.app.master_toggle_right_state
        self.app.master_toggle_right_state = new_state
        self.master_collapse_btn_right.setArrowType(
            Qt.ArrowType.DownArrow if new_state else Qt.ArrowType.UpArrow
        )

        for section in self.app.collapsible_sections:
            if not hasattr(section, "set_open"):
                continue

            # right-side only
            if section.parent() is self.side_frame:
                if section.is_open != new_state:
                    section.set_open(new_state)

        self.app.save_all_settings()

    # ==================================================
    # Visibility helpers
    # ==================================================

    def show(self):
        # sync before showing
        self.app._sync_windows("main")

        self.showNormal()

        # re-apply topmost if needed
        self.setWindowFlag(
            Qt.WindowType.WindowStaysOnTopHint,
            bool(self._desired_topmost)
        )
        self.show()  # required after changing flags

        self.raise_()
        self.activateWindow()


    def hide(self):
        self.hide()

        # mirror CTk state cleanup
        if hasattr(self.app, "expanded"):
            self.app.expanded = False
        if hasattr(self.app, "expand_btn"):
            # Qt equivalent: button text setter
            self.app.expand_btn.setText("▾")


    def _position_next_to_main(self):
        # Ensure geometry is up to date
        self.app.repaint()
        self.app.updateGeometry()

        main_pos = self.app.frameGeometry().topLeft()
        x = main_pos.x() + self.app.width() + 8
        y = main_pos.y()

        self.move(QPoint(x, y))


    def _on_close(self):
        # same logic as toggle close
        self.app.advanced_panel_open_state = False
        self.hide()
        self.app.save_all_settings()

    # --------------------------------------------------
    # Event hooks
    # --------------------------------------------------
    def closeEvent(self, event):
        self._on_close()
        event.accept()

    def resizeEvent(self, event):
        self.app._sync_windows("side")
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        self.app._set_drag_owner("side")
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.app._clear_drag_owner()
        super().mouseReleaseEvent(event)




















    
        
    
    

    

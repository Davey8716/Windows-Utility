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
from tooltips import format_tooltip_text, tooltip_text
from universal_bookmarks_export import BraveBookmarksExporter
import win32file
from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, QProcess
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QListWidget,
    QMessageBox,
    QMenu,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)


def get_usb_drive_letters() -> set[str]:
    try:
        result = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_DiskDrive | "
                    "Where-Object { $_.InterfaceType -eq 'USB' } | "
                    "ForEach-Object { "
                    "Get-CimAssociatedInstance -InputObject $_ "
                    "-Association Win32_DiskDriveToDiskPartition | "
                    "ForEach-Object { "
                    "Get-CimAssociatedInstance -InputObject $_ "
                    "-Association Win32_LogicalDiskToPartition | "
                    "ForEach-Object { $_.DeviceID } } }"
                ),
            ],
            text=True,
            errors="ignore",
            startupinfo=_hidden_startupinfo(),
        )
    except Exception:
        return set()

    drive_letters = set()
    for line in result.splitlines():
        entry = line.strip().upper()
        if len(entry) >= 2 and entry[1] == ":":
            drive_letters.add(f"{entry[:2]}\\")
    return drive_letters


def _hidden_startupinfo():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return startupinfo

def get_drive_info():
    usb_drives = get_usb_drive_letters()
    drives = []
    for letter in string.ascii_uppercase:
        path = f"{letter}:\\"
        if not os.path.exists(path):
            continue
        try:
            total, used, free = shutil.disk_usage(path)
        except Exception:
            continue
        try:
            drive_type = win32file.GetDriveType(path)
        except Exception:
            drive_type = None
        drives.append(
            {
                "drive": path,
                "total": total,
                "free": free,
                "used": used,
                "ejectable": (
                    drive_type == win32file.DRIVE_REMOVABLE
                    or path.upper() in usb_drives
                ),
            }
        )
    return drives

class AdvancedToolsPanel(QWidget):
    SIDEBAR_OUTPUT_CLEAR_BUTTON_SIZE = 18
    SIDEBAR_OUTPUT_CLEAR_BUTTON_INSET = 6
    SIDEBAR_OUTPUT_CLEAR_BUTTON_RIGHT_OFFSET = 20
    SIDEBAR_OUTPUT_CLEAR_BUTTON_UP_OFFSET = 20
    TRACKED_WINDOW_BUTTON_REFRESH_MS = 1500
    OUTER_SIDE_PADDING = 14
    WINDOWS_UTILITIES_FRAME_WIDTH = styles.RIGHT_SECTION_MAX_WIDTH
    WINDOWS_UTILITIES_SECTION_WIDTH = WINDOWS_UTILITIES_FRAME_WIDTH + 8
    WINDOWS_UTILITIES_CONTENT_WIDTH = WINDOWS_UTILITIES_FRAME_WIDTH - 8
    MAINTENANCE_CONTENT_WIDTH = styles.RIGHT_SECTION_MAX_WIDTH - 4
    MAINTENANCE_CONTROL_WIDTH = (
        MAINTENANCE_CONTENT_WIDTH - styles.PAGE_CONTROL_GAP
    ) // 2
    DRIVE_SPACE_CONTENT_WIDTH = styles.EXTERNAL_DRIVES_CONTENT_WIDTH
    DRIVE_SPACE_CONTROL_WIDTH = styles.EXTERNAL_DRIVES_CONTROL_WIDTH
    SIDEBAR_OUTPUT_CLEAR_MESSAGES = {
        "IP Configuration": "IP configuration output log cleared.",
        "Flush DNS": "Dns output log cleared.",
        "Renew DHCP Lease": "Dhcp lease output log cleared.",
        "Restart Explorer": "Explorer output log cleared.",
        "Restart Bluetooth Service": "Bluetooth service output log cleared.",
        "Clear Temp Files": "Temp files output log cleared.",
        "Clear Clipboard": "Clipboard output log cleared.",
        "Open Prefetch Folder": "Prefetch folder output log cleared.",
        "Open Temp Folder": "Temp folder output log cleared.",
        "Display Settings": "Display settings output log cleared.",
        "Clipboard History": "Clipboard history output log cleared.",
        "Open Downloads Folder": "Downloads folder output log cleared.",
        "Open Startup Folder": "Startup folder output log cleared.",
        "Sound Devices": "Sound devices output log cleared.",
        "Run DISM Repair": "Dism repair output log cleared.",
        "Run System File Checker (SFC)": "System file checker output log cleared.",
        "Run Check Disk (CHKDSK)": "Check disk output log cleared.",
    }
    WINDOWS_DROPDOWN_TOOLTIP_KEYS = {
        "System": "windows_dropdown_system",
        "Monitoring & Security": "windows_dropdown_monitoring_security",
        "Devices & Storage": "windows_dropdown_devices_storage",
        "Services & Logs": "windows_dropdown_services_logs",
        "Network": "windows_dropdown_network",
        "Startup & Power": "windows_dropdown_startup_power",
    }
    SIDEBAR_DROPDOWN_TOOLTIP_KEYS = {
        "Network / Sys Quick Fix": "sidebar_dropdown_network_fix",
        "Cleanup / Quick Actions": "sidebar_dropdown_cleanup",
        "Display And Sound": "sidebar_dropdown_quick_open",
        "Sys Integrity / Disk": "sidebar_dropdown_integrity",
    }
    SIDE_FRAME_WIDTH = styles.RIGHT_SECTION_MAX_WIDTH + (OUTER_SIDE_PADDING * 2)

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._sidebar_process = None
        self._sidebar_finished_handler = None
        self._sidebar_output_timer = None
        self._sidebar_output_path = None
        self._sidebar_output_offset = 0
        self._tracked_window_buttons: dict[str, dict[str, object]] = {}
        self._tracked_window_button_refresh_timer = QTimer(self)
        self._tracked_window_button_refresh_timer.timeout.connect(
            self._refresh_tracked_window_button_labels
        )

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setViewportMargins(0, 0, 0, 0)
        root_layout.addWidget(self.scroll)

        self.side_frame = QWidget()
        self.side_frame.setFixedWidth(self.SIDE_FRAME_WIDTH)
        self.side_frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.scroll.setWidget(self.side_frame)

        self.side_layout = QVBoxLayout(self.side_frame)
        self.side_layout.setContentsMargins(self.OUTER_SIDE_PADDING, 0, self.OUTER_SIDE_PADDING, 5)
        self.side_layout.setSpacing(2)
        self.side_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title_row = QWidget()
        title_row.setMaximumWidth(styles.RIGHT_SECTION_MAX_WIDTH)
        title_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        title_row_layout = QHBoxLayout(title_row)
        title_row_layout.setContentsMargins(
            0,
            10,
            0,
            10,
        )

        self.advanced_title = QLabel("Advanced Tools", title_row)
        self.advanced_title.setStyleSheet(styles.label_style(font_size=20))
        self.advanced_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.master_collapse_btn_right = QToolButton()
        self.master_collapse_btn_right.setProperty("rightMasterToggleButton", True)
        self.app.master_toggle_right_state = bool(
            self.app.saved_state.get("master_toggle_right", False)
        )
        self.master_collapse_btn_right.setArrowType(Qt.ArrowType.NoArrow)
        self.master_collapse_btn_right.setText(
            styles.arrow_glyph(
                Qt.ArrowType.DownArrow
                if self.app.master_toggle_right_state
                else Qt.ArrowType.UpArrow
            )
        )
        self.master_collapse_btn_right.setStyleSheet(
            styles.right_master_toggle_style(
                styles.theme_text_color(),
                styles.SURFACE_DARK,
            )
        )
        right_master_slot_width, right_master_slot_height = (
            styles.right_master_toggle_slot_size()
        )
        self.master_collapse_btn_right.setFixedSize(
            right_master_slot_width,
            right_master_slot_height,
        )
        self.master_collapse_btn_right.clicked.connect(
            self.toggle_all_right_sections
        )
        self.app.register_tooltip(
            self.master_collapse_btn_right,
            tooltip_text("master_collapse_right"),
        )
        title_spacer = QWidget(title_row)
        title_spacer.setFixedSize(
            right_master_slot_width,
            right_master_slot_height,
        )
        title_row_layout.addWidget(title_spacer)
        title_row_layout.addStretch()
        title_row_layout.addWidget(self.advanced_title)
        title_row_layout.addStretch()
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
            tooltip_text("windows_utilities_toggle"),
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
        self.sidebar_utils_section.content_layout.setSpacing(16)
        self.app.register_tooltip(
            self.sidebar_utils_section.toggle_btn,
            tooltip_text("maintenance_quick_actions_toggle"),
        )

        self.sidebar_output_container = QWidget()
        self.sidebar_output_container.setFixedSize(
            self.MAINTENANCE_CONTENT_WIDTH,
            285,
        )
        self.sidebar_output_container.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        sidebar_output_layout = QGridLayout(self.sidebar_output_container)
        sidebar_output_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_output_layout.setSpacing(0)

        self.sidebar_output = QTextEdit()
        self.sidebar_output.setFixedWidth(self.MAINTENANCE_CONTENT_WIDTH)
        self.sidebar_output.setReadOnly(True)
        self.sidebar_output.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.sidebar_output.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.sidebar_output.setProperty("surfaceFieldStyle", True)
        self.sidebar_output.setViewportMargins(
            0,
            self.SIDEBAR_OUTPUT_CLEAR_BUTTON_SIZE
            + (self.SIDEBAR_OUTPUT_CLEAR_BUTTON_INSET * 2),
            self.SIDEBAR_OUTPUT_CLEAR_BUTTON_SIZE
            + (self.SIDEBAR_OUTPUT_CLEAR_BUTTON_INSET * 2),
            0,
        )
        self.sidebar_output.document().setDocumentMargin(6)
        sidebar_output_layout.addWidget(self.sidebar_output, 0, 0)
        self._sidebar_output_last_action_label = None

        self.sidebar_output_clear_btn = QToolButton(self.sidebar_output.viewport())
        self.sidebar_output_clear_btn.setText("")
        self.sidebar_output_clear_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self.sidebar_output_clear_btn.setFixedSize(
            QSize(
                self.SIDEBAR_OUTPUT_CLEAR_BUTTON_SIZE,
                self.SIDEBAR_OUTPUT_CLEAR_BUTTON_SIZE,
            )
        )
        self.sidebar_output_clear_btn.setIconSize(
            QSize(
                self.SIDEBAR_OUTPUT_CLEAR_BUTTON_SIZE,
                self.SIDEBAR_OUTPUT_CLEAR_BUTTON_SIZE,
            )
        )
        self.sidebar_output_clear_btn.setProperty("sidebarOutputClearButton", True)
        self.sidebar_output_clear_btn.clicked.connect(self._clear_sidebar_output)
        self.sidebar_output.viewport().installEventFilter(self)
        self.sidebar_output_clear_btn.raise_()
        self._position_sidebar_output_clear_button()
        self._apply_sidebar_output_theme()
        self.sidebar_utils_section.content_layout.addWidget(
            self.sidebar_output_container,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

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
            tooltip_text("drive_space_display_toggle"),
        )
        self._build_drive_space_display()

    def _build_windows_utilities(self):
        parent_layout = self.windows_utility_section.content_layout

        row = QWidget()
        row.setProperty("centeredControlGrid", True)
        row.setFixedWidth(
            (styles.PAGE_CONTROL_WIDTH * 2) + styles.PAGE_CONTROL_GAP
        )
        row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(styles.PAGE_CONTROL_GAP)
        parent_layout.addWidget(row, 0, Qt.AlignmentFlag.AlignHCenter)

        left_drop_col = QWidget()
        left_drop_col.setFixedWidth(styles.PAGE_CONTROL_WIDTH)
        left_drop_col.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        left_drop_layout = QVBoxLayout(left_drop_col)
        left_drop_layout.setContentsMargins(0, 0, 0, 0)
        left_drop_layout.setSpacing(10)

        right_drop_col = QWidget()
        right_drop_col.setFixedWidth(styles.PAGE_CONTROL_WIDTH)
        right_drop_col.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        right_drop_layout = QVBoxLayout(right_drop_col)
        right_drop_layout.setContentsMargins(0, 0, 0, 0)
        right_drop_layout.setSpacing(10)

        row_layout.addWidget(left_drop_col)
        row_layout.addWidget(right_drop_col)
        row_layout.setAlignment(left_drop_col, Qt.AlignmentFlag.AlignTop)
        row_layout.setAlignment(right_drop_col, Qt.AlignmentFlag.AlignTop)

        self._add_windows_dropdown(
            left_drop_layout, "System", self._system_utilities()
        )
        self._add_windows_dropdown(
            left_drop_layout, "Devices & Storage", self._devices_storage_utilities()
        )
        self._add_windows_dropdown(
            left_drop_layout, "Services & Logs", self._services_logs_utilities()
        )
        self._add_windows_dropdown(
            right_drop_layout,
            "Monitoring & Security",
            self._monitoring_security_utilities(),
        )
        self._add_windows_dropdown(
            right_drop_layout, "Network", self._network_utilities()
        )
        self._add_windows_dropdown(
            right_drop_layout, "Startup & Power", self._startup_power_utilities()
        )
        left_width = max(
            widget.width()
            for widget in left_drop_col.findChildren(QComboBox)
        )
        right_width = max(
            widget.width()
            for widget in right_drop_col.findChildren(QComboBox)
        )
        left_drop_col.setFixedWidth(left_width)
        right_drop_col.setFixedWidth(right_width)
        row.setFixedWidth(left_width + styles.PAGE_CONTROL_GAP + right_width)

    def _apply_sidebar_output_theme(self):
        self.sidebar_output.setStyleSheet(
            styles.surfaced_text_edit_style("Consolas", 15)
            + """
            QTextEdit {
                padding: 6px;
            }
            """
        )
        self._update_sidebar_output_clear_button_icon()
        self.sidebar_output_clear_btn.setStyleSheet(
            styles.sidebar_output_clear_button_style()
        )
        self._position_sidebar_output_clear_button()

    def _update_sidebar_output_clear_button_icon(self):
        icon_size = self.SIDEBAR_OUTPUT_CLEAR_BUTTON_SIZE
        pixmap = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(styles.theme_text_color())
        pen.setWidth(2)
        painter.setPen(pen)

        margin = 5
        painter.drawLine(margin, margin, icon_size - margin, icon_size - margin)
        painter.drawLine(margin, icon_size - margin, icon_size - margin, margin)
        painter.end()

        self.sidebar_output_clear_btn.setIcon(QIcon(pixmap))

    def _position_sidebar_output_clear_button(self):
        viewport = self.sidebar_output.viewport()
        inset = self.SIDEBAR_OUTPUT_CLEAR_BUTTON_INSET
        x_pos = (
            viewport.width()
            - self.sidebar_output_clear_btn.width()
            - inset
            + self.SIDEBAR_OUTPUT_CLEAR_BUTTON_RIGHT_OFFSET
        )
        y_pos = inset - self.SIDEBAR_OUTPUT_CLEAR_BUTTON_UP_OFFSET
        max_x = max(0, viewport.width() - self.sidebar_output_clear_btn.width())
        self.sidebar_output_clear_btn.move(max(0, min(max_x, x_pos)), max(0, y_pos))

    def _set_sidebar_output_context(self, action_label: str):
        if action_label in self.SIDEBAR_OUTPUT_CLEAR_MESSAGES:
            self._sidebar_output_last_action_label = action_label

    def _clear_sidebar_output(self):
        self.sidebar_output.clear()
        message = self.SIDEBAR_OUTPUT_CLEAR_MESSAGES.get(
            self._sidebar_output_last_action_label,
            "Output log cleared.",
        )
        self.sidebar_output.setPlainText(message)

    def eventFilter(self, obj, event):
        if obj is self.sidebar_output.viewport() and event.type() == QEvent.Type.Resize:
            self._position_sidebar_output_clear_button()
        return super().eventFilter(obj, event)

    def _build_drive_space_display(self):
        drive_parent = self.display_space_section.content_layout

        button_row = QWidget()
        button_row.setProperty("centeredControlGrid", True)
        button_row.setFixedWidth(self.DRIVE_SPACE_CONTENT_WIDTH)
        button_row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button_row_layout = QHBoxLayout(button_row)
        button_row_layout.setContentsMargins(0, 0, 0, 0)
        button_row_layout.setSpacing(styles.PAGE_CONTROL_GAP)

        this_pc_titles = ("This PC",)
        btn_this_pc = QPushButton("Open This PC")
        self.btn_this_pc = btn_this_pc
        styles.apply_page_control_size(
            btn_this_pc,
            width=self.DRIVE_SPACE_CONTROL_WIDTH,
        )
        btn_this_pc.setProperty("styleFontSize", 14)
        btn_this_pc.setStyleSheet(styles.button_text_style(14))
        self._install_green_flash(btn_this_pc)
        self._register_tracked_window_button(
            "this_pc",
            btn_this_pc,
            labels={
                "closed": "Open This PC",
                "open": "Close This PC",
                "minimized": "Focus This PC",
            },
            title_candidates=this_pc_titles,
            open_action=lambda: self.app.actions.open_or_focus_window_titles(
                this_pc_titles,
                lambda: self._shell_execute("explorer.exe", "shell:MyComputerFolder"),
            ),
        )
        self.app.register_tooltip(
            btn_this_pc,
            tooltip_text("open_this_pc"),
        )
        button_row_layout.addWidget(btn_this_pc)

        storage_sense_titles = ("Settings",)
        btn_storage_sense = QPushButton("Open Storage Sense")
        self.btn_storage_sense = btn_storage_sense
        styles.apply_page_control_size(
            btn_storage_sense,
            width=self.DRIVE_SPACE_CONTROL_WIDTH,
        )
        btn_storage_sense.setProperty("styleFontSize", 14)
        btn_storage_sense.setStyleSheet(styles.button_text_style(14))
        self._install_green_flash(btn_storage_sense)
        self._register_tracked_window_button(
            "storage_sense",
            btn_storage_sense,
            labels={
                "closed": "Open Storage Sense",
                "open": "Close Storage Sense",
                "minimized": "Focus Storage Sense",
            },
            title_candidates=storage_sense_titles,
            open_action=lambda: self.app.actions.open_or_focus_window_titles(
                storage_sense_titles,
                lambda: self._shell_open("ms-settings:storagepolicies"),
            ),
        )
        self.app.register_tooltip(
            btn_storage_sense,
            tooltip_text("open_storage_sense"),
        )
        button_row_layout.addWidget(btn_storage_sense)
        self._refresh_tracked_window_button_labels()
        if not self._tracked_window_button_refresh_timer.isActive():
            self._tracked_window_button_refresh_timer.start(
                self.TRACKED_WINDOW_BUTTON_REFRESH_MS
            )

        drive_parent.addWidget(button_row, 0, Qt.AlignmentFlag.AlignHCenter)

        self.drive_space_list = QListWidget()
        self.drive_space_list.setFixedSize(self.DRIVE_SPACE_CONTENT_WIDTH, 120)
        self.drive_space_list.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.drive_space_list.setSpacing(0)
        self.drive_space_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.drive_space_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.drive_space_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.drive_space_list.setWordWrap(False)
        self.drive_space_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.drive_space_list.setProperty("surfaceFieldStyle", True)
        self._apply_drive_space_list_style()
        self.drive_space_list.itemDoubleClicked.connect(self._open_drive_from_item)
        self.drive_space_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.drive_space_list.customContextMenuRequested.connect(
            self._show_drive_context_menu
        )
        drive_parent.addWidget(
            self.drive_space_list,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        self._refresh_drive_space_display()
        self.drive_refresh_timer = QTimer(self)
        self.drive_refresh_timer.timeout.connect(self._refresh_drive_space_display)
        self.drive_refresh_timer.start(10_000)

    def _apply_drive_space_list_style(self):
        self.drive_space_list.setStyleSheet(
            styles.surfaced_list_widget_style("Consolas", 15)
            + """
            QListWidget {
                padding: 6px;
            }
            QListWidget::item {
                padding: 0px;
                margin: 0px;
            }
            """
        )

    def _open_drive_from_item(self, item: QListWidgetItem):
        drive_path = item.data(Qt.ItemDataRole.UserRole)
        if not drive_path:
            return
        self._minimize_and_run(lambda: os.startfile(drive_path))

    def _show_drive_context_menu(self, pos: QPoint):
        item = self.drive_space_list.itemAt(pos)
        if not item:
            return

        if not item.data(Qt.ItemDataRole.UserRole + 1):
            return

        drive_path = item.data(Qt.ItemDataRole.UserRole)
        if not drive_path:
            return

        menu = QMenu(self.drive_space_list)
        styles.apply_popup_menu_style(menu)
        remove_action = menu.addAction(f"Safely Remove {drive_path}")
        selected_action = menu.exec(self.drive_space_list.mapToGlobal(pos))
        if selected_action is remove_action:
            self._safely_remove_drive(drive_path)

    def _safely_remove_drive(self, drive_path: str):
        drive_name = drive_path[:2]
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "(New-Object -ComObject Shell.Application)"
                        f".Namespace(17).ParseName('{drive_name}').InvokeVerb('Eject')"
                    ),
                ],
                check=True,
                startupinfo=_hidden_startupinfo(),
            )
        except Exception as exc:
            self.app._show_timed_message(
                QMessageBox.Icon.Warning,
                "Drive Removal",
                f"Could not safely remove {drive_name}.\n{exc}",
            )
            return

        self.app._show_timed_message(
            QMessageBox.Icon.Information,
            "Drive Removal",
            f"Requested safe removal for {drive_name}.",
        )
        QTimer.singleShot(1500, self.drive_space_list.clear)
        QTimer.singleShot(1600, self._refresh_drive_space_display)

    def _refresh_drive_space_display(self):
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
            item.setData(Qt.ItemDataRole.UserRole, d["drive"])
            item.setData(Qt.ItemDataRole.UserRole + 1, d["ejectable"])
            tooltip = f"Open {d['drive']} in File Explorer"
            if d["ejectable"]:
                tooltip += "\nRight-click to safely remove this drive."
            item.setToolTip(format_tooltip_text(tooltip))
            item.setSizeHint(QSize(0, 20))
            self.drive_space_list.addItem(item)

    def _register_tracked_window_button(
        self,
        key: str,
        button: QPushButton,
        *,
        labels: dict[str, str],
        title_candidates: list[str] | tuple[str, ...],
        open_action,
    ) -> None:
        self._tracked_window_buttons[key] = {
            "button": button,
            "labels": dict(labels),
            "title_candidates": tuple(title_candidates),
            "open_action": open_action,
        }
        button.clicked.connect(
            lambda _checked=False, action_key=key: self._handle_tracked_window_button(
                action_key
            )
        )

    def _tracked_window_button_label(
        self,
        labels: dict[str, str],
        state: str,
    ) -> str:
        return labels.get(state, labels["closed"])

    def _refresh_tracked_window_button_labels(self):
        for key in self._tracked_window_buttons:
            self._refresh_tracked_window_button_label(key)

    def _refresh_tracked_window_button_label(self, key: str):
        spec = self._tracked_window_buttons.get(key)
        if not spec:
            return

        button = spec["button"]
        labels = spec["labels"]
        title_candidates = spec["title_candidates"]
        state = self.app.actions.get_window_titles_state(title_candidates)
        button_text = self._tracked_window_button_label(labels, state)
        if button.text() != button_text:
            button.setText(button_text)

    def _handle_tracked_window_button(self, key: str):
        spec = self._tracked_window_buttons.get(key)
        if not spec:
            return

        title_candidates = spec["title_candidates"]
        state = self.app.actions.get_window_titles_state(title_candidates)

        if state == "open":
            self.app.actions.close_window_titles(title_candidates)
        elif state == "minimized":
            self._minimize_and_run(
                lambda: self.app.actions.maximize_window_titles(title_candidates)
            )
        else:
            self._minimize_and_run(spec["open_action"])

        self._refresh_tracked_window_button_label(key)
        QTimer.singleShot(350, self._refresh_tracked_window_button_labels)

    def _add_action_button(self, parent_layout, label, action):
        button = QPushButton(label)
        styles.apply_default_button_size(button)
        button.setProperty("styleFontSize", 14)
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
            "Control Panel": self.open_control_panel,
            "Credential Manager": self.open_credential_manager,
            "Local Users and Groups": self.open_local_users_and_groups,
            "System Restore": self.open_system_restore,
            "System Settings": self.open_system_settings,
            "System Information": self.open_system_information,
        }

    def _monitoring_security_utilities(self):
        return {
            "Hosts File Editor": self.open_hosts_file_editor,
            "Reliability Monitor": self.open_reliability_monitor,
            "Resource Monitor": self.open_resource_monitor,
            "Task Manager": self.open_task_manager,
            "Windows Memory Diagnostic": self.open_windows_memory_diagnostic,
            "Windows Defender / Virus & Threat Protection": self.open_windows_security,
            "Windows Update Troubleshooter": self.open_windows_update_troubleshooter,
        }

    def _devices_storage_utilities(self):
        return {
            "Device Manager": self.open_device_manager,
            "Disk Cleanup": self.open_disk_cleanup,
            "Disk Management": self.open_disk_management,
        }

    def _services_logs_utilities(self):
        return {
            "Services": self.open_services,
            "Event Viewer": self.open_event_viewer,
        }

    def open_device_manager(self):
        self.app.actions.open_or_focus_window_titles(
            ["Device Manager"],
            lambda: self._shell_open("devmgmt.msc"),
        )

    def open_disk_management(self):
        self.app.actions.open_or_focus_window_titles(
            ["Disk Management"],
            lambda: self._shell_open("diskmgmt.msc"),
        )

    def open_services(self):
        self.app.actions.open_or_focus_window_titles(
            ["Services"],
            lambda: self._shell_open("services.msc"),
        )

    def open_event_viewer(self):
        self.app.actions.open_or_focus_window_titles(
            ["Event Viewer"],
            lambda: self._shell_open("eventvwr.msc"),
        )

    def open_advanced_display_settings(self):
        self.app.actions.open_or_focus_window_titles(
            ["Advanced display"],
            lambda: self._shell_open("ms-settings:display-advanced"),
        )

    def open_disk_cleanup(self):
        self.app.actions.open_or_focus_window_titles(
            ["Disk Cleanup"],
            lambda: subprocess.Popen(["cleanmgr"]),
        )

    def open_system_settings(self):
        self.app.actions.open_or_focus_window_titles(
            ["Settings"],
            lambda: self._shell_open("ms-settings:"),
        )

    def open_control_panel(self):
        self.app.actions.open_or_focus_explorer_title(
            "Control Panel",
            lambda: self._shell_execute("explorer.exe", "shell:ControlPanelFolder"),
        )

    def open_credential_manager(self):
        self.app.actions.open_or_focus_window_titles(
            ["Credential Manager"],
            lambda: self._shell_execute(
                "control.exe",
                "/name Microsoft.CredentialManager",
            ),
        )

    def open_system_information(self):
        self.app.actions.open_or_focus_window_titles(
            ["System Information"],
            lambda: subprocess.Popen(["msinfo32"]),
        )

    def open_system_restore(self):
        self.app.actions.open_or_focus_window_titles(
            ["System Restore", "System Restore Properties"],
            lambda: self._shell_execute("rstrui.exe"),
        )

    def open_local_users_and_groups(self):
        self.app.actions.open_or_focus_window_titles(
            ["Local Users and Groups", "lusrmgr"],
            lambda: self._shell_execute("lusrmgr.msc"),
        )

    def open_reliability_monitor(self):
        self.app.actions.open_or_focus_window_titles(
            [
                "Reliability Monitor",
                "View reliability history",
                "Performance Monitor",
            ],
            lambda: self._shell_execute("perfmon.exe", "/rel"),
        )

    def open_resource_monitor(self):
        self.app.actions.open_or_focus_window_titles(
            ["Resource Monitor"],
            lambda: subprocess.Popen(["resmon"]),
        )

    def open_task_manager(self):
        self.app.actions.open_or_focus_window_titles(
            ["Task Manager", "Windows Task Manager"],
            lambda: subprocess.Popen(["taskmgr"]),
        )

    def open_windows_security(self):
        self.app.actions.open_or_focus_window_titles(
            ["Virus & threat protection", "Windows Security", "Security at a glance"],
            lambda: self._shell_open("windowsdefender://threat"),
        )

    def open_windows_update_troubleshooter(self):
        self.app.actions.open_or_focus_window_titles(
            ["Troubleshoot", "Get Help", "Windows Update"],
            lambda: self._shell_open("ms-settings:troubleshoot"),
        )

    def open_windows_memory_diagnostic(self):
        diagnostic_path = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "mdsched.exe",
        )
        self.app.actions.open_or_focus_window_titles(
            ["Windows Memory Diagnostic", "Diagnosing your computer's memory problems"],
            lambda: self._shell_execute(diagnostic_path),
        )

    def open_hosts_file_editor(self):
        hosts_path = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "drivers",
            "etc",
            "hosts",
        )
        self.app.actions.open_or_focus_window_titles(
            ["hosts - Notepad", "Notepad"],
            lambda: self._shell_execute_elevated("notepad.exe", hosts_path),
        )

    def _shell_open(self, target: str):
        ctypes.windll.shell32.ShellExecuteW(None, "open", target, None, None, 1)

    def _shell_execute(self, target: str, parameters: str | None = None):
        ctypes.windll.shell32.ShellExecuteW(
            None, "open", target, parameters, None, 1
        )

    def _shell_execute_elevated(self, target: str, parameters: str | None = None):
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", target, parameters, None, 1
        )

    def _control_exe_path(self) -> str:
        return os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "control.exe",
        )

    def _should_minimize_after_use(self) -> bool:
        app_state = getattr(getattr(self, "app", None), "state", None)
        if isinstance(app_state, dict):
            return bool(app_state.get("minimize_after_use_enabled", True))
        return True

    def _minimize_and_run(self, action):
        if self._should_minimize_after_use():
            self.app.showMinimized()
            self.showMinimized()
        action()

    def _run_without_minimize(self, action):
        def wrapper():
            action()

        wrapper.skip_minimize_after_use = True
        return wrapper

    def _network_utilities(self):
        return {
            "Network Connections": self.open_network_connections,
            "Network Diagnostics": self.open_network_diagnostics,
            "Network Reset": self.open_network_reset,
            "Firewall": self.open_firewall,
            "IP Configuration": self._run_without_minimize(self.show_ip_config),
            "Router Login": self.app.actions.open_router_page,
        }

    def open_network_connections(self):
        self.app.actions.open_or_focus_window_titles(
            ["Network Connections"],
            lambda: self._shell_execute("control.exe", "ncpa.cpl"),
        )

    def open_firewall(self):
        self.app.actions.open_or_focus_window_titles(
            ["Windows Defender Firewall", "Firewall"],
            lambda: self._shell_open("wf.msc"),
        )

    def open_network_reset(self):
        self.app.actions.open_or_focus_window_titles(
            ["Network reset", "Network & internet"],
            lambda: self._shell_open("ms-settings:network-advancedsettings"),
        )

    def open_network_diagnostics(self):
        self.app.actions.open_or_focus_window_titles(
            ["Troubleshoot", "Get Help", "Network & internet"],
            lambda: self._shell_open("ms-settings:network-status"),
        )

    def _startup_power_utilities(self):
        return {
            "AutoPlay Settings": self.open_autoplay_settings,
            "Common Startup Folder": self.open_common_startup_folder,
            "Installed Programs": self.open_installed_programs,
            "Startup Apps": self.open_startup_apps,
            "Power Options": self.open_power_options,
        }

    def open_startup_apps(self):
        self.app.actions.open_or_focus_window_titles(
            ["Startup apps"],
            lambda: self._shell_open("ms-settings:startupapps"),
        )

    def open_autoplay_settings(self):
        self.app.actions.open_or_focus_window_titles(
            ["AutoPlay"],
            lambda: self._shell_execute(
                "control.exe",
                "/name Microsoft.AutoPlay",
            ),
        )

    def open_common_startup_folder(self):
        common_startup_path = os.path.join(
            os.environ.get("ProgramData", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup",
        )
        self.app.actions.open_or_focus_folder_path(common_startup_path)

    def open_installed_programs(self):
        self.app.actions.open_or_focus_window_titles(
            ["Programs and Features", "Installed Programs"],
            lambda: self._shell_execute("control.exe", "appwiz.cpl"),
        )

    def open_power_options(self):
        self.app.actions.open_or_focus_window_titles(
            ["Power Options"],
            lambda: self._shell_execute("control.exe", "/name Microsoft.PowerOptions"),
        )

    def _add_windows_dropdown(self, parent_layout, label, actions_map):
        placeholder = f" {label} "
        combo = QComboBox()
        combo.addItem(placeholder)
        combo.addItems(sorted(actions_map.keys()))
        combo.setCurrentText(placeholder)
        combo.view().setRowHidden(0, True)
        combo.setProperty("styleFontSize", 15)
        combo.setStyleSheet(styles.organizing_combo_style(15))
        styles.fit_page_combo_width(
            combo,
            placeholder=placeholder,
            font_size=15,
        )
        tooltip_key = self.WINDOWS_DROPDOWN_TOOLTIP_KEYS.get(label)
        if tooltip_key:
            self.app.register_tooltip(combo, tooltip_text(tooltip_key))

        def runner(text: str):
            if text == placeholder:
                return
            action = actions_map.get(text)
            if action:
                self._set_sidebar_output_context(text)
                if getattr(action, "skip_minimize_after_use", False):
                    action()
                else:
                    self._minimize_and_run(action)
            combo.setCurrentText(placeholder)

        combo.currentTextChanged.connect(runner)
        parent_layout.addWidget(combo)

    def _sidebar_network_actions(self):
        return {
            "Flush DNS": self.flush_dns,
            "Renew DHCP Lease": self.renew_ip,
            "Restart Explorer": self.restart_explorer,
            "Restart Bluetooth Service": self.restart_bluetooth,
        }

    def _sidebar_cleanup_actions(self):
        actions = {
            "Clear Temp Files": self.clear_temp,
            "Clear Clipboard": self.clear_clipboard,
            "Clipboard History": lambda: self._minimize_and_run(
                self.open_clipboard_history
            ),
            "Open Downloads Folder": lambda: self._minimize_and_run(self.open_downloads),
            "Open Prefetch Folder": lambda: self._minimize_and_run(
                self.open_prefetch_folder
            ),
            "Open Startup Folder": lambda: self._minimize_and_run(
                self.open_startup_folder
            ),
            "Open Temp Folder": lambda: self._minimize_and_run(
                self.open_temp_folder
            ),
        }
        return dict(sorted(actions.items(), key=lambda item: item[0].casefold()))

    def _sidebar_quick_open_actions(self):
        actions = {
            "Advanced Display Settings": lambda: self._minimize_and_run(
                self.open_advanced_display_settings
            ),
            "Display Settings": lambda: self._minimize_and_run(
                self.open_display_settings
            ),
            "Sound Devices": lambda: self._minimize_and_run(self.open_sound_settings),
        }
        return dict(sorted(actions.items(), key=lambda item: item[0].casefold()))

    def build_sidebar_utilities(self):
        parent_layout = self.sidebar_utils_section.content_layout
        dropdown_grid = QWidget()
        dropdown_grid.setProperty("centeredControlGrid", True)
        dropdown_grid.setFixedWidth(self.MAINTENANCE_CONTENT_WIDTH)
        dropdown_grid.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        grid_layout = QGridLayout(dropdown_grid)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setHorizontalSpacing(styles.PAGE_CONTROL_GAP)
        grid_layout.setVerticalSpacing(10)
        grid_layout.setColumnMinimumWidth(0, self.MAINTENANCE_CONTROL_WIDTH)
        grid_layout.setColumnMinimumWidth(1, self.MAINTENANCE_CONTROL_WIDTH)
        parent_layout.addWidget(
            dropdown_grid,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        self._add_sidebar_dropdown(
            grid_layout,
            0,
            0,
            "Cleanup / Quick Actions",
            self._sidebar_cleanup_actions(),
            fixed_width=self.MAINTENANCE_CONTROL_WIDTH,
        )
        self._add_sidebar_dropdown(
            grid_layout,
            0,
            1,
            "Network / Sys Quick Fix",
            self._sidebar_network_actions(),
            fixed_width=self.MAINTENANCE_CONTROL_WIDTH,
        )
        self._add_sidebar_dropdown(
            grid_layout,
            1,
            0,
            "Display And Sound",
            self._sidebar_quick_open_actions(),
            fixed_width=self.MAINTENANCE_CONTROL_WIDTH,
        )
        self._add_sidebar_dropdown(
            grid_layout,
            1,
            1,
            "Sys Integrity / Disk",
            self._sidebar_system_integrity_actions(),
            fixed_width=self.MAINTENANCE_CONTROL_WIDTH,
        )

    def _sidebar_system_integrity_actions(self):
        return {
            "Run DISM Repair": self.run_dism_restorehealth,
            "Run System File Checker (SFC)": self.run_sfc_scannow,
            "Run Check Disk (CHKDSK)": self.run_chkdsk,
        }

    def _is_admin(self):
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _message_box_button(self, name: str):
        getter = getattr(getattr(self, "app", None), "_message_box_button", None)
        if callable(getter):
            return getter(name)
        button_namespace = getattr(QMessageBox, "StandardButton", QMessageBox)
        return getattr(button_namespace, name, 0)

    def _message_box_icon(self, name: str):
        getter = getattr(getattr(self, "app", None), "_message_box_icon", None)
        if callable(getter):
            return getter(name)
        icon_namespace = getattr(QMessageBox, "Icon", QMessageBox)
        return getattr(icon_namespace, name, None)

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
        self._sidebar_finished_handler = None
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

        output_text = self.sidebar_output.toPlainText()
        finished_handler = self._sidebar_finished_handler
        self._reset_sidebar_process()
        if callable(finished_handler):
            finished_handler(exit_code, output_text)

    def _command_display_text(self, cmd) -> str:
        if isinstance(cmd, str):
            return cmd
        return subprocess.list2cmdline([str(part) for part in cmd])

    def _run_and_output(self, cmd, shell=False, finished_handler=None):
        self.sidebar_output.clear()
        try:
            self._reset_sidebar_process()
            command_text = self._command_display_text(cmd)
            self._sidebar_finished_handler = finished_handler

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
                self._sidebar_finished_handler = None
                process.deleteLater()
                self.sidebar_output.setPlainText(output)
                return

            self.sidebar_output.setPlainText(f"Running: {command_text}\n")
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
            f"-ArgumentList {args_expr} -Verb RunAs -WindowStyle Hidden "
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

        command_text = self._command_display_text(command)
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
        self._run_and_output(
            "taskkill /f /im explorer.exe && start explorer",
            shell=True,
        )

    def restart_bluetooth(self):
        self._run_and_output("powershell Restart-Service bthserv -Force")

    def _clear_temp_command(self) -> list[str]:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            temp_dir = os.path.join(local_app_data, "Temp")
        else:
            temp_dir = tempfile.gettempdir()
        temp_dir = temp_dir.rstrip("\\/")
        quoted_temp_dir = "'" + temp_dir.replace("'", "''") + "'"
        command = (
            f"$tempDir = {quoted_temp_dir}; "
            "if (Test-Path -LiteralPath $tempDir) { "
            "$accessDenied = 0; "
            "$inUse = 0; "
            "$other = 0; "
            "Get-ChildItem -LiteralPath $tempDir -Force -Recurse -ErrorAction SilentlyContinue | "
            "ForEach-Object { "
            "try { "
            "Remove-Item -LiteralPath $_.FullName -Force -Recurse -ErrorAction Stop "
            "} catch { "
            "$message = $_.Exception.Message; "
            "if ($message -match 'Access to the path .* is denied|Access is denied') { $accessDenied++ } "
            "elseif ($message -match 'being used by another process') { $inUse++ } "
            "else { $other++ } "
            "} "
            "}; "
            "if ($accessDenied -gt 0) { Write-Output \"Access is denied for $accessDenied item(s).\" } "
            "if ($inUse -gt 0) { Write-Output \"In-use files were skipped: $inUse item(s).\" } "
            "if ($other -gt 0) { Write-Output \"Additional cleanup errors: $other item(s).\" } "
            "}"
        )
        return ["powershell.exe", "-WindowStyle", "Hidden", "-NoProfile", "-Command", command]

    def _handle_clear_temp_finished(self, exit_code: int, output_text: str):
        if self._is_admin():
            return

        if "access is denied" not in output_text.lower():
            return

        show_modal = getattr(getattr(self, "app", None), "_show_modal_message", None)
        if not callable(show_modal):
            return

        yes_button = self._message_box_button("Yes")
        no_button = self._message_box_button("No")
        if not no_button:
            no_button = self._message_box_button("Cancel")

        result = show_modal(
            self._message_box_icon("NoIcon"),
            "Temp Cleanup Needs Admin Access",
            (
                "Some temp files could not be removed because access was denied.\n\n"
                "Run temp cleanup again as administrator?\n\n"
                "Files currently in use may still be skipped."
            ),
            yes_button | no_button,
            no_button,
        )
        if result == yes_button:
            self._run_elevated_and_output(self._clear_temp_command())

    def clear_temp(self):
        kwargs = {}
        if not self._is_admin():
            kwargs["finished_handler"] = self._handle_clear_temp_finished
        self._run_and_output(self._clear_temp_command(), **kwargs)

    def clear_clipboard(self):
        self._run_and_output("cmd /c echo off | clip")

    def open_display_settings(self):
        self.sidebar_output.clear()
        self._shell_open("ms-settings:display")
        self.sidebar_output.append("Opened Display Settings.")

    def open_downloads(self):
        self.sidebar_output.clear()
        opened = self.app.actions.open_or_focus_explorer_title(
            "Downloads",
            lambda: subprocess.Popen(["explorer", "shell:downloads"]),
        )
        if opened:
            self.sidebar_output.append("Opened Downloads folder.")
        else:
            self.sidebar_output.append("Could not open Downloads folder.")

    def open_startup_folder(self):
        self.sidebar_output.clear()
        startup_path = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup",
        )
        opened = self.app.actions.open_or_focus_folder_path(
            startup_path,
            lambda: os.startfile(startup_path),
        )
        if opened:
            self.sidebar_output.append("Opened Startup folder.")
        else:
            self.sidebar_output.append("Could not open Startup folder.")

    def open_sound_settings(self):
        self.sidebar_output.clear()
        self._shell_open("ms-settings:sound")
        self.sidebar_output.append("Opened Sound Settings.")

    def open_temp_folder(self):
        self.sidebar_output.clear()
        temp_path = tempfile.gettempdir()
        opened = self.app.actions.open_or_focus_folder_path(
            temp_path,
            lambda: os.startfile(temp_path),
        )
        if opened:
            self.sidebar_output.append("Opened Temp folder.")
        else:
            self.sidebar_output.append("Could not open Temp folder.")

    def open_prefetch_folder(self):
        self.sidebar_output.clear()
        prefetch_path = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "Prefetch",
        )
        opened = self.app.actions.open_or_focus_folder_path(
            prefetch_path,
            lambda: os.startfile(prefetch_path),
        )
        if opened:
            self.sidebar_output.append("Opened Prefetch folder.")
        else:
            self.sidebar_output.append("Could not open Prefetch folder.")

    def open_clipboard_history(self):
        self.sidebar_output.clear()
        self._shell_open("ms-settings:clipboard")
        self.sidebar_output.append("Opened Clipboard History.")

    def run_dism_restorehealth(self):
        command = [
            "DISM",
            "/Online",
            "/Cleanup-Image",
            "/RestoreHealth",
        ]

        if self._is_admin():
            self._run_and_output(command)
            return

        self._run_elevated_and_output(command)

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

    def _add_sidebar_dropdown(
        self,
        parent_layout,
        row,
        column,
        title,
        actions_map,
        *,
        fixed_width: int | None = None,
    ):
        placeholder = f" {title} "
        combo = QComboBox()
        combo.addItem(placeholder)
        combo.addItems(actions_map.keys())
        combo.setCurrentText(placeholder)
        combo.view().setRowHidden(0, True)
        combo.setProperty("styleFontSize", 14)
        combo.setStyleSheet(styles.organizing_combo_style(14))
        styles.fit_page_combo_width(
            combo,
            placeholder=placeholder,
            font_size=14,
        )
        if fixed_width is not None:
            styles.apply_page_control_size(
                combo,
                width=fixed_width,
                role="maintenance",
            )
        tooltip_key = self.SIDEBAR_DROPDOWN_TOOLTIP_KEYS.get(title)
        if tooltip_key:
            self.app.register_tooltip(combo, tooltip_text(tooltip_key))

        def runner(text: str):
            if text == placeholder:
                return
            action = actions_map.get(text)
            if action:
                self._set_sidebar_output_context(text)
                action()
            combo.setCurrentText(placeholder)

        combo.currentTextChanged.connect(runner)
        parent_layout.addWidget(combo, row, column)

    def _run_brave_export(self):
        start_dir = Path(self.app.get_default_bookmarks_export_dir())
        start_dir.mkdir(parents=True, exist_ok=True)
        exporters = [
            exporter
            for exporter in BraveBookmarksExporter.supported_exporters()
            if exporter.has_bookmarks()
        ]
        if not exporters:
            return False

        export_targets = [
            (exporter, start_dir / exporter.output_filename)
            for exporter in exporters
        ]
        prompt = "Export bookmarks to:\n" + "\n".join(
            str(out_path) for _exporter, out_path in export_targets
        )
        if any(out_path.exists() for _exporter, out_path in export_targets):
            prompt += (
                "\n\nExisting bookmark export files in this list will be overwritten."
            )

        result = self.app._show_modal_message(
            QMessageBox.Icon.NoIcon,
            "Export Bookmarks",
            prompt,
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if result != QMessageBox.StandardButton.Save:
            return None

        exported_paths = []

        def run_export():
            nonlocal exported_paths
            for exporter, out_path in export_targets:
                if exporter.export_to_file(str(out_path)):
                    exported_paths.append(str(out_path))

        minimize_runner = getattr(self.app, "_run_with_optional_minimize", None)
        if callable(minimize_runner):
            minimize_runner(run_export)
        else:
            run_export()

        if exported_paths:
            save_state(self.app.state)
            return exported_paths

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
        self.master_collapse_btn_right.setText(
            styles.arrow_glyph(
                Qt.ArrowType.DownArrow if new_state else Qt.ArrowType.UpArrow
            )
        )

        for section in self.app.collapsible_sections:
            if hasattr(section, "set_open") and section.parent() is self.side_frame:
                if section.is_open != new_state:
                    section.set_open(new_state)

        self.app.save_all_settings()

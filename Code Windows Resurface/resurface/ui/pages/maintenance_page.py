from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from resurface.features.system.command_runner import CommandRunner
from resurface.features.system.maintenance_actions import MaintenanceActions
from resurface.ui import styles
from resurface.ui.tooltips import tooltip_text


class MaintenancePage(QWidget):
    CONTENT_WIDTH = styles.RIGHT_SECTION_MAX_WIDTH - 4
    CONTROL_WIDTH = (CONTENT_WIDTH - styles.PAGE_CONTROL_GAP) // 2
    OUTPUT_CLEAR_MESSAGES = {
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
    TOOLTIP_KEYS = {
        "Network / Sys Quick Fix": "sidebar_dropdown_network_fix",
        "Cleanup / Quick Actions": "sidebar_dropdown_cleanup",
        "Display And Sound": "sidebar_dropdown_quick_open",
        "Sys Integrity / Disk": "sidebar_dropdown_integrity",
    }

    def __init__(
        self,
        actions: MaintenanceActions,
        runner: CommandRunner,
        register_tooltip: Callable,
        run_with_optional_minimize: Callable,
        show_modal_message: Callable,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.actions = actions
        self.runner = runner
        self.register_tooltip = register_tooltip
        self.run_with_optional_minimize = run_with_optional_minimize
        self.show_modal_message = show_modal_message
        self._output_last_action_label: str | None = None
        self._has_output_to_clear = False
        self.quick_action_dropdowns: list[tuple[QComboBox, str, dict[str, Callable]]] = []

        self.page_layout = QVBoxLayout(self)
        self.page_layout.setContentsMargins(0, 0, 0, 0)
        self._build_selectors()
        self.page_layout.setSpacing(16)
        self._build_output()
        runner.output_reset.connect(self._reset_output)
        runner.output_appended.connect(self._append_output)
        actions.temp_cleanup_admin_required.connect(self._confirm_temp_elevation)
        actions.admin_access_required.connect(self._confirm_integrity_elevation)
        actions.chkdsk_blocked_by_vanguard.connect(self._show_vanguard_chkdsk_warning)
        actions.chkdsk_access_denied.connect(self._show_generic_chkdsk_warning)

    def _build_selectors(self):
        grid = QWidget()
        grid.setProperty("centeredControlGrid", True)
        grid.setFixedWidth(self.CONTENT_WIDTH)
        grid.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QGridLayout(grid)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(styles.PAGE_CONTROL_GAP)
        layout.setVerticalSpacing(10)
        layout.setColumnMinimumWidth(0, self.CONTROL_WIDTH)
        layout.setColumnMinimumWidth(1, self.CONTROL_WIDTH)
        self.page_layout.addWidget(grid, 0, Qt.AlignmentFlag.AlignHCenter)

        cleanup = {
            "Clear Temp Files": self.actions.clear_temp,
            "Clear Clipboard": self.actions.clear_clipboard,
            "Clipboard History": lambda: self.run_with_optional_minimize(self.actions.open_clipboard_history),
            "Open Downloads Folder": lambda: self.run_with_optional_minimize(self.actions.open_downloads),
            "Open Prefetch Folder": lambda: self.run_with_optional_minimize(self.actions.open_prefetch_folder),
            "Open Startup Folder": lambda: self.run_with_optional_minimize(self.actions.open_startup_folder),
            "Open Temp Folder": lambda: self.run_with_optional_minimize(self.actions.open_temp_folder),
        }
        quick_open = {
            "Advanced Display Settings": lambda: self.run_with_optional_minimize(self.actions.open_advanced_display_settings),
            "Display Settings": lambda: self.run_with_optional_minimize(self.actions.open_display_settings),
            "Sound Devices": lambda: self.run_with_optional_minimize(self.actions.open_sound_settings),
        }
        self._add_dropdown(layout, 0, 0, "Cleanup / Quick Actions", dict(sorted(cleanup.items(), key=lambda item: item[0].casefold())))
        self._add_dropdown(
            layout,
            0,
            1,
            "Network / Sys Quick Fix",
            {
                "Flush DNS": self.actions.flush_dns,
                "Renew DHCP Lease": self.actions.renew_ip,
                "Restart Explorer": self.actions.restart_explorer,
                "Restart Bluetooth Service": self.actions.restart_bluetooth,
            },
        )
        self._add_dropdown(layout, 1, 0, "Display And Sound", dict(sorted(quick_open.items(), key=lambda item: item[0].casefold())))
        self._add_dropdown(
            layout,
            1,
            1,
            "Sys Integrity / Disk",
            {
                "Run DISM Repair": self.actions.run_dism_restorehealth,
                "Run System File Checker (SFC)": self.actions.run_sfc_scannow,
                "Run Check Disk (CHKDSK)": self.actions.run_chkdsk,
            },
        )

    def _build_output(self):
        self.sidebar_output_container = QWidget()
        self.sidebar_output_container.setFixedSize(self.CONTENT_WIDTH, 285)
        self.sidebar_output_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        output_layout = QGridLayout(self.sidebar_output_container)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(0)
        self.sidebar_output = QTextEdit()
        self.sidebar_output.setFixedWidth(self.CONTENT_WIDTH)
        self.sidebar_output.setReadOnly(True)
        self.sidebar_output.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_output.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.sidebar_output.setProperty("surfaceFieldStyle", True)
        self.sidebar_output.document().setDocumentMargin(6)
        output_layout.addWidget(self.sidebar_output, 0, 0)
        self.apply_theme()
        self.page_layout.addWidget(self.sidebar_output_container, 0, Qt.AlignmentFlag.AlignHCenter)

        clear_row = QWidget()
        clear_row.setFixedWidth(self.CONTENT_WIDTH)
        clear_row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        clear_layout = QHBoxLayout(clear_row)
        clear_layout.setContentsMargins(0, 0, 0, 0)
        clear_layout.setSpacing(0)
        self.sidebar_output_clear_btn = QPushButton("Clear Log")
        styles.apply_default_button_size(self.sidebar_output_clear_btn)
        self.sidebar_output_clear_btn.setProperty("styleFontSize", 14)
        self.sidebar_output_clear_btn.setProperty("lightModeBlackDisabledText", True)
        self.sidebar_output_clear_btn.setStyleSheet(styles.button_text_style(14))
        self.sidebar_output_clear_btn.setEnabled(False)
        self.register_tooltip(
            self.sidebar_output_clear_btn,
            tooltip_text("maintenance_clear_log"),
        )
        self.sidebar_output_clear_btn.clicked.connect(self.clear_output)
        clear_layout.addWidget(self.sidebar_output_clear_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.page_layout.addWidget(clear_row, 0, Qt.AlignmentFlag.AlignHCenter)

    def _add_dropdown(self, layout, row, column, title, action_map):
        placeholder = f" {title} "
        combo = QComboBox()
        combo.addItem(placeholder)
        combo.addItems(action_map.keys())
        combo.setCurrentText(placeholder)
        combo.view().setRowHidden(0, True)
        combo.setProperty("styleFontSize", 14)
        combo.setStyleSheet(styles.organizing_combo_style(14))
        styles.fit_page_combo_width(combo, placeholder=placeholder, font_size=14)
        styles.apply_page_control_size(combo, width=self.CONTROL_WIDTH, role="maintenance")
        self.register_tooltip(combo, tooltip_text(self.TOOLTIP_KEYS[title]))

        def selected(text: str):
            if text == placeholder:
                return
            action = action_map.get(text)
            if action is not None:
                self.set_output_context(text)
                action()
            combo.setCurrentText(placeholder)

        combo.currentTextChanged.connect(selected)
        layout.addWidget(combo, row, column)
        self.quick_action_dropdowns.append((combo, title, action_map))

    def set_output_context(self, action_label: str):
        if action_label in self.OUTPUT_CLEAR_MESSAGES:
            self._output_last_action_label = action_label

    def clear_output(self):
        if not self._has_output_to_clear:
            return
        self.sidebar_output.setPlainText(
            self.OUTPUT_CLEAR_MESSAGES.get(self._output_last_action_label, "Output log cleared.")
        )
        self._set_output_clearable(False)

    def _reset_output(self):
        self.sidebar_output.clear()
        self._set_output_clearable(False)

    def _append_output(self, text: str):
        if not text:
            return
        cursor = self.sidebar_output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self.sidebar_output.setTextCursor(cursor)
        self.sidebar_output.ensureCursorVisible()
        self._set_output_clearable(True)

    def _set_output_clearable(self, clearable: bool):
        self._has_output_to_clear = bool(clearable)
        self.sidebar_output_clear_btn.setEnabled(self._has_output_to_clear)

    def apply_theme(self):
        self.sidebar_output.setStyleSheet(
            styles.frame_text_edit_style(font_size=styles.FONT_SIZE_STANDARD)
            + "QTextEdit { padding: 6px; }"
        )

    def _confirm_temp_elevation(self):
        result = self.show_modal_message(
            QMessageBox.Icon.NoIcon,
            "Temp Cleanup Needs Admin Access",
            (
                "Some temp files could not be removed because access was denied.\n\n"
                "Run temp cleanup again as administrator?\n\n"
                "Files currently in use may still be skipped."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.actions.retry_temp_cleanup_elevated()

    def _confirm_integrity_elevation(
        self,
        action_name: str,
        command: list[str],
        finished=None,
    ):
        result = self.show_modal_message(
            QMessageBox.Icon.NoIcon,
            f"{action_name} Needs Admin Access",
            (
                f"{action_name} requires administrator access.\n\n"
                "Run it as administrator?\n\n"
                "Windows will ask you to approve this action."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.actions.run_admin_command_elevated(command, finished=finished)
            return
        self.runner.set_output(
            f"{action_name} was cancelled. Administrator access is required to run it."
        )

    def _show_vanguard_chkdsk_warning(self):
        self.show_modal_message(
            QMessageBox.Icon.Warning,
            "Vanguard Is Blocking Check Disk",
            (
                "Riot Vanguard's vgk kernel driver is running and can block "
                "CHKDSK from accessing the Windows volume.\n\n"
                "The Vanguard tray app may be closed even while this driver remains loaded.\n\n"
                "Open Command Prompt as administrator, run 'sc stop vgk', then retry "
                "Check Disk. Vanguard normally reloads after Windows restarts."
            ),
            QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
        )

    def _show_generic_chkdsk_warning(self):
        self.show_modal_message(
            QMessageBox.Icon.Warning,
            "Check Disk Access Was Blocked",
            (
                "CHKDSK was elevated, but Windows denied access to the volume. "
                "The command output has been preserved in the Maintenance log.\n\n"
                "An antivirus, anti-cheat, encryption, backup, or storage filter "
                "driver may be blocking access. Close or stop the relevant software "
                "and retry, or run CHKDSK from Windows Recovery."
            ),
            QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
        )

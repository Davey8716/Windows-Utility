"""Application-wide live theme propagation."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from resurface.ui import styles
from resurface.ui.tooltips import refresh_visible_tooltip
from resurface.ui.window_chrome import SeverityComboItemDelegate


def apply_power_action_dropdown_style(combo: QComboBox) -> None:
    font_size = styles.coerce_font_size(combo.property("styleFontSize"), 14) or 14
    combo.setStyleSheet(styles.power_combo_style(font_size))

    severity_map = combo.property("powerActionSeverityMap") or {}
    placeholder_text = combo.property("powerActionPlaceholder") or ""
    for row in range(combo.count()):
        label = combo.itemText(row)
        severity = "placeholder" if label == placeholder_text else severity_map.get(label)
        if not severity:
            continue
        background = styles.power_action_color(severity)
        combo.setItemData(row, background, Qt.ItemDataRole.BackgroundRole)
        combo.setItemData(
            row,
            styles.power_action_item_foreground(label, background),
            Qt.ItemDataRole.ForegroundRole,
        )

    if not isinstance(combo.itemDelegate(), SeverityComboItemDelegate):
        combo.setItemDelegate(SeverityComboItemDelegate(combo))


class ApplicationThemeController:
    def __init__(
        self,
        *,
        root: QWidget,
        window_chrome,
        navigation_shell,
        refresh_master_backup_path: Callable[[], None],
        refresh_connected_drives_style: Callable[[], None],
        screen_mover_settings_page=None,
        hover_window_controls_page=None,
        user_interface_page=None,
        quick_actions_grid=None,
        folder_utilities_page=None,
        maintenance_page=None,
        drive_space_page=None,
        clipboard_provenance_page=None,
        monitor_rules_page=None,
        overview_status_labels: dict | None = None,
    ) -> None:
        self.root = root
        self.window_chrome = window_chrome
        self.navigation_shell = navigation_shell
        self._refresh_master_backup_path = refresh_master_backup_path
        self._refresh_connected_drives_style = refresh_connected_drives_style
        self.screen_mover_settings_page = screen_mover_settings_page
        self.hover_window_controls_page = hover_window_controls_page
        self.user_interface_page = user_interface_page
        self.quick_actions_grid = quick_actions_grid
        self.folder_utilities_page = folder_utilities_page
        self.maintenance_page = maintenance_page
        self.drive_space_page = drive_space_page
        self.clipboard_provenance_page = clipboard_provenance_page
        self.monitor_rules_page = monitor_rules_page
        self.overview_status_labels = overview_status_labels or {}

    @staticmethod
    def _is_screen_mover_shortcut_internal_field(line_edit: QLineEdit) -> bool:
        parent = line_edit.parentWidget()
        return (
            isinstance(parent, QKeySequenceEdit)
            and parent.objectName() == "ScreenMoverShortcutEdit"
        )

    def refresh_screen_mover_shortcut_styles(self) -> None:
        if self.screen_mover_settings_page is not None:
            self.screen_mover_settings_page.refresh_shortcut_styles()
            return
        for hotkey_edit in self.root.findChildren(QKeySequenceEdit):
            if hotkey_edit.objectName() != "ScreenMoverShortcutEdit":
                continue
            internal_edits = hotkey_edit.findChildren(QLineEdit)
            for internal_edit in internal_edits:
                internal_edit.setStyleSheet("")
            hotkey_edit.setStyleSheet(styles.hotkey_edit_style(13))
            for widget in (hotkey_edit, *internal_edits):
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()
            hotkey_edit.setFixedHeight(styles.PAGE_CONTROL_HEIGHT)
            if hasattr(hotkey_edit, "_fill_internal_field"):
                hotkey_edit._fill_internal_field()

    def apply_theme(self, is_dark: bool) -> None:
        styles.set_theme(is_dark)
        self.root.setStyleSheet(styles.window_style())
        refresh_visible_tooltip()
        self.window_chrome.apply_theme()

        for line_edit in self.root.findChildren(QLineEdit):
            if self._is_screen_mover_shortcut_internal_field(line_edit):
                continue
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

        self.refresh_screen_mover_shortcut_styles()

        for label in self.root.findChildren(QLabel):
            if label.property("surfaceLabelStyle"):
                font_size = styles.coerce_font_size(
                    label.property("styleFontSize"), 14
                ) or 14
                label.setStyleSheet(styles.surfaced_label_style(font_size))

        self._refresh_master_backup_path()

        for button in self.root.findChildren(QPushButton):
            font_size = styles.coerce_font_size(
                button.property("styleFontSize"), 14
            ) or 14
            severity = button.property("quickActionSeverity")
            if severity:
                button.setStyleSheet(
                    styles.power_action_button_style(font_size, severity, button.text())
                )
            elif button.property("dangerToggle"):
                button.setStyleSheet(styles.danger_toggle_button_style(font_size))
            elif button.property("quickActionToggle"):
                button.setStyleSheet(styles.toggle_button_style(font_size=font_size))
            else:
                button.setStyleSheet(styles.organizing_button_style(font_size=font_size))

        if self.user_interface_page is not None:
            self.user_interface_page.refresh_icons()
        if self.quick_actions_grid is not None:
            self.quick_actions_grid.refresh_source_icons()
        if self.folder_utilities_page is not None:
            self.folder_utilities_page.refresh_icons()

        for combo in self.root.findChildren(QComboBox):
            font_size = styles.coerce_font_size(
                combo.property("styleFontSize"), 14
            ) or 14
            if combo.property("connectedDrivesFieldStyle"):
                self._refresh_connected_drives_style()
            elif combo.property("powerActionStyle"):
                apply_power_action_dropdown_style(combo)
            elif combo.property("surfaceFieldStyle"):
                combo.setStyleSheet(styles.surfaced_combo_style(font_size=font_size))
            else:
                combo.setStyleSheet(styles.organizing_combo_style(font_size=font_size))

        if self.maintenance_page is not None:
            self.maintenance_page.apply_theme()
        if self.drive_space_page is not None:
            self.drive_space_page.apply_theme()
        if self.clipboard_provenance_page is not None:
            self.clipboard_provenance_page.refresh_theme()
        if self.monitor_rules_page is not None:
            self.monitor_rules_page.apply_theme()

        for label in self.root.findChildren(QLabel, "PageTitle"):
            label.setStyleSheet(styles.page_title_style())
        for label in self.root.findChildren(QLabel, "PageSectionHeading"):
            label.setStyleSheet(styles.page_section_heading_style())
        for label in self.root.findChildren(QLabel, "OverviewSummaryLabel"):
            label.setStyleSheet(styles.summary_label_style())
        for label in self.overview_status_labels.values():
            label.setStyleSheet(styles.summary_value_style())
        self.navigation_shell.apply_theme()

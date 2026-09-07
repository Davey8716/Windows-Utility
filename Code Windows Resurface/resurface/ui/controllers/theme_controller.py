"""Application-wide live theme propagation."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from resurface.ui import styles
from resurface.ui.window_chrome import SeverityComboItemDelegate


def _power_action_item_colors() -> dict[str, QColor]:
    return {
        "placeholder": QColor(26, 118, 214) if styles.THEME_IS_DARK else QColor(42, 134, 230),
        "blue": QColor(36, 104, 196) if styles.THEME_IS_DARK else QColor(68, 142, 236),
        "yellow": QColor(196, 162, 32) if styles.THEME_IS_DARK else QColor(224, 196, 74),
        "amber": QColor(207, 132, 30) if styles.THEME_IS_DARK else QColor(230, 154, 56),
        "orange": QColor(210, 95, 26) if styles.THEME_IS_DARK else QColor(234, 118, 42),
        "orange_red": QColor(198, 67, 35) if styles.THEME_IS_DARK else QColor(220, 88, 48),
        "red": QColor(176, 38, 38) if styles.THEME_IS_DARK else QColor(204, 52, 52),
    }


def _power_action_item_foreground(label: str, background: QColor) -> QColor:
    if styles.THEME_IS_DARK and label in {"Sleep", "Log out"}:
        return styles.TEXT_LIGHT
    if not styles.THEME_IS_DARK and label == "Shutdown":
        return QColor(0, 0, 0)
    return styles.contrasting_text_color(background)


def apply_power_action_dropdown_style(combo: QComboBox) -> None:
    font_size = styles.coerce_font_size(combo.property("styleFontSize"), 14) or 14
    combo.setStyleSheet(styles.power_combo_style(font_size))

    severity_map = combo.property("powerActionSeverityMap") or {}
    placeholder_text = combo.property("powerActionPlaceholder") or ""
    color_map = _power_action_item_colors()

    for row in range(combo.count()):
        label = combo.itemText(row)
        severity = "placeholder" if label == placeholder_text else severity_map.get(label)
        if not severity:
            continue
        background = color_map[severity]
        combo.setItemData(row, background, Qt.ItemDataRole.BackgroundRole)
        combo.setItemData(
            row,
            _power_action_item_foreground(label, background),
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
        maintenance_page=None,
        drive_space_page=None,
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
        self.maintenance_page = maintenance_page
        self.drive_space_page = drive_space_page
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

    def apply_theme(self, is_dark: bool) -> None:
        styles.set_theme(is_dark)
        self.root.setStyleSheet(styles.window_style() + styles.tooltip_style())
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
            button.setStyleSheet(styles.organizing_button_style(font_size=font_size))

        if self.user_interface_page is not None:
            self.user_interface_page.refresh_icons()

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

        for label in self.root.findChildren(QLabel, "PageTitle"):
            label.setStyleSheet(styles.page_title_style())
        for label in self.root.findChildren(QLabel, "PageDescription"):
            label.setStyleSheet(styles.page_description_style())
        for label in self.root.findChildren(QLabel, "PageSectionHeading"):
            label.setStyleSheet(styles.page_section_heading_style())
        for label in self.root.findChildren(QLabel, "OverviewSummaryLabel"):
            label.setStyleSheet(styles.summary_label_style())
        for label in self.overview_status_labels.values():
            label.setStyleSheet(styles.summary_value_style())
        self.navigation_shell.apply_theme()

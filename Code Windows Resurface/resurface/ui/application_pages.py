"""Construction and page-specific signal wiring for the main application UI."""

from dataclasses import dataclass
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QFrame, QGridLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from resurface.core.state_manager import save_state
from resurface.features.system.windows_tool_catalog import WindowsToolCatalog
from resurface.ui import styles
from resurface.ui.controllers.theme_controller import apply_power_action_dropdown_style
from resurface.ui.monitor_rules_page import MonitorRulesPage
from resurface.ui.navigation_shell import NavigationShell
from resurface.ui.pages.drive_space_page import DriveSpacePage
from resurface.ui.pages.external_drives_page import ExternalDrivesPage
from resurface.ui.pages.folder_utilities_page import FolderUtilitiesPage
from resurface.ui.pages.hover_window_controls_page import HoverWindowControlsPage
from resurface.ui.pages.maintenance_page import MaintenancePage
from resurface.ui.pages.organising_utilities_page import OrganisingUtilitiesPage
from resurface.ui.pages.recycle_bin_page import RecycleBinPage
from resurface.ui.pages.screen_mover_settings_page import ScreenMoverSettingsPage
from resurface.ui.pages.user_interface_page import UserInterfacePage
from resurface.ui.pages.windows_utilities_page import WindowsUtilitiesPage


class OverviewPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content_width = (styles.PAGE_CONTROL_WIDTH * 2) + styles.PAGE_CONTROL_GAP
        summary = QFrame(self)
        summary.setObjectName("OverviewSummary")
        summary.setFixedWidth(content_width)
        summary_layout = QGridLayout(summary)
        summary_layout.setContentsMargins(20, 18, 20, 18)
        summary_layout.setHorizontalSpacing(24)
        summary_layout.setVerticalSpacing(12)

        self.status_labels = {}
        for row, (key, label_text) in enumerate(
            (
                ("screen_mover", "Screen Mover"),
                ("drives", "Connected drives"),
                ("backup_path", "Master backup path"),
                ("recycle", "Recycle Bin auto-clean"),
            )
        ):
            label = QLabel(label_text, summary)
            label.setObjectName("OverviewSummaryLabel")
            label.setStyleSheet(styles.summary_label_style())
            value = QLabel(summary)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setStyleSheet(styles.summary_value_style())
            summary_layout.addWidget(label, row, 0)
            summary_layout.addWidget(value, row, 1)
            self.status_labels[key] = value
        summary_layout.setColumnStretch(1, 1)
        layout.addWidget(summary, 0, Qt.AlignmentFlag.AlignHCenter)

    def refresh(self, state: dict, connected_drives) -> None:
        self.status_labels["screen_mover"].setText(
            "On" if state.get("title_bar_dock_enabled", True) else "Off"
        )
        drive_count = len(connected_drives)
        self.status_labels["drives"].setText(
            f"{drive_count} connected" if drive_count else "None connected"
        )
        self.status_labels["backup_path"].setText(
            str(state.get("master_backup_output_path", "Not set"))
        )
        self.status_labels["recycle"].setText(
            "On" if state.get("recycle_bin_auto_clean_enabled", False) else "Off"
        )


class QuickActionsPage(QWidget):
    def __init__(self, actions, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        content_width = (styles.PAGE_CONTROL_WIDTH * 2) + styles.PAGE_CONTROL_GAP
        quick_row = QWidget(self)
        quick_row.setProperty("centeredControlGrid", True)
        quick_row.setObjectName("QuickActionsGrid")
        quick_row.setFixedWidth(content_width)
        quick_layout = QGridLayout(quick_row)
        quick_layout.setContentsMargins(0, 0, 0, 0)
        quick_layout.setHorizontalSpacing(styles.PAGE_CONTROL_GAP)
        quick_layout.setVerticalSpacing(12)
        for index, (text, callback) in enumerate(actions):
            button = QPushButton(text, quick_row)
            styles.apply_page_control_size(button)
            button.setProperty("styleFontSize", 13)
            button.setStyleSheet(styles.organizing_button_style(13))
            button.clicked.connect(callback)
            quick_layout.addWidget(button, index // 2, index % 2)
        layout.addWidget(quick_row, 0, Qt.AlignmentFlag.AlignHCenter)


@dataclass(frozen=True)
class ApplicationPages:
    overview_page: OverviewPage
    quick_actions_page: QuickActionsPage
    user_interface_page: UserInterfacePage
    screen_mover_settings_page: ScreenMoverSettingsPage
    monitor_rules_page: MonitorRulesPage
    external_drives_page: ExternalDrivesPage
    drive_space_page: DriveSpacePage
    organising_utilities_page: OrganisingUtilitiesPage
    folder_utilities_page: FolderUtilitiesPage
    recycle_bin_page: RecycleBinPage
    windows_utilities_page: WindowsUtilitiesPage
    maintenance_page: MaintenancePage
    hover_window_controls_page: HoverWindowControlsPage


class ApplicationPageComposer:
    """Build pages directly in their final hosts and wire page-local behavior."""

    def __init__(self, app, shell: NavigationShell):
        self.app = app
        self.shell = shell
        self.state = app.state

    def compose(self) -> ApplicationPages:
        app = self.app
        shell = self.shell

        overview_page = OverviewPage(shell.content_parent("overview"))
        shell.mount_content("overview", overview_page)
        quick_actions_page = QuickActionsPage(
            (
                ("Desktop Screenshot", app.organising_actions.take_desktop_screenshot),
                ("Export Bookmarks", app.organising_actions.export_bookmarks),
                ("Create Desktop Folder", app._open_folder_utilities),
                ("Open Recycle Bin", app.recycle_bin_actions.open_recycle_bin),
            ),
            shell.content_parent("quick_actions"),
        )
        shell.mount_content("quick_actions", quick_actions_page)

        icons_visible = app.actions.desktop_icons_visible()
        user_interface_page = UserInterfacePage(
            self.state,
            app.register_tooltip,
            apply_power_action_dropdown_style,
            desktop_icons_visible=icons_visible,
            parent=shell.content_parent("user_interface"),
        )
        if icons_visible is not None:
            self.state["desktop_zen_mode_enabled"] = not icons_visible
            save_state(self.state)
        self._wire_user_interface_page(user_interface_page)
        shell.mount_content("user_interface", user_interface_page)

        screen_mover_settings_page = ScreenMoverSettingsPage(
            self.state, app.register_tooltip, shell.content_parent("screen_mover")
        )
        screen_mover_settings_page.settings_changed.connect(self._screen_mover_settings_changed)
        shell.mount_content("screen_mover", screen_mover_settings_page)

        monitor_rules_page = MonitorRulesPage(
            shell.content_parent("monitor_rules"),
            rules=self.state.get("monitor_rules", []),
            app_hwnd=int(app.winId()),
            on_rules_changed=app.set_monitor_rules,
            get_master_backup_dir=app._get_master_backup_dir,
        )
        shell.mount_content("monitor_rules", monitor_rules_page)

        external_drives_page = ExternalDrivesPage(
            self.state, app.register_tooltip, shell.content_parent("external_drives")
        )
        external_drives_page.settings_changed.connect(self._update_state)
        shell.mount_content("external_drives", external_drives_page)
        shell.add_subheading("external_drives", "Storage")
        drive_space_page = DriveSpacePage(
            app.drive_service,
            app.window_management,
            app.register_tooltip,
            app._show_timed_message,
            app.organising_actions.run_with_optional_minimize,
            shell.content_parent("external_drives"),
        )
        shell.mount_content("external_drives", drive_space_page)

        organising_utilities_page = OrganisingUtilitiesPage(
            app._get_master_backup_dir(),
            app.register_tooltip,
            shell.content_parent("organising_utilities"),
        )
        self._wire_organising_page(organising_utilities_page)
        shell.mount_content("organising_utilities", organising_utilities_page)

        folder_utilities_page = FolderUtilitiesPage(
            app.register_tooltip, shell.content_parent("folder_utilities")
        )
        folder_utilities_page.create_folder_requested.connect(
            lambda name, save_name: app.folder_actions.create_desktop_folder(
                name, save_name=save_name
            )
        )
        folder_utilities_page.folder_creator_requested.connect(app.folder_actions.open_folder_creator)
        shell.mount_content("folder_utilities", folder_utilities_page)

        recycle_bin_page = RecycleBinPage(
            self.state, app.register_tooltip, shell.content_parent("recycle_bin")
        )
        self._wire_recycle_bin_page(recycle_bin_page)
        shell.mount_content("recycle_bin", recycle_bin_page)

        maintenance_page = MaintenancePage(
            app.maintenance_actions,
            app.command_runner,
            app.register_tooltip,
            app.organising_actions.run_with_optional_minimize,
            app._show_modal_message,
            shell.content_parent("maintenance"),
        )
        shell.mount_content("maintenance", maintenance_page)
        windows_utilities_page = WindowsUtilitiesPage(
            WindowsToolCatalog(),
            app.router_service,
            app.explorer_windows,
            app.window_management,
            app.maintenance_actions,
            app.register_tooltip,
            app.organising_actions.run_with_optional_minimize,
            maintenance_page.set_output_context,
            shell.content_parent("windows_utilities"),
        )
        shell.mount_content("windows_utilities", windows_utilities_page)

        hover_service = app.hover_window_controls
        hover_page = HoverWindowControlsPage(
            self.state,
            app.register_tooltip,
            taskbar_restore_available=hover_service.taskbar_restore_available,
            parent=shell.content_parent("hover_window_controls"),
        )
        hover_page.enabled_changed.connect(hover_service.set_enabled)
        hover_page.dwell_changed.connect(hover_service.set_dwell_ms)
        hover_page.calibration_requested.connect(self._calibrate_hover_controls)
        hover_page.export_requested.connect(self._export_hover_controls)
        hover_page.clear_requested.connect(self._clear_hover_controls_cache)
        hover_service.settings_changed.connect(hover_page.sync_settings)
        shell.mount_content("hover_window_controls", hover_page)
        shell.finish_page_layouts()

        pages = ApplicationPages(
            overview_page=overview_page,
            quick_actions_page=quick_actions_page,
            user_interface_page=user_interface_page,
            screen_mover_settings_page=screen_mover_settings_page,
            monitor_rules_page=monitor_rules_page,
            external_drives_page=external_drives_page,
            drive_space_page=drive_space_page,
            organising_utilities_page=organising_utilities_page,
            folder_utilities_page=folder_utilities_page,
            recycle_bin_page=recycle_bin_page,
            windows_utilities_page=windows_utilities_page,
            maintenance_page=maintenance_page,
            hover_window_controls_page=hover_page,
        )
        overview_page.refresh(self.state, getattr(app, "_overview_connected_drives", set()))
        return pages

    def _calibrate_hover_controls(self) -> None:
        try:
            self.app.hover_window_controls.calibrate(self.app)
        except Exception as error:
            QMessageBox.warning(
                self.app,
                "Calibration failed",
                f"Hover Window Controls calibration could not be opened.\n\n{error}",
            )

    def _export_hover_controls(self) -> None:
        destination = QFileDialog.getExistingDirectory(
            self.app,
            "Export Hover Window Controls data",
            str(Path.home()),
        )
        if not destination:
            return
        try:
            result = self.app.hover_window_controls.export_all_data(
                Path(destination)
            )
        except Exception as error:
            QMessageBox.critical(
                self.app,
                "Export failed",
                f"Hover Window Controls data could not be exported.\n\n{error}",
            )
            return
        QMessageBox.information(
            self.app,
            "Hover data exported",
            f"The export was created successfully.\n\n{result.directory}",
        )

    def _clear_hover_controls_cache(self) -> None:
        answer = QMessageBox.warning(
            self.app,
            "Clear all learned buttons?",
            "This permanently removes every learned caption-button image and "
            "all manual calibration data. Hover preferences are kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.app.hover_window_controls.clear_learned_buttons()
        except OSError as error:
            QMessageBox.warning(
                self.app,
                "Could not clear learned buttons",
                str(error),
            )

    def _wire_user_interface_page(self, page: UserInterfacePage) -> None:
        app = self.app
        page.theme_changed.connect(self._theme_changed)
        page.always_on_top_changed.connect(self._always_on_top_changed)
        page.tooltips_changed.connect(self._tooltips_changed)
        page.maximize_all_changed.connect(self._maximize_all_changed)
        page.minimize_after_use_changed.connect(
            lambda enabled: self._set_state_value("minimize_after_use_enabled", enabled)
        )
        page.desktop_zen_changed.connect(
            lambda enabled: self._desktop_zen_changed(page, enabled)
        )
        actions = {
            "Lock PC": app.maintenance_actions.run_lock_pc,
            "Sleep": app.maintenance_actions.run_sleep,
            "Log out": app.maintenance_actions.run_logout,
            "Restart": app.maintenance_actions.run_restart,
            "Shutdown": app.maintenance_actions.run_shutdown,
        }
        page.power_action_requested.connect(
            lambda name: app.external_drive_controller.confirm_power_action(
                name,
                actions[name],
            )
        )

    def _theme_changed(self, enabled: bool) -> None:
        self.state["theme_dark"] = enabled
        self.app.apply_theme(enabled)
        save_state(self.state)

    def _always_on_top_changed(self, enabled: bool) -> None:
        self.app._set_main_window_topmost_state(enabled)
        self._set_state_value("main_always_on_top_enabled", enabled)

    def _tooltips_changed(self, enabled: bool) -> None:
        self.state["tooltips_enabled"] = enabled
        self.app.actions.tooltips_toggle(enabled)
        save_state(self.state)

    def _maximize_all_changed(self, enabled: bool) -> None:
        self.state["maximize_all_enabled"] = enabled
        self.state.pop("minimize_all_enabled", None)
        save_state(self.state)
        actions = self.app.actions
        for name in ("maximize_all_toggle", "minimize_all_toggle", "maximize_all", "minimize_all"):
            callback = getattr(actions, name, None)
            if callback:
                callback(enabled)
                break

    def _desktop_zen_changed(self, page: UserInterfacePage, enabled: bool) -> None:
        self.state["desktop_zen_mode_enabled"] = enabled
        if self.app.actions.desktop_zen_mode_toggle(enabled) is not None:
            save_state(self.state)
            if enabled and getattr(self.app, "tray_manager", None):
                self.app.organising_actions.minimize_self_if_configured()
            return
        self.state["desktop_zen_mode_enabled"] = not enabled
        page.revert_desktop_zen(not enabled)
        save_state(self.state)
        self.app._show_timed_message(
            QMessageBox.Icon.Warning,
            "Desktop Icons",
            "Could not change desktop icon visibility.",
        )

    def _screen_mover_settings_changed(self, settings: dict) -> None:
        self.state.update(settings)
        save_state(self.state)
        self.app.apply_screen_mover_settings()
        self.app.refresh_overview()

    def _wire_organising_page(self, page: OrganisingUtilitiesPage) -> None:
        app = self.app
        actions = {
            "desktop_screenshot": app.organising_actions.take_desktop_screenshot,
            "capture_layout": app.organising_actions.capture_desktop_layout,
            "restore_layout": app.organising_actions.restore_desktop_layout,
            "export_bookmarks": app.organising_actions.export_bookmarks,
            "backup_taskbar": app.organising_actions.backup_taskbar_apps,
            "open_backup_folder": app.organising_actions.open_taskbar_backup_folder,
        }
        page.action_requested.connect(lambda name: actions[name]())
        page.master_backup_path_requested.connect(app._choose_master_backup_dir)
        app._taskbar_backup_folder_timer = QTimer(app)
        app._taskbar_backup_folder_timer.timeout.connect(app._refresh_taskbar_backup_folder_button)
        app._taskbar_backup_folder_timer.start(1000)

    def _wire_recycle_bin_page(self, page: RecycleBinPage) -> None:
        app = self.app
        actions = {
            "open": app.recycle_bin_actions.open_recycle_bin,
            "run": app.recycle_bin_actions.run_cleanup_now,
            "empty": app.recycle_bin_actions.empty_recycle_bin,
        }
        page.action_requested.connect(lambda name: actions[name]())
        page.settings_changed.connect(self._recycle_settings_changed)

    def _recycle_settings_changed(self, settings: dict) -> None:
        old_days = self.state.get("recycle_bin_age_rule_days")
        self.state.update(settings)
        if old_days != settings.get("recycle_bin_age_rule_days"):
            self.state["recycle_bin_last_auto_clean_popup_days"] = None
        save_state(self.state)
        self.app.refresh_overview()

    def _set_state_value(self, key: str, value) -> None:
        self.state[key] = value
        save_state(self.state)

    def _update_state(self, values: dict) -> None:
        self.state.update(values)
        save_state(self.state)

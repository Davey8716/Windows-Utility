import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from resurface.core.state_manager import save_state
from resurface.ui.pages.external_drives_page import ExternalDrivesPage
from resurface.ui.pages.folder_utilities_page import FolderUtilitiesPage
from resurface.ui.pages.organising_utilities_page import OrganisingUtilitiesPage
from resurface.ui.pages.recycle_bin_page import RecycleBinPage
from resurface.ui.pages.screen_mover_settings_page import ScreenMoverSettingsPage
from resurface.ui.pages.user_interface_page import UserInterfacePage


class LeftPanelBuilder:
    """Compose settings pages without publishing their individual controls."""

    def __init__(self, app):
        self.app = app
        self.state = app.state

    def build(self) -> None:
        app = self.app
        app.left_page_contents = {}
        icons_visible = app.actions.desktop_icons_visible()
        app.user_interface_page = UserInterfacePage(
            self.state, app.register_tooltip, app._apply_power_action_dropdown_style,
            desktop_icons_visible=icons_visible, parent=app,
        )
        if icons_visible is not None:
            self.state["desktop_zen_mode_enabled"] = not icons_visible
            save_state(self.state)
        self._wire_user_interface_page(app.user_interface_page)

        app.screen_mover_settings_page = ScreenMoverSettingsPage(
            self.state, app.register_tooltip, app
        )
        app.screen_mover_settings_page.settings_changed.connect(
            self._screen_mover_settings_changed
        )
        app.external_drives_page = ExternalDrivesPage(
            self.state, app.register_tooltip, app
        )
        app.external_drives_page.settings_changed.connect(self._update_state)
        app.external_drives_page.drive_open_requested.connect(
            lambda path: app.organising_actions.run_with_optional_minimize(
                lambda: os.startfile(path)
            )
        )
        app.external_drives_page.context_menu_requested.connect(
            app._show_connected_drives_context_menu
        )
        app._refresh_connected_drive_status_label()

        app.organising_utilities_page = OrganisingUtilitiesPage(
            app._get_master_backup_dir(), app.register_tooltip, app
        )
        self._wire_organising_page(app.organising_utilities_page)
        app.folder_utilities_page = FolderUtilitiesPage(app.register_tooltip, app)
        app.folder_utilities_page.create_folder_requested.connect(
            lambda name, save_name: app.folder_actions.create_desktop_folder(
                name, save_name=save_name
            )
        )
        app.folder_utilities_page.folder_creator_requested.connect(
            app.folder_actions.open_folder_creator
        )
        app.recycle_bin_page = RecycleBinPage(self.state, app.register_tooltip, app)
        self._wire_recycle_bin_page(app.recycle_bin_page)

        for page in (
            app.user_interface_page, app.screen_mover_settings_page,
            app.external_drives_page, app.organising_utilities_page,
            app.folder_utilities_page, app.recycle_bin_page,
        ):
            app.left_page_contents[page.section_id] = page

    def _wire_user_interface_page(self, page: UserInterfacePage) -> None:
        app = self.app
        page.theme_changed.connect(self._theme_changed)
        page.always_on_top_changed.connect(self._always_on_top_changed)
        page.tooltips_changed.connect(self._tooltips_changed)
        page.maximize_all_changed.connect(self._maximize_all_changed)
        page.minimize_after_use_changed.connect(
            lambda enabled: self._set_state_value("minimize_after_use_enabled", enabled)
        )
        page.desktop_zen_changed.connect(self._desktop_zen_changed)
        actions = {
            "Lock PC": app.maintenance_actions.run_lock_pc,
            "Sleep": app.maintenance_actions.run_sleep,
            "Log out": app.maintenance_actions.run_logout,
            "Restart": app.maintenance_actions.run_restart,
            "Shutdown": app.maintenance_actions.run_shutdown,
        }
        page.power_action_requested.connect(
            lambda name: app._confirm_power_action(name, actions[name])
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

    def _desktop_zen_changed(self, enabled: bool) -> None:
        self.state["desktop_zen_mode_enabled"] = enabled
        if self.app.actions.desktop_zen_mode_toggle(enabled) is not None:
            save_state(self.state)
            if enabled and getattr(self.app, "tray_manager", None):
                self.app.organising_actions.minimize_self_if_configured()
            return
        self.state["desktop_zen_mode_enabled"] = not enabled
        self.app.user_interface_page.revert_desktop_zen(not enabled)
        save_state(self.state)
        self.app._show_timed_message(
            QMessageBox.Icon.Warning, "Desktop Icons",
            "Could not change desktop icon visibility.",
        )

    def _screen_mover_settings_changed(self, settings: dict) -> None:
        self.state.update(settings)
        save_state(self.state)
        self.app.apply_screen_mover_settings()
        refresh = getattr(self.app, "refresh_overview", None)
        if refresh:
            refresh()

    def _wire_organising_page(self, page: OrganisingUtilitiesPage) -> None:
        actions = {
            "desktop_screenshot": self.app.organising_actions.take_desktop_screenshot,
            "capture_layout": self.app.organising_actions.capture_desktop_layout,
            "restore_layout": self.app.organising_actions.restore_desktop_layout,
            "export_bookmarks": self.app.organising_actions.export_bookmarks,
            "backup_taskbar": self.app.organising_actions.backup_taskbar_apps,
            "open_backup_folder": self.app.organising_actions.open_taskbar_backup_folder,
        }
        page.action_requested.connect(lambda name: actions[name]())
        page.master_backup_path_requested.connect(self.app._choose_master_backup_dir)
        self.app._taskbar_backup_folder_timer = QTimer(self.app)
        self.app._taskbar_backup_folder_timer.timeout.connect(
            self.app._refresh_taskbar_backup_folder_button
        )
        self.app._taskbar_backup_folder_timer.start(1000)
        self.app._refresh_taskbar_backup_folder_button()
        self.app._refresh_master_backup_path_display()

    def _wire_recycle_bin_page(self, page: RecycleBinPage) -> None:
        actions = {
            "open": self.app.recycle_bin_actions.open_recycle_bin,
            "run": self.app.recycle_bin_actions.run_cleanup_now,
            "empty": self.app.recycle_bin_actions.empty_recycle_bin,
        }
        page.action_requested.connect(lambda name: actions[name]())
        page.settings_changed.connect(self._recycle_settings_changed)

    def _recycle_settings_changed(self, settings: dict) -> None:
        old_days = self.state.get("recycle_bin_age_rule_days")
        self.state.update(settings)
        if old_days != settings.get("recycle_bin_age_rule_days"):
            self.state["recycle_bin_last_auto_clean_popup_days"] = None
        save_state(self.state)
        refresh = getattr(self.app, "refresh_overview", None)
        if refresh:
            refresh()

    def _set_state_value(self, key: str, value) -> None:
        self.state[key] = value
        save_state(self.state)

    def _update_state(self, values: dict) -> None:
        self.state.update(values)
        save_state(self.state)

"""Construction and page-specific signal wiring for the main application UI."""

from dataclasses import dataclass
from html import escape
from pathlib import Path
from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from resurface.core.state_manager import save_state
from resurface.features.screen_mover.hotkeys import active_hotkeys
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
from resurface.ui.quick_actions import QuickActionRegistry, QuickActionSpec
from resurface.ui.tooltips import tooltip_text


QUICK_ACTION_MIME = "application/x-windows-resurface-quick-action"


class QuickActionButton(QPushButton):
    def __init__(self, action_id: str, registry: QuickActionRegistry, parent=None):
        super().__init__(parent)
        self.action_id = action_id
        self.registry = registry
        self._press_pos: QPoint | None = None
        self._dragged = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._press_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (event.position().toPoint() - self._press_pos).manhattanLength() >= 10
        ):
            self._dragged = True
            self.setDown(False)
            mime = QMimeData()
            mime.setData(QUICK_ACTION_MIME, self.action_id.encode("utf-8"))
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragged:
            self._press_pos = None
            event.accept()
            return
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        styles.apply_popup_menu_style(menu)
        action = menu.addAction("Unpin from Quick Actions")
        action.triggered.connect(lambda: self.registry.unpin(self.action_id))
        menu.exec(event.globalPos())


class QuickActionsGrid(QWidget):
    VISIBLE_LIMIT = 8

    def __init__(self, registry: QuickActionRegistry, register_tooltip, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.register_tooltip = register_tooltip
        self.expanded = False
        self.buttons: dict[str, QuickActionButton] = {}
        self.tooltip_managers = {}
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_area_menu)
        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setHorizontalSpacing(styles.PAGE_CONTROL_GAP)
        self.layout.setVerticalSpacing(12)
        self.registry.pins_changed.connect(self.rebuild)
        self.registry.action_changed.connect(self.refresh_action)
        self.rebuild()

    def rebuild(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.buttons.clear()
        self.tooltip_managers.clear()
        specs = self.registry.specs()
        visible = specs if self.expanded else specs[: self.VISIBLE_LIMIT]
        for index, spec in enumerate(visible):
            button = QuickActionButton(spec.action_id, self.registry, self)
            styles.apply_page_control_size(button)
            button.setProperty("styleFontSize", 13)
            button.setStyleSheet(
                styles.toggle_button_style(13)
                if spec.is_toggle
                else styles.organizing_button_style(13)
            )
            if spec.is_toggle:
                button.setCheckable(True)
                button.setProperty("quickActionToggle", True)
                button.clicked.connect(
                    lambda checked, target=spec: target.set_checked(bool(checked))
                )
            else:
                button.clicked.connect(spec.invoke)
            self.buttons[spec.action_id] = button
            self.tooltip_managers[spec.action_id] = self.register_tooltip(button, spec.tooltip)
            self.layout.addWidget(button, index // 2, index % 2)
            self.refresh_action(spec.action_id)

        row = (len(visible) + 1) // 2
        if not specs:
            empty = QLabel(
                "No Quick Actions pinned. Right-click an action elsewhere in the app to add it.",
                self,
            )
            empty.setObjectName("QuickActionsEmptyState")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout.addWidget(empty, 0, 0, 1, 2)
        elif len(specs) > self.VISIBLE_LIMIT:
            more = QPushButton("Show Less" if self.expanded else "Show More", self)
            more.setObjectName("QuickActionsShowMore")
            more.clicked.connect(self._toggle_expanded)
            self.layout.addWidget(more, row, 0, 1, 2, Qt.AlignmentFlag.AlignHCenter)

    def refresh_action(self, action_id: str) -> None:
        button = self.buttons.get(action_id)
        spec = self.registry.spec(action_id)
        if button is None or spec is None:
            return
        label = spec.source.text() if spec.source is not None and spec.source.text() else spec.label
        button.setText(label)
        if spec.is_toggle:
            button.blockSignals(True)
            button.setChecked(bool(spec.checked()))
            button.blockSignals(False)
        available, reason = self.registry.availability(spec)
        button.setEnabled(available)
        button.setToolTip(reason or spec.tooltip)
        manager = self.tooltip_managers.get(action_id)
        if manager is not None:
            manager.set_text(reason or spec.tooltip)

    def _toggle_expanded(self) -> None:
        self.expanded = not self.expanded
        self.rebuild()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(QUICK_ACTION_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(QUICK_ACTION_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event):
        action_id = bytes(event.mimeData().data(QUICK_ACTION_MIME)).decode("utf-8")
        target = self.childAt(event.position().toPoint())
        while target is not None and not isinstance(target, QuickActionButton):
            target = target.parentWidget()
        ids = self.registry.pinned_ids()
        target_index = ids.index(target.action_id) if isinstance(target, QuickActionButton) else len(ids) - 1
        if self.registry.move(action_id, target_index):
            event.acceptProposedAction()

    def _show_area_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        styles.apply_popup_menu_style(menu)
        reset = menu.addAction("Reset Quick Actions to Defaults")
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen is not reset:
            return
        answer = QMessageBox.question(
            self,
            "Reset Quick Actions",
            "Replace your pinned Quick Actions and their order with the defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.expanded = False
            self.registry.reset()


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
        configured_shortcuts = len(
            active_hotkeys(state.get("screen_mover_keyboard_hotkeys", {}))
        )
        self.status_labels["screen_mover"].setText(
            f"{configured_shortcuts} configured"
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
    def __init__(self, quick_actions: QuickActionRegistry, register_tooltip, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.quick_actions_grid = QuickActionsGrid(
            quick_actions, register_tooltip, self
        )
        self.quick_actions_grid.setObjectName("QuickActionsGrid")
        self.quick_actions_grid.setFixedWidth(
            (styles.PAGE_CONTROL_WIDTH * 2) + styles.PAGE_CONTROL_GAP
        )
        layout.addWidget(
            self.quick_actions_grid, 0, Qt.AlignmentFlag.AlignHCenter
        )


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

        self.quick_actions = QuickActionRegistry(self.state, save_state, app)
        overview_page = OverviewPage(shell.content_parent("overview"))
        shell.mount_content("overview", overview_page)
        quick_actions_page = QuickActionsPage(
            self.quick_actions,
            app.register_tooltip,
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
        screen_mover_settings_page.reset_confirmation_requested.connect(
            lambda: self._confirm_screen_mover_reset(screen_mover_settings_page)
        )
        shell.mount_content("screen_mover", screen_mover_settings_page)

        monitor_rules_page = MonitorRulesPage(
            shell.content_parent("monitor_rules"),
            rules=self.state.get("monitor_rules", []),
            app_hwnd=int(app.winId()),
            on_rules_changed=app.set_monitor_rules,
            get_master_backup_dir=app._get_master_backup_dir,
            open_backup_folder=app.explorer_windows.open_or_focus_folder,
            get_import_baseline=lambda: self.state.get("monitor_rules_import_baseline"),
            set_import_baseline=app.set_monitor_rules_import_baseline,
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
            app.folder_actions.create_desktop_folder
        )
        folder_utilities_page.save_name_requested.connect(
            app.folder_actions.save_folder_name
        )
        folder_utilities_page.delete_name_requested.connect(
            app.folder_actions.delete_saved_folder_name
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
            has_export_changes=lambda: hover_service.has_export_changes(
                Path(app.get_default_hover_controls_export_dir())
            ),
            parent=shell.content_parent("hover_window_controls"),
        )
        hover_page.enabled_changed.connect(hover_service.set_enabled)
        hover_page.taskbar_restore_enabled_changed.connect(
            hover_service.set_taskbar_restore_enabled
        )
        hover_page.dwell_changed.connect(hover_service.set_dwell_ms)
        hover_page.calibration_requested.connect(self._calibrate_hover_controls)
        hover_page.export_requested.connect(self._export_hover_controls)
        hover_page.import_requested.connect(self._import_hover_controls)
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
        self._register_quick_actions(pages)
        self.quick_actions.finalize()
        app.quick_actions = self.quick_actions
        overview_page.refresh(self.state, getattr(app, "_overview_connected_drives", set()))
        return pages

    def _register_quick_actions(self, pages: ApplicationPages) -> None:
        registry = self.quick_actions

        def button(action_id, label, widget, tooltip=""):
            registry.register_button(action_id, label, widget, tooltip=tooltip)

        ui = pages.user_interface_page
        button("ui.theme", "Dark Mode", ui._dark_mode_button, "Switch the app theme.")
        button("ui.desktop_zen", "Desktop Zen Mode", ui._desktop_zen_button, "Show or hide desktop icons.")
        button("ui.always_on_top", "Always on Top", ui.always_on_top_button)
        button("ui.tooltips", "Tooltips", ui.tooltips_button)
        button("ui.maximize_all", "Maximize All", ui.maximize_all_button)
        button("ui.minimize_after_use", "Minimize After Use", ui.minimize_after_use_button)
        power_callbacks = {
            "Lock PC": self.app.maintenance_actions.run_lock_pc,
            "Sleep": self.app.maintenance_actions.run_sleep,
            "Log out": self.app.maintenance_actions.run_logout,
            "Restart": self.app.maintenance_actions.run_restart,
            "Shutdown": self.app.maintenance_actions.run_shutdown,
        }
        registry.register_dropdown(
            ui.power_actions_combo,
            [
                QuickActionSpec(
                    f"power.{name.lower().replace(' ', '_')}",
                    name,
                    lambda name=name, callback=callback: self.app.external_drive_controller.confirm_power_action(name, callback),
                    "Uses the normal power-action and external-drive confirmation.",
                )
                for name, callback in power_callbacks.items()
            ],
        )

        screen = pages.screen_mover_settings_page
        button("screen_mover.reset", "Reset Shortcut Defaults", screen.reset_button)

        drives = pages.external_drives_page
        button("drives.leave_reminder", "Drive Leave Reminder", drives.leave_reminder_button)
        space = pages.drive_space_page
        button("drives.this_pc", "Open This PC", space.btn_this_pc)
        button("drives.storage_sense", "Open Storage Sense", space.btn_storage_sense)

        organising = pages.organising_utilities_page
        button("organising.desktop_screenshot", "Desktop Screenshot", organising.screenshot_button)
        button("organising.export_bookmarks", "Export Bookmarks", organising.bookmarks_button)
        button("organising.master_backup_path", "Master Backup Path", organising.master_backup_button)
        organising_callbacks = {
            "Capture Layout": self.app.organising_actions.capture_desktop_layout,
            "Restore Layout": self.app.organising_actions.restore_desktop_layout,
        }
        registry.register_dropdown(
            organising.desktop_actions_combo,
            [QuickActionSpec(f"organising.{label.lower().replace(' ', '_')}", label, callback) for label, callback in organising_callbacks.items()],
        )
        taskbar_callbacks = {
            "Backup Taskbar": self.app.organising_actions.backup_taskbar_apps,
            "Open Backup Folder": self.app.organising_actions.open_taskbar_backup_folder,
        }
        registry.register_dropdown(
            organising.taskbar_actions_combo,
            [QuickActionSpec(f"organising.{label.lower().replace(' ', '_')}", label, callback) for label, callback in taskbar_callbacks.items()],
        )

        registry.register(
            QuickActionSpec(
                "folder.create_desktop_folder",
                "Create Desktop Folder",
                self.app._open_folder_utilities,
                tooltip_text("quick_action_create_desktop_folder"),
            )
        )
        button("folder.creator", "Folder Creator", pages.folder_utilities_page.folder_creator_button)

        recycle = pages.recycle_bin_page
        button("recycle.auto_clean", "Auto-clean", recycle.auto_clean_button)
        recycle_callbacks = {
            "Open Recycle Bin": self.app.recycle_bin_actions.open_recycle_bin,
            "Run Auto-Clean Now": self.app.recycle_bin_actions.run_cleanup_now,
            "Empty Recycle Bin": self.app.recycle_bin_actions.empty_recycle_bin,
        }
        recycle_ids = {
            "Open Recycle Bin": "recycle.open",
            "Run Auto-Clean Now": "recycle.run_auto_clean",
            "Empty Recycle Bin": "recycle.empty",
        }
        registry.register_dropdown(
            recycle.actions_combo,
            [QuickActionSpec(recycle_ids[label], label, callback) for label, callback in recycle_callbacks.items()],
        )

        hover = pages.hover_window_controls_page
        for action_id, label, widget in (
            ("hover.enabled", "Hover Controls", hover.enabled_button),
            ("hover.taskbar_restore", "Taskbar Restoration", hover.taskbar_restore_button),
            ("hover.calibrate", "Calibrate Application…", hover.calibrate_button),
            ("hover.export", "Export Hover Data…", hover.export_button),
            ("hover.import", "Import Hover Data…", hover.import_button),
            ("hover.clear", "Clear Learned Buttons…", hover.clear_button),
        ):
            button(action_id, label, widget)

        monitor = pages.monitor_rules_page
        for action_id, widget in (
            ("monitor_rules.add", monitor.add_button),
            ("monitor_rules.sort", monitor.alphabet_sort_button),
            ("monitor_rules.turn_off_all", monitor.turn_off_all_button),
            ("monitor_rules.delete_all", monitor.delete_all_button),
            ("monitor_rules.export", monitor.export_rules_button),
            ("monitor_rules.import", monitor.import_rules_button),
        ):
            button(action_id, widget.text(), widget)

        maintenance = pages.maintenance_page
        for combo, title, action_map in maintenance.quick_action_dropdowns:
            registry.register_dropdown(
                combo,
                [
                    QuickActionSpec(
                        f"maintenance.{label.lower().replace(' ', '_').replace('/', '_')}",
                        label,
                        lambda label=label, callback=callback: (maintenance.set_output_context(label), callback()),
                    )
                    for label, callback in action_map.items()
                ],
            )

        windows = pages.windows_utilities_page
        for combo, group, tools_by_label in windows.quick_action_dropdowns:
            registry.register_dropdown(
                combo,
                [
                    QuickActionSpec(
                        f"windows.{tool.key}", tool.label,
                        lambda tool=tool: windows.invoke_tool(tool),
                        available=lambda tool=tool: windows.tool_availability(tool),
                    )
                    for tool in tools_by_label.values()
                ],
            )

    def _calibrate_hover_controls(self) -> None:
        try:
            self.app.hover_window_controls.calibrate(self.app)
        except Exception as error:
            QMessageBox.warning(
                self.app,
                "Calibration failed",
                f"Hover Window Controls calibration could not be opened.\n\n{error}",
            )
        finally:
            self._refresh_hover_export_button()

    def _refresh_hover_export_button(self) -> None:
        page = getattr(
            getattr(self.app, "pages", None),
            "hover_window_controls_page",
            None,
        )
        if page is not None:
            page.refresh_export_button()

    def _export_hover_controls(self) -> None:
        destination = Path(self.app.get_default_hover_controls_export_dir())
        try:
            if not self.app.hover_window_controls.has_export_changes(
                destination
            ):
                self._refresh_hover_export_button()
                return
        except (OSError, RuntimeError, TypeError, ValueError):
            pass

        def open_destination(_link: str) -> None:
            try:
                destination.mkdir(parents=True, exist_ok=True)
                opened = self.app.explorer_windows.open_or_focus_folder(
                    str(destination)
                )
            except Exception as error:
                self.app._show_modal_message(
                    QMessageBox.Icon.Critical,
                    "Open export folder failed",
                    f"The export folder could not be opened.\n\n{error}",
                    QMessageBox.StandardButton.Ok,
                    QMessageBox.StandardButton.Ok,
                )
                return
            if not opened:
                self.app._show_modal_message(
                    QMessageBox.Icon.Critical,
                    "Open export folder failed",
                    f"The export folder could not be opened.\n\n{destination}",
                    QMessageBox.StandardButton.Ok,
                    QMessageBox.StandardButton.Ok,
                )

        destination_text = escape(str(destination))
        link_color = styles.message_box_link_color().name()
        answer = self.app._show_modal_message(
            QMessageBox.Icon.NoIcon,
            "Export Hover Data",
            "Export Hover Window Controls data to:<br>"
            f'<a href="open-export-destination" '
            f'style="color: {link_color}; text-decoration: underline;">'
            f"{destination_text}</a>",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
            link_activated=open_destination,
            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
        )
        if answer != QMessageBox.StandardButton.Save:
            return
        try:
            destination.mkdir(parents=True, exist_ok=True)
            result = self.app.hover_window_controls.export_all_data(destination)
        except Exception as error:
            self.app._show_modal_message(
                QMessageBox.Icon.Critical,
                "Export failed",
                f"Hover Window Controls data could not be exported.\n\n{error}",
                QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Ok,
            )
            return
        self._refresh_hover_export_button()
        if result is None:
            return
        self.app._show_timed_message(
            QMessageBox.Icon.Information,
            "Hover data exported",
            f"The export was created successfully.\n\n{result.directory}",
            show_close_now_button=True,
        )

    def _import_hover_controls(self) -> None:
        start_dir = self.app.get_default_hover_controls_export_dir()
        dialog = QFileDialog(
            self.app,
            "Import Hover Data",
            start_dir,
            "Hover data manifest (export_manifest.json);;JSON files (*.json)",
        )
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        dialog.setStyleSheet(styles.file_dialog_style())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected_files = dialog.selectedFiles()
        if not selected_files:
            return
        manifest_path = Path(selected_files[0])
        if manifest_path.name.casefold() != "export_manifest.json":
            self.app._show_modal_message(
                QMessageBox.Icon.Warning,
                "Import Hover Data",
                "Select the export_manifest.json file from a Hover Window "
                "Controls backup.",
                QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Ok,
            )
            return
        source_directory = manifest_path.parent
        try:
            self.app.hover_window_controls.validate_import(source_directory)
        except Exception as error:
            self.app._show_modal_message(
                QMessageBox.Icon.Warning,
                "Import Hover Data",
                f"The selected Hover Window Controls backup is invalid.\n\n{error}",
                QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Ok,
            )
            return
        answer = self.app._show_modal_message(
            QMessageBox.Icon.Warning,
            "Import Hover Data",
            "Replace the current Hover Window Controls settings and learned "
            "button data with this backup?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self.app.hover_window_controls.import_all_data(
                source_directory
            )
        except Exception as error:
            self.app._show_modal_message(
                QMessageBox.Icon.Critical,
                "Import failed",
                f"Hover Window Controls data could not be imported.\n\n{error}",
                QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Ok,
            )
            return
        self._refresh_hover_export_button()
        self.app._show_timed_message(
            QMessageBox.Icon.Information,
            "Hover data imported",
            f"The backup was imported successfully.\n\n{result.source_directory}",
            show_close_now_button=True,
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
        finally:
            self._refresh_hover_export_button()

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

    def _confirm_screen_mover_reset(self, page: ScreenMoverSettingsPage) -> None:
        answer = self.app._show_modal_message(
            QMessageBox.Icon.Question,
            "Reset Shortcut Defaults",
            "This will clear all Screen Mover keyboard shortcuts. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
        )
        if answer == QMessageBox.StandardButton.Yes:
            page.reset_settings()

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

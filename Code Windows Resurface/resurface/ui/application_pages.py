"""Construction and page-specific signal wiring for the main application UI."""

from dataclasses import dataclass
from collections.abc import Callable
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

from resurface.core.state_manager import get_config_path, save_state
from resurface.features.hover_window_controls.service import normalized_dwell_ms
from resurface.features.screen_mover.hotkeys import (
    active_hotkeys,
    normalize_hotkeys,
    normalize_unique_hotkeys,
)
from resurface.features.system.windows_tool_catalog import WindowsToolCatalog
from resurface.ui import styles
from resurface.ui.app_notifications import WindowMessageMixin
from resurface.ui.opaque_rounded_frame import paint_opaque_rounded_frame
from resurface.ui.controllers.theme_controller import apply_power_action_dropdown_style
from resurface.ui.monitor_rules_page import MonitorRulesPage
from resurface.ui.clipboard_provenance_page import ClipboardProvenancePage
from resurface.ui.navigation_shell import NavigationShell
from resurface.ui.pages.drive_space_page import DriveSpacePage
from resurface.ui.pages.external_drives_page import ExternalDrivesPage
from resurface.ui.pages.folder_utilities_page import FolderUtilitiesPage
from resurface.ui.pages.maintenance_page import MaintenancePage
from resurface.ui.pages.organising_utilities_page import (
    ORGANISING_UTILITIES_HELP_TEXT,
    OrganisingUtilitiesPage,
)
from resurface.ui.pages.recycle_bin_page import RecycleBinPage
from resurface.ui.pages.screen_mover_settings_page import ScreenMoverSettingsPage
from resurface.ui.pages.user_interface_page import UserInterfacePage
from resurface.ui.pages.windows_utilities_page import WindowsUtilitiesPage
from resurface.ui.quick_actions import QuickActionRegistry, QuickActionSpec
from resurface.ui.tooltips import set_tooltip, tooltip_text


QUICK_ACTION_MIME = "application/x-windows-resurface-quick-action"
HOVER_CONTROLS_PROMPT_CORNER_RADIUS = 12


class HoverDataImportDialog(QFileDialog):
    """Opaque, frameless file picker with a single continuous outer frame."""

    FRAME_WIDTH = 2

    def __init__(self, parent, directory: str) -> None:
        super().__init__(
            parent,
            "Import Hover Data",
            directory,
            "Hover data manifest (export_manifest.json);;JSON files (*.json)",
        )
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self.setFileMode(QFileDialog.FileMode.ExistingFile)
        self.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setStyleSheet(styles.file_dialog_style())
        self.setSizeGripEnabled(False)
        self.setFixedSize(self.sizeHint())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        paint_opaque_rounded_frame(
            self,
            radius=styles.BUTTON_CORNER_RADIUS,
            frame_width=self.FRAME_WIDTH,
        )


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
        styles.apply_popup_menu_style(menu, radius=styles.BUTTON_CORNER_RADIUS)
        action = menu.addAction("Unpin from Quick Actions")
        action.triggered.connect(lambda: self.registry.unpin(self.action_id))
        menu.exec(event.globalPos())


class QuickActionsGrid(WindowMessageMixin, QWidget):
    VISIBLE_LIMIT = 8
    COMPACT_COLUMNS = 4

    def __init__(self, registry: QuickActionRegistry, register_tooltip, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.register_tooltip = register_tooltip
        self.expanded = False
        self.buttons: dict[str, QuickActionButton] = {}
        self.tooltip_managers = {}
        self.empty_state_label: QLabel | None = None
        self.reset_defaults_button: QPushButton | None = None
        self.setAcceptDrops(True)
        self._availability_timer = QTimer(self)
        self._availability_timer.setInterval(2_000)
        self._availability_timer.timeout.connect(self._refresh_dynamic_availability)
        self._availability_timer.start()
        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setHorizontalSpacing(styles.PAGE_CONTROL_GAP)
        self.layout.setVerticalSpacing(styles.PAGE_CONTROL_ROW_GAP)
        compact_width = (
            styles.PAGE_CONTROL_WIDTH - styles.PAGE_CONTROL_GAP
        ) // 2
        for column in range(self.COMPACT_COLUMNS):
            self.layout.setColumnMinimumWidth(column, compact_width)
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
        self.empty_state_label = None
        self.reset_defaults_button = None
        specs = self.registry.specs()
        visible = specs if self.expanded else specs[: self.VISIBLE_LIMIT]
        next_slot = 0
        for spec in visible:
            button = QuickActionButton(spec.action_id, self.registry, self)
            compact = bool(spec.compact)
            if compact:
                source = spec.source
                width = source.width() if source is not None else styles.PAGE_COMPACT_CONTROL_WIDTH
                height = source.height() if source is not None else styles.PAGE_CONTROL_HEIGHT
                styles.apply_page_control_size(
                    button, width=width, height=height, role="compact"
                )
                button.setProperty("quickActionCompact", True)
            else:
                styles.apply_page_control_size(button)
            button.setProperty("styleFontSize", 13)
            if spec.action_id == "recycle.empty":
                button.setProperty("lightModeBlackDisabledText", True)
            if spec.severity:
                button.setProperty("quickActionSeverity", spec.severity)
                button.setStyleSheet(
                    styles.power_action_button_style(13, spec.severity, spec.label)
                )
            else:
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
            column_span = 1 if compact else 2
            column = next_slot % self.COMPACT_COLUMNS
            if column + column_span > self.COMPACT_COLUMNS:
                next_slot += self.COMPACT_COLUMNS - column
                column = 0
            self.layout.addWidget(
                button,
                next_slot // self.COMPACT_COLUMNS,
                column,
                1,
                column_span,
            )
            next_slot += column_span
            self.refresh_action(spec.action_id)

        row = (next_slot + self.COMPACT_COLUMNS - 1) // self.COMPACT_COLUMNS
        if not specs:
            empty = QLabel(
                "No Quick Actions pinned. Right-click an action elsewhere in the app to add it.",
                self,
            )
            empty.setObjectName("QuickActionsEmptyState")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout.addWidget(empty, 0, 0, 1, self.COMPACT_COLUMNS)
            self.empty_state_label = empty

            reset = QPushButton("Reset Quick Actions to Defaults", self)
            reset.setObjectName("QuickActionsResetDefaults")
            styles.apply_page_control_size(reset)
            reset.setProperty("styleFontSize", 13)
            reset.setStyleSheet(styles.organizing_button_style(13))
            reset.clicked.connect(self._reset_to_defaults)
            self.register_tooltip(reset, tooltip_text("quick_actions_reset_defaults"))
            self.layout.addWidget(
                reset, 1, 0, 1, self.COMPACT_COLUMNS, Qt.AlignmentFlag.AlignHCenter
            )
            self.reset_defaults_button = reset
        elif len(specs) > self.VISIBLE_LIMIT:
            more = QPushButton("Show Less" if self.expanded else "Show More", self)
            more.setObjectName("QuickActionsShowMore")
            more.setCursor(Qt.CursorShape.PointingHandCursor)
            styles.apply_page_control_size(more)
            more.setProperty("styleFontSize", 13)
            more.setStyleSheet(styles.organizing_button_style(13))
            more.clicked.connect(self._toggle_expanded)
            self.layout.addWidget(
                more,
                row,
                0,
                1,
                self.COMPACT_COLUMNS,
                Qt.AlignmentFlag.AlignHCenter,
            )

    def refresh_action(self, action_id: str) -> None:
        button = self.buttons.get(action_id)
        spec = self.registry.spec(action_id)
        if button is None or spec is None:
            return
        source = spec.source
        if spec.icon_only and source is not None:
            button.setProperty("quickActionIconOnly", True)
            button.setText("")
            button.setIcon(source.icon())
            button.setIconSize(source.iconSize())
        else:
            label = source.text() if source is not None and source.text() else spec.label
            button.setText(label)
        if spec.is_toggle:
            button.blockSignals(True)
            button.setChecked(bool(spec.checked()))
            button.blockSignals(False)
        available, reason = self.registry.availability(spec)
        button.setEnabled(available)
        set_tooltip(button, reason or spec.tooltip)
        manager = self.tooltip_managers.get(action_id)
        if manager is not None:
            manager.set_text(reason or spec.tooltip)

    def refresh_source_icons(self) -> None:
        """Copy refreshed source icons into icon-only Quick Actions."""
        for action_id in self.buttons:
            self.refresh_action(action_id)

    def _refresh_dynamic_availability(self) -> None:
        """Keep actions backed by changing Windows state accurate while visible."""
        for action_id in self.buttons:
            spec = self.registry.spec(action_id)
            if spec is not None and spec.available is not None:
                self.refresh_action(action_id)

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

    def _reset_to_defaults(self) -> None:
        answer = self._show_modal_message(
            QMessageBox.Icon.Question,
            "Reset Quick Actions",
            "Replace your pinned Quick Actions and their order with the defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
            popup_corner_radius=6,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.expanded = False
            self.registry.reset()


class OverviewPage(QWidget):
    def __init__(
        self,
        parent=None,
        *,
        open_master_backup_path: Callable[[], None] | None = None,
        open_app_data_path: Callable[[], None] | None = None,
        get_app_data_path: Callable[[], str | Path] | None = None,
    ):
        super().__init__(parent)
        self._open_master_backup_path = open_master_backup_path
        self._open_app_data_path = open_app_data_path
        self._get_app_data_path = get_app_data_path or (
            lambda: get_config_path().parent
        )
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
                ("quick_actions", "Quick Actions"),
                ("user_interface", "User Interface"),
                ("confirmations", "Confirmations"),
                ("screen_mover", "Screen Mover"),
                ("monitor_rules", "Monitor Rules"),
                ("drives", "External Drives"),
                ("backup_path", "Master backup path"),
                ("app_data_path", "App data path"),
                ("recycle", "Recycle Bin"),
                ("hover_controls", "Hover Window Controls"),
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
        for key in ("backup_path", "app_data_path"):
            path_label = self.status_labels[key]
            path_label.setTextFormat(Qt.TextFormat.RichText)
            path_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction
            )
            path_label.setOpenExternalLinks(False)
            path_label.linkActivated.connect(self._open_overview_path)
        summary_layout.setColumnStretch(1, 1)
        layout.addWidget(summary, 0, Qt.AlignmentFlag.AlignHCenter)

    def refresh(
        self,
        state: dict,
        connected_drives,
        *,
        hover_settings: tuple[bool, bool, int] | None = None,
    ) -> None:
        quick_action_ids = state.get("quick_action_ids", [])
        self.status_labels["quick_actions"].setText(
            f"{len(quick_action_ids) if isinstance(quick_action_ids, list) else 0} pinned"
        )
        self.status_labels["user_interface"].setText(
            " · ".join(
                (
                    "Dark mode" if state.get("theme_dark", True) else "Light mode",
                    "Desktop Zen On"
                    if state.get("desktop_zen_mode_enabled", False)
                    else "Desktop Zen Off",
                    "Always on Top On"
                    if state.get("main_always_on_top_enabled", True)
                    else "Always on Top Off",
                )
            )
        )
        self.status_labels["confirmations"].setText(
            "Disable All Confirmations On"
            if state.get("disable_all_confirmations_enabled", False)
            else "Disable All Confirmations Off"
        )
        configured_shortcuts = len(
            active_hotkeys(state.get("screen_mover_keyboard_hotkeys", {}))
        )
        self.status_labels["screen_mover"].setText(
            f"{configured_shortcuts} shortcuts configured"
        )
        monitor_rules = state.get("monitor_rules", [])
        if not isinstance(monitor_rules, list):
            monitor_rules = []
        enabled_rules = sum(
            bool(rule.get("enabled", True))
            for rule in monitor_rules
            if isinstance(rule, dict)
        )
        rule_count = len(monitor_rules)
        self.status_labels["monitor_rules"].setText(
            f"{enabled_rules} of {rule_count} enabled" if rule_count else "No rules"
        )
        drive_count = len(connected_drives)
        self.status_labels["drives"].setText(
            " · ".join(
                (
                    f"{drive_count} connected" if drive_count else "None connected",
                    "Leave reminder On"
                    if state.get("usb_idle_enabled", True)
                    else "Leave reminder Off",
                    "Notifications On"
                    if state.get(
                        "usb_plug_notify_mode",
                        "on" if state.get("usb_plug_enabled", True) else "off",
                    )
                    != "off"
                    else "Notifications Off",
                )
            )
        )
        backup_path = str(state.get("master_backup_output_path", "")).strip()
        backup_path_display = backup_path.replace("\\", "/")
        backup_label = self.status_labels["backup_path"]
        if backup_path:
            link_color = styles.TEXT_LIGHT.name()
            backup_label.setText(
                f'<a href="open-master-backup" '
                f'style="color: {link_color}; text-decoration: underline;">'
                f"{escape(backup_path_display)}</a>"
            )
            set_tooltip(backup_label, "Open the Master Backup Path in Explorer")
        else:
            backup_label.setText("Not set")
            set_tooltip(backup_label, "")
        app_data_path = str(self._get_app_data_path()).strip()
        app_data_path_display = app_data_path.replace("\\", "/")
        app_data_label = self.status_labels["app_data_path"]
        if app_data_path:
            link_color = styles.TEXT_LIGHT.name()
            app_data_label.setText(
                f'<a href="open-app-data" '
                f'style="color: {link_color}; text-decoration: underline;">'
                f"{escape(app_data_path_display)}</a>"
            )
            set_tooltip(app_data_label, "Open the live App data path in Explorer")
        else:
            app_data_label.setText("Not available")
            set_tooltip(app_data_label, "")
        recycle_enabled = bool(state.get("recycle_bin_auto_clean_enabled", False))
        recycle_days = state.get("recycle_bin_age_rule_days", 30)
        self.status_labels["recycle"].setText(
            f"Auto-clean On · Items older than {recycle_days} days"
            if recycle_enabled
            else "Auto-clean Off"
        )
        if hover_settings is None:
            hover_enabled = bool(state.get("hover_window_controls_enabled", True))
            taskbar_restore_enabled = bool(
                state.get("hover_taskbar_restore_enabled", True)
            )
            dwell_ms = normalized_dwell_ms(
                state.get("hover_window_controls_dwell_ms", 750)
            )
        else:
            hover_enabled, taskbar_restore_enabled, dwell_ms = hover_settings
            hover_enabled = bool(hover_enabled)
            taskbar_restore_enabled = bool(taskbar_restore_enabled)
            dwell_ms = normalized_dwell_ms(dwell_ms)
        self.status_labels["hover_controls"].setText(
            " · ".join(
                (
                    "On" if hover_enabled else "Off",
                    f"{dwell_ms:,} ms dwell",
                    "Taskbar restoration On"
                    if taskbar_restore_enabled
                    else "Taskbar restoration Off",
                )
            )
        )

    def _open_overview_path(self, link: str) -> None:
        if link == "open-master-backup" and self._open_master_backup_path is not None:
            self._open_master_backup_path()
        elif link == "open-app-data" and self._open_app_data_path is not None:
            self._open_app_data_path()


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
    clipboard_provenance_page: ClipboardProvenancePage
    external_drives_page: ExternalDrivesPage
    drive_space_page: DriveSpacePage
    organising_utilities_page: OrganisingUtilitiesPage
    folder_utilities_page: FolderUtilitiesPage
    recycle_bin_page: RecycleBinPage
    windows_utilities_page: WindowsUtilitiesPage
    maintenance_page: MaintenancePage


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
        overview_page = OverviewPage(
            shell.content_parent("overview"),
            open_master_backup_path=lambda: app.explorer_windows.open_or_focus_folder(
                app._get_master_backup_dir()
            ),
            open_app_data_path=lambda: app.explorer_windows.open_or_focus_folder(
                str(get_config_path().parent)
            ),
        )
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

        stored_hotkeys = self.state.get("screen_mover_keyboard_hotkeys", {})
        normalized_hotkeys = normalize_hotkeys(stored_hotkeys)
        unique_hotkeys = normalize_unique_hotkeys(stored_hotkeys)
        if normalized_hotkeys != unique_hotkeys:
            self.state["screen_mover_keyboard_hotkeys"] = unique_hotkeys
            save_state(self.state)

        screen_mover_settings_page = ScreenMoverSettingsPage(
            self.state, app.register_tooltip, shell.content_parent("screen_mover")
        )
        screen_mover_settings_page.settings_changed.connect(self._screen_mover_settings_changed)
        screen_mover_settings_page.shortcut_capture_changed.connect(
            app.hotkey_manager.set_capture_active
        )
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

        clipboard_provenance_page = ClipboardProvenancePage(
            shell.content_parent("clipboard_provenance"),
            service=app.clipboard_provenance,
            get_master_backup_dir=app._get_master_backup_dir,
            open_backup_folder=app.explorer_windows.open_or_focus_folder,
            register_tooltip=app.register_tooltip,
        )
        shell.mount_content("clipboard_provenance", clipboard_provenance_page)

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
            background_refresh=app.background_refresh,
        )
        app.background_refresh.drives_ready.connect(drive_space_page._render_drives)
        app.background_refresh.title_states_ready.connect(
            drive_space_page.apply_tracked_window_states
        )
        shell.mount_content(
            "external_drives", drive_space_page, vertical_expanding=True
        )

        organising_utilities_page = OrganisingUtilitiesPage(
            app._get_master_backup_dir(),
            app.register_tooltip,
            shell.content_parent("organising_utilities"),
            auto_export_interval=app.state.get("bookmark_auto_export_interval", "off"),
        )
        shell.page_title_help_button("organising_utilities").clicked.connect(
            self._show_organising_utilities_help
        )
        self._wire_organising_page(organising_utilities_page)
        shell.mount_content("organising_utilities", organising_utilities_page)

        folder_utilities_page = FolderUtilitiesPage(
            app.register_tooltip,
            shell.content_parent("folder_utilities"),
            saved_names_path=lambda: Path(app._get_master_backup_dir())
            / "Saved Folder Names" / "saved_folder_names.json",
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
        folder_utilities_page.delete_all_names_requested.connect(
            app.folder_actions.delete_all_saved_folder_names
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
        shell.mount_content("maintenance", maintenance_page, vertical_expanding=True)
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

        shell.finish_page_layouts()

        pages = ApplicationPages(
            overview_page=overview_page,
            quick_actions_page=quick_actions_page,
            user_interface_page=user_interface_page,
            screen_mover_settings_page=screen_mover_settings_page,
            monitor_rules_page=monitor_rules_page,
            clipboard_provenance_page=clipboard_provenance_page,
            external_drives_page=external_drives_page,
            drive_space_page=drive_space_page,
            organising_utilities_page=organising_utilities_page,
            folder_utilities_page=folder_utilities_page,
            recycle_bin_page=recycle_bin_page,
            windows_utilities_page=windows_utilities_page,
            maintenance_page=maintenance_page,
        )
        self._register_quick_actions(pages)
        self.quick_actions.finalize()
        app.quick_actions = self.quick_actions
        overview_page.refresh(
            self.state,
            getattr(app, "_overview_connected_drives", set()),
            hover_settings=(
                app.hover_window_controls.enabled,
                app.hover_window_controls.taskbar_restore_enabled,
                app.hover_window_controls.dwell_ms,
            ),
        )
        return pages

    def _register_quick_actions(self, pages: ApplicationPages) -> None:
        registry = self.quick_actions

        def button(action_id, label, widget, tooltip="", *, compact=False, icon_only=False):
            registry.register_button(
                action_id,
                label,
                widget,
                tooltip=tooltip,
                compact=compact,
                icon_only=icon_only,
            )

        ui = pages.user_interface_page
        button(
            "ui.theme",
            "Dark Mode",
            ui._dark_mode_button,
            "Switch the app theme.",
            compact=True,
            icon_only=True,
        )
        button(
            "ui.desktop_zen",
            "Desktop Zen Mode",
            ui._desktop_zen_button,
            "Show or hide desktop icons.",
            compact=True,
            icon_only=True,
        )
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
        power_severities = {
            "Lock PC": "blue",
            "Sleep": "yellow",
            "Log out": "orange",
            "Restart": "orange_red",
            "Shutdown": "red",
        }
        registry.register_dropdown(
            ui.power_actions_combo,
            [
                QuickActionSpec(
                    f"power.{name.lower().replace(' ', '_')}",
                    name,
                    lambda _checked=False, name=name, callback=callback: self.app.external_drive_controller.confirm_power_action(name, callback),
                    "Uses the normal power-action and external-drive confirmation.",
                    severity=power_severities[name],
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
        registry.register_dropdown(
            organising.auto_export_combo,
            [
                QuickActionSpec(
                    "organising.auto_export_daily",
                    "Auto-Export: Daily",
                    lambda: self.app.organising_actions.set_bookmark_auto_export("daily"),
                )
            ],
        )
        organising_callbacks = {
            "Capture Layout": self.app.organising_actions.capture_desktop_layout,
            "Restore Layout": self.app.organising_actions.restore_desktop_layout,
            "Alphabetise Groups": self.app.organising_actions.alphabetise_desktop_groups,
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
            [
                QuickActionSpec(
                    recycle_ids[label],
                    label,
                    callback,
                    available=(
                        (lambda: (
                            bool(getattr(self.app, "_recycle_bin_has_items_cache", False)),
                            "Recycle Bin is empty.",
                        ))
                        if label == "Empty Recycle Bin"
                        else None
                    ),
                )
                for label, callback in recycle_callbacks.items()
            ],
        )

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
                        lambda _checked=False, label=label, callback=callback: (maintenance.set_output_context(label), callback()),
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
                        lambda _checked=False, tool=tool: windows.invoke_tool(tool),
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
        page = getattr(getattr(self.app, "pages", None), "hover_window_controls_page", None)
        if page is not None:
            page.refresh_export_button()

    def _export_hover_controls(self) -> None:
        has_master_backup_path = getattr(
            self.app, "has_master_backup_path", lambda: True
        )
        if not has_master_backup_path():
            self.app._show_modal_message(
                QMessageBox.Icon.Warning,
                "Master Backup Path Required",
                "Choose a Master Backup Path before exporting Hover Window "
                "Controls data.",
                QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Ok,
                popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
            )
            return
        service = self.app.hover_window_controls
        try:
            if not service.has_export_changes():
                self._refresh_hover_export_button()
                return
        except Exception as error:
            self.app._show_timed_message(
                QMessageBox.Icon.Critical,
                "Export failed",
                f"Hover Window Controls data could not be exported.\n\n{error}",
                timeout_ms=10_000,
                show_close_now_button=True,
                popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
            )
            return
        destination = Path(self.app.get_default_hover_controls_export_dir())

        def open_destination(_link: str) -> None:
            try:
                destination.mkdir(parents=True, exist_ok=True)
                opened = self.app.explorer_windows.open_or_focus_folder(str(destination))
            except Exception as error:
                self.app._show_modal_message(
                    QMessageBox.Icon.Critical, "Open export folder failed",
                    f"The export folder could not be opened.\n\n{error}",
                    QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Ok,
                )
                return
            if not opened:
                self.app._show_modal_message(
                    QMessageBox.Icon.Critical, "Open export folder failed",
                    f"The export folder could not be opened.\n\n{destination}",
                    QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Ok,
                )

        answer = self.app._show_modal_message(
            QMessageBox.Icon.NoIcon,
            "Export Hover Data",
            "Export Hover Window Controls data to:<br>"
            f'<a href="open-export-destination" style="color: {styles.message_box_link_color().name()}; text-decoration: underline;">'
            f"{escape(str(destination))}</a>",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
            link_activated=open_destination,
            popup_corner_radius=HOVER_CONTROLS_PROMPT_CORNER_RADIUS,
        )
        if answer != QMessageBox.StandardButton.Save:
            return
        try:
            result = service.export_all_data()
        except Exception as error:
            self.app._show_timed_message(
                QMessageBox.Icon.Critical, "Export failed",
                f"Hover Window Controls data could not be exported.\n\n{error}",
                timeout_ms=10_000, show_close_now_button=True,
                popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
            )
            return
        self._refresh_hover_export_button()
        if result is not None:
            self.app._show_timed_message(
                QMessageBox.Icon.Information, "Hover data exported",
                f"The export was created successfully.\n\n{result.directory}",
                timeout_ms=10_000,
                show_close_now_button=True,
                popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
            )

    def _import_hover_controls(self) -> None:
        start_dir = self.app.get_default_hover_controls_export_dir()
        dialog = HoverDataImportDialog(self.app, start_dir)
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
            "Replace the current Hover Window Controls\n settings and learned "
            "button data with this backup?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
            fixed_popup_width=360,
            center_text_block=True,
            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
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
        self.app._show_timed_message(
            QMessageBox.Icon.Information,
            "Hover data imported",
            f"The backup was imported successfully.\n\n{result.source_directory}",
            show_close_now_button=True,
            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
        )
        self._refresh_hover_export_button()

    def _clear_hover_controls_cache(self) -> None:
        answer = self.app._show_modal_message(
            QMessageBox.Icon.NoIcon,
            "Clear all learned buttons?",
            "This permanently\n removes all learned caption-button images\n and "
            "calibration data.\nHover preferences are kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
            fixed_popup_width=360,
            center_text_block=True,
            popup_corner_radius=HOVER_CONTROLS_PROMPT_CORNER_RADIUS,
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
        page.disable_all_confirmations_changed.connect(
            lambda enabled: self._disable_all_confirmations_changed(page, enabled)
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

    def _disable_all_confirmations_changed(
        self, page: UserInterfacePage, enabled: bool
    ) -> None:
        if not enabled:
            self._set_state_value("disable_all_confirmations_enabled", False)
            self.app.refresh_overview()
            return
        if self.app.confirm_disable_all_confirmations():
            self._set_state_value("disable_all_confirmations_enabled", True)
            page.set_disable_all_confirmations_enabled(True)
            self.app.refresh_overview()
            return
        page.set_disable_all_confirmations_enabled(False)

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
            "alphabetise_groups": app.organising_actions.alphabetise_desktop_groups,
            "export_bookmarks": app.organising_actions.export_bookmarks,
            "run_bookmark_auto_export_now": app.organising_actions.run_bookmarks_auto_export_now,
            "set_bookmark_auto_export": app.organising_actions.set_bookmark_auto_export,
            "backup_taskbar": app.organising_actions.backup_taskbar_apps,
            "open_backup_folder": app.organising_actions.open_taskbar_backup_folder,
        }
        page.action_requested.connect(
            lambda name: (
                actions["set_bookmark_auto_export"](name.partition(":")[2])
                if name.startswith("set_bookmark_auto_export:")
                else actions[name]()
            )
        )
        page.master_backup_path_requested.connect(app._choose_master_backup_dir)
        app.organising_actions._update_auto_export_page_status()
        app._taskbar_backup_folder_timer = QTimer(app)
        app._taskbar_backup_folder_timer.timeout.connect(app._refresh_taskbar_backup_folder_button)
        app._taskbar_backup_folder_timer.start(1000)

    def _show_organising_utilities_help(self, _checked=False) -> None:
        self.app._show_modal_message(
            QMessageBox.Icon.NoIcon,
            "About Organising Utilities Backups",
            ORGANISING_UTILITIES_HELP_TEXT,
            QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
            minimum_popup_width=500,
            text_minimum_width=430,
            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
            text_color=styles.TEXT_LIGHT,
        )

    def _wire_recycle_bin_page(self, page: RecycleBinPage) -> None:
        app = self.app
        actions = {
            "open": app.recycle_bin_actions.open_recycle_bin,
            "run": app.recycle_bin_actions.run_cleanup_now,
            "empty": app.recycle_bin_actions.empty_recycle_bin,
        }
        page.action_requested.connect(lambda name: actions[name]())
        page.settings_changed.connect(self._recycle_settings_changed)
        app._recycle_bin_has_items_cache = False
        page.availability_changed.connect(self._set_recycle_bin_availability)
        page.set_background_refresh(app.background_refresh)

    def _set_recycle_bin_availability(self, has_items: bool) -> None:
        self.app._recycle_bin_has_items_cache = bool(has_items)
        self.quick_actions.action_changed.emit("recycle.empty")

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

"""UI coordination for external-drive monitoring and reminders."""

from __future__ import annotations

import os
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMenu, QMessageBox

from resurface.features.drives.drive_monitor import external_drive_signature
from resurface.features.drives.drive_reminder_logic import (
    DriveChanges,
    DriveReminderPolicy,
)
from resurface.features.drives.drive_service import DriveServiceError
from resurface.ui import styles
from resurface.ui.external_drive_popups import (
    reminder_popup_options,
    status_popup_options,
)


class ExternalDriveController:
    def __init__(
        self,
        *,
        window,
        state: dict,
        drive_service,
        monitor,
        policy: DriveReminderPolicy,
        page: Callable[[], object | None],
        drive_space_page: Callable[[], object | None],
        refresh_overview: Callable[[], None],
        run_with_optional_minimize: Callable[[Callable[[], None]], None],
    ) -> None:
        self.window = window
        self.state = state
        self.drive_service = drive_service
        self.monitor = monitor
        self.policy = policy
        self._page = page
        self._drive_space_page = drive_space_page
        self._refresh_overview = refresh_overview
        self._run_with_optional_minimize = run_with_optional_minimize
        self._current_drives: tuple[str, ...] = ()
        self._fresh_snapshot_callbacks: list[Callable[[tuple[str, ...]], None]] = []
        self._suppressed_removals: tuple[str, ...] = ()
        self._pending_end_session_warning = False
        self._active_power_message_box = None
        self._active_power_action_name: str | None = None
        self.monitor.snapshot_changed.connect(self._handle_snapshot)

    @property
    def current_drives(self) -> tuple[str, ...]:
        return self._current_drives

    def start(self) -> None:
        page = self._page()
        if page is not None:
            page.drive_open_requested.connect(self.open_drive)
            page.context_menu_requested.connect(self.show_context_menu)
        self.monitor.start()

    def shutdown(self) -> None:
        self._fresh_snapshot_callbacks.clear()
        self.monitor.stop()

    def apply_connected_drives_style(self) -> None:
        page = self._page()
        if page is not None:
            page.apply_drive_field_style()

    def refresh_status(self, drives=None) -> None:
        if drives is None:
            self.monitor.request_scan()
            return
        self._set_connected_drives(drives)

    def _set_connected_drives(self, drives) -> None:
        signature = self.policy.signature(drives)
        self._current_drives = signature
        self.window._overview_connected_drives = set(signature)
        page = self._page()
        if page is not None:
            page.set_connected_drives(signature)
        self._refresh_overview()

    def _handle_snapshot(self, changes: DriveChanges) -> None:
        self._set_connected_drives(changes.current)
        visible_changes = self.policy.notification_changes(
            changes,
            notifications_enabled=(
                self.state.get("usb_plug_notify_mode", "on") != "off"
            ),
            suppressed_removals=self._suppressed_removals,
        )
        self._show_change_notifications(visible_changes)

        message_box = self._active_power_message_box
        action_name = self._active_power_action_name
        if message_box is not None and action_name:
            self._update_power_action_message_box(
                message_box,
                action_name,
                changes.current,
            )

        callbacks, self._fresh_snapshot_callbacks = self._fresh_snapshot_callbacks, []
        for callback in callbacks:
            callback(changes.current)

    def _show_change_notifications(self, changes: DriveChanges) -> None:
        if changes.added:
            drive_label = "drive" if len(changes.added) == 1 else "drives"
            self.window._show_timed_message(
                self.window._message_box_icon("Information"),
                "Drive Connected",
                f"External {drive_label} connected:\n" + "\n".join(changes.added),
                **self._popup_options(),
            )
        if changes.removed:
            drive_label = "drive" if len(changes.removed) == 1 else "drives"
            self.window._show_timed_message(
                self.window._message_box_icon("Information"),
                "Drive Removed",
                f"External {drive_label} removed:\n" + "\n".join(changes.removed),
                **self._popup_options(),
            )

    def _popup_options(self) -> dict:
        return status_popup_options() | {
            "merge_group": "external_drive_changes",
            "merge_title": "External Drives",
            "replace_grouped_entries": True,
        }

    def open_drive(self, drive_path: str) -> None:
        if drive_path:
            self._run_with_optional_minimize(lambda: os.startfile(drive_path))

    def show_context_menu(self, pos) -> None:
        page = self._page()
        if page is None or not self._current_drives:
            return
        combo = page.drive_combo()
        menu = QMenu(combo)
        styles.apply_popup_menu_style(menu)
        actions = {}
        for drive_path in self._current_drives:
            action = menu.addAction(f"Safely Remove {drive_path}")
            actions[action] = drive_path
        selected_action = menu.exec(combo.mapToGlobal(pos))
        drive_path = actions.get(selected_action)
        if drive_path:
            self.safely_remove(drive_path)

    def safely_remove(self, drive_path: str) -> None:
        drive_name = drive_path[:2]
        try:
            self.drive_service.eject(drive_path)
        except DriveServiceError as exc:
            self.window._show_timed_message(
                QMessageBox.Icon.Warning,
                "Drive Removal",
                f"Could not safely remove {drive_name}.\n{exc}",
                **status_popup_options(),
            )
            return
        self.window._show_timed_message(
            QMessageBox.Icon.Information,
            "Drive Removal",
            f"Requested safe removal for {drive_name}.",
            **status_popup_options(),
        )
        QTimer.singleShot(1600, self.monitor.request_scan)
        drive_page = self._drive_space_page()
        if drive_page is not None:
            QTimer.singleShot(1500, drive_page.drive_space_list.clear)
            QTimer.singleShot(1600, drive_page.refresh_drives)

    def _request_fresh_snapshot(
        self,
        callback: Callable[[tuple[str, ...]], None],
    ) -> None:
        if not self.monitor.is_running:
            callback(self._synchronous_signature())
            return
        self._fresh_snapshot_callbacks.append(callback)
        self.monitor.request_scan()

    def _synchronous_signature(self) -> tuple[str, ...]:
        try:
            return external_drive_signature(self.drive_service)
        except Exception:
            return self._current_drives

    def _leave_reminder_enabled(self) -> bool:
        return bool(self.state.get("usb_idle_enabled", True))

    def _show_connected_drive_warning(self, title: str, body: str, on_close=None):
        return self.window._show_acknowledged_message(
            self.window._message_box_icon("NoIcon"),
            title,
            body,
            on_close=on_close,
            **reminder_popup_options(),
        )

    def handle_session_lock(self) -> None:
        self._request_fresh_snapshot(self._show_session_lock_warning)

    def _show_session_lock_warning(self, drives: tuple[str, ...]) -> None:
        if not self.policy.should_remind(self._leave_reminder_enabled(), drives):
            return
        drive_label, drive_lines = self.policy.format_connected_drives(drives)
        self._show_connected_drive_warning(
            "Session Locked With External Drive Connected",
            (
                f"The following external {drive_label} still connected:\n"
                f"{drive_lines}\n\n"
                "If you are stepping away, remove the drive first."
            ),
        )

    def block_end_session(self, action_name: str) -> bool:
        drives = self._synchronous_signature()
        if not self.policy.should_remind(self._leave_reminder_enabled(), drives):
            self._pending_end_session_warning = False
            return False
        if self._pending_end_session_warning:
            return True
        self._pending_end_session_warning = True
        drive_label, drive_lines = self.policy.format_connected_drives(drives)

        def clear_warning_state() -> None:
            self._pending_end_session_warning = False

        QTimer.singleShot(
            0,
            lambda: self._show_connected_drive_warning(
                f"{action_name} Blocked",
                (
                    f"{action_name} was blocked because the following external "
                    f"{drive_label} still connected:\n"
                    f"{drive_lines}\n\n"
                    "Remove the drive first, then try again if you still want to continue."
                ),
                on_close=clear_warning_state,
            ),
        )
        return True

    def confirm_power_action(self, action_name: str, action_callback) -> None:
        self._request_fresh_snapshot(
            lambda drives: self._begin_power_confirmation(
                action_name,
                action_callback,
                drives,
            )
        )

    def _begin_power_confirmation(
        self,
        action_name: str,
        action_callback,
        drives: tuple[str, ...],
    ) -> None:
        if getattr(
            self.window, "disable_all_confirmations_enabled", lambda: False
        )():
            action_callback()
            return
        if not self.policy.should_remind(self._leave_reminder_enabled(), drives):
            action_callback()
            return
        try:
            message_box = QMessageBox(self.window)
        except TypeError:
            return
        self.window._apply_message_box_icon(
            message_box,
            self.window._message_box_icon("NoIcon"),
        )
        for option, value in reminder_popup_options().items():
            setattr(message_box, f"_{option}", value)
        message_box.setStandardButtons(
            self.window._message_box_button("Yes")
            | self.window._message_box_button("Cancel")
        )
        message_box.setDefaultButton(self.window._message_box_button("Cancel"))
        message_box.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._suppressed_removals = drives
        self._active_power_message_box = message_box
        self._active_power_action_name = action_name
        self._update_power_action_message_box(message_box, action_name, drives)

        refresh_timer = QTimer(message_box)
        refresh_timer.setInterval(400)
        refresh_timer.timeout.connect(self.monitor.request_scan)
        refresh_timer.start()
        try:
            result = self.window._exec_message_box(message_box)
        finally:
            self._suppressed_removals = ()
            self._active_power_message_box = None
            self._active_power_action_name = None
        if result == self.window._message_box_button("Yes"):
            action_callback()

    def _update_power_action_message_box(
        self,
        message_box,
        action_name: str,
        drives: tuple[str, ...],
    ) -> bool:
        if drives:
            drive_label, drive_lines = self.policy.format_connected_drives(drives)
            title = f"{action_name} With External Drive Connected"
            body = (
                f"The following external {drive_label} still connected:\n"
                f"{drive_lines}\n\n"
                f"Do you want to continue with {action_name.lower()} anyway?"
            )
        else:
            title = f"{action_name} Ready"
            body = (
                "Drive removed.\n\n"
                f"Do you want to continue with {action_name.lower()}?"
            )
        message_box.setWindowTitle(title)
        message_box.setText(body)
        self.window._prepare_message_box_layout(message_box)
        self.window._apply_rounded_window_mask(message_box)
        return not drives

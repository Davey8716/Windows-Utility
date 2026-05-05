from right_utility_gui import get_drive_info
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMenu, QMessageBox


class ExternalDriveMixin:
    def _current_external_drives(self) -> set[str]:
        drives = set()
        for drive in get_drive_info():
            if drive.get("ejectable"):
                drives.add(str(drive["drive"]))
        return drives

    def _leave_drive_reminder_enabled(self) -> bool:
        return bool(self.state.get("usb_idle_enabled", True))

    def _connected_external_drive_signature(self) -> tuple[str, ...]:
        return tuple(sorted(self._current_external_drives()))

    def _format_external_drive_message(
        self,
        drives: tuple[str, ...],
    ) -> tuple[str, str]:
        drive_label = "drive is" if len(drives) == 1 else "drives are"
        drive_lines = "\n".join(drives)
        return drive_label, drive_lines

    def _refresh_connected_drive_status_label(self, drives=None):
        if not hasattr(self, "connected_drives_field"):
            return

        if drives is None:
            drives = tuple(sorted(self._current_external_drives()))
        elif not isinstance(drives, tuple):
            drives = tuple(sorted(drives))

        self.connected_drives_field.clear()
        if drives:
            self.connected_drives_field.addItems(list(drives))
            self.connected_drives_field.setCurrentIndex(0)
            self.connected_drives_field.setToolTip(
                "Connected drives:\n" + "\n".join(drives)
            )
        else:
            self.connected_drives_field.addItem("No Drives Connected")
            self.connected_drives_field.setCurrentIndex(0)
            self.connected_drives_field.setToolTip("No Drives Connected")

    def _show_connected_drives_context_menu(self, pos):
        if not hasattr(self, "connected_drives_field"):
            return

        drives = tuple(sorted(self._current_external_drives()))
        if not drives:
            return

        removal_handler = getattr(
            getattr(self, "right_tools_panel", None),
            "_safely_remove_drive",
            None,
        )
        if not callable(removal_handler):
            return

        menu = QMenu(self.connected_drives_field)
        actions = {}
        for drive_path in drives:
            action = menu.addAction(f"Safely Remove {drive_path}")
            actions[action] = drive_path

        selected_action = menu.exec(self.connected_drives_field.mapToGlobal(pos))
        drive_path = actions.get(selected_action)
        if drive_path:
            removal_handler(drive_path)

    def _show_connected_drive_warning(self, title: str, body: str, on_close=None):
        return self._show_acknowledged_message(
            self._message_box_icon("Warning"),
            title,
            body,
            on_close=on_close,
        )

    def _handle_session_lock_reminder(self):
        if not self._leave_drive_reminder_enabled():
            return

        current_signature = self._connected_external_drive_signature()
        if not current_signature:
            return

        drive_label, drive_lines = self._format_external_drive_message(
            current_signature
        )
        self._show_connected_drive_warning(
            "Session Locked With External Drive Connected",
            (
                f"The following external {drive_label} still connected:\n"
                f"{drive_lines}\n\n"
                "If you are stepping away, remove the drive first."
            ),
        )

    def _block_end_session_for_connected_drives(self, action_name: str) -> bool:
        if not self._leave_drive_reminder_enabled():
            self._pending_end_session_warning = False
            return False

        current_signature = self._connected_external_drive_signature()
        if not current_signature:
            self._pending_end_session_warning = False
            return False

        if self._pending_end_session_warning:
            return True

        self._pending_end_session_warning = True
        drive_label, drive_lines = self._format_external_drive_message(
            current_signature
        )

        def clear_warning_state():
            self._pending_end_session_warning = False

        QTimer.singleShot(
            0,
            lambda: self._show_connected_drive_warning(
                f"{action_name} Blocked",
                (
                    f"{action_name} was blocked because the following external {drive_label} still connected:\n"
                    f"{drive_lines}\n\n"
                    "Remove the drive first, then try again if you still want to continue."
                ),
                on_close=clear_warning_state,
            ),
        )
        return True

    def _confirm_power_action(self, action_name: str, action_callback):
        if not self._leave_drive_reminder_enabled():
            action_callback()
            return

        current_signature = self._connected_external_drive_signature()
        if not current_signature:
            action_callback()
            return

        drive_label, drive_lines = self._format_external_drive_message(
            current_signature
        )
        confirm_box = QMessageBox(self)
        confirm_box.setIcon(self._message_box_icon("Warning"))
        confirm_box.setWindowTitle(f"{action_name} With External Drive Connected")
        confirm_box.setText(
            (
                f"The following external {drive_label} still connected:\n"
                f"{drive_lines}\n\n"
                f"Do you want to continue with {action_name.lower()} anyway?"
            )
        )
        confirm_box.setStandardButtons(
            self._message_box_button("Yes") | self._message_box_button("Cancel")
        )
        confirm_box.setDefaultButton(self._message_box_button("Cancel"))
        confirm_box.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._set_borderless_message_box(
            confirm_box,
            stays_on_top=True,
            tool_window=True,
        )
        QTimer.singleShot(0, lambda: self._apply_rounded_window_mask(confirm_box))

        if confirm_box.exec() == self._message_box_button("Yes"):
            action_callback()

    def _check_external_drive_changes(self):
        current_drives = self._current_external_drives()
        self._refresh_connected_drive_status_label(current_drives)

        if self.state.get("usb_plug_notify_mode", "on") == "off":
            self._known_external_drives = current_drives
            return

        added_drives = sorted(current_drives - self._known_external_drives)
        removed_drives = sorted(self._known_external_drives - current_drives)
        self._known_external_drives = current_drives

        if added_drives:
            drive_label = "drive" if len(added_drives) == 1 else "drives"
            self._show_timed_message(
                self._message_box_icon("Information"),
                "Drive Connected",
                f"External {drive_label} connected:\n" + "\n".join(added_drives),
                timeout_ms=10_000,
            )

        if removed_drives:
            drive_label = "drive" if len(removed_drives) == 1 else "drives"
            self._show_timed_message(
                self._message_box_icon("Information"),
                "Drive Removed",
                f"External {drive_label} removed:\n" + "\n".join(removed_drives),
                timeout_ms=10_000,
            )

import os
from pathlib import Path

from resurface.ui import styles
from resurface.features.drives.drive_service import DriveServiceError
from PySide6.QtCore import QEvent, QModelIndex, QSize, Qt, QTimer
from PySide6.QtWidgets import QMenu, QMessageBox


class ExternalDriveMixin:
    USB_POPUP_ICON_SIZE = QSize(126, 126)

    def _usb_popup_icon_path(self) -> Path:
        return Path(__file__).resolve().parents[4] / "App Icons" / "Usb Icon.png"

    def eventFilter(self, watched, event):
        page = getattr(self, "external_drives_page", None)
        combo = page.drive_combo() if page is not None else None
        if combo is not None:
            popup_view = combo.view()
            popup_viewport = popup_view.viewport()
            if watched is popup_viewport:
                if event.type() == QEvent.Type.MouseButtonRelease:
                    if popup_view.indexAt(event.pos()).isValid():
                        return True
                if event.type() == QEvent.Type.MouseButtonDblClick:
                    index = popup_view.indexAt(event.pos())
                    if index.isValid():
                        self._open_connected_drive_from_index(index)
                        combo.hidePopup()
                        return True

        return super().eventFilter(watched, event)

    def _current_external_drives(self) -> set[str]:
        drives = set()
        for drive in self.drive_service.list_drives():
            if drive.ejectable:
                drives.add(drive.path)
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

    def _apply_connected_drives_field_style(self) -> None:
        page = getattr(self, "external_drives_page", None)
        if page is None:
            return
        page.apply_drive_field_style()

    def _refresh_connected_drive_status_label(self, drives=None):
        page = getattr(self, "external_drives_page", None)
        if page is None:
            return

        if drives is None:
            drives = tuple(sorted(self._current_external_drives()))
        elif not isinstance(drives, tuple):
            drives = tuple(sorted(drives))
        self._overview_connected_drives = set(drives)
        page.set_connected_drives(drives)
        refresh_overview = getattr(self, "refresh_overview", None)
        if refresh_overview is not None:
            refresh_overview()

    def _open_connected_drive_from_index(self, index: QModelIndex) -> None:
        page = getattr(self, "external_drives_page", None)
        if page is None or not index.isValid():
            return
        drive_path = page.drive_combo().itemData(index.row())
        if not drive_path:
            return

        minimize_and_run = getattr(self, "_run_with_optional_minimize", None)
        if callable(minimize_and_run):
            minimize_and_run(lambda: os.startfile(drive_path))
            return

        os.startfile(drive_path)

    def _show_connected_drives_context_menu(self, pos):
        page = getattr(self, "external_drives_page", None)
        if page is None:
            return
        combo = page.drive_combo()

        drives = tuple(sorted(self._current_external_drives()))
        if not drives:
            return

        menu = QMenu(combo)
        styles.apply_popup_menu_style(menu)
        actions = {}
        for drive_path in drives:
            action = menu.addAction(f"Safely Remove {drive_path}")
            actions[action] = drive_path

        selected_action = menu.exec(combo.mapToGlobal(pos))
        drive_path = actions.get(selected_action)
        if drive_path:
            self._safely_remove_external_drive(drive_path)

    def _safely_remove_external_drive(self, drive_path: str) -> None:
        drive_name = drive_path[:2]
        try:
            self.drive_service.eject(drive_path)
        except DriveServiceError as exc:
            self._show_timed_message(
                QMessageBox.Icon.Warning,
                "Drive Removal",
                f"Could not safely remove {drive_name}.\n{exc}",
            )
            return

        self._show_timed_message(
            QMessageBox.Icon.Information,
            "Drive Removal",
            f"Requested safe removal for {drive_name}.",
        )
        QTimer.singleShot(1600, self._refresh_connected_drive_status_label)
        drive_page = getattr(self, "drive_space_page", None)
        if drive_page is not None:
            QTimer.singleShot(1500, drive_page.drive_space_list.clear)
            QTimer.singleShot(1600, drive_page.refresh_drives)

    def _show_connected_drive_warning(self, title: str, body: str, on_close=None):
        return self._show_acknowledged_message(
            self._message_box_icon("NoIcon"),
            title,
            body,
            on_close=on_close,
            accessory_icon_path=self._usb_popup_icon_path(),
            accessory_icon_size=self.USB_POPUP_ICON_SIZE,
            minimum_popup_width=460,
            text_minimum_width=320,
            center_text_block=True,
            accessory_leading_spacer_width=34,
        )

    def _update_power_action_message_box(
        self,
        message_box: QMessageBox,
        action_name: str,
    ) -> bool:
        current_signature = self._connected_external_drive_signature()
        if current_signature:
            drive_label, drive_lines = self._format_external_drive_message(
                current_signature
            )
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
        self._prepare_message_box_layout(message_box)
        self._apply_rounded_window_mask(message_box)
        return not current_signature

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

        try:
            message_box = QMessageBox(self)
        except TypeError:
            return

        self._apply_message_box_icon(
            message_box,
            self._message_box_icon("NoIcon"),
        )
        message_box._accessory_icon_path = self._usb_popup_icon_path()
        message_box._accessory_icon_size = self.USB_POPUP_ICON_SIZE
        message_box._minimum_popup_width = 460
        message_box._text_minimum_width = 320
        message_box._center_text_block = True
        message_box._accessory_leading_spacer_width = 34
        message_box.setStandardButtons(
            self._message_box_button("Yes") | self._message_box_button("Cancel")
        )
        message_box.setDefaultButton(self._message_box_button("Cancel"))
        message_box.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._suppress_drive_change_popup_signature = current_signature
        self._update_power_action_message_box(message_box, action_name)

        refresh_timer = QTimer(message_box)
        refresh_timer.setInterval(400)
        refresh_timer.timeout.connect(
            lambda: self._update_power_action_message_box(message_box, action_name)
        )
        refresh_timer.start()

        try:
            result = self._exec_message_box(message_box)
        finally:
            self._suppress_drive_change_popup_signature = None

        if result == self._message_box_button("Yes"):
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
        suppressed_signature = getattr(
            self,
            "_suppress_drive_change_popup_signature",
            None,
        )
        if suppressed_signature:
            suppressed_drives = set(suppressed_signature)
            if removed_drives and set(removed_drives).issubset(suppressed_drives):
                removed_drives = []

        if added_drives:
            drive_label = "drive" if len(added_drives) == 1 else "drives"
            self._show_timed_message(
                self._message_box_icon("Information"),
                "Drive Connected",
                f"External {drive_label} connected:\n" + "\n".join(added_drives),
                timeout_ms=10_000,
                merge_group="external_drive_changes",
                merge_title="External Drives",
                accessory_icon_path=self._usb_popup_icon_path(),
                accessory_icon_size=self.USB_POPUP_ICON_SIZE,
                minimum_popup_width=460,
                text_minimum_width=320,
                center_text_block=True,
                accessory_leading_spacer_width=34,
                show_close_now_button=True,
                replace_grouped_entries=True,
            )

        if removed_drives:
            drive_label = "drive" if len(removed_drives) == 1 else "drives"
            self._show_timed_message(
                self._message_box_icon("Information"),
                "Drive Removed",
                f"External {drive_label} removed:\n" + "\n".join(removed_drives),
                timeout_ms=10_000,
                merge_group="external_drive_changes",
                merge_title="External Drives",
                accessory_icon_path=self._usb_popup_icon_path(),
                accessory_icon_size=self.USB_POPUP_ICON_SIZE,
                minimum_popup_width=460,
                text_minimum_width=320,
                center_text_block=True,
                accessory_leading_spacer_width=34,
                show_close_now_button=True,
                replace_grouped_entries=True,
            )

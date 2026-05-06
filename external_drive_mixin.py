import os

import styles
from PySide6.QtGui import QFont, QFontMetrics
from right_utility_gui import get_drive_info
from PySide6.QtCore import QEvent, QModelIndex, Qt, QTimer
from PySide6.QtWidgets import QMenu
from tooltips import format_tooltip_text


class ExternalDriveMixin:
    def eventFilter(self, watched, event):
        combo = getattr(self, "connected_drives_field", None)
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

    def _apply_connected_drives_field_style(self) -> None:
        combo = getattr(self, "connected_drives_field", None)
        if combo is None:
            return

        visible_text = ""
        current_text_getter = getattr(combo, "currentText", None)
        if callable(current_text_getter):
            visible_text = current_text_getter() or ""
        if not visible_text:
            placeholder_text_getter = getattr(combo, "placeholderText", None)
            if callable(placeholder_text_getter):
                visible_text = placeholder_text_getter() or ""

        combo_width = 0
        width_getter = getattr(combo, "width", None)
        if callable(width_getter):
            measured_width = width_getter()
            if isinstance(measured_width, (int, float)):
                combo_width = int(measured_width)

        chosen_font_size = 15
        chosen_font_family = "Segoe UI"
        if visible_text and combo_width > 0:
            text_width_limit = max(0, combo_width - 34)
            for candidate_family in ("Segoe UI", "Arial", "Consolas"):
                for candidate_size in (15, 14, 13, 12):
                    metrics = QFontMetrics(QFont(candidate_family, candidate_size))
                    if metrics.horizontalAdvance(visible_text) <= text_width_limit:
                        chosen_font_family = candidate_family
                        chosen_font_size = candidate_size
                        break
                else:
                    continue
                break
            else:
                chosen_font_size = 12
                chosen_font_family = "Arial"

        combo.setProperty("styleFontSize", chosen_font_size)
        combo.setProperty("styleFontFamily", chosen_font_family)
        combo.setStyleSheet(
            styles.connected_drives_combo_style(
                chosen_font_size,
                chosen_font_family,
            )
        )

    def _refresh_connected_drive_status_label(self, drives=None):
        if not hasattr(self, "connected_drives_field"):
            return

        if drives is None:
            drives = tuple(sorted(self._current_external_drives()))
        elif not isinstance(drives, tuple):
            drives = tuple(sorted(drives))

        self.connected_drives_field.clear()
        if drives:
            self.connected_drives_field.setPlaceholderText("")
            display_drives = [f"{drive} Connected" for drive in drives]
            for drive_path, display_text in zip(drives, display_drives):
                self.connected_drives_field.addItem(display_text, drive_path)
            self.connected_drives_field.setCurrentIndex(0)
            self.connected_drives_field.setToolTip(
                format_tooltip_text(
                    "Connected drives:\n" + "\n".join(display_drives)
                )
            )
        else:
            self.connected_drives_field.setPlaceholderText("No Drives Connected")
            self.connected_drives_field.setCurrentIndex(-1)
            self.connected_drives_field.setToolTip(
                format_tooltip_text("No Drives Connected")
            )

        self._apply_connected_drives_field_style()
        QTimer.singleShot(0, self._apply_connected_drives_field_style)

    def _open_connected_drive_from_index(self, index: QModelIndex) -> None:
        if not hasattr(self, "connected_drives_field") or not index.isValid():
            return

        drive_path = self.connected_drives_field.itemData(index.row())
        if not drive_path:
            return

        minimize_and_run = getattr(
            getattr(self, "right_tools_panel", None),
            "_minimize_and_run",
            None,
        )
        if callable(minimize_and_run):
            minimize_and_run(lambda: os.startfile(drive_path))
            return

        os.startfile(drive_path)

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
        if hasattr(menu, "setStyleSheet"):
            menu.setStyleSheet(styles.message_popup_menu_style())
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
            self._message_box_icon("NoIcon"),
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
        if self._show_modal_message(
            self._message_box_icon("NoIcon"),
            f"{action_name} With External Drive Connected",
            (
                f"The following external {drive_label} still connected:\n"
                f"{drive_lines}\n\n"
                f"Do you want to continue with {action_name.lower()} anyway?"
            ),
            self._message_box_button("Yes") | self._message_box_button("Cancel"),
            self._message_box_button("Cancel"),
        ) == self._message_box_button("Yes"):
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

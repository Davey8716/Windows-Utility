from __future__ import annotations

import ctypes
import os
from collections.abc import Callable

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from resurface.features.drives.drive_service import DriveService, DriveServiceError
from resurface.ui import styles
from resurface.ui.external_drive_popups import status_popup_options
from resurface.ui.tooltips import format_tooltip_text, tooltip_text


class DriveSpacePage(QWidget):
    TRACKED_WINDOW_BUTTON_REFRESH_MS = 1500
    CONTENT_WIDTH = styles.EXTERNAL_DRIVES_CONTENT_WIDTH
    CONTROL_WIDTH = styles.EXTERNAL_DRIVES_CONTROL_WIDTH

    def __init__(
        self,
        drive_service: DriveService,
        windows,
        register_tooltip: Callable,
        show_timed_message: Callable,
        run_with_optional_minimize: Callable,
        parent: QWidget | None = None,
        background_refresh=None,
    ):
        super().__init__(parent)
        self.drive_service = drive_service
        self.windows = windows
        self.register_tooltip = register_tooltip
        self.show_timed_message = show_timed_message
        self.run_with_optional_minimize = run_with_optional_minimize
        self._tracked_window_buttons: dict[str, dict[str, object]] = {}
        self.background_refresh = background_refresh
        self._tracked_window_button_refresh_timer = QTimer(self)
        self._tracked_window_button_refresh_timer.timeout.connect(self._refresh_tracked_window_button_labels)

        self.page_layout = QVBoxLayout(self)
        self.page_layout.setContentsMargins(0, 0, 0, 0)
        self.page_layout.setSpacing(16)
        self._build()

    @staticmethod
    def _shell_open(target: str, parameters: str | None = None):
        ctypes.windll.shell32.ShellExecuteW(None, "open", target, parameters, None, 1)

    def _build(self):
        button_row = QWidget()
        button_row.setProperty("centeredControlGrid", True)
        button_row.setFixedWidth(self.CONTENT_WIDTH)
        button_row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(styles.PAGE_CONTROL_GAP)

        self.btn_this_pc = self._tracked_button(
            "this_pc",
            "Open This PC",
            labels={"closed": "Open This PC", "open": "Close This PC", "minimized": "Focus This PC"},
            title_candidates=("This PC",),
            open_action=lambda: self.windows.open_or_focus_titles(
                ("This PC",), lambda: self._shell_open("explorer.exe", "shell:MyComputerFolder")
            ),
            tooltip_key="open_this_pc",
        )
        button_layout.addWidget(self.btn_this_pc)
        self.btn_storage_sense = self._tracked_button(
            "storage_sense",
            "Open Storage Sense",
            labels={"closed": "Open Storage Sense", "open": "Close Storage Sense", "minimized": "Focus Storage Sense"},
            title_candidates=("Settings",),
            open_action=lambda: self.windows.open_or_focus_titles(
                ("Settings",), lambda: self._shell_open("ms-settings:storagepolicies")
            ),
            tooltip_key="open_storage_sense",
        )
        button_layout.addWidget(self.btn_storage_sense)
        self.page_layout.addWidget(button_row, 0, Qt.AlignmentFlag.AlignHCenter)

        self.drive_space_list = QListWidget()
        self.drive_space_list.setFixedSize(self.CONTENT_WIDTH, 120)
        self.drive_space_list.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.drive_space_list.setSpacing(0)
        self.drive_space_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.drive_space_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.drive_space_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.drive_space_list.setWordWrap(False)
        self.drive_space_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.drive_space_list.setProperty("surfaceFieldStyle", True)
        self.apply_theme()
        self.drive_space_list.itemDoubleClicked.connect(self._open_drive_from_item)
        self.drive_space_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.drive_space_list.customContextMenuRequested.connect(self._show_drive_context_menu)
        self.page_layout.addWidget(self.drive_space_list, 0, Qt.AlignmentFlag.AlignHCenter)

        self._refresh_tracked_window_button_labels()
        self._tracked_window_button_refresh_timer.start(self.TRACKED_WINDOW_BUTTON_REFRESH_MS)
        self.refresh_drives()
        self.drive_refresh_timer = QTimer(self)
        self.drive_refresh_timer.timeout.connect(self.refresh_drives)
        self.drive_refresh_timer.start(10_000)

    def _tracked_button(self, key, text, *, labels, title_candidates, open_action, tooltip_key):
        button = QPushButton(text)
        styles.apply_page_control_size(
            button,
            width=self.CONTROL_WIDTH,
            role="external_drive",
        )
        button.setProperty("styleFontSize", 14)
        button.setStyleSheet(styles.button_text_style(14))
        self._install_green_flash(button)
        self._tracked_window_buttons[key] = {
            "button": button,
            "labels": dict(labels),
            "title_candidates": tuple(title_candidates),
            "open_action": open_action,
        }
        button.clicked.connect(lambda _checked=False, action_key=key: self._handle_tracked_window_button(action_key))
        self.register_tooltip(button, tooltip_text(tooltip_key))
        return button

    @staticmethod
    def _install_green_flash(button: QPushButton):
        def clear_flash():
            button.setProperty("flashActive", False)
            button.style().unpolish(button)
            button.style().polish(button)

        def flash_active():
            button.setProperty("flashActive", True)
            button.style().unpolish(button)
            button.style().polish(button)
            QTimer.singleShot(180, clear_flash)

        button.clicked.connect(flash_active)

    def apply_theme(self):
        self.drive_space_list.setStyleSheet(
            styles.frame_list_widget_style("Consolas", 15)
            + "QListWidget { padding: 6px; } QListWidget::item { padding: 0px; margin: 0px; }"
        )

    def refresh_drives(self):
        if self.background_refresh is not None:
            self.background_refresh.request_drive_scan()
            return
        self._render_drives(self.drive_service.list_drives())

    def _render_drives(self, drives):
        self.drive_space_list.clear()
        for drive in drives:
            value = drive.get if isinstance(drive, dict) else lambda name: getattr(drive, name)
            path = value("path")
            used_gb = value("used_bytes") / (1024 ** 3)
            total_gb = value("total_bytes") / (1024 ** 3)
            free_gb = value("free_bytes") / (1024 ** 3)
            item = QListWidgetItem(
                f"{path}  Used: {used_gb:.1f} GB  Free: {free_gb:.1f} GB  Total: {total_gb:.1f} GB"
            )
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setData(Qt.ItemDataRole.UserRole + 1, value("ejectable"))
            tooltip = f"Open {path} in File Explorer"
            if value("ejectable"):
                tooltip += "\nRight-click to safely remove this drive."
            item.setToolTip(format_tooltip_text(tooltip))
            item.setSizeHint(QSize(0, 20))
            self.drive_space_list.addItem(item)

    def _open_drive_from_item(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.run_with_optional_minimize(lambda: os.startfile(path))

    def _show_drive_context_menu(self, pos: QPoint):
        item = self.drive_space_list.itemAt(pos)
        if item is None or not item.data(Qt.ItemDataRole.UserRole + 1):
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        menu = QMenu(self.drive_space_list)
        styles.apply_popup_menu_style(menu, radius=styles.BUTTON_CORNER_RADIUS)
        remove_action = menu.addAction(f"Safely Remove {path}")
        if menu.exec(self.drive_space_list.mapToGlobal(pos)) is remove_action:
            self._safely_remove_drive(path)

    def _safely_remove_drive(self, path: str):
        drive_name = path[:2]
        try:
            self.drive_service.eject(path)
        except DriveServiceError as exc:
            self.show_timed_message(
                QMessageBox.Icon.Warning,
                "Drive Removal",
                f"Could not safely remove {drive_name}.\n{exc}",
                **status_popup_options(),
            )
            return
        self.show_timed_message(
            QMessageBox.Icon.Information,
            "Drive Removal",
            f"Requested safe removal for {drive_name}.",
            **status_popup_options(),
        )
        QTimer.singleShot(1500, self.drive_space_list.clear)
        QTimer.singleShot(1600, self.refresh_drives)

    def _refresh_tracked_window_button_labels(self):
        if self.background_refresh is not None:
            self.background_refresh.request_title_state_check({
                key: spec["title_candidates"]
                for key, spec in self._tracked_window_buttons.items()
            })
            return
        for key in self._tracked_window_buttons:
            self._refresh_tracked_window_button_label(key)

    def apply_tracked_window_states(self, states):
        for key, state in states.items():
            spec = self._tracked_window_buttons.get(key)
            if spec is not None:
                text = spec["labels"].get(state, spec["labels"]["closed"])
                if spec["button"].text() != text:
                    spec["button"].setText(text)

    def _refresh_tracked_window_button_label(self, key: str):
        spec = self._tracked_window_buttons.get(key)
        if spec is None:
            return
        state = self.windows.get_titles_state(spec["title_candidates"])
        text = spec["labels"].get(state, spec["labels"]["closed"])
        if spec["button"].text() != text:
            spec["button"].setText(text)

    def _handle_tracked_window_button(self, key: str):
        spec = self._tracked_window_buttons.get(key)
        if spec is None:
            return
        titles = spec["title_candidates"]
        state = self.windows.get_titles_state(titles)
        if state == "open":
            self.windows.close_titles(titles)
        elif state == "minimized":
            self.run_with_optional_minimize(lambda: self.windows.maximize_titles(titles))
        else:
            self.run_with_optional_minimize(spec["open_action"])
        self._refresh_tracked_window_button_label(key)
        QTimer.singleShot(350, self._refresh_tracked_window_button_labels)

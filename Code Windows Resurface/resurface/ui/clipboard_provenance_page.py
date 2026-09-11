"""User interface for locally stored clipboard provenance."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QToolButton, QVBoxLayout, QWidget

from resurface.features.clipboard_provenance import ClipboardProvenanceRepository, ClipboardProvenanceService
from resurface.ui import styles
from resurface.ui.app_notifications import WindowMessageMixin
from resurface.ui.monitor_rule_editor_dialog import style_button
from resurface.ui.opaque_rounded_frame import paint_opaque_rounded_frame


PANEL_WIDTH = 685


class ClipboardClearConfirmationDialog(QMessageBox):
    """Fixed-size, frameless clear-history confirmation matching Hover import."""

    FRAME_WIDTH = 2

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.CustomizeWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowTitleHint, False)
        self.setWindowFlag(Qt.WindowType.WindowSystemMenuHint, False)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setStyleSheet(styles.message_box_style(outer_frame=False))
        self.setIcon(QMessageBox.Icon.Question)
        self.setWindowTitle("Clear Clipboard Provenance")
        self.setText(
            "Clear the local Clipboard Provenance history?\n\n"
            "Exported backup files will not be removed."
        )
        self.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        self.setDefaultButton(QMessageBox.StandardButton.Cancel)
        self.setSizeGripEnabled(False)
        self.setFixedSize(self.sizeHint())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        paint_opaque_rounded_frame(
            self,
            radius=styles.BUTTON_CORNER_RADIUS,
            frame_width=self.FRAME_WIDTH,
        )


class ClipboardProvenancePage(WindowMessageMixin, QWidget):
    def __init__(
        self,
        parent,
        *,
        service: ClipboardProvenanceService,
        get_master_backup_dir: Callable[[], str],
        open_backup_folder: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ClipboardProvenancePage")
        self._service = service
        self._repository = ClipboardProvenanceRepository(get_master_backup_dir)
        self._open_backup_folder = open_backup_folder

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        self.panel = QFrame(self)
        self.panel.setObjectName("MonitorRulesEmptyState")
        self.panel.setFixedWidth(PANEL_WIDTH)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        controls = QHBoxLayout()
        self.recording_button = QPushButton(self.panel)
        self.export_button = QPushButton("Export History", self.panel)
        self.clear_button = QPushButton("Clear All", self.panel)
        for button in (self.recording_button, self.export_button, self.clear_button):
            style_button(button)
            controls.addWidget(button)
        layout.addLayout(controls)
        self.status_label = QLabel(self.panel)
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        self.history_layout = QVBoxLayout()
        self.history_layout.setSpacing(8)
        layout.addLayout(self.history_layout)
        root.addWidget(self.panel, 0, Qt.AlignmentFlag.AlignHCenter)

        self.recording_button.clicked.connect(lambda: self._service.set_enabled(not self._service.enabled))
        self.export_button.clicked.connect(self._export_history)
        self.clear_button.clicked.connect(self._clear_history)
        self._service.history_changed.connect(self._render_history)
        self._service.recording_changed.connect(self._sync_recording)
        self._sync_recording(self._service.enabled)
        self._render_history(self._service.history)

    def _sync_recording(self, enabled: bool) -> None:
        self.recording_button.setText("Recording: On" if enabled else "Recording: Off")
        self.recording_button.setToolTip(
            "Stop recording clipboard changes" if enabled else "Start recording clipboard changes"
        )

    def _clear_layout(self) -> None:
        while self.history_layout.count():
            item = self.history_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _render_history(self, history: list[dict]) -> None:
        self._clear_layout()
        try:
            has_export_changes = self._repository.has_export_changes(history)
        except (OSError, TypeError, ValueError):
            has_export_changes = True
        self.export_button.setEnabled(bool(history) and has_export_changes)
        self.clear_button.setEnabled(bool(history))
        self.status_label.setText(
            f"{len(history)} of 100 saved records. Recording is {'on' if self._service.enabled else 'off'}."
        )
        if not history:
            empty = QLabel("No clipboard provenance has been recorded yet.", self.panel)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.history_layout.addWidget(empty)
            return
        for record in reversed(history):
            self.history_layout.addWidget(self._record_card(record))

    def _record_card(self, record: dict) -> QFrame:
        card = QFrame(self.panel)
        card.setObjectName("ClipboardProvenanceRecordCard")
        card.setStyleSheet(styles.clipboard_provenance_record_card_style())
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        kind = "Copied files" if record.get("content_type") == "files" else "Copied text"
        timestamp = record.get("timestamp") or "Unknown time"
        heading = QLabel(f"{kind}  ·  {timestamp}", card)
        heading.setObjectName("MonitorRuleDetails")
        header = QHBoxLayout()
        header.addWidget(heading)
        header.addStretch(1)
        delete_button = QToolButton(card)
        delete_button.setText("×")
        delete_button.setAccessibleName("Delete clipboard provenance record")
        delete_button.setToolTip("Delete this provenance record")
        delete_button.setFixedSize(24, 24)
        delete_button.setStyleSheet(
            "QToolButton { border: none; background: transparent; font-size: 20px; }"
        )
        delete_button.clicked.connect(lambda _checked=False, value=record: self._service.delete(value["id"]))
        header.addWidget(delete_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        content = record.get("text") if record.get("content_type") == "text" else "\n".join(record.get("files", []))
        urls = [url for url in record.get("urls", []) if isinstance(url, str)]
        is_url_only = len(urls) == 1 and (content or "").strip().rstrip(".,;:!?)]}") == urls[0]
        if is_url_only:
            layout.addWidget(self._link_label(urls[0], card))
        else:
            content_row = QHBoxLayout()
            item = QLabel(content or "", card)
            item.setWordWrap(True)
            item.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            content_row.addWidget(item, 1)
            for url in urls:
                bullet = QLabel("•", card)
                content_row.addWidget(bullet, 0, Qt.AlignmentFlag.AlignTop)
                content_row.addWidget(self._link_label(url, card), 0, Qt.AlignmentFlag.AlignTop)
            layout.addLayout(content_row)
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        source_name = source.get("program_name") or "Unknown program"
        source_label = QLabel(f"Source program: {source_name}", card)
        source_label.setObjectName("MonitorRuleDetails")
        layout.addWidget(source_label)
        return card

    @staticmethod
    def _link_label(url: str, parent: QWidget) -> QLabel:
        color = styles.message_box_link_color().name()
        label = QLabel(
            f'<a href="{escape(url, quote=True)}" '
            f'style="color: {color}; text-decoration: underline;">{escape(url)}</a>',
            parent,
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        label.setOpenExternalLinks(False)
        label.setToolTip("Open this web link in your default browser")
        label.linkActivated.connect(lambda value: QDesktopServices.openUrl(QUrl(value)))
        return label

    def refresh_theme(self) -> None:
        """Rebuild rich-text links using the newly active theme color."""
        self._render_history(self._service.history)

    def _clear_history(self) -> None:
        if self.disable_all_confirmations_enabled():
            self._service.clear()
            return
        answer = ClipboardClearConfirmationDialog(self).exec()
        if answer == QMessageBox.StandardButton.Yes:
            self._service.clear()

    def _open_export_directory(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        if self._open_backup_folder is not None and self._open_backup_folder(str(directory)):
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _export_history(self) -> None:
        destination = self._repository.backup_directory()
        if destination is None:
            QMessageBox.warning(self, "Clipboard Provenance", "Set a Master Backup Path before exporting clipboard provenance.")
            return
        folder = destination / "Clipboard Provenance"
        color = styles.message_box_link_color().name()
        answer = self._show_modal_message(
            QMessageBox.Icon.NoIcon,
            "Export Clipboard Provenance",
            "Export Clipboard Provenance data to:<br>"
            f'<a href="open-export-destination" style="color: {color}; text-decoration: underline;">{escape(str(folder))}</a>',
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
            link_activated=lambda _link: self._open_export_directory(folder),
            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
        )
        if answer != QMessageBox.StandardButton.Save:
            return
        try:
            path = self._repository.export_history(self._service.history)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Clipboard Provenance", f"Could not export clipboard provenance:\n{exc}")
            return
        self._render_history(self._service.history)
        self._show_timed_message(
            QMessageBox.Icon.Information,
            "Clipboard Provenance Exported",
            f"Clipboard provenance was exported to:\n{path}",
            show_close_now_button=True,
            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
        )

from __future__ import annotations

import copy
from html import escape
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from resurface.features.monitor_rules import (
    BackupDirectoryNotConfiguredError,
    MonitorRulesRepository,
    enumerate_monitors,
    normalize_monitor_rules,
)
from resurface.ui import styles
from resurface.ui.app_notifications import WindowMessageMixin
from resurface.ui.monitor_rule_editor_dialog import (
    PLACEMENT_LABELS,
    MonitorRuleEditorDialog,
    StateIndicatorCheckBox,
    style_button as _style_button,
)


class MonitorRulesPage(WindowMessageMixin, QFrame):
    def __init__(
        self,
        parent,
        *,
        rules,
        app_hwnd,
        on_rules_changed,
        get_master_backup_dir=None,
        open_backup_folder: Callable[[str], bool] | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("MonitorRulesEmptyState")
        self._app_hwnd = app_hwnd
        self._on_rules_changed = on_rules_changed
        self._has_backup_destination = callable(get_master_backup_dir)
        self._repository = MonitorRulesRepository(get_master_backup_dir)
        self._open_backup_folder = open_backup_folder
        self.rules = normalize_monitor_rules(copy.deepcopy(rules))
        self._sort_ascending = True

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)
        action_grid = QGridLayout()
        # Inset the action controls within the panel.  Keeping this on the grid
        # (rather than changing its columns) preserves the existing alignment
        # and spacing of both rows of buttons.
        action_grid.setContentsMargins(12, 12, 12, 0)
        action_grid.setHorizontalSpacing(6)
        action_grid.setVerticalSpacing(root.spacing())
        summary = QLabel(
            "The first matching rule wins. Windows are placed at startup and when "
            "applications open, with 15 seconds of recovery. Rule changes also apply "
            "to affected open windows. Changes in the Add or Edit dialog apply only "
            "after Save, including full placement on the same monitor. "
            "Moves pause while the left mouse button is held. "
            "After recovery, manual moves are allowed unless Reapply if moved is enabled.",
            self,
        )
        summary.setWordWrap(True)
        summary.setStyleSheet(styles.page_description_style())
        root.addWidget(summary)
        self.add_button = QPushButton("Add Rule", self)
        self.add_button.setToolTip("Create an automatic application placement rule")
        self.alphabet_sort_button = QPushButton("A–Z", self)
        self.turn_off_all_button = QPushButton("Turn Off All", self)
        self.delete_all_button = QPushButton("Delete All", self)
        self.delete_all_button.setToolTip("Delete all monitor rules")

        self.alphabet_sort_button.setAccessibleName("Sort monitor rules alphabetically")
        self.alphabet_sort_button.setToolTip("Sort rules A to Z")
        _style_button(self.add_button)
        _style_button(self.turn_off_all_button)
        _style_button(self.delete_all_button)
        _style_button(self.alphabet_sort_button)
        self.add_button.clicked.connect(self._add_rule)
        self.turn_off_all_button.clicked.connect(self._toggle_all)
        self.delete_all_button.clicked.connect(self._delete_all_rules)
        self.alphabet_sort_button.clicked.connect(self._sort_alphabetically)
        action_grid.addWidget(self.alphabet_sort_button, 0, 0)
        action_grid.addWidget(self.add_button, 0, 1)
        action_grid.addWidget(self.turn_off_all_button, 0, 2)
        action_grid.addWidget(self.delete_all_button, 0, 3)
        self.export_rules_button = QPushButton("Export Rules", self)
        self.export_rules_button.setToolTip(
            "Export monitor rules to the Master Backup Path"
        )
        self.import_rules_button = QPushButton("Import Rules", self)
        self.import_rules_button.setToolTip(
            "Import monitor rules from a backup file"
        )
        _style_button(self.export_rules_button)
        _style_button(self.import_rules_button)
        self.export_rules_button.clicked.connect(self._export_rules)
        self.import_rules_button.clicked.connect(self._import_rules)
        action_grid.addWidget(self.export_rules_button, 1, 2)
        action_grid.addWidget(self.import_rules_button, 1, 3)
        minimum_column_width = max(
            button.sizeHint().width()
            for button in (
                self.alphabet_sort_button,
                self.add_button,
                self.turn_off_all_button,
                self.delete_all_button,
            )
        )
        for column in range(4):
            action_grid.setColumnMinimumWidth(column, minimum_column_width)
            action_grid.setColumnStretch(column, 1)
        root.addLayout(action_grid)

        self.rule_list = QWidget(self)
        self.rule_list_layout = QVBoxLayout(self.rule_list)
        self.rule_list_layout.setContentsMargins(0, 0, 0, 0)
        self.rule_list_layout.setSpacing(10)
        root.addWidget(self.rule_list)
        self._render_rules()

    def _available_devices(self) -> set[str]:
        try:
            return {item["device"].casefold() for item in enumerate_monitors()}
        except Exception:
            return set()

    def _clear_rule_widgets(self) -> None:
        while self.rule_list_layout.count():
            item = self.rule_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_rules(self) -> None:
        self._clear_rule_widgets()
        any_enabled = any(rule["enabled"] for rule in self.rules)
        self.turn_off_all_button.setEnabled(bool(self.rules))
        self.delete_all_button.setEnabled(bool(self.rules))
        self.export_rules_button.setEnabled(bool(self.rules))
        self.alphabet_sort_button.setEnabled(len(self.rules) > 1)
        self.turn_off_all_button.setText(
            "Turn Off All" if any_enabled else "Turn On All"
        )
        self.turn_off_all_button.setToolTip(
            "Disable all monitor rules" if any_enabled else "Enable all monitor rules"
        )
        if not self.rules:
            empty = QLabel(
                "No application monitor rules have been created or imported.",
                self.rule_list,
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            empty.setStyleSheet(styles.page_description_style())
            self.rule_list_layout.addWidget(empty)
            return

        available_devices = self._available_devices()
        for index, rule in enumerate(self.rules):
            card = QFrame(self.rule_list)
            card.setObjectName("MonitorRuleCard")
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(8)

            header = QHBoxLayout()
            enabled = StateIndicatorCheckBox(rule["name"], card)
            enabled.setChecked(rule["enabled"])
            enabled.setStyleSheet(styles.label_style(font_size=13, bold=True))
            enabled.toggled.connect(
                lambda checked, idx=index: self._set_enabled(idx, checked)
            )
            unavailable = rule["target_device"].casefold() not in available_devices
            if unavailable:
                status = QLabel("Target unavailable", card)
                status.setObjectName("MonitorRuleStatus")
                status.setStyleSheet(
                    styles.label_style(
                        font_size=11,
                        bold=True,
                        color=QColor(210, 70, 70),
                    )
                )
            header.addWidget(enabled, 1)
            if unavailable:
                header.addWidget(status)
            card_layout.addLayout(header)

            match_text = rule["executable_path"] if rule["match_exact_path"] else rule["executable_name"]
            filters = []
            if rule["title_contains"]:
                filters.append(f"title contains ‘{rule['title_contains']}’")
            if rule["class_name"]:
                filters.append(f"class {rule['class_name']}")
            # Keep each rule property on a stable line.  In the previous arrow-separated
            # sentence, a long executable path could wrap immediately before the
            # placement value, making (for example) "Maximize" look detached from its
            # rule and appear to move between cards when the rules were reordered.
            details = (
                f"Application: {match_text}\n"
                f"Target: {rule['target_label']}\n"
                f"Placement: {PLACEMENT_LABELS[rule['placement_mode']]}"
            )
            if filters:
                details += "\nFilters: " + ", ".join(filters)
            if rule["reapply_if_moved"]:
                details += "\nReapply if moved is enabled"
            detail_label = QLabel(details, card)
            detail_label.setObjectName("MonitorRuleDetails")
            detail_label.setWordWrap(True)
            detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            detail_label.setStyleSheet(styles.page_description_style())
            card_layout.addWidget(detail_label)

            actions = QHBoxLayout()
            for text, callback in (
                ("Edit", lambda _checked=False, idx=index: self._edit_rule(idx)),
                ("Delete", lambda _checked=False, idx=index: self._delete_rule(idx)),
                ("Move Up", lambda _checked=False, idx=index: self._move_rule(idx, -1)),
                ("Move Down", lambda _checked=False, idx=index: self._move_rule(idx, 1)),
            ):
                button = QPushButton(text, card)
                if text in {"Move Up", "Move Down"}:
                    button.setProperty("lightModeBlackDisabledText", True)
                _style_button(button)
                button.clicked.connect(callback)
                if text == "Move Up":
                    button.setEnabled(index > 0)
                elif text == "Move Down":
                    button.setEnabled(index < len(self.rules) - 1)
                actions.addWidget(button)
            actions.addStretch(1)
            card_layout.addLayout(actions)
            self.rule_list_layout.addWidget(card)

    def _commit(self, *, apply_rule_ids=None) -> None:
        self.rules = normalize_monitor_rules(self.rules)
        if apply_rule_ids is None:
            self._on_rules_changed(copy.deepcopy(self.rules))
        else:
            self._on_rules_changed(copy.deepcopy(self.rules), apply_rule_ids=apply_rule_ids)
        self._render_rules()

    def _add_rule(self) -> None:
        dialog = MonitorRuleEditorDialog(self, app_hwnd=self._app_hwnd)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.rules.append(dialog.result_rule())
            self._commit(apply_rule_ids={self.rules[-1]["id"]})

    def _edit_rule(self, index: int) -> None:
        dialog = MonitorRuleEditorDialog(
            self,
            rule=self.rules[index],
            app_hwnd=self._app_hwnd,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.rules[index] = dialog.result_rule()
            self._commit(apply_rule_ids={self.rules[index]["id"]})

    def _delete_rule(self, index: int) -> None:
        message_box = QMessageBox(self)
        message_box.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        message_box.setStyleSheet(styles.message_box_style())
        message_box.setIcon(QMessageBox.Icon.Question)
        message_box.setWindowTitle("Delete Monitor Rule")
        message_box.setText(f"Delete the rule ‘{self.rules[index]['name']}’?")
        message_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        message_box.setDefaultButton(QMessageBox.StandardButton.No)
        result = message_box.exec()
        if result == QMessageBox.StandardButton.Yes:
            self.rules.pop(index)
            self._commit()

    def _delete_all_rules(self) -> None:
        if not self.rules:
            return
        message_box = QMessageBox(self)
        message_box.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        message_box.setStyleSheet(styles.message_box_style())
        message_box.setIcon(QMessageBox.Icon.Question)
        message_box.setWindowTitle("Delete All Monitor Rules")
        message_box.setText(
            f"Delete all {len(self.rules)} monitor rules? This cannot be undone."
        )
        message_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        message_box.setDefaultButton(QMessageBox.StandardButton.No)
        if message_box.exec() == QMessageBox.StandardButton.Yes:
            if self._has_backup_destination and self._export_rules(
                safety_backup=True
            ) is None:
                return
            self.rules.clear()
            self._commit()

    def _backup_directory(self) -> Path | None:
        return self._repository.backup_directory()

    def _open_export_directory(self, destination: Path) -> None:
        try:
            destination.mkdir(parents=True, exist_ok=True)
            if self._open_backup_folder is not None:
                opened = self._open_backup_folder(str(destination))
            else:
                opened = QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(destination))
                )
        except Exception as exc:
            self._show_modal_message(
                QMessageBox.Icon.Critical,
                "Open export folder failed",
                f"The export folder could not be opened.\n\n{exc}",
                QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Ok,
            )
            return
        if not opened:
            self._show_modal_message(
                QMessageBox.Icon.Critical,
                "Open export folder failed",
                f"The export folder could not be opened.\n\n{destination}",
                QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Ok,
            )

    def _export_rules(self, _checked=False, *, safety_backup=False) -> Path | None:
        if not safety_backup:
            backup_dir = self._backup_directory()
            if backup_dir is None:
                QMessageBox.warning(
                    self,
                    "Monitor Rules",
                    "Set a Master Backup Path before exporting monitor rules.",
                )
                return None
            destination = backup_dir / "Monitor Rules"
            destination_text = escape(str(destination))
            link_color = styles.message_box_link_color().name()
            answer = self._show_modal_message(
                QMessageBox.Icon.NoIcon,
                "Export Monitor Rules",
                "Export Monitor Rules data to:<br>"
                f'<a href="open-export-destination" '
                f'style="color: {link_color}; text-decoration: underline;">'
                f"{destination_text}</a>",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
                link_activated=lambda _link: self._open_export_directory(destination),
            )
            if answer != QMessageBox.StandardButton.Save:
                return None
        try:
            path = self._repository.export_rules(
                self.rules, safety_backup=safety_backup
            )
        except BackupDirectoryNotConfiguredError as exc:
            QMessageBox.warning(
                self,
                "Monitor Rules",
                str(exc),
            )
            return None
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Monitor Rules",
                f"Could not export monitor rules:\n{exc}",
            )
            return None
        if not safety_backup:
            self._show_timed_message(
                QMessageBox.Icon.Information,
                "Monitor Rules Exported",
                f"Monitor rules were exported to:\n{path}",
                show_close_now_button=True,
            )
        return path

    def _import_rules(self) -> None:
        backup_dir = self._backup_directory()
        start_dir = str(backup_dir / "Monitor Rules") if backup_dir else ""
        dialog = QFileDialog(
            self,
            "Import Monitor Rules",
            start_dir,
            "Monitor rule backups (*.json);;All files (*)",
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
        try:
            imported = self._repository.import_rules(selected_files[0])
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Import Monitor Rules", str(exc))
            return

        if self.rules:
            choice = QMessageBox.question(
                self,
                "Import Monitor Rules",
                "Replace the current rules? Choose No to merge the backup instead.",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                return
            if choice == QMessageBox.StandardButton.No:
                by_id = {rule["id"]: rule for rule in self.rules}
                for rule in imported:
                    by_id[rule["id"]] = rule
                imported = list(by_id.values())
        self.rules = imported
        self._commit()

    def _move_rule(self, index: int, direction: int) -> None:
        target = index + direction
        if target < 0 or target >= len(self.rules):
            return
        self.rules[index], self.rules[target] = self.rules[target], self.rules[index]
        self._commit()

    def _sort_alphabetically(self) -> None:
        if len(self.rules) < 2:
            return
        self.rules.sort(
            key=lambda rule: rule["name"].casefold(),
            reverse=not self._sort_ascending,
        )
        self._sort_ascending = not self._sort_ascending
        self.alphabet_sort_button.setText("A–Z" if self._sort_ascending else "Z–A")
        self.alphabet_sort_button.setToolTip(
            "Sort rules A to Z" if self._sort_ascending else "Sort rules Z to A"
        )
        self._commit()

    def _set_enabled(self, index: int, enabled: bool) -> None:
        self.rules[index]["enabled"] = bool(enabled)
        self._commit()

    def _toggle_all(self) -> None:
        if not self.rules:
            return
        self.set_all_enabled(not any(rule["enabled"] for rule in self.rules))

    def set_all_enabled(self, enabled: bool) -> None:
        for rule in self.rules:
            rule["enabled"] = bool(enabled)
        self._commit()

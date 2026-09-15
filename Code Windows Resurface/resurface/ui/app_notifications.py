from pathlib import Path
from typing import Callable

from resurface.ui import styles
from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QWidget,
)


class WindowMessageMixin:
    def _confirmation_state(self) -> dict:
        """Find the application state for this widget or one of its parents."""
        widget = self
        while widget is not None:
            state = getattr(widget, "state", None)
            if isinstance(state, dict):
                return state
            parent = getattr(widget, "parent", lambda: None)()
            if parent is widget:
                break
            widget = parent
        return {}

    def disable_all_confirmations_enabled(self) -> bool:
        return bool(
            self._confirmation_state().get("disable_all_confirmations_enabled", False)
        )

    def _affirmative_confirmation_result(self, buttons):
        """Return the affirmative action when the policy suppresses a confirmation."""
        yes = self._message_box_button("Yes")
        save = self._message_box_button("Save")
        if not self.disable_all_confirmations_enabled():
            return None
        if buttons & yes:
            return yes
        if buttons & save:
            return save
        return None

    @staticmethod
    def _danger_symbol() -> QPixmap:
        pixmap = QPixmap(76, 76)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(
            QPen(
                QColor(205, 48, 48),
                9,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawLine(18, 18, 58, 58)
        painter.drawLine(58, 18, 18, 58)
        painter.end()
        return pixmap

    def confirm_disable_all_confirmations(self) -> bool:
        """Show the one-time danger prompt required before disabling safeguards."""
        message_box = QMessageBox(self)
        self._apply_message_box_icon(message_box, self._message_box_icon("NoIcon"))
        message_box.setIconPixmap(self._danger_symbol())
        message_box.setWindowTitle("Disable all confirmation dialogs?")
        message_box.setText(
            "Destructive actions, overwrites, resets,imports, and power\n or "
            "session actions will run immediately.\n"
            "Only enable this if you are certain you do not want any action\n "
            "confirmation dialogs."
        )
        message_box.setStandardButtons(self._message_box_button("Cancel"))
        danger_button = message_box.addButton(
            "Disable All Confirmations",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        danger_button.setObjectName("disableAllConfirmationsDangerButton")
        danger_button.setStyleSheet(
            "QPushButton { background-color: #c53030; color: white; "
            "border: 2px solid #f06a6a; border-radius: 8px; padding: 8px 14px; "
            "font-weight: bold; } "
            "QPushButton:hover, QPushButton:pressed { background-color: #9f2020; }"
        )
        message_box.setDefaultButton(self._message_box_button("Cancel"))
        message_box.setWindowModality(Qt.WindowModality.ApplicationModal)
        message_box.setMinimumWidth(570)
        message_box._text_block_width = 410
        message_box._center_text_block = True
        message_box._popup_corner_radius = 18
        self._exec_message_box(message_box)
        return message_box.clickedButton() is danger_button

    def _is_standard_message_box_icon(self, icon) -> bool:
        icon_namespace = getattr(QMessageBox, "Icon", QMessageBox)
        standard_icons = (
            getattr(icon_namespace, "NoIcon", None),
            getattr(icon_namespace, "Information", None),
            getattr(icon_namespace, "Question", None),
            getattr(icon_namespace, "Warning", None),
            getattr(icon_namespace, "Critical", None),
        )
        return icon in standard_icons

    def _get_grouped_timed_message_boxes(self) -> dict:
        grouped_boxes = getattr(self, "_grouped_timed_message_boxes", None)
        if isinstance(grouped_boxes, dict):
            return grouped_boxes

        grouped_boxes = {}
        self._grouped_timed_message_boxes = grouped_boxes
        return grouped_boxes

    def _get_active_message_boxes(self) -> list:
        active_boxes = getattr(self, "_active_message_boxes", None)
        if isinstance(active_boxes, list):
            return active_boxes

        active_boxes = []
        self._active_message_boxes = active_boxes
        return active_boxes

    def _apply_message_box_icon(self, message_box: QMessageBox, icon) -> None:
        if self._is_standard_message_box_icon(icon):
            message_box._suppress_standard_icon = True
            message_box.setIcon(self._message_box_icon("NoIcon"))
            message_box.setIconPixmap(QPixmap())
            return
        message_box._suppress_standard_icon = False
        message_box.setIcon(icon)

    def _compose_timed_message_text(
        self,
        text: str,
        timeout_seconds: int,
        timeout_verb: str = "close",
    ) -> str:
        return f"{text}\n\nThis message will {timeout_verb} in {timeout_seconds} seconds."

    def _refresh_grouped_timed_message(
        self,
        message_box: QMessageBox,
        *,
        title: str,
        timeout_ms: int,
    ) -> None:
        entries = getattr(message_box, "_grouped_entries", [])
        timeout_seconds = max(1, timeout_ms // 1000)
        body = "\n\n".join(
            f"{entry_title}\n{entry_text}" for entry_title, entry_text in entries
        )
        message_box.setWindowTitle(title)
        message_box.setText(
            self._compose_timed_message_text(
                body,
                timeout_seconds,
                getattr(message_box, "_timeout_verb", "close"),
            )
        )

    def _message_box_icon(self, name: str):
        icon_namespace = getattr(QMessageBox, "Icon", QMessageBox)
        return getattr(icon_namespace, name, None)

    def _message_box_button(self, name: str):
        button_namespace = getattr(QMessageBox, "StandardButton", QMessageBox)
        return getattr(button_namespace, name, 0)

    def _set_borderless_message_box(
        self,
        message_box: QMessageBox,
        *,
        stays_on_top: bool = False,
        tool_window: bool = False,
    ) -> QMessageBox:
        message_box.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        message_box.setWindowFlag(Qt.WindowType.CustomizeWindowHint, True)
        message_box.setWindowFlag(Qt.WindowType.WindowTitleHint, False)
        message_box.setWindowFlag(Qt.WindowType.WindowSystemMenuHint, False)
        message_box.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        message_box.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        message_box.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        message_box.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        message_box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, stays_on_top)
        message_box.setWindowFlag(Qt.WindowType.Tool, tool_window)
        popup_corner_radius = getattr(message_box, "_popup_corner_radius", None)
        message_box.setStyleSheet(
            styles.message_box_style(radius=popup_corner_radius)
        )
        return message_box

    def _prepare_message_box_layout(self, message_box: QMessageBox) -> None:
        self._suppress_message_box_icon_label(message_box)
        self._balance_message_box_text_padding(message_box)
        self._configure_message_box_links(message_box)
        self._apply_message_box_accessory(message_box)
        self._center_message_box_text_block(message_box)
        self._ensure_timed_close_button(message_box)
        self._center_message_box_buttons(message_box)
        fixed_popup_width = int(
            getattr(message_box, "_fixed_popup_width", 0)
        )
        if fixed_popup_width > 0:
            message_box.setFixedWidth(fixed_popup_width)

    def _configure_message_box_links(self, message_box: QMessageBox) -> None:
        link_activated = getattr(message_box, "_link_activated", None)
        if link_activated is None:
            return

        text_label = message_box.findChild(QLabel, "qt_msgbox_label")
        if text_label is None:
            return

        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        text_label.setOpenExternalLinks(False)
        palette = text_label.palette()
        link_color = styles.message_box_link_color()
        palette.setColor(QPalette.ColorRole.Link, link_color)
        palette.setColor(QPalette.ColorRole.LinkVisited, link_color)
        text_label.setPalette(palette)
        text_label.linkActivated.connect(link_activated)

    def _suppress_message_box_icon_label(self, message_box: QMessageBox) -> None:
        if not getattr(message_box, "_suppress_standard_icon", False):
            return

        layout = message_box.layout()
        if not isinstance(layout, QGridLayout):
            return

        for object_name in ("qt_msgboxex_icon_label", "qt_msgbox_icon_label"):
            icon_label = message_box.findChild(QLabel, object_name)
            if icon_label is None:
                continue
            layout.removeWidget(icon_label)
            icon_label.clear()
            icon_label.hide()

    def _ensure_timed_close_button(self, message_box: QMessageBox) -> None:
        if not getattr(message_box, "_show_close_now_button", False):
            return

        if getattr(message_box, "_close_now_button", None) is not None:
            return

        close_button = message_box.addButton(
            "Close now",
            QMessageBox.ButtonRole.AcceptRole,
        )
        message_box._close_now_button = close_button

    def _center_message_box_buttons(self, message_box: QMessageBox) -> None:
        button_box = message_box.findChild(QDialogButtonBox)
        if button_box is None:
            return

        button_box.setCenterButtons(True)
        layout = message_box.layout()
        if isinstance(layout, QGridLayout):
            index = layout.indexOf(button_box)
            if index >= 0:
                row, _, row_span, _ = layout.getItemPosition(index)
                layout.removeWidget(button_box)
                column_span = max(1, layout.columnCount())
                layout.addWidget(
                    button_box,
                    row,
                    0,
                    row_span,
                    column_span,
                    Qt.AlignmentFlag.AlignHCenter,
                )

    def _balance_message_box_text_padding(
        self,
        message_box: QMessageBox,
        padding: int = 16,
    ) -> None:
        layout = message_box.layout()
        if not isinstance(layout, QGridLayout):
            return

        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setHorizontalSpacing(0)

        text_label = message_box.findChild(QLabel, "qt_msgbox_label")
        if text_label is None:
            return

        text_block_width = getattr(message_box, "_text_block_width", None)
        if text_block_width is not None:
            text_label.setWordWrap(True)
            text_label.setFixedWidth(int(text_block_width))
            text_label.setMinimumHeight(
                text_label.heightForWidth(int(text_block_width))
            )
            text_label.updateGeometry()

        index = layout.indexOf(text_label)
        if index < 0:
            return

        row, _, row_span, _ = layout.getItemPosition(index)
        layout.removeWidget(text_label)
        text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        column_span = max(1, layout.columnCount())
        layout.addWidget(
            text_label,
            row,
            0,
            row_span,
            column_span,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

    def _center_message_box_text_block(self, message_box: QMessageBox) -> None:
        if not getattr(message_box, "_center_text_block", False):
            return

        text_label = message_box.findChild(QLabel, "qt_msgbox_label")
        if text_label is None:
            return

        text_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )

    def _apply_message_box_accessory(self, message_box: QMessageBox) -> None:
        accessory_path = getattr(message_box, "_accessory_icon_path", None)
        if not accessory_path:
            return

        layout = message_box.layout()
        if not isinstance(layout, QGridLayout):
            return

        text_label = message_box.findChild(QLabel, "qt_msgbox_label")
        if text_label is None:
            return

        accessory_label = getattr(message_box, "_accessory_icon_label", None)
        if accessory_label is None:
            accessory_label = QLabel(message_box)
            accessory_label.setObjectName("message_box_accessory_icon")
            accessory_label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            message_box._accessory_icon_label = accessory_label

        pixmap = QPixmap(str(accessory_path))
        if pixmap.isNull():
            return

        icon_size = getattr(message_box, "_accessory_icon_size", QSize(42, 42))
        scaled_pixmap = pixmap.scaled(
            icon_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        accessory_label.setPixmap(scaled_pixmap)
        accessory_label.setFixedSize(icon_size)

        text_label.setWordWrap(True)
        text_label.setMinimumWidth(
            max(
                int(getattr(message_box, "_text_minimum_width", 0)),
                text_label.minimumWidth(),
            )
        )

        leading_spacer_width = int(
            getattr(message_box, "_accessory_leading_spacer_width", 0)
        )

        text_index = layout.indexOf(text_label)
        if text_index < 0:
            return

        text_row, _, text_row_span, _ = layout.getItemPosition(text_index)
        layout.removeWidget(text_label)
        if leading_spacer_width > 0:
            layout.setColumnMinimumWidth(0, leading_spacer_width)
            layout.setColumnStretch(0, 0)
        else:
            layout.setColumnMinimumWidth(0, 0)
        layout.addWidget(
            text_label,
            text_row,
            1 if leading_spacer_width > 0 else 0,
            text_row_span,
            1,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        accessory_index = layout.indexOf(accessory_label)
        if accessory_index >= 0:
            layout.removeWidget(accessory_label)
        layout.addWidget(
            accessory_label,
            text_row,
            2 if leading_spacer_width > 0 else 1,
            text_row_span,
            1,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        minimum_width = int(getattr(message_box, "_minimum_popup_width", 0))
        if minimum_width > 0:
            message_box.setMinimumWidth(minimum_width)

    def _apply_rounded_window_mask(
        self,
        widget: QWidget,
        radius: int | None = None,
    ) -> None:
        configured_radius = getattr(widget, "_popup_corner_radius", None)
        if configured_radius is not None:
            radius = int(configured_radius)
        elif radius is None:
            radius = int(getattr(styles, "POPUP_CORNER_RADIUS", 0))
        if radius <= 0:
            widget.clearMask()
            return
        rect = QRectF(widget.rect())
        if rect.isEmpty():
            return
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        widget.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _exec_message_box(
        self,
        message_box: QMessageBox,
        *,
        stays_on_top: bool = True,
        tool_window: bool = True,
    ) -> int:
        self._set_borderless_message_box(
            message_box,
            stays_on_top=stays_on_top,
            tool_window=tool_window,
        )
        self._prepare_message_box_layout(message_box)
        QTimer.singleShot(0, lambda: self._apply_rounded_window_mask(message_box))
        return message_box.exec()

    def _show_modal_message(
        self,
        icon,
        title: str,
        text: str,
        buttons,
        default_button,
        *,
        stays_on_top: bool = True,
        tool_window: bool = True,
        accessory_icon_path: str | Path | None = None,
        accessory_icon_size: QSize | None = None,
        minimum_popup_width: int | None = None,
        text_minimum_width: int | None = None,
        text_block_width: int | None = None,
        fixed_popup_width: int | None = None,
        center_text_block: bool = False,
        accessory_leading_spacer_width: int | None = None,
        popup_corner_radius: int | None = None,
        link_activated: Callable[[str], None] | None = None,
    ) -> int:
        suppressed_result = self._affirmative_confirmation_result(buttons)
        if suppressed_result is not None:
            return suppressed_result
        try:
            message_box = QMessageBox(self)
        except TypeError:
            return self._message_box_button("Cancel")
        self._apply_message_box_icon(message_box, icon)
        message_box.setWindowTitle(title)
        message_box._link_activated = link_activated
        if link_activated is not None:
            message_box.setTextFormat(Qt.TextFormat.RichText)
        message_box.setText(text)
        if accessory_icon_path:
            message_box._accessory_icon_path = Path(accessory_icon_path)
            message_box._accessory_icon_size = accessory_icon_size or QSize(42, 42)
            message_box._minimum_popup_width = minimum_popup_width or 420
            message_box._text_minimum_width = text_minimum_width or 280
        if fixed_popup_width is not None:
            fixed_popup_width = int(fixed_popup_width)
            message_box._fixed_popup_width = fixed_popup_width
            if text_block_width is None:
                # The standard frameless popup uses 16 px on either side.
                text_block_width = max(0, fixed_popup_width - 32)
        message_box._text_block_width = text_block_width
        message_box._center_text_block = center_text_block
        message_box._show_close_now_button = False
        message_box._popup_corner_radius = popup_corner_radius
        if accessory_leading_spacer_width:
            message_box._accessory_leading_spacer_width = accessory_leading_spacer_width
        message_box.setStandardButtons(buttons)
        message_box.setDefaultButton(default_button)
        message_box.setWindowModality(Qt.WindowModality.ApplicationModal)
        return self._exec_message_box(
            message_box,
            stays_on_top=stays_on_top,
            tool_window=tool_window,
        )

    def _show_timed_message(
        self,
        icon,
        title: str,
        text: str,
        timeout_ms: int = 10_000,
        merge_group: str | None = None,
        merge_title: str | None = None,
        accessory_icon_path: str | Path | None = None,
        accessory_icon_size: QSize | None = None,
        minimum_popup_width: int | None = None,
        text_minimum_width: int | None = None,
        text_block_width: int | None = None,
        fixed_popup_width: int | None = None,
        center_text_block: bool = False,
        accessory_leading_spacer_width: int | None = None,
        show_close_now_button: bool = False,
        replace_grouped_entries: bool = False,
        popup_corner_radius: int | None = None,
        timeout_verb: str = "close",
    ) -> QMessageBox:
        timeout_seconds = max(1, timeout_ms // 1000)
        grouped_boxes = self._get_grouped_timed_message_boxes()
        if merge_group:
            active_grouped_box = grouped_boxes.get(merge_group)
            if active_grouped_box is not None:
                if replace_grouped_entries:
                    active_grouped_box._grouped_entries = [(title, text)]
                else:
                    active_grouped_box._grouped_entries.append((title, text))
                if accessory_icon_path:
                    active_grouped_box._accessory_icon_path = Path(accessory_icon_path)
                    active_grouped_box._accessory_icon_size = (
                        accessory_icon_size or QSize(42, 42)
                    )
                    active_grouped_box._minimum_popup_width = (
                        minimum_popup_width or 420
                    )
                    active_grouped_box._text_minimum_width = (
                        text_minimum_width or 280
                    )
                    if accessory_leading_spacer_width:
                        active_grouped_box._accessory_leading_spacer_width = (
                            accessory_leading_spacer_width
                        )
                self._apply_message_box_icon(active_grouped_box, icon)
                active_grouped_box._timeout_verb = timeout_verb
                self._refresh_grouped_timed_message(
                    active_grouped_box,
                    title=merge_title or title,
                    timeout_ms=timeout_ms,
                )
                self._apply_message_box_accessory(active_grouped_box)
                self._center_message_box_text_block(active_grouped_box)
                # Rebuild the action row after the text/accessory grid changes.
                # This keeps the timed close button centered across the complete
                # popup, rather than a stale subset of its columns.
                active_grouped_box._show_close_now_button = show_close_now_button
                self._ensure_timed_close_button(active_grouped_box)
                self._center_message_box_buttons(active_grouped_box)
                if popup_corner_radius is not None:
                    active_grouped_box._popup_corner_radius = popup_corner_radius
                active_grouped_box.adjustSize()
                close_timer = getattr(active_grouped_box, "_close_timer", None)
                if close_timer is not None:
                    close_timer.start(timeout_ms)
                active_grouped_box.show()
                active_grouped_box.raise_()
                active_grouped_box.activateWindow()
                QTimer.singleShot(
                    0,
                    lambda box=active_grouped_box: self._apply_rounded_window_mask(box),
                )
                return active_grouped_box
        try:
            message_box = QMessageBox(self)
        except TypeError:
            return None
        self._apply_message_box_icon(message_box, icon)
        message_box.setWindowTitle(title)
        if merge_group:
            message_box._grouped_entries = [(title, text)]
            self._refresh_grouped_timed_message(
                message_box,
                title=merge_title or title,
                timeout_ms=timeout_ms,
            )
        else:
            message_box.setText(
                self._compose_timed_message_text(text, timeout_seconds, timeout_verb)
            )
        if accessory_icon_path:
            message_box._accessory_icon_path = Path(accessory_icon_path)
            message_box._accessory_icon_size = accessory_icon_size or QSize(42, 42)
            message_box._minimum_popup_width = minimum_popup_width or 420
            message_box._text_minimum_width = text_minimum_width or 280
        if fixed_popup_width is not None:
            fixed_popup_width = int(fixed_popup_width)
            message_box._fixed_popup_width = fixed_popup_width
            if text_block_width is None:
                # Timed QMessageBoxes reserve 18 px beyond the standard side padding.
                text_block_width = max(0, fixed_popup_width - 50)
        message_box._text_block_width = text_block_width
        message_box._center_text_block = center_text_block
        message_box._show_close_now_button = show_close_now_button
        message_box._popup_corner_radius = popup_corner_radius
        message_box._timeout_verb = timeout_verb
        if accessory_leading_spacer_width:
            message_box._accessory_leading_spacer_width = accessory_leading_spacer_width
        message_box.setStandardButtons(self._message_box_button("NoButton"))
        message_box.setModal(False)
        self._set_borderless_message_box(
            message_box,
            stays_on_top=True,
            tool_window=True,
        )
        self._prepare_message_box_layout(message_box)
        self._get_active_message_boxes().append(message_box)
        close_timer = QTimer(message_box)
        close_timer.setSingleShot(True)
        message_box._close_timer = close_timer

        def cleanup_message_box():
            active_boxes = self._get_active_message_boxes()
            if message_box in active_boxes:
                active_boxes.remove(message_box)
            if merge_group:
                if grouped_boxes.get(merge_group) is message_box:
                    grouped_boxes.pop(merge_group, None)
            message_box.deleteLater()

        message_box.finished.connect(lambda _: cleanup_message_box())
        close_timer.timeout.connect(message_box.accept)
        if merge_group:
            grouped_boxes[merge_group] = message_box
        message_box.show()
        fixed_popup_width = int(getattr(message_box, "_fixed_popup_width", 0))
        if fixed_popup_width > 0:
            layout = message_box.layout()
            if isinstance(layout, QLayout):
                layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            message_box.setMinimumWidth(0)
            message_box.setMaximumWidth(16_777_215)
            message_box.setFixedWidth(fixed_popup_width)
            layout.activate()
            message_box.adjustSize()
        self._apply_rounded_window_mask(message_box)
        close_timer.start(timeout_ms)
        return message_box

    def _show_acknowledged_message(
        self,
        icon,
        title: str,
        text: str,
        on_close=None,
        accessory_icon_path: str | Path | None = None,
        accessory_icon_size: QSize | None = None,
        minimum_popup_width: int | None = None,
        text_minimum_width: int | None = None,
        center_text_block: bool = False,
        accessory_leading_spacer_width: int | None = None,
        popup_corner_radius: int | None = None,
    ) -> QMessageBox:
        try:
            message_box = QMessageBox(self)
        except TypeError:
            if on_close:
                on_close()
            return None
        self._apply_message_box_icon(message_box, icon)
        message_box.setWindowTitle(title)
        message_box.setText(text)
        if accessory_icon_path:
            message_box._accessory_icon_path = Path(accessory_icon_path)
            message_box._accessory_icon_size = accessory_icon_size or QSize(42, 42)
            message_box._minimum_popup_width = minimum_popup_width or 420
            message_box._text_minimum_width = text_minimum_width or 280
        message_box._center_text_block = center_text_block
        message_box._show_close_now_button = False
        message_box._popup_corner_radius = popup_corner_radius
        if accessory_leading_spacer_width:
            message_box._accessory_leading_spacer_width = accessory_leading_spacer_width
        message_box.setStandardButtons(self._message_box_button("Ok"))
        message_box.setWindowModality(Qt.WindowModality.NonModal)
        self._set_borderless_message_box(
            message_box,
            stays_on_top=True,
            tool_window=True,
        )
        self._prepare_message_box_layout(message_box)
        message_box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        message_box.setModal(False)
        self._get_active_message_boxes().append(message_box)

        def cleanup_message_box():
            active_boxes = self._get_active_message_boxes()
            if message_box in active_boxes:
                active_boxes.remove(message_box)
            if on_close:
                on_close()
            message_box.deleteLater()

        message_box.finished.connect(lambda _: cleanup_message_box())
        message_box.show()
        self._apply_rounded_window_mask(message_box)
        message_box.raise_()
        message_box.activateWindow()
        return message_box

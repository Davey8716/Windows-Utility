from pathlib import Path
from typing import Callable

import styles
from hotkeys import ACTION_LABELS, hotkey_to_display, normalize_hotkey
from state_manager import save_state
from tooltips import left_section_toggle_tooltip, tooltip_text
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class LeftPanelBuilder:
    LEFT_CONTROL_COLUMN_WIDTH = styles.PAGE_CONTROL_WIDTH
    RIGHT_CONTROL_COLUMN_WIDTH = styles.PAGE_CONTROL_WIDTH
    CONTROL_COLUMN_GAP = styles.PAGE_CONTROL_GAP
    CONTROL_ROW_WIDTH = (
        LEFT_CONTROL_COLUMN_WIDTH + CONTROL_COLUMN_GAP + RIGHT_CONTROL_COLUMN_WIDTH
    )
    EXTERNAL_DRIVE_CONTROL_WIDTH = styles.EXTERNAL_DRIVES_CONTROL_WIDTH
    EXTERNAL_DRIVE_ROW_WIDTH = styles.EXTERNAL_DRIVES_CONTENT_WIDTH

    def __init__(self, app):
        self.app = app
        self.state = app.state
        self.master_btn = None

    @property
    def icons_root(self) -> Path:
        return Path(__file__).resolve().parent.parent / "App Icons"

    def build(self) -> None:
        self.master_btn = getattr(self.app, "master_collapse_btn_left", None)
        self.app.left_sections = []
        self.app.master_toggle_left_state = bool(
            self.state.get("master_toggle_left", True)
        )

        self._build_user_interface_section()
        self._build_screen_mover_section()
        self._build_drive_reminder_section()
        self._build_organising_utilities_section()
        self._build_folder_utilities_section()
        self._build_recycle_bin_section()

        self.app.main_layout.addStretch(1)
        if self.master_btn is not None:
            self._wire_master_toggle()

    def _add_left_section_spacer(self, height: int):
        self.app.main_layout.addSpacing(height)
        return self.app.main_layout.itemAt(self.app.main_layout.count() - 1).spacerItem()

    def _register_left_section(
        self,
        section: QWidget,
        *,
        top_spacer,
        expanded_spacer_height: int,
    ) -> None:
        section.top_spacer = top_spacer
        section.expanded_spacer_height = expanded_spacer_height
        self.app.left_sections.append(section)
        self.app._sync_left_section_spacing(section)

    def _attach_left_section(
        self,
        section: QWidget,
        *,
        expanded_spacer_height: int,
    ) -> None:
        top_spacer = self._add_left_section_spacer(expanded_spacer_height)
        self.app.main_layout.addWidget(section)
        self._register_left_section(
            section,
            top_spacer=top_spacer,
            expanded_spacer_height=expanded_spacer_height,
        )

    def _make_section(self, title_text: str, section_id: str):
        app = self.app
        section = QWidget(app.main_frame)
        section.section_id = section_id
        section.setFixedWidth(app.MAIN_SECTION_OUTER_WIDTH)
        section.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(section)
        section.section_layout = layout
        layout.setContentsMargins(
            app.MAIN_SECTION_SIDE_PADDING,
            app.LEFT_SECTION_TOP_MARGIN,
            app.MAIN_SECTION_SIDE_PADDING,
            app.LEFT_SECTION_BOTTOM_MARGIN,
        )
        layout.setSpacing(4)

        sec_header = QWidget(section)
        sec_header.setMaximumWidth(app.LEFT_SECTION_VISIBLE_FRAME_WIDTH)
        sec_header.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        sec_header_layout = QHBoxLayout(sec_header)
        sec_header_layout.setContentsMargins(0, 0, app.LEFT_TOGGLE_RIGHT_INSET, 0)

        sec_title = QLabel(title_text, sec_header)
        sec_title.setStyleSheet(styles.label_style(font_size=15))

        toggle = QToolButton(sec_header)
        toggle.setCursor(Qt.CursorShape.ArrowCursor)
        toggle.setArrowType(Qt.ArrowType.NoArrow)
        toggle.setText(styles.arrow_glyph(Qt.ArrowType.DownArrow))
        toggle.setStyleSheet(
            styles.section_toggle_style(
                styles.theme_text_color(),
                styles.SURFACE_DARK,
            )
        )
        section_toggle_slot_width, section_toggle_slot_height = (
            styles.section_toggle_slot_size()
        )
        toggle.setFixedSize(section_toggle_slot_width, section_toggle_slot_height)
        section.toggle_btn = toggle
        app.register_tooltip(toggle, left_section_toggle_tooltip(title_text))

        title_spacer = QWidget(sec_header)
        title_spacer.setFixedSize(section_toggle_slot_width, section_toggle_slot_height)

        sec_header_layout.addWidget(title_spacer)
        sec_header_layout.addStretch()
        sec_header_layout.addWidget(sec_title)
        sec_header_layout.addStretch()
        sec_header_layout.addWidget(toggle)

        frame = QFrame(section)
        section.frame = frame
        frame.setObjectName("CollapsibleSectionFrame")
        frame.setMaximumWidth(app.LEFT_SECTION_VISIBLE_FRAME_WIDTH)
        frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        frame.setStyleSheet(styles.LEFT_PANEL_FRAME_STYLE)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(2, 2, 2, 2)
        frame_layout.setSpacing(0)

        section.content = QWidget(frame)
        content = section.content
        content.setMaximumWidth(app.LEFT_SECTION_VISIBLE_FRAME_WIDTH - 4)
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        initial_open = (
            True
            if getattr(app, "sidebar_navigation_mode", False)
            else app.state.get("left_section_states", {}).get(section_id, True)
        )
        section.is_open = bool(initial_open)
        content.setVisible(initial_open)
        frame.setVisible(initial_open)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 10)

        layout.addWidget(sec_header)
        frame_layout.addWidget(content)
        layout.addWidget(frame)

        def toggle_section():
            app._set_left_section_open(section, not bool(section.is_open))
            app.save_all_settings()

        toggle.clicked.connect(toggle_section)
        toggle.setText(
            styles.arrow_glyph(
                Qt.ArrowType.DownArrow if initial_open else Qt.ArrowType.UpArrow
            )
        )

        return section, content_layout

    def _make_toggle_button(self, text: str, checked: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(button)
        button.setProperty("styleFontSize", 14)
        button.setStyleSheet(styles.toggle_button_style(font_size=14))
        return button

    def _make_compact_toggle_button(
        self,
        text: str,
        checked: bool = False,
        *,
        width: int,
        font_size: int = 11,
    ) -> QPushButton:
        button = self._make_toggle_button(text, checked)
        styles.apply_page_control_size(button, width=width, role="compact")
        button.setProperty("styleFontSize", font_size)
        button.setStyleSheet(styles.toggle_button_style(font_size=font_size))
        return button

    def _make_two_column_control_row(self) -> tuple[QWidget, QGridLayout]:
        row = QWidget()
        row.setProperty("centeredControlGrid", True)
        row.setFixedWidth(self.CONTROL_ROW_WIDTH)
        row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QGridLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(self.CONTROL_COLUMN_GAP)
        layout.setVerticalSpacing(0)
        layout.setColumnMinimumWidth(0, self.LEFT_CONTROL_COLUMN_WIDTH)
        layout.setColumnMinimumWidth(1, self.RIGHT_CONTROL_COLUMN_WIDTH)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        return row, layout

    def _add_two_column_control_row(
        self,
        parent_layout: QVBoxLayout,
        left_widget: QWidget,
        right_widget: QWidget,
    ) -> QWidget:
        row, row_layout = self._make_two_column_control_row()
        if left_widget.property("pageControlRole") != "wide":
            left_widget.setFixedWidth(self.LEFT_CONTROL_COLUMN_WIDTH)
        if right_widget.property("pageControlRole") != "wide":
            right_widget.setFixedWidth(self.RIGHT_CONTROL_COLUMN_WIDTH)
        left_width = left_widget.width()
        right_width = right_widget.width()
        row.setFixedWidth(left_width + self.CONTROL_COLUMN_GAP + right_width)
        row_layout.setColumnMinimumWidth(0, left_width)
        row_layout.setColumnMinimumWidth(1, right_width)
        row_layout.addWidget(left_widget, 0, 0)
        row_layout.addWidget(right_widget, 0, 1)
        parent_layout.addWidget(row, 0, Qt.AlignmentFlag.AlignHCenter)
        return row

    def _bind_toggle_state_text(
        self,
        button: QPushButton,
        label: str,
        *,
        on_text: str = "On",
        off_text: str = "Off",
    ) -> None:
        def update_text(checked: bool) -> None:
            button.setText(f"{label} {on_text}" if checked else f"{label} {off_text}")

        update_text(button.isChecked())
        button.toggled.connect(update_text)

    def _bind_toggle_state_icon(
        self,
        button: QPushButton,
        *,
        checked_icon_path: Path,
        unchecked_icon_path: Path,
        icon_size: int = 18,
    ) -> None:
        checked_icon = QIcon(str(checked_icon_path))
        unchecked_icon = QIcon(str(unchecked_icon_path))
        button.setIconSize(QSize(icon_size, icon_size))

        def update_icon(checked: bool) -> None:
            button.setIcon(checked_icon if checked else unchecked_icon)

        update_icon(button.isChecked())
        button.toggled.connect(update_icon)

    def _bind_toggle_state_text_with_checked_icon(
        self,
        button: QPushButton,
        label: str,
        *,
        checked_icon_path: Path,
        checked_text: str = "",
        unchecked_text: str = "Off",
        icon_size: int = 18,
    ) -> None:
        checked_icon = QIcon(str(checked_icon_path))
        button.setIconSize(QSize(icon_size, icon_size))

        def update_state(checked: bool) -> None:
            if checked:
                button.setText(f"{label} {checked_text}".rstrip())
                button.setIcon(checked_icon)
            else:
                button.setText(f"{label} {unchecked_text}")
                button.setIcon(QIcon())

        update_state(button.isChecked())
        button.toggled.connect(update_state)

    def _coerce_icon(self, icon_source: Path | QIcon) -> QIcon:
        return icon_source if isinstance(icon_source, QIcon) else QIcon(str(icon_source))

    def _bind_toggle_icon_only(
        self,
        button: QPushButton,
        *,
        checked_icon_source: Path | QIcon,
        unchecked_icon_source: Path | QIcon,
        icon_size: int = 18,
    ) -> None:
        checked_icon = self._coerce_icon(checked_icon_source)
        unchecked_icon = self._coerce_icon(unchecked_icon_source)
        button.setIconSize(QSize(icon_size, icon_size))

        def update_state(checked: bool) -> None:
            button.setText("")
            button.setIcon(checked_icon if checked else unchecked_icon)

        update_state(button.isChecked())
        button.toggled.connect(update_state)

    def _create_theme_toggle_icon(self, mode: str, icon_size: int = 18) -> QIcon:
        pixmap = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if mode == "dark":
            moon_color = QColor(191, 205, 224)
            cutout_color = QColor(0, 0, 0, 0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(moon_color)
            painter.drawEllipse(3, 2, icon_size - 6, icon_size - 6)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.setBrush(cutout_color)
            painter.drawEllipse(7, 2, icon_size - 6, icon_size - 6)
        else:
            sun_color = QColor(0, 0, 0)
            pen = QPen(sun_color)
            pen.setWidth(2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(sun_color)

            center = icon_size / 2
            ray_inner = 6
            ray_outer = 8
            painter.drawEllipse(5, 5, icon_size - 10, icon_size - 10)
            painter.drawLine(int(center), ray_outer - 6, int(center), ray_outer - 2)
            painter.drawLine(int(center), icon_size - (ray_outer - 6), int(center), icon_size - (ray_outer - 2))
            painter.drawLine(ray_outer - 6, int(center), ray_outer - 2, int(center))
            painter.drawLine(icon_size - (ray_outer - 6), int(center), icon_size - (ray_outer - 2), int(center))
            painter.drawLine(ray_inner - 2, ray_inner - 2, ray_outer - 1, ray_outer - 1)
            painter.drawLine(icon_size - (ray_inner - 2), ray_inner - 2, icon_size - (ray_outer - 1), ray_outer - 1)
            painter.drawLine(ray_inner - 2, icon_size - (ray_inner - 2), ray_outer - 1, icon_size - (ray_outer - 1))
            painter.drawLine(
                icon_size - (ray_inner - 2),
                icon_size - (ray_inner - 2),
                icon_size - (ray_outer - 1),
                icon_size - (ray_outer - 1),
            )

        painter.end()
        return QIcon(pixmap)

    def _bind_combo_placeholder_icon(
        self,
        combo: QComboBox,
        *,
        placeholder: str,
        icon_path: Path,
        icon_size: int = 18,
    ) -> None:
        combo.setIconSize(QSize(icon_size, icon_size))
        placeholder_index = combo.findText(placeholder)
        if placeholder_index >= 0:
            combo.setItemIcon(placeholder_index, QIcon(str(icon_path)))

    def _install_green_flash(self, button: QPushButton) -> QPushButton:
        def flash_active():
            button.setProperty("flashActive", True)
            button.style().unpolish(button)
            button.style().polish(button)
            QTimer.singleShot(180, clear_flash)

        def clear_flash():
            button.setProperty("flashActive", False)
            button.style().unpolish(button)
            button.style().polish(button)

        button.clicked.connect(flash_active)
        return button

    def _style_organizing_button(self, button: QPushButton) -> QPushButton:
        button.setCheckable(False)
        button.setAutoExclusive(False)
        button.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(button)
        button.setProperty("styleFontSize", 14)
        button.setStyleSheet(styles.organizing_button_style(font_size=14))
        self._install_green_flash(button)
        return button

    def _make_action_dropdown(
        self,
        placeholder: str,
        actions_map: dict[str, Callable[[], None]],
        *,
        power_action_style: bool = False,
        severity_map: dict[str, str] | None = None,
    ) -> QComboBox:
        combo = QComboBox()
        combo.addItem(placeholder)
        combo.addItems(actions_map.keys())
        combo.setCurrentText(placeholder)
        combo.view().setRowHidden(0, True)
        combo.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(combo)
        combo.setProperty("styleFontSize", 14)
        if power_action_style:
            combo.setProperty("powerActionStyle", True)
            combo.setProperty("powerActionPlaceholder", placeholder)
            combo.setProperty("powerActionSeverityMap", severity_map or {})
            self.app._apply_power_action_dropdown_style(combo)
        else:
            combo.setStyleSheet(styles.organizing_combo_style(14))
        styles.fit_page_combo_width(
            combo,
            placeholder=placeholder,
            font_size=14,
        )

        def run_action(text: str):
            if text == placeholder:
                return
            action = actions_map.get(text)
            if action:
                action()
            combo.setCurrentText(placeholder)

        combo.currentTextChanged.connect(run_action)
        return combo

    def _make_value_dropdown(self, values: list[str], current_value: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(values)
        combo.setCurrentText(current_value if current_value in values else values[0])
        combo.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(combo)
        combo.setProperty("styleFontSize", 14)
        combo.setStyleSheet(styles.organizing_combo_style(14))
        styles.fit_page_combo_width(combo, font_size=14)
        return combo

    def _build_user_interface_section(self) -> None:
        app = self.app
        state = self.state
        ui_section, ui_layout = self._make_section("User Interface", "user_interface")
        self._attach_left_section(
            ui_section,
            expanded_spacer_height=app.USER_INTERFACE_TOP_SPACER,
        )

        compact_toggle_width = (
            self.LEFT_CONTROL_COLUMN_WIDTH - self.CONTROL_COLUMN_GAP
        ) // 2

        ui_top_row, ui_top_row_layout = self._make_two_column_control_row()
        compact_toggle_slot = QWidget(ui_top_row)
        compact_toggle_slot.setFixedWidth(self.LEFT_CONTROL_COLUMN_WIDTH)
        compact_toggle_slot_layout = QHBoxLayout(compact_toggle_slot)
        compact_toggle_slot_layout.setContentsMargins(0, 0, 0, 0)
        compact_toggle_slot_layout.setSpacing(self.CONTROL_COLUMN_GAP)
        ui_layout.addWidget(ui_top_row)

        dark_mode_btn = self._make_compact_toggle_button(
            "",
            state.get("theme_dark", True),
            width=compact_toggle_width,
            font_size=10,
        )
        self._bind_toggle_icon_only(
            dark_mode_btn,
            checked_icon_source=self._create_theme_toggle_icon("dark"),
            unchecked_icon_source=self._create_theme_toggle_icon("light"),
            icon_size=18,
        )
        compact_toggle_slot_layout.addWidget(dark_mode_btn)
        app.register_tooltip(dark_mode_btn, tooltip_text("dark_mode"))

        desktop_zen_mode_enabled = bool(state.get("desktop_zen_mode_enabled", False))
        current_icons_visible = app.actions.desktop_icons_visible()
        if current_icons_visible is not None:
            desktop_zen_mode_enabled = not current_icons_visible
            state["desktop_zen_mode_enabled"] = desktop_zen_mode_enabled
            save_state(state)

        desktop_zen_btn = self._make_compact_toggle_button(
            "Zen Mode",
            desktop_zen_mode_enabled,
            width=compact_toggle_width,
            font_size=10,
        )
        app.desktop_zen_btn = desktop_zen_btn
        self._bind_toggle_state_text_with_checked_icon(
            desktop_zen_btn,
            "Zen Mode",
            checked_icon_path=self.icons_root / "Zen Mode On.png",
            unchecked_text="Off",
            icon_size=18,
        )
        compact_toggle_slot_layout.addWidget(desktop_zen_btn)
        app.register_tooltip(desktop_zen_btn, tooltip_text("desktop_zen_mode"))

        power_dropdown = self._make_action_dropdown(
            " Power and Session ",
            {
                "Lock PC": lambda: app._confirm_power_action(
                    "Lock PC", app.right_tools_panel.run_lock_pc
                ),
                "Sleep": lambda: app._confirm_power_action(
                    "Sleep", app.right_tools_panel.run_sleep
                ),
                "Log out": lambda: app._confirm_power_action(
                    "Log out", app.right_tools_panel.run_logout
                ),
                "Restart": lambda: app._confirm_power_action(
                    "Restart", app.right_tools_panel.run_restart
                ),
                "Shutdown": lambda: app._confirm_power_action(
                    "Shutdown", app.right_tools_panel.run_shutdown
                ),
            },
            power_action_style=True,
            severity_map={
                "Lock PC": "blue",
                "Sleep": "yellow",
                "Restart": "orange_red",
                "Log out": "orange",
                "Shutdown": "red",
            },
        )
        ui_top_row_layout.addWidget(compact_toggle_slot, 0, 0)
        ui_top_row_layout.addWidget(power_dropdown, 0, 1)
        app.register_tooltip(power_dropdown, tooltip_text("power_options"))

        always_on_top_btn = self._make_toggle_button(
            "Always on Top",
            state.get("main_always_on_top_enabled", True),
        )
        self._bind_toggle_state_text(always_on_top_btn, "Always on Top")
        app.register_tooltip(always_on_top_btn, tooltip_text("always_on_top"))

        tooltips_btn = self._make_toggle_button(
            "Tooltips",
            state.get("tooltips_enabled", True),
        )
        self._bind_toggle_state_text(tooltips_btn, "Tooltips")
        app.register_tooltip(tooltips_btn, tooltip_text("enable_tooltips"))
        self._add_two_column_control_row(ui_layout, always_on_top_btn, tooltips_btn)

        maximize_all_enabled = bool(
            state.get(
                "maximize_all_enabled",
                not state.get("minimize_all_enabled", False),
            )
        )
        max_all_btn = self._make_toggle_button("Maximize All", maximize_all_enabled)
        self._bind_toggle_state_text(max_all_btn, "Maximize All")
        app.register_tooltip(max_all_btn, tooltip_text("maximize_all"))

        minimize_after_use_btn = self._make_toggle_button(
            "Minimize After Use",
            bool(state.get("minimize_after_use_enabled", True)),
        )
        self._bind_toggle_state_text(
            minimize_after_use_btn,
            "Minimize After Use",
            on_text="On",
            off_text="Off",
        )
        minimize_after_use_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        app.register_tooltip(
            minimize_after_use_btn,
            tooltip_text("minimize_after_use"),
        )
        self._add_two_column_control_row(
            ui_layout,
            max_all_btn,
            minimize_after_use_btn,
        )

        def on_dark_mode_changed(checked: bool):
            state["theme_dark"] = checked
            app.apply_theme(checked)
            save_state(state)

        dark_mode_btn.toggled.connect(on_dark_mode_changed)

        def on_always_on_top_changed(checked):
            app._set_main_window_topmost_state(checked)
            state["main_always_on_top_enabled"] = checked
            save_state(state)

        always_on_top_btn.toggled.connect(on_always_on_top_changed)

        def on_tooltips_changed(checked):
            state["tooltips_enabled"] = checked
            app.actions.tooltips_toggle(checked)
            save_state(state)

        tooltips_btn.toggled.connect(on_tooltips_changed)

        def on_max_all_changed(checked: bool):
            state["maximize_all_enabled"] = checked
            state.pop("minimize_all_enabled", None)
            save_state(state)

            if hasattr(app.actions, "maximize_all_toggle"):
                app.actions.maximize_all_toggle(checked)
            elif hasattr(app.actions, "minimize_all_toggle"):
                app.actions.minimize_all_toggle(checked)
            elif hasattr(app.actions, "maximize_all"):
                app.actions.maximize_all(checked)
            elif hasattr(app.actions, "minimize_all"):
                app.actions.minimize_all(checked)

        max_all_btn.toggled.connect(on_max_all_changed)

        def on_minimize_after_use_changed(checked: bool):
            state["minimize_after_use_enabled"] = checked
            save_state(state)

        minimize_after_use_btn.toggled.connect(on_minimize_after_use_changed)

        def on_desktop_zen_mode_changed(checked: bool):
            state["desktop_zen_mode_enabled"] = checked

            if app.actions.desktop_zen_mode_toggle(checked) is not None:
                save_state(state)
                if checked and getattr(app, "tray_manager", None):
                    app._minimize_self_if_configured()
                return

            desktop_zen_btn.blockSignals(True)
            desktop_zen_btn.setChecked(not checked)
            desktop_zen_btn.blockSignals(False)
            state["desktop_zen_mode_enabled"] = not checked
            save_state(state)
            app._show_timed_message(
                QMessageBox.Icon.Warning,
                "Desktop Icons",
                "Could not change desktop icon visibility.",
            )

        desktop_zen_btn.toggled.connect(on_desktop_zen_mode_changed)

    def _build_screen_mover_section(self) -> None:
        app = self.app
        state = self.state
        screen_section, screen_layout = self._make_section("Screen Mover", "screen_mover")

        screen_row = QWidget(screen_section.content)
        screen_row.setProperty("centeredControlGrid", True)
        screen_row.setFixedWidth(self.CONTROL_ROW_WIDTH)
        screen_row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        screen_row_layout = QHBoxLayout(screen_row)
        screen_row_layout.setContentsMargins(0, 0, 0, 0)
        screen_row_layout.setSpacing(self.CONTROL_COLUMN_GAP)
        screen_layout.addWidget(screen_row, 0, Qt.AlignmentFlag.AlignHCenter)

        screen_mover_enabled_btn = self._make_toggle_button(
            "Screen Mover",
            state.get("title_bar_dock_enabled", True),
        )
        self._bind_toggle_state_text(screen_mover_enabled_btn, "Screen Mover")
        screen_row_layout.addWidget(screen_mover_enabled_btn)
        app.screen_mover_enabled_btn = screen_mover_enabled_btn
        app.register_tooltip(
            screen_mover_enabled_btn,
            tooltip_text("screen_mover_enabled"),
        )

        screen_mover_enabled_btn.toggled.connect(app.set_screen_mover_enabled)

        screen_move_button_combo = QComboBox()
        screen_move_button_combo.addItem("Move Button: Off", "off")
        screen_move_button_combo.addItem("Left Mouse Button", "left")
        screen_move_button_combo.addItem("Middle Mouse Button", "middle")
        screen_move_button_combo.addItem("Right Mouse Button", "right")
        screen_move_button_combo.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(screen_move_button_combo)
        screen_move_button_combo.setProperty("styleFontSize", 14)
        screen_move_button_combo.setStyleSheet(styles.organizing_combo_style(14))
        app.screen_move_button_combo = screen_move_button_combo

        aligned_screen_mover_widgets = [screen_row]

        def sync_screen_mover_control_widths() -> None:
            styles.fit_page_combo_width(
                screen_move_button_combo,
                placeholder=screen_move_button_combo.currentText(),
                font_size=14,
            )
            aligned_width = (
                screen_mover_enabled_btn.width()
                + self.CONTROL_COLUMN_GAP
                + screen_move_button_combo.width()
            )
            for widget in aligned_screen_mover_widgets:
                widget.setFixedWidth(aligned_width)

        app._sync_screen_mover_control_widths = sync_screen_mover_control_widths

        def update_screen_move_combo_state() -> None:
            sync_screen_mover_control_widths()
            screen_move_button_combo.setProperty(
                "persistPressed",
                screen_move_button_combo.currentData() != "off",
            )
            screen_move_button_combo.style().unpolish(screen_move_button_combo)
            screen_move_button_combo.style().polish(screen_move_button_combo)

        stored_move_button = (
            str(state.get("screen_mover_activation_button", "")).strip().lower()
        )
        if stored_move_button not in {"left", "middle", "right", "off"}:
            stored_move_button = (
                "middle" if state.get("mmb_activation_enabled", True) else "off"
            )
        combo_index = screen_move_button_combo.findData(stored_move_button)
        if combo_index >= 0:
            screen_move_button_combo.setCurrentIndex(combo_index)
        update_screen_move_combo_state()

        screen_row_layout.addWidget(screen_move_button_combo)
        app.register_tooltip(
            screen_move_button_combo,
            tooltip_text("screen_move_button"),
        )

        def on_screen_move_button_changed(_text: str):
            button_value = screen_move_button_combo.currentData()
            state["screen_mover_activation_button"] = button_value
            state["mmb_activation_enabled"] = button_value == "middle"
            save_state(state)
            app.apply_screen_mover_settings()
            update_screen_move_combo_state()

        screen_move_button_combo.currentTextChanged.connect(
            on_screen_move_button_changed
        )

        shortcuts_header = QWidget(screen_section.content)
        shortcuts_header.setProperty("centeredControlGrid", True)
        shortcuts_header.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        shortcuts_header_layout = QHBoxLayout(shortcuts_header)
        shortcuts_header_layout.setContentsMargins(0, 0, 0, 0)

        shortcut_title = QLabel("Keyboard Shortcuts", shortcuts_header)
        shortcut_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        shortcut_title.setStyleSheet(styles.label_style(font_size=14))

        shortcut_toggle = QToolButton(shortcuts_header)
        shortcut_toggle.setCursor(Qt.CursorShape.ArrowCursor)
        shortcut_toggle.setArrowType(Qt.ArrowType.NoArrow)
        shortcut_toggle.setStyleSheet(
            styles.section_toggle_style(
                styles.theme_text_color(),
                styles.SURFACE_DARK,
            )
        )
        section_toggle_slot_width, section_toggle_slot_height = (
            styles.section_toggle_slot_size()
        )
        shortcut_toggle.setFixedSize(
            section_toggle_slot_width,
            section_toggle_slot_height,
        )
        app.register_tooltip(
            shortcut_toggle,
            tooltip_text("screen_mover_hotkeys_toggle"),
        )

        shortcut_title_spacer = QWidget(shortcuts_header)
        shortcut_title_spacer.setFixedSize(
            section_toggle_slot_width,
            section_toggle_slot_height,
        )
        shortcuts_header_layout.addWidget(shortcut_title_spacer)
        shortcuts_header_layout.addStretch()
        shortcuts_header_layout.addWidget(shortcut_title)
        shortcuts_header_layout.addStretch()
        shortcuts_header_layout.addWidget(shortcut_toggle)
        screen_layout.addWidget(
            shortcuts_header,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        shortcuts_container = QWidget(screen_section.content)
        shortcuts_container.setProperty("centeredControlGrid", True)
        shortcuts_container.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        shortcuts_layout = QVBoxLayout(shortcuts_container)
        shortcuts_layout.setContentsMargins(0, 0, 0, 0)
        shortcuts_layout.setSpacing(6)
        screen_layout.addWidget(
            shortcuts_container,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        aligned_screen_mover_widgets.extend(
            (shortcuts_header, shortcuts_container)
        )
        sync_screen_mover_control_widths()
        app.screen_mover_controls_row = screen_row
        app.screen_mover_shortcuts_header = shortcuts_header
        app.screen_mover_shortcuts_container = shortcuts_container
        app.screen_mover_shortcuts_toggle_btn = shortcut_toggle

        def set_shortcuts_open(is_open: bool, *, persist: bool = True) -> None:
            is_open = bool(is_open)
            state["screen_mover_keyboard_shortcuts_open"] = is_open
            shortcuts_container.setVisible(is_open)
            shortcut_toggle.setText(
                styles.arrow_glyph(
                    Qt.ArrowType.DownArrow if is_open else Qt.ArrowType.UpArrow
                )
            )
            app._update_main_scrollbar_policy()
            if persist:
                app.save_all_settings()

        initial_shortcuts_open = bool(
            state.get("screen_mover_keyboard_shortcuts_open", True)
        )
        set_shortcuts_open(initial_shortcuts_open, persist=False)

        def toggle_shortcuts() -> None:
            set_shortcuts_open(
                not bool(state.get("screen_mover_keyboard_shortcuts_open", True))
            )

        shortcut_toggle.clicked.connect(toggle_shortcuts)

        shortcut_grid = QGridLayout()
        shortcut_grid.setContentsMargins(0, 0, 0, 0)
        shortcut_grid.setHorizontalSpacing(self.CONTROL_COLUMN_GAP)
        shortcut_grid.setVerticalSpacing(6)
        shortcut_grid.setColumnStretch(1, 1)
        shortcuts_layout.addLayout(shortcut_grid)

        hotkey_values = state.get("screen_mover_keyboard_hotkeys", {})
        if not isinstance(hotkey_values, dict):
            hotkey_values = {}
            state["screen_mover_keyboard_hotkeys"] = hotkey_values

        app.screen_mover_hotkey_edits = {}

        def save_hotkey(action: str, edit: QKeySequenceEdit) -> None:
            portable_text = edit.keySequence().toString(
                QKeySequence.SequenceFormat.PortableText
            )
            normalized = normalize_hotkey(portable_text)
            state.setdefault("screen_mover_keyboard_hotkeys", {})[
                action
            ] = normalized

            display_text = hotkey_to_display(normalized)
            if (
                edit.keySequence().toString(
                    QKeySequence.SequenceFormat.PortableText
                )
                != display_text
            ):
                edit.blockSignals(True)
                edit.setKeySequence(QKeySequence(display_text))
                edit.blockSignals(False)

            save_state(state)
            app.apply_screen_mover_settings()
            QTimer.singleShot(0, edit.clearFocus)

        def clear_hotkey(action: str, edit: QKeySequenceEdit) -> None:
            state.setdefault("screen_mover_keyboard_hotkeys", {})[action] = ""
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
            save_state(state)
            app.apply_screen_mover_settings()

        shortcut_labels = []
        for row, (action, label_text) in enumerate(ACTION_LABELS.items()):
            label = QLabel(label_text, shortcuts_container)
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            label.setStyleSheet(styles.label_style(font_size=12))
            shortcut_labels.append(label)

            edit = QKeySequenceEdit(shortcuts_container)
            if hasattr(edit, "setMaximumSequenceLength"):
                edit.setMaximumSequenceLength(1)
            edit.setFixedHeight(styles.PAGE_CONTROL_HEIGHT)
            edit.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            edit.setKeySequence(
                QKeySequence(hotkey_to_display(hotkey_values.get(action, "")))
            )
            edit.setStyleSheet(styles.hotkey_edit_style(13))
            edit.keySequenceChanged.connect(
                lambda _sequence, action=action, edit=edit: save_hotkey(action, edit)
            )
            app.screen_mover_hotkey_edits[action] = edit

            clear_button = QPushButton("Clear", shortcuts_container)
            clear_button.setCursor(Qt.CursorShape.ArrowCursor)
            styles.apply_page_control_size(
                clear_button,
                width=styles.PAGE_COMPACT_CONTROL_WIDTH,
                role="compact",
            )
            clear_button.setProperty("styleFontSize", 11)
            clear_button.setStyleSheet(styles.organizing_button_style(11))
            clear_button.clicked.connect(
                lambda _checked=False, action=action, edit=edit: clear_hotkey(
                    action,
                    edit,
                )
            )

            shortcut_grid.addWidget(label, row, 0)
            shortcut_grid.addWidget(edit, row, 1)
            shortcut_grid.addWidget(clear_button, row, 2)
            app.register_tooltip(edit, tooltip_text("screen_mover_hotkey"))
            app.register_tooltip(
                clear_button,
                tooltip_text("screen_mover_hotkey_clear"),
            )

        shortcut_label_width = max(
            label.sizeHint().width() for label in shortcut_labels
        )
        for label in shortcut_labels:
            label.setFixedWidth(shortcut_label_width)
        shortcut_grid.setColumnMinimumWidth(0, shortcut_label_width)
        shortcut_grid.setColumnMinimumWidth(
            2,
            styles.PAGE_COMPACT_CONTROL_WIDTH,
        )

        reset_button = QPushButton(
            "Reset Screen Mover Defaults",
            shortcuts_container,
        )
        reset_button.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(reset_button)
        reset_button.setProperty("styleFontSize", 12)
        reset_button.setStyleSheet(styles.organizing_button_style(12))

        def reset_screen_mover_defaults() -> None:
            app.reset_screen_mover_settings()

        reset_button.clicked.connect(reset_screen_mover_defaults)
        shortcuts_layout.addWidget(
            reset_button,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        app.screen_mover_reset_btn = reset_button
        app.register_tooltip(
            reset_button,
            tooltip_text("screen_mover_reset"),
        )

        self._attach_left_section(
            screen_section,
            expanded_spacer_height=app.SCREEN_MOVER_TOP_SPACER,
        )

    def _build_drive_reminder_section(self) -> None:
        app = self.app
        state = self.state
        usb_section, usb_layout = self._make_section(
            "External Drive Reminder Options",
            "drive_reminder_options",
        )

        leave_reminder_row = QWidget()
        leave_reminder_row.setProperty("centeredControlGrid", True)
        leave_reminder_row.setFixedWidth(self.EXTERNAL_DRIVE_ROW_WIDTH)
        leave_reminder_row.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        leave_reminder_row_layout = QHBoxLayout(leave_reminder_row)
        leave_reminder_row_layout.setContentsMargins(0, 0, 0, 0)
        leave_reminder_row_layout.setSpacing(self.CONTROL_COLUMN_GAP)

        leave_reminder_btn = self._make_toggle_button(
            "Drive Leave Reminder Off",
            state.get("usb_idle_enabled", True),
        )
        styles.apply_page_control_size(
            leave_reminder_btn,
            width=self.EXTERNAL_DRIVE_CONTROL_WIDTH,
            role="externalDrive",
        )
        self._bind_toggle_state_text(leave_reminder_btn, "Drive Leave Reminder")
        leave_reminder_row_layout.addWidget(leave_reminder_btn)
        app.register_tooltip(
            leave_reminder_btn,
            tooltip_text("idle_plugged_reminder"),
        )

        app.connected_drives_field = QComboBox()
        app.connected_drives_field.setEditable(False)
        app.connected_drives_field.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_page_control_size(
            app.connected_drives_field,
            width=self.EXTERNAL_DRIVE_CONTROL_WIDTH,
            role="externalDrive",
        )
        app.connected_drives_field.setMinimumContentsLength(
            len("No Drives Connected")
        )
        app.connected_drives_field.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        app.connected_drives_field.setProperty("connectedDrivesFieldStyle", True)
        app.connected_drives_field.setProperty("surfaceFieldStyle", True)
        app.connected_drives_field.setProperty("styleFontSize", 15)
        app.connected_drives_field.setStyleSheet(
            styles.connected_drives_combo_style(15)
        )
        app.connected_drives_field.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        app.connected_drives_field.view().viewport().installEventFilter(app)
        app.connected_drives_field.customContextMenuRequested.connect(
            app._show_connected_drives_context_menu
        )

        app.connected_drives_empty_label = QLabel("No Drives Connected")
        app.connected_drives_empty_label.setStyleSheet(
            styles.label_style(font_size=14, color=styles.theme_text_color())
        )
        app.connected_drives_empty_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        app.connected_drives_empty_label.setFixedSize(
            self.EXTERNAL_DRIVE_CONTROL_WIDTH,
            styles.PAGE_CONTROL_HEIGHT,
        )
        app.connected_drives_empty_label.hide()

        leave_reminder_row_layout.addWidget(app.connected_drives_field)
        leave_reminder_row_layout.addWidget(app.connected_drives_empty_label)
        usb_layout.addWidget(leave_reminder_row, 0, Qt.AlignmentFlag.AlignHCenter)
        app._refresh_connected_drive_status_label()

        def on_leave_reminder_changed(checked: bool):
            state["usb_idle_enabled"] = checked
            save_state(state)

        leave_reminder_btn.toggled.connect(on_leave_reminder_changed)

        plug_notification_label = QLabel("Plug/unplug notifications")
        plug_notification_label.setStyleSheet(styles.label_style(font_size=14))
        plug_notification_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        plug_notification_label.setFixedSize(
            self.EXTERNAL_DRIVE_CONTROL_WIDTH,
            styles.PAGE_CONTROL_HEIGHT,
        )

        plug_combo = self._create_drive_reminder_combo(
            "plug_unplug_notify",
            "usb_plug_notify_mode",
            "usb_plug_enabled",
            [
                ("Off", "off"),
                ("On", "on"),
            ],
            fixed_width=self.EXTERNAL_DRIVE_CONTROL_WIDTH,
        )
        plug_combo.setProperty("plugUnplugNotificationCombo", True)
        plug_notification_row = QWidget()
        plug_notification_row.setProperty("centeredControlGrid", True)
        plug_notification_row.setFixedWidth(self.EXTERNAL_DRIVE_ROW_WIDTH)
        plug_notification_row.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        plug_notification_row_layout = QHBoxLayout(plug_notification_row)
        plug_notification_row_layout.setContentsMargins(0, 0, 0, 0)
        plug_notification_row_layout.setSpacing(self.CONTROL_COLUMN_GAP)
        plug_notification_row_layout.addWidget(plug_notification_label)
        plug_notification_row_layout.addWidget(plug_combo)
        usb_layout.addWidget(
            plug_notification_row,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        self._attach_left_section(
            usb_section,
            expanded_spacer_height=app.DRIVE_REMINDER_TOP_SPACER,
        )

    def _create_drive_reminder_combo(
        self,
        tooltip_key: str,
        state_key: str,
        legacy_enabled_key: str,
        items: list[tuple[str, str]],
        *,
        fixed_width: int | None = None,
    ) -> QComboBox:
        combo = QComboBox()
        for text, value in items:
            combo.addItem(text, value)
        combo.setCursor(Qt.CursorShape.ArrowCursor)
        combo.setProperty("styleFontSize", 14)
        combo.setStyleSheet(styles.organizing_combo_style(14))
        def update_combo_state() -> None:
            styles.fit_page_combo_width(
                combo,
                placeholder=combo.currentText(),
                font_size=14,
            )
            if fixed_width is not None:
                styles.apply_page_control_size(
                    combo,
                    width=fixed_width,
                    role="wide",
                )
            combo.setProperty("persistPressed", combo.currentData() != "off")
            combo.style().unpolish(combo)
            combo.style().polish(combo)

        stored_value = str(self.state.get(state_key, "")).strip().lower()
        valid_values = {value for _, value in items}
        if stored_value not in valid_values:
            stored_value = (
                items[1][1] if self.state.get(legacy_enabled_key, True) else "off"
            )

        combo_index = combo.findData(stored_value)
        if combo_index >= 0:
            combo.setCurrentIndex(combo_index)
        update_combo_state()

        def on_combo_changed(_text: str):
            selected_value = combo.currentData()
            self.state[state_key] = selected_value
            self.state[legacy_enabled_key] = selected_value != "off"
            save_state(self.state)
            update_combo_state()

        combo.currentTextChanged.connect(on_combo_changed)
        self.app.register_tooltip(combo, tooltip_text(tooltip_key))
        return combo

    def _build_organising_utilities_section(self) -> None:
        app = self.app
        org_section, org_layout = self._make_section(
            "General Organising Utilities",
            "organising_utilities",
        )
        app.backup_path = app._get_master_backup_dir()

        screenshot_btn = QPushButton("Desktop Screenshot")
        self._style_organizing_button(screenshot_btn)
        screenshot_btn.clicked.connect(app.take_desktop_screenshot)
        app.register_tooltip(screenshot_btn, tooltip_text("desktop_screenshot"))

        layout_actions_combo = self._make_action_dropdown(
            " Desktop Actions ",
            {
                "Capture Layout": app.capture_desktop_layout,
                "Restore Layout": app.restore_desktop_layout,
            },
        )
        app.register_tooltip(
            layout_actions_combo,
            tooltip_text("capture_desktop_layout"),
        )
        self._add_two_column_control_row(
            org_layout,
            screenshot_btn,
            layout_actions_combo,
        )

        brave_export_btn = QPushButton("Export Bookmarks")
        self._style_organizing_button(brave_export_btn)
        brave_export_btn.clicked.connect(app.export_bookmarks)
        app.register_tooltip(brave_export_btn, tooltip_text("export_bookmarks"))

        taskbar_actions_combo = self._make_action_dropdown(
            " Taskbar Actions ",
            {
                "Backup Taskbar": app.backup_taskbar_apps,
                "Open Backup Folder": app.open_taskbar_backup_folder,
            },
        )
        app.register_tooltip(taskbar_actions_combo, tooltip_text("backup_taskbar"))
        self._add_two_column_control_row(
            org_layout,
            brave_export_btn,
            taskbar_actions_combo,
        )

        master_backup_btn = QPushButton("Master Backup Path")
        self._style_organizing_button(master_backup_btn)
        app.register_tooltip(master_backup_btn, tooltip_text("master_backup_path"))

        app.backup_path_input = QLabel()
        app.backup_path_input.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        app.backup_path_input.setProperty("plainThemeLabelStyle", True)
        app.backup_path_input.setStyleSheet(styles.plain_theme_label_style(15))
        app.backup_path_input.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        app._refresh_master_backup_path_display()

        self._add_two_column_control_row(
            org_layout,
            master_backup_btn,
            app.backup_path_input,
        )

        master_backup_btn.clicked.connect(app._choose_master_backup_dir)
        app._taskbar_backup_folder_timer = QTimer(app)
        app._taskbar_backup_folder_timer.timeout.connect(
            app._refresh_taskbar_backup_folder_button
        )
        app._taskbar_backup_folder_timer.start(1000)
        app._refresh_taskbar_backup_folder_button()

        self._attach_left_section(
            org_section,
            expanded_spacer_height=app.ORGANISING_SECTION_TOP_SPACER,
        )

    def _build_folder_utilities_section(self) -> None:
        app = self.app
        state = self.state
        folder_section, folder_layout = self._make_section(
            "Folder Utilities",
            "folder_utilities",
        )

        folder_creator_btn = QPushButton("Folder Creator")
        self._style_organizing_button(folder_creator_btn)
        app.register_tooltip(
            folder_creator_btn,
            tooltip_text("folder_creator_launcher"),
        )

        folder_btn = QPushButton("Folder To Desktop")
        self._style_organizing_button(folder_btn)
        app.register_tooltip(folder_btn, tooltip_text("folder_to_desktop"))

        folder_input = QLineEdit()
        app.folder_input = folder_input
        folder_input.setPlaceholderText("Folder name")
        folder_input.setText(state.get("folder_to_desktop_name", ""))
        folder_input.setReadOnly(False)
        folder_input.setFixedSize(300, styles.PAGE_CONTROL_HEIGHT)
        folder_input.setProperty("framelessSurfaceFieldStyle", True)
        folder_input.setStyleSheet(styles.frameless_surfaced_line_edit_style(15))
        app.register_tooltip(folder_input, tooltip_text("folder_name_input"))

        folder_layout.addWidget(
            folder_creator_btn,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        folder_create_row = QWidget()
        folder_create_row.setProperty("centeredControlGrid", True)
        folder_create_row.setFixedWidth(
            300 + self.CONTROL_COLUMN_GAP + styles.PAGE_CONTROL_WIDTH
        )
        folder_create_row.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        folder_create_row_layout = QHBoxLayout(folder_create_row)
        folder_create_row_layout.setContentsMargins(0, 0, 0, 0)
        folder_create_row_layout.setSpacing(self.CONTROL_COLUMN_GAP)
        folder_create_row_layout.addWidget(folder_input)
        folder_create_row_layout.addWidget(folder_btn)
        folder_layout.addWidget(
            folder_create_row,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        def on_folder_name_changed(text: str):
            state["folder_to_desktop_name"] = text
            folder_btn.setEnabled(bool(text.strip()))
            save_state(state)

        def on_create_folder_clicked():
            app._create_desktop_folder(folder_input)

        folder_btn.setEnabled(bool(folder_input.text().strip()))
        folder_btn.clicked.connect(on_create_folder_clicked)
        folder_creator_btn.clicked.connect(app.open_folder_creator)
        folder_input.textChanged.connect(on_folder_name_changed)

        self._attach_left_section(
            folder_section,
            expanded_spacer_height=app.FOLDER_UTILITIES_TOP_SPACER,
        )

    def _build_recycle_bin_section(self) -> None:
        app = self.app
        state = self.state
        recycle_bin_section, recycle_bin_layout = self._make_section(
            "Recycle Bin Actions",
            "recycle_bin_actions",
        )

        recycle_bin_controls = QWidget()
        recycle_bin_controls.setProperty("centeredControlGrid", True)
        recycle_bin_controls.setFixedWidth(self.CONTROL_ROW_WIDTH)
        recycle_bin_controls.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        recycle_bin_controls_layout = QGridLayout(recycle_bin_controls)
        recycle_bin_controls_layout.setContentsMargins(0, 0, 0, 0)
        recycle_bin_controls_layout.setHorizontalSpacing(self.CONTROL_COLUMN_GAP)
        recycle_bin_controls_layout.setVerticalSpacing(10)
        recycle_bin_controls_layout.setColumnMinimumWidth(
            0,
            self.LEFT_CONTROL_COLUMN_WIDTH,
        )
        recycle_bin_controls_layout.setColumnMinimumWidth(
            1,
            self.RIGHT_CONTROL_COLUMN_WIDTH,
        )

        cleanup_actions_combo = self._make_action_dropdown(
            " Cleanup Actions ",
            {
                "Open Recycle Bin": app.open_recycle_bin,
                "Run Auto-Clean Now": app.run_recycle_bin_cleanup_now,
                "Empty Recycle Bin": app.empty_recycle_bin,
            },
        )
        if cleanup_actions_combo.property("pageControlRole") != "wide":
            cleanup_actions_combo.setFixedWidth(self.LEFT_CONTROL_COLUMN_WIDTH)
        empty_row = cleanup_actions_combo.findText("Empty Recycle Bin")
        if empty_row >= 0:
            danger = QColor(164, 56, 56) if styles.THEME_IS_DARK else QColor(190, 66, 66)
            cleanup_actions_combo.setItemData(
                empty_row,
                danger,
                Qt.ItemDataRole.ForegroundRole,
            )
        recycle_bin_controls_layout.addWidget(cleanup_actions_combo, 0, 0)
        app.register_tooltip(cleanup_actions_combo, tooltip_text("cleanup_actions"))

        recycle_bin_auto_clean_enabled = bool(
            state.get("recycle_bin_auto_clean_enabled", False)
        )
        recycle_bin_auto_clean_btn = self._make_toggle_button(
            "Auto-clean On",
            recycle_bin_auto_clean_enabled,
        )
        self._bind_toggle_state_text(recycle_bin_auto_clean_btn, "Auto-clean")
        recycle_bin_auto_clean_btn.setFixedWidth(self.RIGHT_CONTROL_COLUMN_WIDTH)
        recycle_bin_controls_layout.addWidget(recycle_bin_auto_clean_btn, 0, 1)
        app.register_tooltip(
            recycle_bin_auto_clean_btn,
            tooltip_text("recycle_bin_auto_clean"),
        )

        age_rule_values = ["7 days", "14 days", "30 days"]
        current_age_rule_days = int(state.get("recycle_bin_age_rule_days", 30))
        current_age_rule_text = f"{current_age_rule_days} days"
        recycle_bin_age_rule_combo = self._make_value_dropdown(
            age_rule_values,
            current_age_rule_text,
        )
        app.register_tooltip(
            recycle_bin_age_rule_combo,
            tooltip_text("recycle_bin_age_rule"),
        )

        cleanup_rule_label = QLabel("Delete items older than:")
        cleanup_rule_label.setFixedWidth(self.LEFT_CONTROL_COLUMN_WIDTH)
        cleanup_rule_label.setStyleSheet(styles.label_style(font_size=14))
        recycle_bin_age_rule_row = QWidget()
        recycle_bin_age_rule_row.setFixedWidth(self.CONTROL_ROW_WIDTH)
        recycle_bin_age_rule_row_layout = QGridLayout(recycle_bin_age_rule_row)
        recycle_bin_age_rule_row_layout.setContentsMargins(0, 0, 0, 0)
        recycle_bin_age_rule_row_layout.setHorizontalSpacing(self.CONTROL_COLUMN_GAP)
        recycle_bin_age_rule_row_layout.setVerticalSpacing(0)
        recycle_bin_age_rule_row_layout.addWidget(cleanup_rule_label, 0, 0)
        if recycle_bin_age_rule_combo.property("pageControlRole") != "wide":
            recycle_bin_age_rule_combo.setFixedWidth(self.RIGHT_CONTROL_COLUMN_WIDTH)
        recycle_bin_age_rule_row_layout.addWidget(recycle_bin_age_rule_combo, 0, 1)
        recycle_bin_age_rule_row_layout.setColumnMinimumWidth(
            0,
            self.LEFT_CONTROL_COLUMN_WIDTH,
        )
        recycle_bin_age_rule_row_layout.setColumnMinimumWidth(
            1,
            self.RIGHT_CONTROL_COLUMN_WIDTH,
        )
        recycle_bin_age_rule_row_height = recycle_bin_age_rule_row.sizeHint().height()
        recycle_bin_age_rule_slot = QWidget()
        recycle_bin_age_rule_slot.setFixedWidth(self.CONTROL_ROW_WIDTH)
        recycle_bin_age_rule_slot.setFixedHeight(recycle_bin_age_rule_row_height)
        recycle_bin_age_rule_slot_layout = QVBoxLayout(recycle_bin_age_rule_slot)
        recycle_bin_age_rule_slot_layout.setContentsMargins(0, 0, 0, 0)
        recycle_bin_age_rule_slot_layout.setSpacing(0)
        recycle_bin_age_rule_slot_layout.addWidget(recycle_bin_age_rule_row)
        recycle_bin_controls_layout.addWidget(recycle_bin_age_rule_slot, 1, 0, 1, 2)

        def set_recycle_bin_age_rule_row_visible(is_visible: bool):
            recycle_bin_age_rule_row.setVisible(is_visible)

        set_recycle_bin_age_rule_row_visible(recycle_bin_auto_clean_enabled)
        recycle_bin_controls_layout.setColumnStretch(0, 1)
        recycle_bin_controls_layout.setColumnStretch(1, 1)
        recycle_bin_controls.setFixedWidth(
            max(cleanup_actions_combo.width(), cleanup_rule_label.width())
            + self.CONTROL_COLUMN_GAP
            + max(
                recycle_bin_auto_clean_btn.width(),
                recycle_bin_age_rule_combo.width(),
            )
        )
        recycle_bin_layout.addWidget(recycle_bin_controls)

        def on_recycle_bin_auto_clean_changed(checked: bool):
            state["recycle_bin_auto_clean_enabled"] = checked
            set_recycle_bin_age_rule_row_visible(checked)
            save_state(state)
            app.refresh_overview()

        def on_recycle_bin_age_rule_changed(text: str):
            try:
                days = int(text.split()[0])
            except (IndexError, ValueError):
                return
            if state.get("recycle_bin_age_rule_days") != days:
                state["recycle_bin_last_auto_clean_popup_days"] = None
            state["recycle_bin_age_rule_days"] = days
            save_state(state)

        recycle_bin_auto_clean_btn.toggled.connect(on_recycle_bin_auto_clean_changed)
        recycle_bin_age_rule_combo.currentTextChanged.connect(
            on_recycle_bin_age_rule_changed
        )

        self._attach_left_section(
            recycle_bin_section,
            expanded_spacer_height=app.RECYCLE_BIN_ACTIONS_TOP_SPACER,
        )

    def _wire_master_toggle(self) -> None:
        app = self.app
        master_btn = self.master_btn
        if master_btn is None:
            return

        def toggle_all():
            any_visible = any(
                bool(getattr(section, "is_open", False))
                for section in app.left_sections
            )

            new_state = not any_visible
            app.master_toggle_left_state = new_state
            app.state["master_toggle_left"] = new_state

            master_btn.setText(
                styles.arrow_glyph(
                    Qt.ArrowType.DownArrow if new_state else Qt.ArrowType.UpArrow
                )
            )

            for section in app.left_sections:
                app._set_left_section_open(section, new_state)

            app.save_all_settings()

        master_btn.clicked.connect(toggle_all)
        master_btn.setText(
            styles.arrow_glyph(
                Qt.ArrowType.DownArrow
                if app.master_toggle_left_state
                else Qt.ArrowType.UpArrow
            )
        )

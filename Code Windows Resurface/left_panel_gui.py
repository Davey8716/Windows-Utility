from pathlib import Path
from typing import Callable

import styles
from screen_mover import SCREEN_MOVER
from state_manager import save_state
from tooltips import left_section_toggle_tooltip, tooltip_text
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
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
    def __init__(self, app):
        self.app = app
        self.state = app.state
        self.master_btn = None

    @property
    def icons_root(self) -> Path:
        return Path(__file__).resolve().parent.parent / "App Icons"

    def build(self) -> None:
        self._build_header()
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
        self._wire_master_toggle()

    def _build_header(self) -> None:
        app = self.app
        header = QWidget(app.main_frame)
        header.setFixedWidth(app.MAIN_SECTION_OUTER_WIDTH)
        header.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(
            app.MAIN_SECTION_SIDE_PADDING,
            10,
            app.MAIN_SECTION_SIDE_PADDING
            + (app.MAIN_SECTION_FRAME_WIDTH - app.LEFT_SECTION_VISIBLE_FRAME_WIDTH)
            + app.LEFT_TOGGLE_RIGHT_INSET,
            10,
        )

        title = QLabel("Windows Resurface", header)
        title.setStyleSheet(styles.label_style(font_size=20))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        master_btn = QToolButton(header)
        master_btn.setProperty("leftMasterToggleButton", True)
        master_btn.setCursor(Qt.CursorShape.ArrowCursor)
        master_btn.setArrowType(Qt.ArrowType.NoArrow)
        master_btn.setText(styles.arrow_glyph(Qt.ArrowType.DownArrow))
        master_btn.setStyleSheet(
            styles.left_master_toggle_style(
                styles.theme_text_color(),
                styles.SURFACE_DARK,
            )
        )
        left_master_slot_width, left_master_slot_height = (
            styles.left_master_toggle_slot_size()
        )
        master_btn.setFixedSize(left_master_slot_width, left_master_slot_height)
        app.master_collapse_btn_left = master_btn
        self.master_btn = master_btn
        app.register_tooltip(master_btn, tooltip_text("master_collapse_left"))

        header_spacer = QWidget(header)
        header_spacer.setFixedSize(left_master_slot_width, left_master_slot_height)

        header_layout.addWidget(header_spacer)
        header_layout.addStretch()
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(master_btn)

        app.main_layout.addWidget(header, 0, Qt.AlignmentFlag.AlignLeft)

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
        initial_open = app.state.get("left_section_states", {}).get(section_id, True)
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
        styles.apply_default_button_size(button)
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
        styles.apply_default_button_size(button, width=width)
        button.setProperty("styleFontSize", font_size)
        button.setStyleSheet(styles.toggle_button_style(font_size=font_size))
        return button

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
        styles.apply_default_button_size(button)
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
        styles.apply_default_button_size(combo)
        combo.setProperty("styleFontSize", 14)
        if power_action_style:
            combo.setProperty("powerActionStyle", True)
            combo.setProperty("powerActionPlaceholder", placeholder)
            combo.setProperty("powerActionSeverityMap", severity_map or {})
            self.app._apply_power_action_dropdown_style(combo)
        else:
            combo.setStyleSheet(styles.organizing_combo_style(14))

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
        styles.apply_default_button_size(combo)
        combo.setProperty("styleFontSize", 14)
        combo.setStyleSheet(styles.organizing_combo_style(14))
        return combo

    def _build_user_interface_section(self) -> None:
        app = self.app
        state = self.state
        ui_section, ui_layout = self._make_section("User Interface", "user_interface")
        self._attach_left_section(
            ui_section,
            expanded_spacer_height=app.USER_INTERFACE_TOP_SPACER,
        )

        compact_toggle_width = (styles.DEFAULT_BUTTON_WIDTH - 10) // 2

        ui_top_row = QWidget(ui_section.content)
        ui_top_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ui_top_row_layout = QHBoxLayout(ui_top_row)
        ui_top_row_layout.setContentsMargins(0, 0, 0, 0)
        ui_top_row_layout.setSpacing(10)
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
        ui_top_row_layout.addWidget(dark_mode_btn)
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
        ui_top_row_layout.addWidget(desktop_zen_btn)
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
        ui_top_row_layout.addWidget(power_dropdown)
        ui_top_row_layout.setStretch(2, 1)
        app.register_tooltip(power_dropdown, tooltip_text("power_options"))

        ui_middle_row = QWidget(ui_section.content)
        ui_middle_row.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        ui_middle_row_layout = QHBoxLayout(ui_middle_row)
        ui_middle_row_layout.setContentsMargins(0, 0, 0, 0)
        ui_middle_row_layout.setSpacing(10)
        ui_layout.addWidget(ui_middle_row)

        always_on_top_btn = self._make_toggle_button(
            "Always on Top",
            state.get("main_always_on_top_enabled", True),
        )
        self._bind_toggle_state_text(always_on_top_btn, "Always on Top")
        ui_middle_row_layout.addWidget(always_on_top_btn)
        app.register_tooltip(always_on_top_btn, tooltip_text("always_on_top"))

        tooltips_btn = self._make_toggle_button(
            "Tooltips",
            state.get("tooltips_enabled", True),
        )
        self._bind_toggle_state_text(tooltips_btn, "Tooltips")
        ui_middle_row_layout.addWidget(tooltips_btn)
        app.register_tooltip(tooltips_btn, tooltip_text("enable_tooltips"))

        ui_bottom_row = QWidget(ui_section.content)
        ui_bottom_row.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        ui_bottom_row_layout = QHBoxLayout(ui_bottom_row)
        ui_bottom_row_layout.setContentsMargins(0, 0, 0, 0)
        ui_bottom_row_layout.setSpacing(10)
        ui_layout.addWidget(ui_bottom_row)

        maximize_all_enabled = bool(
            state.get(
                "maximize_all_enabled",
                not state.get("minimize_all_enabled", False),
            )
        )
        max_all_btn = self._make_toggle_button("Maximize All", maximize_all_enabled)
        self._bind_toggle_state_text(max_all_btn, "Maximize All")
        ui_bottom_row_layout.addWidget(max_all_btn)
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
        styles.apply_default_button_size(minimize_after_use_btn)
        ui_bottom_row_layout.addWidget(minimize_after_use_btn)
        app.register_tooltip(
            minimize_after_use_btn,
            tooltip_text("minimize_after_use"),
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
        screen_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        screen_row_layout = QHBoxLayout(screen_row)
        screen_row_layout.setContentsMargins(0, 0, 0, 0)
        screen_row_layout.setSpacing(10)
        screen_layout.addWidget(screen_row)

        title_bar_dock_btn = self._make_toggle_button(
            "Title Bar Dock",
            state.get("title_bar_dock_enabled", True),
        )
        self._bind_toggle_state_text(title_bar_dock_btn, "Title Bar Dock")
        screen_row_layout.addWidget(title_bar_dock_btn)
        app.register_tooltip(title_bar_dock_btn, tooltip_text("title_bar_dock"))

        def on_title_bar_dock_changed(checked: bool):
            state["title_bar_dock_enabled"] = checked
            save_state(state)
            SCREEN_MOVER.title_bar_dock_enabled = checked

        title_bar_dock_btn.toggled.connect(on_title_bar_dock_changed)

        screen_move_button_combo = QComboBox()
        screen_move_button_combo.addItem("Move Button: Off", "off")
        screen_move_button_combo.addItem("Left Mouse Button", "left")
        screen_move_button_combo.addItem("Middle Mouse Button", "middle")
        screen_move_button_combo.addItem("Right Mouse Button", "right")
        screen_move_button_combo.setCursor(Qt.CursorShape.ArrowCursor)
        styles.apply_default_button_size(screen_move_button_combo)
        screen_move_button_combo.setStyleSheet(styles.organizing_combo_style(14))

        def update_screen_move_combo_state() -> None:
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
        screen_row_layout.addStretch()

        def on_screen_move_button_changed(_text: str):
            button_value = screen_move_button_combo.currentData()
            state["screen_mover_activation_button"] = button_value
            state["mmb_activation_enabled"] = button_value == "middle"
            save_state(state)
            SCREEN_MOVER.activation_button = button_value
            update_screen_move_combo_state()

        screen_move_button_combo.currentTextChanged.connect(
            on_screen_move_button_changed
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
        leave_reminder_row.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        leave_reminder_row_layout = QHBoxLayout(leave_reminder_row)
        leave_reminder_row_layout.setContentsMargins(0, 0, 0, 0)
        leave_reminder_row_layout.setSpacing(10)

        leave_reminder_btn = self._make_toggle_button(
            "Drive Leave Reminder Off",
            state.get("usb_idle_enabled", True),
        )
        self._bind_toggle_state_text(leave_reminder_btn, "Drive Leave Reminder")
        leave_reminder_btn.setFixedSize(190, styles.DEFAULT_BUTTON_HEIGHT)
        leave_reminder_row_layout.addWidget(leave_reminder_btn)
        app.register_tooltip(
            leave_reminder_btn,
            tooltip_text("idle_plugged_reminder"),
        )

        app.connected_drives_field = QComboBox()
        app.connected_drives_field.setEditable(False)
        app.connected_drives_field.setCursor(Qt.CursorShape.ArrowCursor)
        app.connected_drives_field.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        app.connected_drives_field.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
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
        app.connected_drives_empty_label.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        app.connected_drives_empty_label.hide()

        leave_reminder_row_layout.addWidget(app.connected_drives_field)
        leave_reminder_row_layout.addWidget(app.connected_drives_empty_label)
        usb_layout.addWidget(leave_reminder_row)
        app._refresh_connected_drive_status_label()

        def on_leave_reminder_changed(checked: bool):
            state["usb_idle_enabled"] = checked
            save_state(state)

        leave_reminder_btn.toggled.connect(on_leave_reminder_changed)

        plug_combo = self._create_drive_reminder_combo(
            "plug_unplug_notify",
            "usb_plug_notify_mode",
            "usb_plug_enabled",
            [
                ("Plug / Unplug Notify: Off", "off"),
                ("Show plug and unplug notifications", "on"),
            ],
        )
        usb_layout.addWidget(plug_combo)

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
    ) -> QComboBox:
        combo = QComboBox()
        for text, value in items:
            combo.addItem(text, value)
        combo.setCursor(Qt.CursorShape.ArrowCursor)
        combo.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        combo.setStyleSheet(styles.organizing_combo_style(14))

        def update_combo_state() -> None:
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

        desktop_actions_row = QWidget()
        desktop_actions_row.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        desktop_actions_row_layout = QHBoxLayout(desktop_actions_row)
        desktop_actions_row_layout.setContentsMargins(0, 0, 0, 0)
        desktop_actions_row_layout.setSpacing(10)

        screenshot_btn = QPushButton("Desktop Screenshot")
        self._style_organizing_button(screenshot_btn)
        desktop_actions_row_layout.addWidget(screenshot_btn)
        screenshot_btn.clicked.connect(app.take_desktop_screenshot)
        app.register_tooltip(screenshot_btn, tooltip_text("desktop_screenshot"))

        layout_actions_combo = self._make_action_dropdown(
            " Desktop Actions ",
            {
                "Capture Layout": app.capture_desktop_layout,
                "Restore Layout": app.restore_desktop_layout,
            },
        )
        desktop_actions_row_layout.addWidget(layout_actions_combo)
        org_layout.addWidget(desktop_actions_row)
        app.register_tooltip(
            layout_actions_combo,
            tooltip_text("capture_desktop_layout"),
        )

        bookmarks_taskbar_row = QWidget()
        bookmarks_taskbar_row.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        bookmarks_taskbar_row_layout = QHBoxLayout(bookmarks_taskbar_row)
        bookmarks_taskbar_row_layout.setContentsMargins(0, 0, 0, 0)
        bookmarks_taskbar_row_layout.setSpacing(10)

        brave_export_btn = QPushButton("Export Bookmarks")
        self._style_organizing_button(brave_export_btn)
        bookmarks_taskbar_row_layout.addWidget(brave_export_btn)
        brave_export_btn.clicked.connect(app.export_bookmarks)
        app.register_tooltip(brave_export_btn, tooltip_text("export_bookmarks"))

        taskbar_actions_combo = self._make_action_dropdown(
            " Taskbar Actions ",
            {
                "Backup Taskbar": app.backup_taskbar_apps,
                "Open Backup Folder": app.open_taskbar_backup_folder,
            },
        )
        bookmarks_taskbar_row_layout.addWidget(taskbar_actions_combo)
        org_layout.addWidget(bookmarks_taskbar_row)
        app.register_tooltip(taskbar_actions_combo, tooltip_text("backup_taskbar"))

        master_backup_row = QWidget()
        master_backup_row.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        master_backup_row_layout = QHBoxLayout(master_backup_row)
        master_backup_row_layout.setContentsMargins(0, 0, 0, 0)
        master_backup_row_layout.setSpacing(10)

        master_backup_btn = QPushButton("Master Backup Path")
        self._style_organizing_button(master_backup_btn)
        master_backup_row_layout.addWidget(master_backup_btn)
        app.register_tooltip(master_backup_btn, tooltip_text("master_backup_path"))

        app.backup_path_input = QLabel()
        app.backup_path_input.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        app.backup_path_input.setProperty("plainThemeLabelStyle", True)
        app.backup_path_input.setStyleSheet(styles.plain_theme_label_style(15))
        app.backup_path_input.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        master_backup_row_layout.addWidget(app.backup_path_input)
        app._refresh_master_backup_path_display()

        org_layout.addWidget(master_backup_row)

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

        folder_row = QWidget()
        folder_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        folder_row_layout = QHBoxLayout(folder_row)
        folder_row_layout.setContentsMargins(0, 0, 0, 0)
        folder_row_layout.setSpacing(10)

        folder_creator_btn = QPushButton("Folder Creator")
        self._style_organizing_button(folder_creator_btn)
        styles.apply_default_button_size(folder_creator_btn, width=118)
        app.register_tooltip(
            folder_creator_btn,
            tooltip_text("folder_creator_launcher"),
        )

        folder_btn = QPushButton("Folder \u2192 Desktop")
        self._style_organizing_button(folder_btn)
        styles.apply_default_button_size(folder_btn, width=122)
        app.register_tooltip(folder_btn, tooltip_text("folder_to_desktop"))

        folder_input = QLineEdit()
        folder_input.setPlaceholderText("Folder name")
        folder_input.setText(state.get("folder_to_desktop_name", ""))
        folder_input.setReadOnly(False)
        folder_input.setFixedHeight(styles.DEFAULT_BUTTON_HEIGHT)
        folder_input.setProperty("framelessSurfaceFieldStyle", True)
        folder_input.setStyleSheet(styles.frameless_surfaced_line_edit_style(15))
        app.register_tooltip(folder_input, tooltip_text("folder_name_input"))

        folder_row_layout.addWidget(folder_creator_btn)
        folder_row_layout.addWidget(folder_btn)
        folder_row_layout.addWidget(folder_input)
        folder_layout.addWidget(folder_row)

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
        recycle_bin_controls.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        recycle_bin_controls_layout = QGridLayout(recycle_bin_controls)
        recycle_bin_controls_layout.setContentsMargins(0, 0, 0, 0)
        recycle_bin_controls_layout.setHorizontalSpacing(10)
        recycle_bin_controls_layout.setVerticalSpacing(10)

        cleanup_actions_combo = self._make_action_dropdown(
            " Cleanup Actions ",
            {
                "Open Recycle Bin": app.open_recycle_bin,
                "Run Auto-Clean Now": app.run_recycle_bin_cleanup_now,
                "Empty Recycle Bin": app.empty_recycle_bin,
            },
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
        cleanup_rule_label.setStyleSheet(styles.label_style(font_size=14))
        recycle_bin_age_rule_slot = QWidget()
        recycle_bin_age_rule_slot.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        recycle_bin_age_rule_row = QWidget()
        recycle_bin_age_rule_row_layout = QGridLayout(recycle_bin_age_rule_row)
        recycle_bin_age_rule_row_layout.setContentsMargins(0, 0, 0, 0)
        recycle_bin_age_rule_row_layout.setHorizontalSpacing(10)
        recycle_bin_age_rule_row_layout.setVerticalSpacing(0)
        recycle_bin_age_rule_row_layout.addWidget(cleanup_rule_label, 0, 0)
        recycle_bin_age_rule_row_layout.addWidget(recycle_bin_age_rule_combo, 0, 1)
        recycle_bin_age_rule_row_layout.setColumnStretch(0, 1)
        recycle_bin_age_rule_row_layout.setColumnStretch(1, 1)
        recycle_bin_age_rule_row_height = recycle_bin_age_rule_row.sizeHint().height()
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
        recycle_bin_layout.addWidget(recycle_bin_controls)

        def on_recycle_bin_auto_clean_changed(checked: bool):
            state["recycle_bin_auto_clean_enabled"] = checked
            set_recycle_bin_age_rule_row_visible(checked)
            save_state(state)

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

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from resurface.ui import styles
from resurface.ui.pages.page_controls import PageControls
from resurface.ui.tooltips import tooltip_text


class UserInterfacePage(PageControls):
    theme_changed = Signal(bool)
    desktop_zen_changed = Signal(bool)
    always_on_top_changed = Signal(bool)
    tooltips_changed = Signal(bool)
    maximize_all_changed = Signal(bool)
    minimize_after_use_changed = Signal(bool)
    disable_all_confirmations_changed = Signal(bool)
    power_action_requested = Signal(str)

    def __init__(
        self,
        settings: dict,
        register_tooltip,
        style_power_action,
        *,
        desktop_icons_visible: bool | None = None,
        parent=None,
    ):
        super().__init__("user_interface", register_tooltip, parent)
        compact_width = (
            self.LEFT_CONTROL_COLUMN_WIDTH - self.CONTROL_COLUMN_GAP
        ) // 2
        top_row, top_layout = self.make_two_column_control_row()
        compact_slot = QWidget(top_row)
        compact_slot.setFixedWidth(self.LEFT_CONTROL_COLUMN_WIDTH)
        compact_layout = QHBoxLayout(compact_slot)
        compact_layout.setContentsMargins(0, 0, 0, 0)
        compact_layout.setSpacing(self.CONTROL_COLUMN_GAP)
        self.content_layout.addWidget(top_row)

        self._dark_mode_button = self.make_compact_toggle_button(
            "", bool(settings.get("theme_dark", True)), width=compact_width, font_size=10
        )
        self.bind_toggle_icon_only(
            self._dark_mode_button, checked_glyph="\ue708", unchecked_glyph="\ue706"
        )
        compact_layout.addWidget(self._dark_mode_button)
        self.register_tooltip(self._dark_mode_button, tooltip_text("dark_mode"))

        zen_enabled = bool(settings.get("desktop_zen_mode_enabled", False))
        if desktop_icons_visible is not None:
            zen_enabled = not desktop_icons_visible
        self._desktop_zen_button = self.make_compact_toggle_button(
            "", zen_enabled, width=compact_width, font_size=10
        )
        self.bind_toggle_icon_only(
            self._desktop_zen_button, checked_glyph="\ued1a", unchecked_glyph="\ue890"
        )
        compact_layout.addWidget(self._desktop_zen_button)
        self.register_tooltip(
            self._desktop_zen_button, tooltip_text("desktop_zen_mode")
        )

        power = self.make_action_dropdown(
            " Power and Session ",
            ["Lock PC", "Sleep", "Log out", "Restart", "Shutdown"],
            self.power_action_requested.emit,
            power_action_style=True,
            severity_map={
                "Lock PC": "blue", "Sleep": "yellow", "Restart": "orange_red",
                "Log out": "orange", "Shutdown": "red",
            },
            style_power_action=style_power_action,
        )
        top_layout.addWidget(compact_slot, 0, 0)
        top_layout.addWidget(power, 0, 1)
        self.register_tooltip(power, tooltip_text("power_options"))
        self.power_actions_combo = power

        always = self.make_toggle_button(
            "Always on Top", bool(settings.get("main_always_on_top_enabled", True))
        )
        self.bind_toggle_state_text(always, "Always on Top")
        self.register_tooltip(always, tooltip_text("always_on_top"))
        tips = self.make_toggle_button(
            "Tooltips", bool(settings.get("tooltips_enabled", True))
        )
        self.bind_toggle_state_text(tips, "Tooltips")
        self.register_tooltip(tips, tooltip_text("enable_tooltips"))
        self.add_two_column_control_row(self.content_layout, always, tips)

        maximize = self.make_toggle_button(
            "Maximize All",
            bool(settings.get("maximize_all_enabled", not settings.get("minimize_all_enabled", False))),
        )
        self.bind_toggle_state_text(maximize, "Maximize All")
        self.register_tooltip(maximize, tooltip_text("maximize_all"))
        minimize_after = self.make_toggle_button(
            "Minimize After Use", bool(settings.get("minimize_after_use_enabled", True))
        )
        self.bind_toggle_state_text(minimize_after, "Minimize After Use")
        minimize_after.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.register_tooltip(minimize_after, tooltip_text("minimize_after_use"))
        self.add_two_column_control_row(self.content_layout, maximize, minimize_after)

        disable_confirmations = self.make_toggle_button(
            "Disable All Confirmations",
            bool(settings.get("disable_all_confirmations_enabled", False)),
        )
        self.bind_toggle_state_text(
            disable_confirmations, "Disable All Confirmations"
        )
        disable_confirmations.setProperty("dangerToggle", True)
        disable_confirmations.setStyleSheet(styles.danger_toggle_button_style(14))
        self.register_tooltip(
            disable_confirmations, tooltip_text("disable_all_confirmations")
        )
        self.add_two_column_control_row(
            self.content_layout, disable_confirmations, QWidget()
        )

        self.always_on_top_button = always
        self.tooltips_button = tips
        self.maximize_all_button = maximize
        self.minimize_after_use_button = minimize_after
        self.disable_all_confirmations_button = disable_confirmations

        self._dark_mode_button.toggled.connect(self.theme_changed.emit)
        self._desktop_zen_button.toggled.connect(self.desktop_zen_changed.emit)
        always.toggled.connect(self.always_on_top_changed.emit)
        tips.toggled.connect(self.tooltips_changed.emit)
        maximize.toggled.connect(self.maximize_all_changed.emit)
        minimize_after.toggled.connect(self.minimize_after_use_changed.emit)
        disable_confirmations.toggled.connect(
            self._disable_all_confirmations_toggled
        )

    def set_desktop_zen_enabled(self, enabled: bool) -> None:
        if self._desktop_zen_button.isChecked() != enabled:
            self._desktop_zen_button.setChecked(enabled)

    def revert_desktop_zen(self, enabled: bool) -> None:
        self._desktop_zen_button.blockSignals(True)
        self._desktop_zen_button.setChecked(enabled)
        self._desktop_zen_button.blockSignals(False)
        refresh = getattr(self._desktop_zen_button, "_refresh_toggle_icon", None)
        if refresh:
            refresh()

    def set_disable_all_confirmations_enabled(self, enabled: bool) -> None:
        button = self.disable_all_confirmations_button
        button.blockSignals(True)
        button.setChecked(enabled)
        button.blockSignals(False)
        button.setText(
            "Disable All Confirmations On"
            if enabled
            else "Disable All Confirmations Off"
        )

    def _disable_all_confirmations_toggled(self, enabled: bool) -> None:
        if enabled:
            # Keep the control visibly off until the danger dialog is approved.
            self.set_disable_all_confirmations_enabled(False)
        self.disable_all_confirmations_changed.emit(enabled)

    def refresh_icons(self) -> None:
        for button in (self._dark_mode_button, self._desktop_zen_button):
            refresh = getattr(button, "_refresh_toggle_icon", None)
            if refresh:
                refresh()

from PySide6.QtCore import QSize, Qt
import pytest
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QComboBox, QMessageBox, QPushButton, QWidget

from resurface.ui.application_pages import QuickActionsGrid
from resurface.ui.controllers.theme_controller import ApplicationThemeController
from resurface.ui.quick_actions import (
    DEFAULT_QUICK_ACTION_IDS,
    QuickActionRegistry,
    QuickActionSpec,
)
from resurface.ui import styles
from resurface.ui.tooltips import QtTooltipManager, registered_tooltip_text, tooltip_text


def _app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    ("is_dark", "expected_colors"),
    [
        (True, {"blue": "#2468c4", "yellow": "#786300", "orange": "#a94b00", "orange_red": "#c64323", "red": "#b02626"}),
        (False, {"blue": "#2468c4", "yellow": "#786300", "orange": "#a94b00", "orange_red": "#c64323", "red": "#cc3434"}),
    ],
)
def test_power_action_palette_is_shared_and_theme_aware(is_dark, expected_colors):
    styles.set_theme(is_dark)
    try:
        for severity, expected_color in expected_colors.items():
            assert styles.power_action_color(severity).name() == expected_color

        for severity in expected_colors:
            background = styles.power_action_color(severity)
            assert styles.power_action_item_foreground(severity, background) == (
                styles.TEXT_LIGHT
            )
    finally:
        styles.set_theme(True)


def test_registry_normalizes_duplicate_unknown_and_malformed_ids():
    _app()
    state = {"quick_action_ids": ["one", "one", 3, "retired", "two"]}
    saves = []
    registry = QuickActionRegistry(state, lambda value: saves.append(dict(value)))
    registry.register(QuickActionSpec("one", "One", lambda: None))
    registry.register(QuickActionSpec("two", "Two", lambda: None))
    registry.finalize()

    assert registry.pinned_ids() == ["one", "two"]
    assert state["quick_action_ids"] == ["one", "two"]
    assert saves[-1]["quick_action_ids"] == ["one", "two"]


def test_registry_preserves_an_intentional_empty_selection():
    _app()
    state = {"quick_action_ids": []}
    registry = QuickActionRegistry(state, lambda _value: None)
    registry.register(QuickActionSpec("one", "One", lambda: None))
    registry.finalize()
    assert registry.pinned_ids() == []


def test_missing_or_malformed_selection_uses_registered_defaults():
    _app()
    for state in ({}, {"quick_action_ids": "not-a-list"}):
        registry = QuickActionRegistry(state, lambda _value: None)
        for action_id in DEFAULT_QUICK_ACTION_IDS:
            registry.register(QuickActionSpec(action_id, action_id, lambda: None))
        registry.finalize()
        assert registry.pinned_ids() == list(DEFAULT_QUICK_ACTION_IDS)


def test_registry_migrates_legacy_create_desktop_folder_action():
    _app()
    state = {"quick_action_ids": ["folder.create_desktop_folder"]}
    saves = []
    registry = QuickActionRegistry(state, lambda value: saves.append(dict(value)))
    registry.register(QuickActionSpec("organising.capture_layout", "Capture Layout", lambda: None))
    registry.finalize()

    assert registry.pinned_ids() == ["organising.capture_layout"]
    assert saves[-1]["quick_action_ids"] == ["organising.capture_layout"]


def test_registry_migrates_legacy_open_recycle_bin_action_and_deduplicates():
    _app()
    state = {"quick_action_ids": ["one", "recycle.open", "recycle.empty", "two"]}
    saves = []
    registry = QuickActionRegistry(state, lambda value: saves.append(dict(value)))
    for action_id in ("one", "recycle.empty", "two"):
        registry.register(QuickActionSpec(action_id, action_id, lambda: None))
    registry.finalize()

    assert registry.pinned_ids() == ["one", "recycle.empty", "two"]
    assert saves[-1]["quick_action_ids"] == ["one", "recycle.empty", "two"]


def test_pin_unpin_move_and_reset_persist_immediately():
    _app()
    state = {"quick_action_ids": []}
    saves = []
    registry = QuickActionRegistry(state, lambda value: saves.append(list(value["quick_action_ids"])))
    for action_id in (*DEFAULT_QUICK_ACTION_IDS, "extra"):
        registry.register(QuickActionSpec(action_id, action_id, lambda: None))
    registry.finalize()

    assert registry.pin("extra")
    assert not registry.pin("extra")
    assert registry.pin(DEFAULT_QUICK_ACTION_IDS[0])
    assert registry.move(DEFAULT_QUICK_ACTION_IDS[0], 0)
    assert registry.unpin("extra")
    registry.reset()

    assert registry.pinned_ids() == list(DEFAULT_QUICK_ACTION_IDS)
    assert saves[-1] == list(DEFAULT_QUICK_ACTION_IDS)


def test_grid_limits_to_eight_and_expands_inline():
    app = _app()
    ids = [f"action.{index}" for index in range(10)]
    registry = QuickActionRegistry({"quick_action_ids": ids}, lambda _value: None)
    for action_id in ids:
        registry.register(QuickActionSpec(action_id, action_id, lambda: None))
    registry.finalize()
    grid = QuickActionsGrid(registry, lambda widget, text: None)

    assert list(grid.buttons) == ids[:8]
    more = grid.findChild(QPushButton, "QuickActionsShowMore")
    assert more is not None
    assert more.size().width() == styles.PAGE_CONTROL_WIDTH
    assert more.size().height() == styles.PAGE_CONTROL_HEIGHT
    assert more.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert more.styleSheet() == styles.organizing_button_style(13)
    grid._toggle_expanded()
    app.processEvents()
    assert list(grid.buttons) == ids
    assert any(
        button.text() == "Show Less"
        for button in grid.findChildren(QPushButton, "QuickActionsShowMore")
    )
    grid.deleteLater()


def test_compact_icon_actions_keep_source_icons_and_share_a_row_with_a_standard_tile():
    app = _app()
    first_icon = QPixmap(16, 16)
    first_icon.fill(QColor("red"))
    second_icon = QPixmap(16, 16)
    second_icon.fill(QColor("blue"))
    dark_mode = QPushButton()
    dark_mode.setCheckable(True)
    dark_mode.setFixedSize(119, 34)
    dark_mode.setIcon(QIcon(first_icon))
    dark_mode.setIconSize(QSize(16, 16))
    zen_mode = QPushButton()
    zen_mode.setCheckable(True)
    zen_mode.setFixedSize(119, 34)
    zen_mode.setIcon(QIcon(second_icon))
    zen_mode.setIconSize(QSize(16, 16))
    registry = QuickActionRegistry(
        {"quick_action_ids": ["dark", "zen", "standard"]}, lambda _value: None
    )
    registry.register_button(
        "dark", "Dark Mode", dark_mode, compact=True, icon_only=True
    )
    registry.register_button(
        "zen", "Desktop Zen Mode", zen_mode, compact=True, icon_only=True
    )
    registry.register(QuickActionSpec("standard", "Standard", lambda: None))
    registry.finalize()
    grid = QuickActionsGrid(registry, lambda _widget, _text: None)

    dark_tile = grid.buttons["dark"]
    zen_tile = grid.buttons["zen"]
    assert dark_tile.text() == zen_tile.text() == ""
    assert dark_tile.size() == dark_mode.size()
    assert zen_tile.size() == zen_mode.size()
    assert dark_tile.icon().cacheKey() == dark_mode.icon().cacheKey()
    assert zen_tile.icon().cacheKey() == zen_mode.icon().cacheKey()

    refreshed_icon = QPixmap(16, 16)
    refreshed_icon.fill(QColor("green"))
    zen_mode.setIcon(QIcon(refreshed_icon))
    grid.refresh_source_icons()
    assert zen_tile.icon().cacheKey() == zen_mode.icon().cacheKey()

    positions = {
        action_id: grid.layout.getItemPosition(grid.layout.indexOf(button))
        for action_id, button in grid.buttons.items()
    }
    assert positions == {
        "dark": (0, 0, 1, 1),
        "zen": (0, 1, 1, 1),
        "standard": (0, 2, 1, 2),
    }

    grid.deleteLater()
    dark_mode.deleteLater()
    zen_mode.deleteLater()
    app.processEvents()


def test_power_quick_actions_keep_their_semantic_tile_style():
    app = _app()
    registry = QuickActionRegistry(
        {"quick_action_ids": ["power.sleep", "standard", "toggle"]},
        lambda _value: None,
    )
    registry.register(QuickActionSpec("power.sleep", "Sleep", lambda: None, severity="yellow"))
    registry.register(QuickActionSpec("standard", "Standard", lambda: None))
    registry.register(
        QuickActionSpec(
            "toggle",
            "Toggle",
            lambda: None,
            checked=lambda: False,
            set_checked=lambda _value: None,
        )
    )
    registry.finalize()
    grid = QuickActionsGrid(registry, lambda _widget, _text: None)

    power = grid.buttons["power.sleep"]
    assert power.property("quickActionSeverity") == "yellow"
    assert f"background-color: {styles.power_action_color('yellow').name()};" in power.styleSheet()
    assert "#c4a220" not in grid.buttons["standard"].styleSheet()
    assert grid.buttons["toggle"].property("quickActionToggle")

    grid.deleteLater()
    app.processEvents()


def test_live_theme_refresh_preserves_power_quick_action_severity():
    app = _app()
    root = QWidget()
    power = QPushButton("Shutdown", root)
    power.setProperty("styleFontSize", 13)
    power.setProperty("quickActionSeverity", "red")
    standard = QPushButton("Standard", root)
    standard.setProperty("styleFontSize", 13)
    danger_toggle = QPushButton("Disable All Confirmations On", root)
    danger_toggle.setProperty("styleFontSize", 13)
    danger_toggle.setProperty("dangerToggle", True)
    danger_toggle.setCheckable(True)
    danger_toggle.setChecked(True)

    class ThemeTarget:
        def __init__(self):
            self.apply_calls = 0

        def apply_theme(self):
            self.apply_calls += 1

    monitor_rules_page = ThemeTarget()

    controller = ApplicationThemeController(
        root=root,
        window_chrome=ThemeTarget(),
        navigation_shell=ThemeTarget(),
        refresh_master_backup_path=lambda: None,
        refresh_connected_drives_style=lambda: None,
        monitor_rules_page=monitor_rules_page,
    )
    try:
        controller.apply_theme(False)
        assert f"background-color: {styles.power_action_color('red').name()};" in power.styleSheet()
        assert f"background-color: {styles.themed_button_bg().name()};" in standard.styleSheet()
        assert f"background-color: {styles.power_action_color('red').name()};" in danger_toggle.styleSheet()

        controller.apply_theme(True)
        assert f"background-color: {styles.power_action_color('red').name()};" in power.styleSheet()
        assert f"background-color: {styles.themed_button_bg().name()};" in standard.styleSheet()
        assert f"background-color: {styles.power_action_color('red').name()};" in danger_toggle.styleSheet()
        assert monitor_rules_page.apply_calls == 2
    finally:
        styles.set_theme(True)
        root.deleteLater()
        app.processEvents()


def test_empty_grid_shows_registered_reset_button_only_when_no_actions_are_pinned():
    app = _app()
    registry = QuickActionRegistry({"quick_action_ids": []}, lambda _value: None)
    registry.register(QuickActionSpec("action", "Action", lambda: None))
    registry.finalize()
    grid = QuickActionsGrid(registry, lambda widget, text: QtTooltipManager(widget, text))

    assert grid.empty_state_label is not None
    assert grid.reset_defaults_button is not None
    assert registered_tooltip_text(grid.reset_defaults_button) == tooltip_text(
        "quick_actions_reset_defaults"
    )
    assert "border-radius" in grid.reset_defaults_button.styleSheet()
    assert grid.contextMenuPolicy() == Qt.ContextMenuPolicy.DefaultContextMenu

    registry.pin("action")
    app.processEvents()

    assert grid.empty_state_label is None
    assert grid.reset_defaults_button is None
    grid.deleteLater()


def test_empty_grid_reset_button_confirms_then_restores_default_actions(monkeypatch):
    app = _app()
    state = {"quick_action_ids": []}
    saves = []
    registry = QuickActionRegistry(state, lambda value: saves.append(list(value["quick_action_ids"])))
    for action_id in DEFAULT_QUICK_ACTION_IDS:
        registry.register(QuickActionSpec(action_id, action_id, lambda: None))
    registry.finalize()
    grid = QuickActionsGrid(registry, lambda _widget, _text: None)
    monkeypatch.setattr(
        QMessageBox,
        "exec",
        lambda _dialog: QMessageBox.StandardButton.Yes,
    )

    grid.reset_defaults_button.click()
    app.processEvents()

    assert registry.pinned_ids() == list(DEFAULT_QUICK_ACTION_IDS)
    assert saves[-1] == list(DEFAULT_QUICK_ACTION_IDS)
    assert list(grid.buttons) == list(DEFAULT_QUICK_ACTION_IDS)
    assert grid.reset_defaults_button is None
    grid.deleteLater()


def test_empty_grid_reset_confirmation_matches_frameless_popups(monkeypatch):
    app = _app()
    registry = QuickActionRegistry({"quick_action_ids": []}, lambda _value: None)
    registry.register(QuickActionSpec("action", "Action", lambda: None))
    registry.finalize()
    grid = QuickActionsGrid(registry, lambda _widget, _text: None)
    dialogs = []

    def capture_dialog(dialog):
        dialogs.append(dialog)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "exec", capture_dialog)

    grid.reset_defaults_button.click()
    app.processEvents()

    assert len(dialogs) == 1
    dialog = dialogs[0]
    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert not dialog.windowFlags() & Qt.WindowType.WindowTitleHint
    assert dialog._popup_corner_radius == 6
    assert dialog.styleSheet() == styles.message_box_style(radius=6)
    grid.deleteLater()


def test_toggle_and_disabled_state_stay_synchronized():
    app = _app()
    source = QPushButton("Feature Off")
    source.setCheckable(True)
    source.toggled.connect(lambda enabled: source.setText(f"Feature {'On' if enabled else 'Off'}"))
    registry = QuickActionRegistry({"quick_action_ids": ["feature"]}, lambda _value: None)
    registry.register_button("feature", "Feature", source, tooltip="Feature setting")
    registry.finalize()
    class Tooltip:
        text = ""

        def set_text(self, text):
            self.text = text

    grid = QuickActionsGrid(registry, lambda widget, text: Tooltip())
    tile = grid.buttons["feature"]

    tile.click()
    app.processEvents()
    assert source.isChecked()
    assert tile.isChecked()
    assert tile.text() == "Feature On"

    source.setEnabled(False)
    app.processEvents()
    assert not tile.isEnabled()
    assert tile.toolTip()
    grid.deleteLater()
    source.deleteLater()


def test_button_quick_action_inherits_its_registered_tooltip():
    _app()
    source = QPushButton("Action")
    manager = QtTooltipManager(source, "Useful action details")
    registry = QuickActionRegistry({"quick_action_ids": ["action"]}, lambda _value: None)

    registry.register_button("action", "Action", source)

    assert registry.spec("action").tooltip == "Useful action details"
    manager.deleteLater()
    source.deleteLater()


def test_dropdown_quick_actions_inherit_the_registered_group_tooltip():
    _app()
    combo = QComboBox()
    manager = QtTooltipManager(combo, "Useful group details")
    registry = QuickActionRegistry({"quick_action_ids": ["action"]}, lambda _value: None)

    registry.register_dropdown(
        combo,
        [QuickActionSpec("action", "Action", lambda: None)],
    )

    assert registry.spec("action").tooltip == "Useful group details"
    manager.deleteLater()
    combo.deleteLater()


def test_unavailable_action_adds_reason_then_clears_blank_tooltip():
    app = _app()
    source = QPushButton("Unavailable Action")
    source.setEnabled(False)
    registry = QuickActionRegistry({"quick_action_ids": ["unavailable"]}, lambda _value: None)
    registry.register_button("unavailable", "Unavailable Action", source)
    registry.finalize()

    class Tooltip:
        def __init__(self, text):
            self.text = text

        def set_text(self, text):
            self.text = text

    grid = QuickActionsGrid(registry, lambda widget, text: Tooltip(text))
    manager = grid.tooltip_managers["unavailable"]
    assert "unavailable" in manager.text.lower()

    source.setEnabled(True)
    app.processEvents()
    assert grid.buttons["unavailable"].isEnabled()
    assert manager.text == ""
    grid.deleteLater()
    source.deleteLater()


def test_source_context_menu_switches_between_pin_and_unpin():
    _app()
    source = QPushButton("Action")
    registry = QuickActionRegistry({"quick_action_ids": []}, lambda _value: None)
    registry.register_button("action", "Action", source)
    menu = registry.source_menu(source)
    seen = [menu.actions()[0].text()]
    assert "border-radius: 6px;" in menu.styleSheet()
    registry.pin("action")
    menu = registry.source_menu(source)
    seen.append(menu.actions()[0].text())
    assert "border-radius: 6px;" in menu.styleSheet()

    assert seen == ["Pin to Quick Actions", "Unpin from Quick Actions"]
    source.deleteLater()


def test_dropdown_context_menu_groups_individual_commands():
    _app()
    combo = QComboBox()
    registry = QuickActionRegistry({"quick_action_ids": ["second"]}, lambda _value: None)
    registry.register_dropdown(
        combo,
        [
            QuickActionSpec("first", "First Command", lambda: None),
            QuickActionSpec("second", "Second Command", lambda: None),
        ],
    )
    menu = registry.dropdown_menu(combo, ("first", "second"))
    seen = [action.text() for action in menu.actions()]
    assert "border-radius: 6px;" in menu.styleSheet()
    assert all(
        "border-radius: 6px;" in action.menu().styleSheet()
        for action in menu.actions()
    )

    assert seen == ["Pin to Quick Actions", "Unpin from Quick Actions"]
    menu.actions()[0].menu().actions()[0].trigger()
    assert registry.pinned_ids() == ["second", "first"]
    refreshed = registry.dropdown_menu(combo, ("first", "second"))
    refreshed.actions()[0].menu().actions()[1].trigger()
    assert registry.pinned_ids() == ["first"]
    combo.deleteLater()

from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

from resurface.ui.application_pages import QuickActionsGrid
from resurface.ui.quick_actions import (
    DEFAULT_QUICK_ACTION_IDS,
    QuickActionRegistry,
    QuickActionSpec,
)
from resurface.ui.tooltips import QtTooltipManager


def _app():
    return QApplication.instance() or QApplication([])


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
    grid._toggle_expanded()
    app.processEvents()
    assert list(grid.buttons) == ids
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
    seen = [registry.source_menu(source).actions()[0].text()]
    registry.pin("action")
    seen.append(registry.source_menu(source).actions()[0].text())

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

    assert seen == ["Pin to Quick Actions", "Unpin from Quick Actions"]
    menu.actions()[0].menu().actions()[0].trigger()
    assert registry.pinned_ids() == ["second", "first"]
    refreshed = registry.dropdown_menu(combo, ("first", "second"))
    refreshed.actions()[0].menu().actions()[1].trigger()
    assert registry.pinned_ids() == ["first"]
    combo.deleteLater()

import copy

import left_panel_gui
import main
from hotkeys import ACTION_LABELS
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QWidget,
)
from Shared.app_state_defaults import WINDOWS_RESURFACE_DEFAULTS


class FakeRuntime:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.configurations = []

    def configure(self, **settings):
        self.configurations.append(settings)

    def update_settings(self, **settings):
        self.calls.append(settings)

    def request_action(self, _action):
        pass

    def stop(self):
        pass


class FakeHotkeyManager:
    def __init__(self, _callback=None):
        self.calls = []

    def update_hotkeys(self, hotkeys, *, enabled):
        self.calls.append((hotkeys, enabled))

    def stop(self):
        pass


class FakeTrayManager:
    def __init__(self, _window=None):
        self.sync_calls = 0
        self.tray = None

    def create_tray_icon(self):
        pass

    def sync_screen_mover_action(self):
        self.sync_calls += 1


class FakeStyle:
    def unpolish(self, _widget):
        pass

    def polish(self, _widget):
        pass


class FakeCombo:
    def __init__(self):
        self.value = "off"
        self.persist_pressed = False

    def findData(self, value):
        return {"off": 0, "middle": 1}[value]

    def blockSignals(self, _blocked):
        pass

    def setCurrentIndex(self, index):
        self.value = {0: "off", 1: "middle"}[index]

    def setProperty(self, name, value):
        if name == "persistPressed":
            self.persist_pressed = value

    def style(self):
        return FakeStyle()


class FakeEdit:
    def __init__(self):
        self.cleared = False

    def blockSignals(self, _blocked):
        pass

    def clear(self):
        self.cleared = True


class FakeToggle:
    def __init__(self, checked=False):
        self.checked = checked
        self.text = ""

    def isChecked(self):
        return self.checked

    def blockSignals(self, _blocked):
        pass

    def setChecked(self, checked):
        self.checked = checked

    def setText(self, text):
        self.text = text


class FakeWindow:
    apply_screen_mover_settings = main.UtilityControlApp.apply_screen_mover_settings
    set_screen_mover_enabled = main.UtilityControlApp.set_screen_mover_enabled
    reset_screen_mover_settings = main.UtilityControlApp.reset_screen_mover_settings

    def __init__(self):
        self.state = {
            "title_bar_dock_enabled": False,
            "screen_mover_activation_button": "right",
            "mmb_activation_enabled": False,
            "screen_mover_keyboard_hotkeys": {
                "LEFT": "Ctrl+Left",
                "RIGHT": "",
            },
            "theme_dark": False,
        }
        self.screen_mover = FakeRuntime()
        self.hotkey_manager = FakeHotkeyManager()
        self.tray_manager = FakeTrayManager()
        self.screen_mover_enabled_btn = FakeToggle(False)
        self.screen_move_button_combo = FakeCombo()
        self.screen_mover_hotkey_edits = {
            "LEFT": FakeEdit(),
            "RIGHT": FakeEdit(),
        }


def _build_offscreen_window(monkeypatch, state, *, window_height=None):
    monkeypatch.setattr(main, "load_state", lambda: copy.deepcopy(state))
    monkeypatch.setattr(main, "save_state", lambda _state: None)
    monkeypatch.setattr(left_panel_gui, "save_state", lambda _state: None)
    monkeypatch.setattr(main, "ScreenMover", FakeRuntime)
    monkeypatch.setattr(main, "GlobalHotkeyManager", FakeHotkeyManager)
    monkeypatch.setattr(main, "TrayIconManager", FakeTrayManager)
    monkeypatch.setattr(main, "resolve_application_icon", lambda _window: QIcon())
    monkeypatch.setattr(
        main.UtilityControlApp,
        "_current_external_drives",
        lambda _self: set(),
    )
    monkeypatch.setattr(
        main.UtilityControlApp,
        "_set_main_window_topmost_state",
        lambda _self, _enabled: None,
    )
    monkeypatch.setattr(
        main.UtilityControlApp,
        "_apply_fixed_window_style",
        lambda _self: None,
    )
    monkeypatch.setattr(
        main.UtilityControlApp,
        "_register_session_notifications",
        lambda _self: None,
    )
    monkeypatch.setattr(
        main.UtilityControlApp,
        "run_recycle_bin_auto_cleanup",
        lambda _self: None,
    )
    if window_height is not None:
        monkeypatch.setattr(
            main.UtilityControlApp,
            "_resolve_window_height",
            lambda _self: window_height,
        )
    return main.UtilityControlApp()


def test_fixed_sidebar_shell_builds_ten_scrollable_pages(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        assert isinstance(window, QMainWindow)
        assert window.size().width() == 1000
        assert window.size().height() == 800
        assert window.minimumSize() == window.maximumSize()
        assert window.navigation_list.width() == 220
        assert window.navigation_list.count() == 10
        assert window.page_stack.count() == 10
        assert list(window.page_by_id) == [
            "overview",
            "user_interface",
            "screen_mover",
            "monitor_rules",
            "external_drives",
            "organising_utilities",
            "folder_utilities",
            "recycle_bin",
            "windows_utilities",
            "maintenance",
        ]
        assert len(window.page_scroll_areas) == 10
        assert all(
            isinstance(scroll, QScrollArea)
            and scroll.verticalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAsNeeded
            for scroll in window.page_scroll_areas.values()
        )
        assert not hasattr(window, "advanced_settings_toggle")
        assert not hasattr(window, "master_collapse_btn_left")
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_navigation_restores_valid_page_and_falls_back_to_overview(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["last_opened_page"] = "maintenance"
    window = _build_offscreen_window(monkeypatch, state)
    try:
        assert window.navigation_list.currentItem().data(Qt.ItemDataRole.UserRole) == "maintenance"
        window.navigate_to_page("screen_mover")
        assert window.state["last_opened_page"] == "screen_mover"
        assert window.page_stack.currentWidget() is window.page_by_id["screen_mover"]
        window.navigate_to_page("not-a-page")
        assert window.state["last_opened_page"] == "overview"
        assert window.page_stack.currentWidget() is window.page_by_id["overview"]
        assert not window.monitor_rules_add_button.isEnabled()
        assert "monitor_rules" not in window.state
        assert window.findChildren(QShortcut) == []
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_overview_status_and_folder_quick_action(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["title_bar_dock_enabled"] = False
    state["recycle_bin_auto_clean_enabled"] = True
    state["master_backup_output_path"] = r"C:\Backups"
    window = _build_offscreen_window(monkeypatch, state)
    window._overview_connected_drives = {"E:\\", "F:\\"}

    try:
        window.show()
        qt_app.processEvents()
        window.refresh_overview()
        assert window.overview_status_labels["screen_mover"].text() == "Off"
        assert window.overview_status_labels["drives"].text() == "2 connected"
        assert window.overview_status_labels["backup_path"].text() == r"C:\Backups"
        assert window.overview_status_labels["recycle"].text() == "On"

        overview = window.page_by_id["overview"]
        folder_action = next(
            button
            for button in overview.findChildren(QPushButton)
            if button.text() == "Create Desktop Folder"
        )
        folder_action.click()
        qt_app.processEvents()
        assert window.state["last_opened_page"] == "folder_utilities"
        assert window.page_stack.currentWidget() is window.page_by_id["folder_utilities"]
        assert window.folder_input.hasFocus()
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_borderless_title_bar_controls_preserve_window_lifecycle(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["advanced_panel_open"] = True
    minimize_calls = []
    monkeypatch.setattr(
        main.UtilityControlApp,
        "showMinimized",
        lambda window: minimize_calls.append(window),
    )
    window = _build_offscreen_window(monkeypatch, state)

    try:
        window.navigate_to_page("user_interface")
        window.show()
        qt_app.processEvents()

        def window_center_x(widget):
            position = widget.mapTo(window, QPoint(0, 0))
            return position.x() + (widget.width() // 2)

        def window_y(widget):
            return widget.mapTo(window, QPoint(0, 0)).y()

        assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert window.TITLE_BAR_HEIGHT == (
            window.TITLE_TEXT_ROW_HEIGHT + window.TITLE_CONTROL_ROW_HEIGHT
        )
        assert window.window_title_label.text() == "Windows Resurface"
        assert "font-size: 20px" in window.window_title_label.styleSheet()
        assert window.window_minimize_btn.parent() is window.window_title_bar
        assert window.window_close_btn.parent() is window.window_title_bar
        assert not window.window_minimize_btn.icon().isNull()
        assert not window.window_close_btn.icon().isNull()

        assert window_center_x(window.window_title_label) == window.width() // 2
        assert window_y(window.window_title_label) == 0
        assert window.window_title_label.height() == window.TITLE_TEXT_ROW_HEIGHT
        assert window_y(window.window_minimize_btn) == 0
        assert window_y(window.window_close_btn) == 0
        assert window.window_minimize_btn.height() == window.TITLE_TEXT_ROW_HEIGHT
        assert window.window_close_btn.height() == window.TITLE_TEXT_ROW_HEIGHT
        assert window.window_minimize_btn.x() > window.SIDEBAR_WIDTH
        assert window.window_close_btn.x() > window.window_minimize_btn.x()

        left_states = copy.deepcopy(window.state["left_section_states"])
        window.window_minimize_btn.click()
        assert minimize_calls == [window]

        window.apply_theme(False)
        assert "font-size: 18px" in window.window_minimize_btn.styleSheet()
        assert "font-size: 18px" in window.window_close_btn.styleSheet()
        assert window.state["left_section_states"] == left_states

        window.window_close_btn.click()
        qt_app.processEvents()
        assert not window.isVisible()

        shutdown_calls = []
        window.prepare_for_shutdown = lambda: shutdown_calls.append(True)
        window._quit_requested = True
        window.show()
        window.window_close_btn.click()
        assert shutdown_calls == [True]
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_live_theme_switch_preserves_blue_and_power_dropdown_roles(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        combos = window.findChildren(QComboBox)
        power_combo = next(combo for combo in combos if combo.property("powerActionStyle"))
        standard_combo = next(
            combo
            for combo in combos
            if not combo.property("powerActionStyle")
            and not combo.property("connectedDrivesFieldStyle")
        )

        for is_dark, standard_color, power_color in (
            (True, "#1c66c4", "#2b313c"),
            (False, "#2d73c8", "#46515f"),
        ):
            window.apply_theme(is_dark)

            assert f"background-color: {standard_color};" in standard_combo.styleSheet()
            assert f"background-color: {power_color};" in power_combo.styleSheet()
            assert f"background-color: {standard_color};" not in power_combo.styleSheet()

            sleep_row = power_combo.findText("Sleep")
            shutdown_row = power_combo.findText("Shutdown")
            sleep_background = power_combo.itemData(
                sleep_row,
                Qt.ItemDataRole.BackgroundRole,
            )
            shutdown_background = power_combo.itemData(
                shutdown_row,
                Qt.ItemDataRole.BackgroundRole,
            )

            assert isinstance(sleep_background, QColor)
            assert isinstance(shutdown_background, QColor)
            assert power_combo.itemData(
                sleep_row,
                Qt.ItemDataRole.ForegroundRole,
            ) == main.styles.contrasting_text_color(sleep_background)
            assert power_combo.itemData(
                shutdown_row,
                Qt.ItemDataRole.ForegroundRole,
            ) == main.styles.contrasting_text_color(shutdown_background)
    finally:
        main.styles.set_theme(True)
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_main_window_and_power_dropdown_are_wide_enough(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        window.navigate_to_page("user_interface")
        window.show()
        qt_app.processEvents()

        def window_x(widget):
            return widget.mapTo(window, QPoint(0, 0)).x()

        def button_with_text(text):
            return next(
                button
                for button in window.findChildren(QPushButton)
                if button.text() == text
            )

        def combo_with_placeholder(placeholder):
            return next(
                combo
                for combo in window.findChildren(QComboBox)
                if combo.currentText().strip() == placeholder
            )

        power_combo = next(
            combo
            for combo in window.findChildren(QComboBox)
            if combo.property("powerActionStyle")
        )
        compact_slot = power_combo.parent().layout().itemAtPosition(0, 0).widget()
        compact_buttons = sorted(
            compact_slot.findChildren(QPushButton),
            key=window_x,
        )

        left_column_x = window_x(button_with_text("Always on Top On"))
        right_column_x = window_x(power_combo)

        assert window.COLLAPSED_WIDTH == 1000
        assert window.width() == 1000
        assert window.height() == 800
        assert window.navigation_list.width() == 220
        assert window.page_stack.width() == 780
        assert 250 <= power_combo.width() <= 300
        assert power_combo.minimumWidth() == power_combo.width()
        assert power_combo.maximumWidth() == power_combo.width()

        for text in ("Always on Top On", "Maximize All On"):
            assert window_x(button_with_text(text)) == left_column_x

        for widget in (
            button_with_text("Tooltips On"),
            button_with_text("Minimize After Use On"),
        ):
            assert window_x(widget) == right_column_x
            assert widget.width() == 250

        assert window_x(compact_buttons[0]) == left_column_x
        assert compact_buttons[0].width() == 119
        assert compact_buttons[1].width() == 119
        assert window_x(compact_buttons[1]) == left_column_x + 131
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_page_controls_use_standard_sizes_centering_and_fitted_combo_text(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        window.show()
        qt_app.processEvents()

        standard_controls = [
            widget
            for widget in window.findChildren(QWidget)
            if widget.property("pageControlRole") == "standard"
        ]
        compact_controls = [
            widget
            for widget in window.findChildren(QWidget)
            if widget.property("pageControlRole") == "compact"
        ]
        wide_controls = [
            widget
            for widget in window.findChildren(QWidget)
            if widget.property("pageControlRole") == "wide"
        ]

        assert standard_controls
        assert all(
            widget.size().width() == 250 and widget.size().height() == 34
            for widget in standard_controls
        )
        assert compact_controls
        assert all(
            widget.size().width() == 119 and widget.size().height() == 34
            for widget in compact_controls
        )
        assert all(
            250 < widget.size().width() <= 300
            and widget.size().height() == 34
            for widget in wide_controls
        )

        for combo in window.findChildren(QComboBox):
            if combo.property("pageControlRole") not in {"standard", "wide"}:
                continue
            font_size = int(combo.property("styleFontSize") or 14)
            metrics = QFontMetrics(
                QFont(
                    combo.font().family().strip() or "Segoe UI",
                    max(1, round(font_size * 0.75)),
                )
            )
            collapsed_required = metrics.horizontalAdvance(
                combo.currentText().strip()
            ) + 58
            assert (
                collapsed_required <= combo.width()
                or combo.width() == 300
            )
            popup_width = int(combo.property("comboPopupWidth") or 0)
            assert popup_width == combo.view().minimumWidth()
            for row in range(combo.count()):
                item_text = combo.itemText(row)
                required = metrics.horizontalAdvance(item_text) + 42
                assert required <= popup_width or popup_width == 420
                assert combo.itemData(row, Qt.ItemDataRole.ToolTipRole) == item_text

        window._refresh_connected_drive_status_label(
            ("E:\\Example Removable Drive With A Long Volume Name",)
        )
        qt_app.processEvents()
        connected_combo = window.connected_drives_field
        connected_row = connected_combo.parentWidget()
        assert connected_row.width() == 250 + 12 + connected_combo.width()
        assert 250 <= connected_combo.width() <= 300
        assert connected_combo.itemData(
            0,
            Qt.ItemDataRole.ToolTipRole,
        ) == connected_combo.itemText(0)

        for label_name in ("PageTitle", "PageDescription", "PageSectionHeading"):
            labels = window.findChildren(QLabel, label_name)
            assert labels
            assert all(
                label.alignment() & Qt.AlignmentFlag.AlignHCenter
                for label in labels
            )

        marked_controls = standard_controls + compact_controls + wide_controls
        size_snapshot = {
            id(widget): (widget.width(), widget.height())
            for widget in marked_controls
        }
        active_page_id = window.navigation_list.currentItem().data(
            Qt.ItemDataRole.UserRole
        )
        for is_dark in (False, True):
            window.apply_theme(is_dark)
            qt_app.processEvents()
            assert window.navigation_list.currentItem().data(
                Qt.ItemDataRole.UserRole
            ) == active_page_id
            assert all(
                (widget.width(), widget.height()) == size_snapshot[id(widget)]
                for widget in marked_controls
            )

        for page_id in window.page_by_id:
            window.navigate_to_page(page_id)
            qt_app.processEvents()
            viewport = window.page_scroll_areas[page_id].viewport()
            grids = [
                widget
                for widget in window.page_by_id[page_id].findChildren(QWidget)
                if widget.property("centeredControlGrid")
            ]
            for grid in grids:
                grid_left = grid.mapTo(viewport, QPoint(0, 0)).x()
                grid_center = grid_left + (grid.width() / 2)
                assert abs(grid_center - (viewport.width() / 2)) <= 2

        folder_page = window.page_by_id["folder_utilities"]
        folder_creator = next(
            button
            for button in folder_page.findChildren(QPushButton)
            if button.text() == "Folder Creator"
        )
        folder_desktop = next(
            button
            for button in folder_page.findChildren(QPushButton)
            if button.text() == "Folder Desktop"
        )
        assert folder_creator.size().width() == folder_desktop.size().width() == 250
        assert folder_creator.mapTo(folder_page, QPoint()).y() < window.folder_input.mapTo(
            folder_page,
            QPoint(),
        ).y()
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_plug_notification_control_uses_simple_choices_and_stays_centered(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)
    saved_states = []
    monkeypatch.setattr(
        left_panel_gui,
        "save_state",
        lambda saved_state: saved_states.append(dict(saved_state)),
    )

    try:
        window.navigate_to_page("external_drives")
        window.show()
        qt_app.processEvents()

        notification_combo = next(
            combo
            for combo in window.findChildren(QComboBox)
            if combo.property("plugUnplugNotificationCombo")
        )
        notification_label = next(
            label
            for label in window.findChildren(QLabel)
            if label.text() == "Plug/unplug notifications"
        )
        leave_reminder_button = next(
            button
            for button in window.findChildren(QPushButton)
            if button.text().startswith("Drive Leave Reminder")
        )
        assert [
            notification_combo.itemText(row)
            for row in range(notification_combo.count())
        ] == ["Off", "On"]
        assert notification_combo.width() == (
            left_panel_gui.LeftPanelBuilder.RIGHT_CONTROL_COLUMN_WIDTH
        )
        assert notification_combo.height() == 34
        assert notification_label.width() == (
            left_panel_gui.LeftPanelBuilder.LEFT_CONTROL_COLUMN_WIDTH
        )

        external_viewport = window.page_scroll_areas["external_drives"].viewport()

        def assert_centered() -> None:
            control_row = notification_combo.parentWidget()
            row_left = control_row.mapTo(
                external_viewport,
                QPoint(),
            ).x()
            assert abs(
                row_left
                + (control_row.width() / 2)
                - (external_viewport.width() / 2)
            ) <= 2

        stable_width = notification_combo.width()
        assert window.state["usb_idle_enabled"] is True
        assert leave_reminder_button.isChecked() is True
        for selected_value in ("off", "on"):
            notification_combo.setCurrentIndex(
                notification_combo.findData(selected_value)
            )
            qt_app.processEvents()
            assert notification_combo.width() == stable_width
            assert window.state["usb_plug_notify_mode"] == selected_value
            assert window.state["usb_plug_enabled"] is (selected_value == "on")
            assert window.state["usb_idle_enabled"] is True
            assert_centered()
        assert [
            saved_state["usb_plug_notify_mode"] for saved_state in saved_states
        ] == ["off", "on"]

        for row in range(notification_combo.count()):
            assert notification_combo.itemData(
                row,
                Qt.ItemDataRole.ToolTipRole,
            ) == notification_combo.itemText(row)

        for is_dark in (False, True):
            window.apply_theme(is_dark)
            qt_app.processEvents()
            assert notification_combo.width() == stable_width
            assert_centered()
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_master_toggle_synchronizes_state_ui_runtime_and_tray(monkeypatch):
    saved_states = []
    monkeypatch.setattr(main, "save_state", lambda state: saved_states.append(dict(state)))
    window = FakeWindow()

    window.set_screen_mover_enabled(True)

    assert window.state["title_bar_dock_enabled"] is True
    assert window.screen_mover_enabled_btn.checked is True
    assert window.screen_mover_enabled_btn.text == "Screen Mover On"
    assert window.screen_mover.calls[-1] == {
        "title_bar_dock_enabled": True,
        "activation_button": "right",
        "force_running": True,
    }
    assert window.hotkey_manager.calls[-1] == (
        {"LEFT": "<ctrl>+<left>"},
        True,
    )
    assert window.tray_manager.sync_calls == 1
    assert saved_states[-1]["title_bar_dock_enabled"] is True


def test_reset_defaults_changes_only_screen_mover_settings(monkeypatch):
    monkeypatch.setattr(main, "save_state", lambda _state: None)
    window = FakeWindow()

    window.reset_screen_mover_settings()

    assert window.state["theme_dark"] is False
    assert window.state["title_bar_dock_enabled"] is True
    assert window.state["screen_mover_activation_button"] == "middle"
    assert window.state["mmb_activation_enabled"] is True
    assert all(
        value == ""
        for value in window.state["screen_mover_keyboard_hotkeys"].values()
    )
    assert window.screen_move_button_combo.value == "middle"
    assert window.screen_move_button_combo.persist_pressed is True
    assert all(edit.cleared for edit in window.screen_mover_hotkey_edits.values())
    assert window.screen_mover.calls[-1]["activation_button"] == "middle"
    assert window.screen_mover.calls[-1]["force_running"] is False


def test_real_screen_mover_section_builds_and_resets_offscreen(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["theme_dark"] = False
    state["screen_mover_activation_button"] = "right"
    state["screen_mover_keyboard_hotkeys"]["LEFT"] = "<ctrl>+<left>"

    window = _build_offscreen_window(monkeypatch, state)
    try:
        assert window.screen_mover_enabled_btn.isChecked()
        assert window.screen_move_button_combo.currentData() == "right"
        assert set(window.screen_mover_hotkey_edits) == {
            "FAR_LEFT",
            "LEFT",
            "RIGHT",
            "FAR_RIGHT",
            "MINIMIZE",
            "MAXIMIZE",
        }
        assert (
            window.screen_mover_hotkey_edits["LEFT"].keySequence().toString()
            == QKeySequence("Ctrl+Left").toString()
        )
        assert not window.screen_mover_shortcuts_container.isHidden()

        window.screen_mover_shortcuts_toggle_btn.click()
        assert window.screen_mover_shortcuts_container.isHidden()
        assert window.state["screen_mover_keyboard_shortcuts_open"] is False
        assert window.screen_mover_shortcuts_toggle_btn.text() == "▲"

        screen_section = next(
            section
            for section in window.left_sections
            if section.section_id == "screen_mover"
        )
        window._set_left_section_open(screen_section, False)
        window._set_left_section_open(screen_section, True)
        assert window.screen_mover_shortcuts_container.isHidden()

        window.screen_mover_shortcuts_toggle_btn.click()
        assert not window.screen_mover_shortcuts_container.isHidden()
        assert window.state["screen_mover_keyboard_shortcuts_open"] is True
        assert window.screen_mover_shortcuts_toggle_btn.text() == "▼"

        window.state["desktop_screenshot_last_dir"] = "unchanged"
        window.reset_screen_mover_settings()

        assert window.state["desktop_screenshot_last_dir"] == "unchanged"
        assert window.screen_move_button_combo.currentData() == "middle"
        assert all(
            edit.keySequence().isEmpty()
            for edit in window.screen_mover_hotkey_edits.values()
        )
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_screen_mover_shortcut_controls_align_with_primary_row(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["screen_mover_activation_button"] = "off"
    window = _build_offscreen_window(monkeypatch, state)

    try:
        window.navigate_to_page("screen_mover")
        window.show()
        qt_app.processEvents()

        controls_row = window.screen_mover_controls_row
        shortcuts_header = window.screen_mover_shortcuts_header
        shortcuts_container = window.screen_mover_shortcuts_container
        screen_page = window.page_by_id["screen_mover"]

        def assert_blocks_aligned() -> None:
            widgets = (controls_row, shortcuts_header, shortcuts_container)
            widths = {widget.width() for widget in widgets}
            left_edges = {
                widget.mapTo(screen_page, QPoint()).x() for widget in widgets
            }
            right_edges = {
                widget.mapTo(screen_page, QPoint()).x() + widget.width()
                for widget in widgets
            }
            assert len(widths) == 1
            assert len(left_edges) == 1
            assert len(right_edges) == 1

        assert_blocks_aligned()
        assert controls_row.width() == (
            window.screen_mover_enabled_btn.width()
            + 12
            + window.screen_move_button_combo.width()
        )
        assert shortcuts_header.y() >= controls_row.y() + controls_row.height()
        assert shortcuts_container.y() >= (
            shortcuts_header.y() + shortcuts_header.height()
        )

        shortcut_labels = [
            label
            for label in shortcuts_container.findChildren(QLabel)
            if label.text() in ACTION_LABELS.values()
        ]
        shortcut_edits = list(window.screen_mover_hotkey_edits.values())
        clear_buttons = [
            button
            for button in shortcuts_container.findChildren(QPushButton)
            if button.text() == "Clear"
        ]
        assert len(shortcut_labels) == len(ACTION_LABELS)
        assert len(shortcut_edits) == len(ACTION_LABELS)
        assert len(clear_buttons) == len(ACTION_LABELS)
        assert len({label.width() for label in shortcut_labels}) == 1
        assert all(label.width() >= label.sizeHint().width() for label in shortcut_labels)
        assert len({edit.width() for edit in shortcut_edits}) == 1
        assert all(edit.height() == 34 for edit in shortcut_edits)
        assert all(button.size().width() == 119 for button in clear_buttons)
        assert all(button.size().height() == 34 for button in clear_buttons)
        assert all(
            button.mapTo(shortcuts_container, QPoint()).x() + button.width()
            == shortcuts_container.width()
            for button in clear_buttons
        )

        assert window.screen_mover_reset_btn.size().width() == 250
        assert window.screen_mover_reset_btn.size().height() == 34
        reset_left = window.screen_mover_reset_btn.mapTo(
            shortcuts_container,
            QPoint(),
        ).x()
        assert reset_left == (shortcuts_container.width() - 250) // 2

        selection_widths = {}
        for button_value in ("off", "left", "middle", "right"):
            combo_index = window.screen_move_button_combo.findData(button_value)
            window.screen_move_button_combo.setCurrentIndex(combo_index)
            qt_app.processEvents()
            selection_widths[button_value] = controls_row.width()
            assert_blocks_aligned()
        narrow_value = min(selection_widths, key=selection_widths.get)
        wide_value = max(selection_widths, key=selection_widths.get)
        standard_width = selection_widths[narrow_value]
        assert selection_widths[wide_value] > standard_width
        window.screen_move_button_combo.setCurrentIndex(
            window.screen_move_button_combo.findData(wide_value)
        )
        qt_app.processEvents()
        assert controls_row.width() == selection_widths[wide_value]
        assert_blocks_aligned()

        for is_dark in (False, True):
            window.apply_theme(is_dark)
            qt_app.processEvents()
            assert_blocks_aligned()

        narrow_index = window.screen_move_button_combo.findData(narrow_value)
        window.screen_move_button_combo.setCurrentIndex(narrow_index)
        qt_app.processEvents()
        assert controls_row.width() == standard_width
        window.reset_screen_mover_settings()
        qt_app.processEvents()
        assert window.screen_move_button_combo.currentData() == "middle"
        assert controls_row.width() == (
            window.screen_mover_enabled_btn.width()
            + 12
            + window.screen_move_button_combo.width()
        )
        assert_blocks_aligned()
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_screen_mover_shortcuts_restore_collapsed_state_offscreen(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["screen_mover_keyboard_shortcuts_open"] = False
    window = _build_offscreen_window(monkeypatch, state)

    try:
        assert window.screen_mover_shortcuts_container.isHidden()
        assert window.screen_mover_shortcuts_toggle_btn.text() == "▲"
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()

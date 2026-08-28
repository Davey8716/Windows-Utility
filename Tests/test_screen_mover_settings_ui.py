import copy
import ctypes

from resurface.ui import application_window as main
from resurface.ui import left_panel_gui, styles
from resurface.ui import navigation_shell
from resurface.ui.window_chrome import CenteredTitleComboBox
from resurface.features.screen_mover.hotkeys import ACTION_LABELS
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
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
    monkeypatch.setattr(navigation_shell, "save_state", lambda _state: None)
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


def test_folder_to_desktop_starts_empty_and_saved_selection_populates_input(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["folder_to_desktop_name"] = "Legacy Name"
    monkeypatch.setattr(
        left_panel_gui,
        "load_saved_folder_names",
        lambda: ["Reports", "Invoices"],
    )
    window = _build_offscreen_window(monkeypatch, state)

    try:
        assert window.folder_input.text() == ""
        assert window.folder_name_combo.isEditable()
        folder_button = next(
            button
            for button in window.findChildren(QPushButton)
            if button.text() == "Folder To Desktop"
        )
        assert folder_button.property("lightModePlaceholderButton") is True
        assert [
            window.folder_name_combo.itemText(index)
            for index in range(window.folder_name_combo.count())
        ] == ["Reports", "Invoices"]
        window.folder_name_combo.setCurrentIndex(1)
        assert window.folder_input.text() == "Invoices"
        assert window.save_folder_name_toggle.isCheckable()
        assert not window.save_folder_name_toggle.isChecked()
        assert window.save_folder_name_toggle.width() == 250
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_native_window_corner_preference_uses_standard_dwm_rounding(monkeypatch):
    calls = []

    class FakeDwmApi:
        def DwmSetWindowAttribute(self, hwnd, attribute, value, value_size):
            preference = ctypes.cast(
                value,
                ctypes.POINTER(ctypes.c_int),
            ).contents.value
            calls.append((hwnd, attribute, preference, value_size))
            return 0

    class FakeWindll:
        dwmapi = FakeDwmApi()

    class Window:
        def winId(self):
            return 1234

    monkeypatch.setattr(main.ctypes, "windll", FakeWindll())

    main.UtilityControlApp._apply_native_window_corner_preference(Window())

    assert calls == [(1234, 33, 2, ctypes.sizeof(ctypes.c_int))]


def test_native_window_corner_preference_ignores_missing_dwm_api(monkeypatch):
    class FakeWindll:
        pass

    class Window:
        def winId(self):
            return 1234

    monkeypatch.setattr(main.ctypes, "windll", FakeWindll())

    main.UtilityControlApp._apply_native_window_corner_preference(Window())


def test_fixed_sidebar_shell_builds_scrollable_pages(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        assert isinstance(window, QMainWindow)
        assert window.size().width() == 1000
        assert window.size().height() == 800
        assert window.minimumSize() == window.maximumSize()
        assert window.navigation_list.width() == 220
        assert window.navigation_list.count() == 11
        assert window.page_stack.count() == 11
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
            "hover_window_controls",
        ]
        assert len(window.page_scroll_areas) == 11
        assert all(
            isinstance(scroll, QScrollArea)
            and scroll.verticalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAsNeeded
            for scroll in window.page_scroll_areas.values()
        )
        assert not hasattr(window, "advanced_settings_toggle")
        # assert not hasattr(window, "master_collapse_btn_left")
        assert not hasattr(window, "left_sections")
        assert not hasattr(window, "collapsible_sections")
        for obsolete_key in (
            "advanced_panel_open",
            "master_toggle_left",
            "master_toggle_right",
            "left_section_states",
            "right_section_states",
        ):
            assert obsolete_key not in WINDOWS_RESURFACE_DEFAULTS
        mounted_content = {
            "user_interface": window.left_page_contents["user_interface"],
            "screen_mover": window.left_page_contents["screen_mover"],
            "external_drives": window.right_tools_panel.drive_space_content,
            "windows_utilities": window.right_tools_panel.windows_utilities_content,
            "maintenance": window.right_tools_panel.maintenance_content,
        }
        assert all(
            window.page_by_id[page_id].isAncestorOf(content)
            for page_id, content in mounted_content.items()
        )
        hover_item = window.navigation_list.item(10)
        assert hover_item.text() == "Hover Window Controls"
        assert hover_item.data(Qt.ItemDataRole.UserRole) == "hover_window_controls"
        window.navigate_to_page("hover_window_controls")
        placeholder = window.page_by_id["hover_window_controls"].findChild(
            QFrame, "HoverWindowControlsPlaceholder"
        )
        assert placeholder is not None
        assert placeholder.findChild(
            QLabel, "HoverWindowControlsStatus"
        ).text() == "COMING SOON"
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
        assert window.monitor_rules_add_button.isEnabled()
        assert window.state["monitor_rules"] == []
        assert window.findChildren(QShortcut) == []
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()

def test_theme_and_zen_toggles_use_fluent_icons_and_preserve_zen_rollback(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["theme_dark"] = True
    state["desktop_zen_mode_enabled"] = False
    monkeypatch.setattr(
        main.UtilityActionsManager,
        "desktop_zen_mode_toggle",
        lambda _self, _enabled: True,
    )
    window = _build_offscreen_window(monkeypatch, state)

    try:
        window.show()
        qt_app.processEvents()

        theme_button = window.dark_mode_btn
        zen_button = window.desktop_zen_btn
        for button in (theme_button, zen_button):
            assert button.text() == ""
            assert not button.icon().isNull()
            assert button.iconSize().width() == button.iconSize().height() == 16

        dark_icon_key = theme_button.icon().cacheKey()
        dark_zen_icon_key = zen_button.icon().cacheKey()
        theme_button.setChecked(False)
        qt_app.processEvents()
        assert window.state["theme_dark"] is False
        assert theme_button.text() == ""
        assert theme_button.icon().cacheKey() != dark_icon_key
        assert zen_button.icon().cacheKey() != dark_zen_icon_key

        zen_off_icon_key = zen_button.icon().cacheKey()
        zen_button.setChecked(True)
        qt_app.processEvents()
        assert window.state["desktop_zen_mode_enabled"] is True
        assert zen_button.text() == ""
        assert zen_button.icon().cacheKey() != zen_off_icon_key

        monkeypatch.setattr(
            window.actions,
            "desktop_zen_mode_toggle",
            lambda _enabled: None,
        )
        monkeypatch.setattr(window, "_show_timed_message", lambda *_args: None)
        zen_button.setChecked(False)
        qt_app.processEvents()
        assert zen_button.isChecked()
        assert window.state["desktop_zen_mode_enabled"] is True
        assert zen_button.icon().cacheKey() != zen_off_icon_key
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
        summary = overview.findChild(QWidget, "OverviewSummary")
        quick_actions = next(
            widget
            for widget in overview.findChildren(QWidget)
            if widget.property("centeredControlGrid")
        )
        assert summary is not None
        assert summary.width() == quick_actions.width() == 512
        summary_center = summary.mapTo(overview, QPoint()).x() + (summary.width() / 2)
        actions_center = quick_actions.mapTo(overview, QPoint()).x() + (
            quick_actions.width() / 2
        )
        assert abs(summary_center - actions_center) <= 1

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
        assert "font-size: 25px" in window.window_title_label.styleSheet()
        assert window.window_minimize_btn.parent() is window.window_title_bar
        assert window.window_close_btn.parent() is window.window_title_bar
        assert not window.window_minimize_btn.icon().isNull()
        assert not window.window_close_btn.icon().isNull()

        assert window_center_x(window.window_title_label) == (
            window.page_stack.mapTo(window, QPoint(0, 0)).x()
            + (window.page_stack.width() // 2)
        )
        assert window_y(window.window_title_label) == window.TITLE_TEXT_TOP_PADDING
        assert window.window_title_label.height() == (
            window.TITLE_TEXT_ROW_HEIGHT - window.TITLE_TEXT_TOP_PADDING
        )
        assert window_y(window.window_minimize_btn) == 0
        assert window_y(window.window_close_btn) == 0
        assert window.window_minimize_btn.height() == window.TITLE_TEXT_ROW_HEIGHT
        assert window.window_close_btn.height() == window.TITLE_TEXT_ROW_HEIGHT
        assert window.window_minimize_btn.x() > window.SIDEBAR_WIDTH
        assert window.window_close_btn.x() > window.window_minimize_btn.x()

        window.window_minimize_btn.click()
        assert minimize_calls == [window]

        window.apply_theme(False)
        assert "font-size: 25px" in window.window_title_label.styleSheet()
        assert "font-size: 18px" in window.window_minimize_btn.styleSheet()
        assert "font-size: 18px" in window.window_close_btn.styleSheet()

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
        assert isinstance(power_combo, CenteredTitleComboBox)
        standard_combo = next(
            combo
            for combo in combos
            if not combo.property("powerActionStyle")
            and not combo.property("connectedDrivesFieldStyle")
        )

        for is_dark, standard_color, power_color in (
            (True, "#1c66c4", "#1a76d6"),
            (False, "#2d73c8", "#2a86e6"),
        ):
            window.apply_theme(is_dark)

            assert main.styles.power_action_title_color() == (
                main.styles.TEXT_LIGHT if is_dark else main.styles.theme_text_color()
            )
            assert main.styles.power_action_title_background_color() == QColor(
                power_color
            )

            assert f"background-color: {standard_color};" in standard_combo.styleSheet()
            assert f"background-color: {power_color};" in power_combo.styleSheet()
            assert f"background-color: {standard_color};" not in power_combo.styleSheet()

            sleep_row = power_combo.findText("Sleep")
            logout_row = power_combo.findText("Log out")
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
            if is_dark:
                assert power_combo.itemData(
                    sleep_row,
                    Qt.ItemDataRole.ForegroundRole,
                ) == main.styles.TEXT_LIGHT
                assert power_combo.itemData(
                    logout_row,
                    Qt.ItemDataRole.ForegroundRole,
                ) == main.styles.TEXT_LIGHT
                assert power_combo.itemData(
                    shutdown_row,
                    Qt.ItemDataRole.ForegroundRole,
                ) == main.styles.contrasting_text_color(shutdown_background)
            else:
                assert power_combo.itemData(
                    shutdown_row,
                    Qt.ItemDataRole.ForegroundRole,
                ) == QColor(0, 0, 0)
                assert power_combo.itemData(
                    sleep_row,
                    Qt.ItemDataRole.ForegroundRole,
                ) == main.styles.contrasting_text_color(sleep_background)
    finally:
        main.styles.set_theme(True)
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_cleanup_actions_use_native_theme_text(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    window = _build_offscreen_window(monkeypatch, copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS))

    try:
        cleanup_combo = next(
            combo
            for combo in window.findChildren(QComboBox)
            if combo.findText("Empty Recycle Bin") >= 0
        )
        empty_row = cleanup_combo.findText("Empty Recycle Bin")
        assert cleanup_combo.itemData(empty_row, Qt.ItemDataRole.ForegroundRole) is None
    finally:
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


def test_navigation_panel_border_aligns_with_active_page_title(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        window.show()
        qt_app.processEvents()

        for page_id in ("overview", "user_interface", "screen_mover"):
            window.navigate_to_page(page_id)
            qt_app.processEvents()
            current_page = window.page_stack.currentWidget()
            page_title = current_page.findChild(QLabel, "PageTitle")
            assert page_title is not None
            assert window.navigation_list.mapTo(window, QPoint(0, 0)).y() == (
                page_title.mapTo(window, QPoint(0, 0)).y()
            )
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
                or combo.property("pageControlRole") == "externalDrive"
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
        assert connected_row.width() == styles.EXTERNAL_DRIVES_CONTENT_WIDTH
        assert connected_combo.width() == styles.EXTERNAL_DRIVES_CONTROL_WIDTH
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
            if button.text() == "Folder To Desktop"
        )
        assert folder_creator.size().width() == folder_desktop.size().width() == 250
        folder_row = window.folder_name_combo.parentWidget()
        assert folder_creator.mapTo(folder_page, QPoint()).y() == (
            folder_row.mapTo(folder_page, QPoint()).y() + folder_row.height() + 16
        )
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_folder_utilities_places_creator_below_quick_folder_action(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        window.navigate_to_page("folder_utilities")
        window.show()
        qt_app.processEvents()

        folder_page = window.page_by_id["folder_utilities"]
        folder_creator = next(
            button
            for button in folder_page.findChildren(QPushButton)
            if button.text() == "Folder Creator"
        )
        folder_row = window.folder_name_combo.parentWidget()
        folder_desktop = folder_row.findChild(QPushButton)

        assert folder_desktop is not None
        assert folder_creator.width() == folder_desktop.width() == 250
        assert folder_creator.mapTo(folder_page, QPoint()).y() == (
            folder_row.mapTo(folder_page, QPoint()).y() + folder_row.height() + 16
        )
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
            if label.text() == "Plug/unplug notifications:"
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
        assert notification_combo.width() == styles.EXTERNAL_DRIVES_CONTROL_WIDTH
        assert notification_combo.height() == 34
        assert notification_label.width() == styles.EXTERNAL_DRIVES_CONTROL_WIDTH
        assert leave_reminder_button.width() == styles.EXTERNAL_DRIVES_CONTROL_WIDTH
        assert window.connected_drives_field.width() == styles.EXTERNAL_DRIVES_CONTROL_WIDTH
        assert notification_combo.parentWidget().width() == styles.EXTERNAL_DRIVES_CONTENT_WIDTH
        assert leave_reminder_button.parentWidget().width() == (
            styles.EXTERNAL_DRIVES_CONTENT_WIDTH
        )
        assert window.connected_drives_empty_label.x() < leave_reminder_button.x()

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
            reminder_row = leave_reminder_button.parentWidget()
            reminder_row_left = reminder_row.mapTo(
                external_viewport,
                QPoint(),
            ).x()
            assert abs(
                reminder_row_left
                + (reminder_row.width() / 2)
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

        window._refresh_connected_drive_status_label(
            ("E:\\Example Removable Drive With A Long Volume Name",)
        )
        qt_app.processEvents()
        assert window.connected_drives_field.width() == stable_width
        assert window.connected_drives_field.parentWidget().width() == (
            styles.EXTERNAL_DRIVES_CONTENT_WIDTH
        )

        for is_dark in (False, True):
            window.apply_theme(is_dark)
            qt_app.processEvents()
            assert notification_combo.width() == stable_width
            assert window.connected_drives_field.width() == stable_width
            assert leave_reminder_button.width() == stable_width
            assert_centered()
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_loose_labels_use_sidebar_surface_style_across_themes(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        labels = {
            label.text(): label
            for label in window.findChildren(QLabel)
            if label.property("surfaceLabelStyle")
        }
        surfaced = [
            labels["Delete items older than:"],
            window.backup_path_input,
            window.connected_drives_empty_label,
            labels["Plug/unplug notifications:"],
        ]
        original_sizes = [(label.width(), label.height()) for label in surfaced]

        assert len(surfaced) == 4
        assert all(label.property("surfaceLabelStyle") for label in surfaced)

        for is_dark in (False, True):
            window.apply_theme(is_dark)
            qt_app.processEvents()
            expected_background = styles.qcolor_css(styles.SURFACE_BG)
            expected_border = styles.qcolor_css(styles.SURFACE_BORDER)
            for label, original_size in zip(surfaced, original_sizes):
                assert f"background-color: {expected_background};" in label.styleSheet()
                assert f"border: 1px solid {expected_border};" in label.styleSheet()
                assert "border-radius: 8px;" in label.styleSheet()
                assert "padding: 0px 10px;" in label.styleSheet()
                assert (label.width(), label.height()) == original_size
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_maintenance_controls_and_output_share_the_inner_frame_width(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        window.navigate_to_page("maintenance")
        window.show()
        qt_app.processEvents()

        panel = window.right_tools_panel
        maintenance_content = panel.maintenance_content
        selectors = maintenance_content.findChildren(QComboBox)
        selector_grid = selectors[0].parentWidget()
        maintenance_page = window.page_by_id["maintenance"]

        assert len(selectors) == 4
        assert all(selector.width() == 238 for selector in selectors)
        assert selector_grid.width() == 488
        assert panel.sidebar_output_container.width() == 488
        assert panel.sidebar_output.width() == 488
        assert panel.sidebar_output_container.height() == 285
        assert panel.sidebar_output_clear_btn.text() == "Clear Log"

        grid_left = selector_grid.mapTo(maintenance_page, QPoint()).x()
        output_left = panel.sidebar_output_container.mapTo(
            maintenance_page,
            QPoint(),
        ).x()
        assert grid_left == output_left
        assert grid_left + selector_grid.width() == (
            output_left + panel.sidebar_output_container.width()
        )
        grid_bottom = selector_grid.mapTo(maintenance_page, QPoint()).y() + (
            selector_grid.height()
        )
        output_top = panel.sidebar_output_container.mapTo(
            maintenance_page,
            QPoint(),
        ).y()
        assert output_top - grid_bottom == 16

        clear_button_pos = panel.sidebar_output_clear_btn.mapTo(
            maintenance_page,
            QPoint(),
        )
        output_bottom = output_top + panel.sidebar_output_container.height()
        assert clear_button_pos.x() == output_left
        assert clear_button_pos.y() - output_bottom == 16

        panel._set_sidebar_output_context("Flush DNS")
        panel.sidebar_output.setPlainText("Output to clear")
        panel.sidebar_output_clear_btn.click()
        assert panel.sidebar_output.toPlainText() == "Dns output log cleared."

        for is_dark in (False, True):
            window.apply_theme(is_dark)
            qt_app.processEvents()
            assert panel.sidebar_output_clear_btn.styleSheet() == (
                styles.organizing_button_style(font_size=14)
            )
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_external_drive_controls_and_output_share_the_inner_frame_width(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        window.navigate_to_page("external_drives")
        window.show()
        qt_app.processEvents()

        panel = window.right_tools_panel
        drive_page = window.page_by_id["external_drives"]
        button_row = panel.btn_this_pc.parentWidget()

        assert panel.btn_this_pc.width() == styles.EXTERNAL_DRIVES_CONTROL_WIDTH
        assert panel.btn_storage_sense.width() == styles.EXTERNAL_DRIVES_CONTROL_WIDTH
        assert button_row.width() == styles.EXTERNAL_DRIVES_CONTENT_WIDTH
        assert panel.drive_space_list.width() == styles.EXTERNAL_DRIVES_CONTENT_WIDTH
        assert panel.drive_space_list.height() == 120

        button_row_left = button_row.mapTo(drive_page, QPoint()).x()
        output_left = panel.drive_space_list.mapTo(drive_page, QPoint()).x()
        assert button_row_left == output_left
        assert button_row_left + button_row.width() == (
            output_left + panel.drive_space_list.width()
        )
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_screen_mover_toggle_synchronizes_state_ui_runtime_and_tray(monkeypatch):
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


def test_screen_mover_shortcut_fields_keep_surface_style_after_restart_and_theme_refresh(
    monkeypatch,
):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["theme_dark"] = False

    def assert_shortcut_field_style(window, is_dark: bool) -> None:
        expected_background = styles.qcolor_css(styles.themed_surface_field_bg())
        expected_border = styles.qcolor_css(styles.themed_surface_field_border())

        for edit in window.screen_mover_hotkey_edits.values():
            assert edit.objectName() == "ScreenMoverShortcutEdit"
            assert "QKeySequenceEdit#ScreenMoverShortcutEdit" in edit.styleSheet()
            assert (
                "QKeySequenceEdit#ScreenMoverShortcutEdit QLineEdit"
                in edit.styleSheet()
            )
            assert f"background-color: {expected_background};" in edit.styleSheet()
            assert f"border: 2px solid {expected_border};" in edit.styleSheet()
            internal_edits = edit.findChildren(QLineEdit)
            assert len(internal_edits) == 1
            assert internal_edits[0].objectName() == "qt_keysequenceedit_lineedit"
            assert internal_edits[0].styleSheet() == ""
            image = edit.grab().toImage()
            assert image.pixelColor(
                image.width() // 2,
                image.height() // 2,
            ).name() == expected_background

        assert styles.THEME_IS_DARK is is_dark

    for _ in range(2):
        window = _build_offscreen_window(monkeypatch, state)
        try:
            window.navigate_to_page("screen_mover")
            window.show()
            qt_app.processEvents()
            assert_shortcut_field_style(window, False)

            for is_dark in (True, False):
                window.apply_theme(is_dark)
                qt_app.processEvents()
                assert_shortcut_field_style(window, is_dark)
        finally:
            window._quit_requested = True
            window.close()
            window.deleteLater()
            qt_app.processEvents()


def test_screen_mover_shortcuts_have_balanced_heading_spacing(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        window.navigate_to_page("screen_mover")
        window.show()
        qt_app.processEvents()

        controls_row = window.screen_mover_controls_row
        shortcuts_header = window.screen_mover_shortcuts_header
        shortcuts_container = window.screen_mover_shortcuts_container
        assert shortcuts_header.y() - (
            controls_row.y() + controls_row.height()
        ) == 16
        assert shortcuts_container.y() - (
            shortcuts_header.y() + shortcuts_header.height()
        ) == 16
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()

import copy
import ctypes

from resurface.ui import application_window as main
from resurface.ui import application_pages, styles
from resurface.ui.pages import folder_utilities_page
from resurface.ui.window_chrome import CenteredTitleComboBox
from resurface.ui.tooltips import format_tooltip_text
from resurface.features.screen_mover.hotkeys import ACTION_LABELS
from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
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
        self.capture_calls = []

    def update_hotkeys(self, hotkeys):
        self.calls.append(hotkeys)

    def set_capture_active(self, active):
        self.capture_calls.append(bool(active))

    def stop(self):
        pass


class FakeHoverWindowControlsService(QObject):
    settings_changed = Signal(bool, bool, int)

    def __init__(self, state, _save_state, parent=None, **_kwargs):
        super().__init__(parent)
        self.enabled = bool(state.get("hover_window_controls_enabled", True))
        self.taskbar_restore_enabled = bool(
            state.get("hover_taskbar_restore_enabled", True)
        )
        self.dwell_ms = int(state.get("hover_window_controls_dwell_ms", 750))
        self.taskbar_restore_available = False
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def has_export_changes(self):
        return False

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.settings_changed.emit(
            self.enabled,
            self.taskbar_restore_enabled,
            self.dwell_ms,
        )

    def set_taskbar_restore_enabled(self, enabled):
        self.taskbar_restore_enabled = bool(enabled)
        self.settings_changed.emit(
            self.enabled,
            self.taskbar_restore_enabled,
            self.dwell_ms,
        )

    def set_dwell_ms(self, dwell_ms):
        self.dwell_ms = int(dwell_ms)
        self.settings_changed.emit(
            self.enabled,
            self.taskbar_restore_enabled,
            self.dwell_ms,
        )


class FakeTrayManager:
    def __init__(self, _window=None):
        self.tray = None

    def create_tray_icon(self):
        pass

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
    reset_screen_mover_settings = main.UtilityControlApp.reset_screen_mover_settings

    def __init__(self):
        self.state = {
            "screen_mover_keyboard_hotkeys": {
                "LEFT": "Ctrl+Left",
                "RIGHT": "",
            },
            "theme_dark": False,
        }
        self.hotkey_manager = FakeHotkeyManager()
        self.screen_mover_hotkey_edits = {
            "LEFT": FakeEdit(),
            "RIGHT": FakeEdit(),
        }
        self.screen_mover_settings_controller = main.ScreenMoverSettingsController(
            state=self.state,
            hotkey_manager=self.hotkey_manager,
            save_state=main.save_state,
            settings_page=lambda: None,
            legacy_hotkey_edits=lambda: self.screen_mover_hotkey_edits,
            refresh_overview=lambda: None,
        )


def _build_offscreen_window(
    monkeypatch,
    state,
    *,
    window_height=None,
    application_save_state=None,
):
    state = copy.deepcopy(state)
    monkeypatch.setattr(main, "load_state", lambda: copy.deepcopy(state))
    monkeypatch.setattr(main, "save_state", lambda _state: None)
    monkeypatch.setattr(
        main, "import_standalone_data", lambda _state, **_kwargs: False
    )
    monkeypatch.setattr(
        application_pages,
        "save_state",
        application_save_state or (lambda _state: None),
    )
    monkeypatch.setattr(main, "GlobalHotkeyManager", FakeHotkeyManager)
    monkeypatch.setattr(
        main, "HoverWindowControlsService", FakeHoverWindowControlsService
    )
    monkeypatch.setattr(main, "TrayIconManager", FakeTrayManager)
    monkeypatch.setattr(main, "resolve_application_icon", lambda _window: QIcon())
    monkeypatch.setattr(main.DriveMonitor, "start", lambda _self: None)
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
    monkeypatch.setattr(main.WindowsSessionEventAdapter, "register", lambda _self: None)
    monkeypatch.setattr(main.RecycleBinActionsController, "run_auto_cleanup", lambda _self: None)
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
        folder_utilities_page,
        "load_saved_folder_names",
        lambda: ["Reports", "Invoices"],
    )
    window = _build_offscreen_window(monkeypatch, state)

    try:
        page = window.pages.folder_utilities_page
        assert page._input.text() == ""
        assert page._names.isEditable()
        folder_button = next(
            button
            for button in window.findChildren(QPushButton)
            if button.text() == "Folder To Desktop"
        )
        assert folder_button.property("lightModePlaceholderButton") is True
        assert [
            page._names.itemText(index)
            for index in range(page._names.count())
        ] == ["Reports", "Invoices"]
        page._names.setCurrentIndex(1)
        assert page._input.text() == "Invoices"
        assert not page._save_name.isCheckable()
        assert not page._save_name.isEnabled()
        assert not page._save_name.isChecked()
        assert page._save_name.width() == 250
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
        shell = window.navigation_shell
        assert shell.navigation_list.width() == 220
        assert shell.navigation_list.count() == 12
        assert shell.page_stack.count() == 12
        assert list(shell.page_by_id) == [
            "overview",
            "quick_actions",
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
        assert len(shell.page_scroll_areas) == 12
        assert all(
            isinstance(scroll, QScrollArea)
            for scroll in shell.page_scroll_areas.values()
        )
        assert shell.page_scroll_areas["monitor_rules"].verticalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        assert all(
            scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
            for page_id, scroll in shell.page_scroll_areas.items()
            if page_id != "monitor_rules"
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
            "user_interface": window.pages.user_interface_page,
            "screen_mover": window.pages.screen_mover_settings_page,
            "external_drives": window.pages.drive_space_page,
            "windows_utilities": window.pages.windows_utilities_page,
            "maintenance": window.pages.maintenance_page,
        }
        assert not hasattr(window, "right_tools_panel")
        assert not hasattr(window, "left_page_contents")
        assert hasattr(window, "hover_window_controls")
        assert all(
            shell.page_by_id[page_id].isAncestorOf(content)
            for page_id, content in mounted_content.items()
        )
        hover_item = shell.navigation_list.item(11)
        assert hover_item.text() == "Hover Window Controls"
        assert hover_item.data(Qt.ItemDataRole.UserRole) == "hover_window_controls"
        window.navigate_to_page("hover_window_controls")
        hover_page = window.pages.hover_window_controls_page
        assert hover_page.enabled_button.text() == "Hover Controls On"
        assert hover_page.taskbar_restore_button.text() == "Taskbar Restoration On"
        assert not hasattr(hover_page, "caption_controls_button")
        assert hover_page.dwell_combo.currentData() == 750
        assert hover_page.calibrate_button.text() == "Calibrate Application…"
        assert hover_page.import_button.text() == "Import Hover Data…"
        assert not hasattr(hover_page, "taskbar_status")
        assert not hover_page.taskbar_restore_button.isEnabled()
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_hover_controls_primary_toggle_paints_complete_edges_and_keeps_alignment(
    monkeypatch,
):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        window.navigate_to_page("hover_window_controls")
        window.show()
        qt_app.processEvents()

        page = window.pages.hover_window_controls_page
        toggle_row = page.enabled_button.parentWidget()
        assert toggle_row.width() == page.CONTROL_ROW_WIDTH
        assert page.enabled_button.x() == 0
        assert page.taskbar_restore_button.x() == (
            page.enabled_button.x()
            + page.enabled_button.width()
            + page.CONTROL_COLUMN_GAP
        )
        assert type(page.enabled_button) is QPushButton
        assert type(page.taskbar_restore_button) is QPushButton
        assert page.enabled_button.property("customPaintedButton") is None
        assert page.taskbar_restore_button.property("customPaintedButton") is None
        assert page.enabled_button.styleSheet() == page.taskbar_restore_button.styleSheet()

        hover_content = window.navigation_shell.page_by_id["hover_window_controls"]
        toggle_left = page.enabled_button.mapTo(hover_content, QPoint()).x()
        toggle_right = (
            page.taskbar_restore_button.mapTo(hover_content, QPoint()).x()
            + page.taskbar_restore_button.width()
        )
        action_left = page.calibrate_button.mapTo(hover_content, QPoint()).x()
        action_right = (
            page.export_button.mapTo(hover_content, QPoint()).x()
            + page.export_button.width()
        )
        assert toggle_left == action_left
        assert toggle_right == action_right

        def assert_matching_toggle_paint(
            expected_background: QColor | None,
            *,
            is_dark: bool,
        ) -> None:
            hover_image = page.enabled_button.grab().toImage()
            taskbar_image = page.taskbar_restore_button.grab().toImage()
            center_y = hover_image.height() // 2
            hover_sample = hover_image.pixelColor(18, center_y)
            taskbar_sample = taskbar_image.pixelColor(18, center_y)
            artifact_color = QColor(0, 0, 0) if is_dark else QColor(255, 255, 255)
            assert page.enabled_button.styleSheet() == page.taskbar_restore_button.styleSheet()
            assert hover_sample == taskbar_sample
            if expected_background is not None:
                assert hover_sample == expected_background
            assert [
                hover_image.pixelColor(0, y)
                for y in range(hover_image.height())
            ] == [
                taskbar_image.pixelColor(0, y)
                for y in range(taskbar_image.height())
            ]
            hover_guarded_left_edge = [
                hover_image.pixelColor(x, y)
                for x in range(8)
                for y in range(hover_image.height())
            ]
            taskbar_guarded_left_edge = [
                taskbar_image.pixelColor(x, y)
                for x in range(8)
                for y in range(taskbar_image.height())
            ]
            assert artifact_color not in hover_guarded_left_edge
            assert artifact_color not in taskbar_guarded_left_edge

        for is_dark in (False, True):
            window.apply_theme(is_dark)
            page.taskbar_restore_button.setEnabled(True)
            assert page.enabled_button.styleSheet() == page.taskbar_restore_button.styleSheet()
            page.enabled_button.setAttribute(
                Qt.WidgetAttribute.WA_UnderMouse,
                False,
            )
            page.taskbar_restore_button.setAttribute(
                Qt.WidgetAttribute.WA_UnderMouse,
                False,
            )
            page.enabled_button.setChecked(True)
            page.taskbar_restore_button.setChecked(True)
            page.enabled_button.setDown(False)
            page.taskbar_restore_button.setDown(False)
            page.enabled_button.setEnabled(True)
            qt_app.processEvents()
            assert_matching_toggle_paint(styles.themed_button_pressed(), is_dark=is_dark)

            page.enabled_button.setAttribute(
                Qt.WidgetAttribute.WA_UnderMouse,
                True,
            )
            page.taskbar_restore_button.setAttribute(
                Qt.WidgetAttribute.WA_UnderMouse,
                True,
            )
            qt_app.processEvents()
            assert_matching_toggle_paint(
                None,
                is_dark=is_dark,
            )

            page.enabled_button.setChecked(False)
            page.taskbar_restore_button.setChecked(False)
            qt_app.processEvents()
            assert_matching_toggle_paint(None, is_dark=is_dark)

            page.enabled_button.setAttribute(
                Qt.WidgetAttribute.WA_UnderMouse,
                False,
            )
            page.taskbar_restore_button.setAttribute(
                Qt.WidgetAttribute.WA_UnderMouse,
                False,
            )
            qt_app.processEvents()
            assert_matching_toggle_paint(styles.themed_button_bg(), is_dark=is_dark)

            page.enabled_button.setDown(True)
            page.taskbar_restore_button.setDown(True)
            qt_app.processEvents()
            assert_matching_toggle_paint(styles.themed_button_pressed(), is_dark=is_dark)
            page.enabled_button.setDown(False)
            page.taskbar_restore_button.setDown(False)

            page.enabled_button.setEnabled(False)
            page.taskbar_restore_button.setEnabled(False)
            qt_app.processEvents()
            disabled_hover_image = page.enabled_button.grab().toImage()
            disabled_taskbar_image = page.taskbar_restore_button.grab().toImage()
            center_y = disabled_hover_image.height() // 2
            disabled_artifact_color = (
                QColor(0, 0, 0) if is_dark else QColor(255, 255, 255)
            )
            disabled_hover_guarded_left_edge = [
                disabled_hover_image.pixelColor(x, y)
                for x in range(8)
                for y in range(disabled_hover_image.height())
            ]
            disabled_taskbar_guarded_left_edge = [
                disabled_taskbar_image.pixelColor(x, y)
                for x in range(8)
                for y in range(disabled_taskbar_image.height())
            ]
            assert disabled_artifact_color not in disabled_hover_guarded_left_edge
            assert disabled_artifact_color not in disabled_taskbar_guarded_left_edge
            assert disabled_hover_image.pixelColor(18, center_y) == (
                styles.themed_button_disabled_bg()
            )
            assert disabled_taskbar_image.pixelColor(18, center_y) == (
                styles.themed_button_disabled_bg()
            )
            assert [
                disabled_hover_image.pixelColor(0, y)
                for y in range(disabled_hover_image.height())
            ] == [
                disabled_taskbar_image.pixelColor(0, y)
                for y in range(disabled_taskbar_image.height())
            ]
            page.enabled_button.setEnabled(True)
            page.taskbar_restore_button.setEnabled(True)

            page.enabled_button.setChecked(True)
            assert page.enabled_button.isChecked()
            assert page.enabled_button.width() == styles.PAGE_CONTROL_WIDTH
            assert page.enabled_button.height() == styles.PAGE_CONTROL_HEIGHT
            assert page.enabled_button.mapTo(hover_content, QPoint()).x() == action_left

        emitted = []
        page.enabled_changed.connect(emitted.append)
        page.enabled_button.setChecked(False)
        QTest.mouseClick(
            page.enabled_button,
            Qt.MouseButton.LeftButton,
            pos=page.enabled_button.rect().center(),
        )
        qt_app.processEvents()
        assert emitted[-1] is True
        assert page.enabled_button.text() == "Hover Controls On"
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_page_composer_builds_widgets_in_their_final_hosts(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    window = _build_offscreen_window(
        monkeypatch, copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    )
    page_ids = {
        "overview_page": "overview",
        "quick_actions_page": "quick_actions",
        "user_interface_page": "user_interface",
        "screen_mover_settings_page": "screen_mover",
        "monitor_rules_page": "monitor_rules",
        "external_drives_page": "external_drives",
        "drive_space_page": "external_drives",
        "organising_utilities_page": "organising_utilities",
        "folder_utilities_page": "folder_utilities",
        "recycle_bin_page": "recycle_bin",
        "windows_utilities_page": "windows_utilities",
        "maintenance_page": "maintenance",
        "hover_window_controls_page": "hover_window_controls",
    }
    try:
        assert not hasattr(window, "left_page_contents")
        for alias in (
            "navigation_sidebar",
            "navigation_list",
            "version_label",
            "page_stack",
            "page_registry",
            "page_by_id",
            "page_content_layouts",
            "page_scroll_areas",
            *page_ids,
            "overview_status_labels",
            "monitor_rules_add_button",
        ):
            assert not hasattr(window, alias)
        for attribute, page_id in page_ids.items():
            page = getattr(window.pages, attribute)
            assert page.parentWidget() is window.navigation_shell.content_parent(page_id)
        external_host = window.navigation_shell.content_parent("external_drives")
        assert external_host.isAncestorOf(window.pages.external_drives_page)
        assert external_host.isAncestorOf(window.pages.drive_space_page)
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
        shell = window.navigation_shell
        assert shell.navigation_list.currentItem().data(Qt.ItemDataRole.UserRole) == "maintenance"
        window.navigate_to_page("screen_mover")
        assert window.state["last_opened_page"] == "screen_mover"
        assert shell.page_stack.currentWidget() is shell.page_by_id["screen_mover"]
        window.navigate_to_page("not-a-page")
        assert window.state["last_opened_page"] == "overview"
        assert shell.page_stack.currentWidget() is shell.page_by_id["overview"]
        assert window.pages.monitor_rules_page.add_button.isEnabled()
        assert window.state["monitor_rules"] == []
        assert window.findChildren(QShortcut) == []
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_quick_actions_page_can_be_restored_between_sessions(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["last_opened_page"] = "quick_actions"
    window = _build_offscreen_window(monkeypatch, state)
    try:
        assert window.state["last_opened_page"] == "quick_actions"
        assert window.navigation_shell.page_stack.currentWidget() is window.navigation_shell.page_by_id["quick_actions"]
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_navigation_saves_each_visited_page_immediately(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    saved_states = []

    def capture_save(saved_state):
        saved_states.append(copy.deepcopy(saved_state))

    window = _build_offscreen_window(monkeypatch, state)
    monkeypatch.setattr(main, "save_state", capture_save)
    try:
        for page_id in (
            "screen_mover",
            "maintenance",
            "folder_utilities",
            "overview",
        ):
            window.navigate_to_page(page_id)

        assert [saved["last_opened_page"] for saved in saved_states] == [
            "screen_mover",
            "maintenance",
            "folder_utilities",
            "overview",
        ]
        assert window.state["last_opened_page"] == "overview"
        assert (
            window.navigation_shell.page_stack.currentWidget()
            is window.navigation_shell.page_by_id["overview"]
        )

        window.navigate_to_page("maintenance")
        assert saved_states[-1]["last_opened_page"] == "maintenance"

        window.navigate_to_page("not-a-page")
        assert saved_states[-1]["last_opened_page"] == "overview"
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_overview_refreshes_once_per_navigation(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    window = _build_offscreen_window(
        monkeypatch,
        copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS),
    )
    refresh_calls = []
    window.refresh_overview = lambda: refresh_calls.append(True)
    try:
        window.navigate_to_page("maintenance")
        window.navigate_to_page("overview")
        assert len(refresh_calls) == 1

        refresh_calls.clear()
        window.navigate_to_page("not-a-page")
        assert len(refresh_calls) == 1
        assert window.state["last_opened_page"] == "overview"
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

        theme_button = window.pages.user_interface_page._dark_mode_button
        zen_button = window.pages.user_interface_page._desktop_zen_button
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


def test_overview_status_and_separate_configurable_quick_actions(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["screen_mover_keyboard_hotkeys"]["LEFT"] = "<ctrl>+<left>"
    state["screen_mover_keyboard_hotkeys"]["RIGHT"] = "<ctrl>+<right>"
    state["recycle_bin_auto_clean_enabled"] = True
    state["recycle_bin_age_rule_days"] = 14
    state["master_backup_output_path"] = r"C:\Backups"
    state["monitor_rules"] = [
        {"enabled": True},
        {"enabled": False},
        {"enabled": True},
    ]
    state["hover_window_controls_enabled"] = False
    state["hover_taskbar_restore_enabled"] = True
    state["hover_window_controls_dwell_ms"] = 1_250
    window = _build_offscreen_window(monkeypatch, state)
    window._overview_connected_drives = {"E:\\", "F:\\"}

    try:
        window.show()
        qt_app.processEvents()
        window.refresh_overview()
        status_labels = window.pages.overview_page.status_labels
        assert status_labels["quick_actions"].text() == "4 pinned"
        assert status_labels["user_interface"].text() == (
            "Dark mode · Desktop Zen Off · Always on Top On"
        )
        assert status_labels["screen_mover"].text() == "2 shortcuts configured"
        assert status_labels["monitor_rules"].text() == "2 of 3 enabled"
        assert status_labels["drives"].text() == (
            "2 connected · Leave reminder On · Notifications On"
        )
        assert status_labels["backup_path"].text() == r"C:\Backups"
        assert status_labels["recycle"].text() == (
            "Auto-clean On · Items older than 14 days"
        )
        assert status_labels["hover_controls"].text() == (
            "Off · 1,250 ms dwell · Taskbar restoration On"
        )

        assert all(
            label.textInteractionFlags()
            & Qt.TextInteractionFlag.TextSelectableByMouse
            for label in status_labels.values()
        )

        overview = window.navigation_shell.page_by_id["overview"]
        quick_actions_page = window.navigation_shell.page_by_id["quick_actions"]
        summary = overview.findChild(QWidget, "OverviewSummary")
        quick_actions = quick_actions_page.findChild(QWidget, "QuickActionsGrid")
        overview_scroll = window.navigation_shell.page_scroll_areas["overview"]
        assert summary is not None
        assert quick_actions is not None
        assert overview.findChild(QWidget, "QuickActionsGrid") is None
        assert summary.width() == quick_actions.width() == 512
        assert overview_scroll.widgetResizable()
        assert overview_scroll.verticalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        assert quick_actions.tooltip_managers
        assert all(
            manager.text.strip()
            for manager in quick_actions.tooltip_managers.values()
        )

        window.state.update(
            {
                "quick_action_ids": [],
                "theme_dark": False,
                "desktop_zen_mode_enabled": True,
                "main_always_on_top_enabled": False,
                "screen_mover_keyboard_hotkeys": {},
                "monitor_rules": [],
                "usb_idle_enabled": False,
                "usb_plug_notify_mode": "off",
                "recycle_bin_auto_clean_enabled": False,
                "hover_window_controls_enabled": True,
                "hover_taskbar_restore_enabled": False,
                "hover_window_controls_dwell_ms": 500,
            }
        )
        window._overview_connected_drives = set()
        window.navigate_to_page("overview")
        qt_app.processEvents()
        assert status_labels["quick_actions"].text() == "0 pinned"
        assert status_labels["user_interface"].text() == (
            "Light mode · Desktop Zen On · Always on Top Off"
        )
        assert status_labels["screen_mover"].text() == "0 shortcuts configured"
        assert status_labels["monitor_rules"].text() == "No rules"
        assert status_labels["drives"].text() == (
            "None connected · Leave reminder Off · Notifications Off"
        )
        assert status_labels["recycle"].text() == "Auto-clean Off"
        assert status_labels["hover_controls"].text() == (
            "On · 500 ms dwell · Taskbar restoration Off"
        )

        capture_layout_action = next(
            button
            for button in quick_actions.findChildren(QPushButton)
            if button.text() == "Capture Layout"
        )
        assert "desktop icon layout" in capture_layout_action.toolTip()
        assert not any(
            button.text() == "Create Desktop Folder"
            for button in quick_actions.findChildren(QPushButton)
        )
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
            window.navigation_shell.page_stack.mapTo(window, QPoint(0, 0)).x()
            + (window.navigation_shell.page_stack.width() // 2)
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
        assert window.navigation_shell.navigation_list.width() == 220
        assert window.navigation_shell.page_stack.width() == 780
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
            current_page = window.navigation_shell.page_stack.currentWidget()
            page_title = current_page.findChild(QLabel, "PageTitle")
            assert page_title is not None
            assert window.navigation_shell.navigation_list.mapTo(window, QPoint(0, 0)).y() == (
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
                assert combo.itemData(row, Qt.ItemDataRole.ToolTipRole) == format_tooltip_text(item_text)

        window.external_drive_controller.refresh_status(
            ("E:\\Example Removable Drive With A Long Volume Name",)
        )
        qt_app.processEvents()
        connected_combo = window.pages.external_drives_page.drive_combo()
        connected_row = connected_combo.parentWidget()
        assert connected_row.width() == styles.EXTERNAL_DRIVES_CONTENT_WIDTH
        assert connected_combo.width() == styles.EXTERNAL_DRIVES_CONTROL_WIDTH
        assert connected_combo.itemData(
            0,
            Qt.ItemDataRole.ToolTipRole,
        ) == format_tooltip_text(connected_combo.itemText(0))

        for label_name in ("PageTitle", "PageSectionHeading"):
            labels = window.findChildren(QLabel, label_name)
            assert labels
            assert all(
                label.alignment() & Qt.AlignmentFlag.AlignHCenter
                for label in labels
            )
        assert not window.findChildren(QLabel, "PageDescription")

        marked_controls = standard_controls + compact_controls + wide_controls
        size_snapshot = {
            id(widget): (widget.width(), widget.height())
            for widget in marked_controls
        }
        active_page_id = window.navigation_shell.navigation_list.currentItem().data(
            Qt.ItemDataRole.UserRole
        )
        for is_dark in (False, True):
            window.apply_theme(is_dark)
            qt_app.processEvents()
            assert window.navigation_shell.navigation_list.currentItem().data(
                Qt.ItemDataRole.UserRole
            ) == active_page_id
            assert all(
                (widget.width(), widget.height()) == size_snapshot[id(widget)]
                for widget in marked_controls
            )

        for page_id in window.navigation_shell.page_by_id:
            window.navigate_to_page(page_id)
            qt_app.processEvents()
            viewport = window.navigation_shell.page_scroll_areas[page_id].viewport()
            grids = [
                widget
                for widget in window.navigation_shell.page_by_id[page_id].findChildren(QWidget)
                if widget.property("centeredControlGrid")
            ]
            for grid in grids:
                grid_left = grid.mapTo(viewport, QPoint(0, 0)).x()
                grid_center = grid_left + (grid.width() / 2)
                assert abs(grid_center - (viewport.width() / 2)) <= 2

        folder_page = window.navigation_shell.page_by_id["folder_utilities"]
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
        folder_utilities = window.pages.folder_utilities_page
        folder_name = folder_utilities._names
        save_name = folder_utilities._save_name
        delete_name = folder_utilities._delete_name
        delete_all = folder_utilities._delete_all_names
        folder_row = folder_name.parentWidget()
        assert all(
            control.width() == 250
            for control in (folder_name, folder_desktop, save_name, delete_name)
        )
        assert all(
            control.width() == 512 for control in (delete_all, folder_creator)
        )
        assert folder_name.mapTo(folder_page, QPoint()).x() == save_name.mapTo(
            folder_page, QPoint()
        ).x()
        assert folder_desktop.mapTo(folder_page, QPoint()).x() == delete_name.mapTo(
            folder_page, QPoint()
        ).x()
        assert delete_all.mapTo(folder_page, QPoint()).y() == (
            folder_row.mapTo(folder_page, QPoint()).y()
            + folder_row.height()
            + save_name.height()
            + 24
        )
        assert folder_creator.mapTo(folder_page, QPoint()).y() == (
            delete_all.mapTo(folder_page, QPoint()).y()
            + delete_all.height()
            + 12
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

        folder_page = window.navigation_shell.page_by_id["folder_utilities"]
        folder_creator = next(
            button
            for button in folder_page.findChildren(QPushButton)
            if button.text() == "Folder Creator"
        )
        folder_utilities = window.pages.folder_utilities_page
        folder_name = folder_utilities._names
        save_name = folder_utilities._save_name
        delete_name = folder_utilities._delete_name
        delete_all = folder_utilities._delete_all_names
        folder_row = folder_name.parentWidget()
        folder_desktop = folder_row.findChild(QPushButton)

        assert folder_desktop is not None
        assert all(
            control.width() == 250
            for control in (folder_name, folder_desktop, save_name, delete_name)
        )
        assert all(
            control.width() == 512 for control in (delete_all, folder_creator)
        )
        assert folder_name.mapTo(folder_page, QPoint()).x() == save_name.mapTo(
            folder_page, QPoint()
        ).x()
        assert folder_desktop.mapTo(folder_page, QPoint()).x() == delete_name.mapTo(
            folder_page, QPoint()
        ).x()
        assert delete_all.mapTo(folder_page, QPoint()).y() == (
            folder_row.mapTo(folder_page, QPoint()).y()
            + folder_row.height()
            + save_name.height()
            + 24
        )
        assert folder_creator.mapTo(folder_page, QPoint()).y() == (
            delete_all.mapTo(folder_page, QPoint()).y()
            + delete_all.height()
            + 12
        )
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_overview_hover_controls_status_uses_live_service_settings(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state.update(
        {
            "hover_window_controls_enabled": False,
            "hover_taskbar_restore_enabled": True,
            "hover_window_controls_dwell_ms": 1_250,
        }
    )
    window = _build_offscreen_window(monkeypatch, state)

    try:
        status = window.pages.overview_page.status_labels["hover_controls"]
        window.refresh_overview()

        assert status.text() == "Off · 1,250 ms dwell · Taskbar restoration On"

        window.state.update(
            {
                "hover_window_controls_enabled": False,
                "hover_taskbar_restore_enabled": True,
                "hover_window_controls_dwell_ms": 750,
            }
        )
        window.hover_window_controls.set_enabled(True)
        window.hover_window_controls.set_taskbar_restore_enabled(False)
        window.hover_window_controls.set_dwell_ms(500)
        qt_app.processEvents()

        assert status.text() == "On · 500 ms dwell · Taskbar restoration Off"
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_folder_creator_button_icon_tracks_theme(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        creator = window.pages.folder_utilities_page.folder_creator_button

        window.apply_theme(True)
        qt_app.processEvents()
        dark_icon_key = creator.icon().cacheKey()

        assert creator.text() == "Folder Creator"
        assert creator.width() == 512
        assert not creator.icon().isNull()
        assert creator.iconSize().width() == 30
        assert creator.iconSize().height() == 18
        assert (
            window.pages.folder_utilities_page.FOLDER_CREATOR_ICON_TRAILING_PADDING
            == 12
        )

        window.apply_theme(False)
        qt_app.processEvents()

        assert creator.text() == "Folder Creator"
        assert creator.width() == 512
        assert creator.icon().cacheKey() != dark_icon_key
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
        application_pages,
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
        assert (
            window.pages.external_drives_page.drive_combo().width()
            == styles.EXTERNAL_DRIVES_CONTROL_WIDTH
        )
        assert notification_combo.parentWidget().width() == styles.EXTERNAL_DRIVES_CONTENT_WIDTH
        assert leave_reminder_button.parentWidget().width() == (
            styles.EXTERNAL_DRIVES_CONTENT_WIDTH
        )
        assert window.pages.external_drives_page._empty_label.x() < leave_reminder_button.x()

        external_viewport = window.navigation_shell.page_scroll_areas["external_drives"].viewport()

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
            ) == format_tooltip_text(notification_combo.itemText(row))

        window.external_drive_controller.refresh_status(
            ("E:\\Example Removable Drive With A Long Volume Name",)
        )
        qt_app.processEvents()
        connected_combo = window.pages.external_drives_page.drive_combo()
        assert connected_combo.width() == stable_width
        assert connected_combo.parentWidget().width() == (
            styles.EXTERNAL_DRIVES_CONTENT_WIDTH
        )

        for is_dark in (False, True):
            window.apply_theme(is_dark)
            qt_app.processEvents()
            assert notification_combo.width() == stable_width
            assert connected_combo.width() == stable_width
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
            window.pages.organising_utilities_page._path_label,
            window.pages.external_drives_page._empty_label,
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
                assert "border: none;" in label.styleSheet()
                assert f"border-bottom: 1px solid {expected_border};" in label.styleSheet()
                assert "border-radius:" not in label.styleSheet()
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

        panel = window.pages.maintenance_page
        maintenance_content = panel
        selectors = maintenance_content.findChildren(QComboBox)
        selector_grid = selectors[0].parentWidget()
        maintenance_page = window.navigation_shell.page_by_id["maintenance"]

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

        panel.set_output_context("Flush DNS")
        panel._append_output("Output to clear")
        assert panel.sidebar_output_clear_btn.isEnabled()
        panel.sidebar_output_clear_btn.click()
        assert panel.sidebar_output.toPlainText() == "Dns output log cleared."
        assert not panel.sidebar_output_clear_btn.isEnabled()

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

        panel = window.pages.drive_space_page
        drive_page = window.navigation_shell.page_by_id["external_drives"]
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

        storage_heading = next(
            label
            for label in drive_page.findChildren(QLabel, "PageSectionHeading")
            if label.text() == "Storage"
        )
        storage_heading_y = storage_heading.mapTo(drive_page, QPoint()).y()
        button_row_y = button_row.mapTo(drive_page, QPoint()).y()
        output_y = panel.drive_space_list.mapTo(drive_page, QPoint()).y()
        assert button_row_y - (storage_heading_y + storage_heading.height()) == (
            output_y - (button_row_y + button_row.height())
        )
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_reset_defaults_changes_only_screen_mover_settings(monkeypatch):
    monkeypatch.setattr(main, "save_state", lambda _state: None)
    window = FakeWindow()

    window.reset_screen_mover_settings()

    assert window.state["theme_dark"] is False
    assert all(
        value == ""
        for value in window.state["screen_mover_keyboard_hotkeys"].values()
    )
    assert all(edit.cleared for edit in window.screen_mover_hotkey_edits.values())
    assert window.hotkey_manager.calls[-1] == {}


def test_real_screen_mover_section_builds_and_resets_offscreen(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["theme_dark"] = False
    state["screen_mover_keyboard_hotkeys"]["LEFT"] = "<ctrl>+<left>"

    window = _build_offscreen_window(monkeypatch, state)
    try:
        settings_page = window.pages.screen_mover_settings_page
        assert not hasattr(settings_page, "_enabled_button")
        assert not hasattr(settings_page, "_activation_combo")
        assert set(settings_page._hotkey_edits) == {
            "FAR_LEFT",
            "LEFT",
            "RIGHT",
            "FAR_RIGHT",
            "MINIMIZE",
            "MAXIMIZE",
        }
        assert (
            settings_page._hotkey_edits["LEFT"].keySequence().toString()
            == QKeySequence("Ctrl+Left").toString()
        )
        assert not settings_page.shortcuts_container.isHidden()
        assert settings_page.reset_button.text() == "Reset Shortcut Defaults"
        assert settings_page.reset_button.isEnabled()

        window.state["desktop_screenshot_last_dir"] = "unchanged"
        window.reset_screen_mover_settings()

        assert window.state["desktop_screenshot_last_dir"] == "unchanged"
        assert all(
            edit.keySequence().isEmpty()
            for edit in settings_page._hotkey_edits.values()
        )
        assert not settings_page.reset_button.isEnabled()
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_screen_mover_shortcut_capture_updates_the_global_hotkey_manager(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)
    try:
        window.show()
        window.navigate_to_page("screen_mover")
        edit = window.pages.screen_mover_settings_page._hotkey_edits["LEFT"]

        edit.setFocus()
        qt_app.processEvents()
        assert window.hotkey_manager.capture_calls[-1] is True

        edit.clearFocus()
        qt_app.processEvents()
        assert window.hotkey_manager.capture_calls[-2:] == [True, False]
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_duplicate_screen_mover_state_is_sanitized_saved_and_activated(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["screen_mover_keyboard_hotkeys"].update(
        {
            "FAR_LEFT": "Shift+Ctrl+A",
            "LEFT": "Ctrl+Shift+A",
            "RIGHT": "Ctrl+Right",
        }
    )
    saved_states = []
    window = _build_offscreen_window(
        monkeypatch,
        state,
        application_save_state=lambda value: saved_states.append(copy.deepcopy(value)),
    )

    try:
        expected = {
            "FAR_LEFT": "<ctrl>+<shift>+a",
            "LEFT": "",
            "RIGHT": "<ctrl>+<right>",
            "FAR_RIGHT": "",
            "MINIMIZE": "",
            "MAXIMIZE": "",
        }
        assert window.state["screen_mover_keyboard_hotkeys"] == expected
        assert any(
            saved["screen_mover_keyboard_hotkeys"] == expected
            for saved in saved_states
        )
        assert window.hotkey_manager.calls[-1] == {
            "FAR_LEFT": "<ctrl>+<shift>+a",
            "RIGHT": "<ctrl>+<right>",
        }
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_screen_mover_shortcut_controls_align_without_primary_row(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    window = _build_offscreen_window(monkeypatch, state)

    try:
        window.navigate_to_page("screen_mover")
        window.show()
        qt_app.processEvents()

        settings_page = window.pages.screen_mover_settings_page
        shortcuts_header = settings_page.shortcuts_header
        shortcuts_container = settings_page.shortcuts_container
        screen_page = window.navigation_shell.page_by_id["screen_mover"]

        def assert_blocks_aligned() -> None:
            widgets = (shortcuts_header, shortcuts_container)
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
        assert shortcuts_container.y() >= shortcuts_header.y() + shortcuts_header.height()

        shortcut_labels = [
            label
            for label in shortcuts_container.findChildren(QLabel)
            if label.text() in ACTION_LABELS.values()
        ]
        shortcut_edits = list(settings_page._hotkey_edits.values())
        clear_buttons = [
            button
            for button in shortcuts_container.findChildren(QPushButton)
            if button.text() == "Clear"
        ]
        assert len(shortcut_labels) == len(ACTION_LABELS)
        assert len(shortcut_edits) == len(ACTION_LABELS)
        assert len(clear_buttons) == len(ACTION_LABELS)
        assert all(
            button.property("lightModeBlackDisabledText") is True
            for button in clear_buttons
        )
        assert settings_page.reset_button.property("lightModeBlackDisabledText") is True
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

        assert settings_page.reset_button.size().width() == 250
        assert settings_page.reset_button.size().height() == 34
        assert not settings_page.reset_button.isEnabled()
        reset_left = settings_page.reset_button.mapTo(
            shortcuts_container,
            QPoint(),
        ).x()
        assert reset_left == (shortcuts_container.width() - 250) // 2

        for is_dark in (False, True):
            window.apply_theme(is_dark)
            qt_app.processEvents()
            assert_blocks_aligned()
            assert not settings_page.reset_button.isEnabled()
            reset_stylesheet = settings_page.reset_button.styleSheet()
            assert (
                f"background-color: {styles.qcolor_css(styles.themed_button_disabled_bg())};"
                in reset_stylesheet
            )
            assert (
                f"color: {styles.qcolor_css(styles.themed_button_disabled_text())};"
                in reset_stylesheet
            )

        window.reset_screen_mover_settings()
        qt_app.processEvents()
        assert_blocks_aligned()
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_screen_mover_reset_button_confirms_before_clearing(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["screen_mover_keyboard_hotkeys"]["LEFT"] = "<ctrl>+<left>"
    saved_states = []
    window = _build_offscreen_window(monkeypatch, state)
    monkeypatch.setattr(
        application_pages,
        "save_state",
        lambda saved_state: saved_states.append(copy.deepcopy(saved_state)),
    )
    responses = [QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes]
    modal_calls = []

    def show_modal(*args, **kwargs):
        modal_calls.append((args, kwargs))
        return responses.pop(0)

    window._show_modal_message = show_modal
    try:
        page = window.pages.screen_mover_settings_page
        edit = page._hotkey_edits["LEFT"]
        initial_hotkey_calls = len(window.hotkey_manager.calls)

        page.reset_button.click()

        assert edit.keySequence().toString() == QKeySequence("Ctrl+Left").toString()
        assert page.reset_button.isEnabled()
        assert window.state["screen_mover_keyboard_hotkeys"]["LEFT"] == "<ctrl>+<left>"
        assert saved_states == []
        assert len(window.hotkey_manager.calls) == initial_hotkey_calls

        args, kwargs = modal_calls[-1]
        assert args == (
            QMessageBox.Icon.Question,
            "Reset Shortcut Defaults",
            "This will clear all Screen Mover keyboard shortcuts. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        assert kwargs == {"popup_corner_radius": styles.BUTTON_CORNER_RADIUS}

        page.reset_button.click()

        assert edit.keySequence().isEmpty()
        assert all(
            value == ""
            for value in window.state["screen_mover_keyboard_hotkeys"].values()
        )
        assert len(saved_states) == 1
        assert window.hotkey_manager.calls[-1] == {}
        assert not page.reset_button.isEnabled()
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_screen_mover_reset_popup_is_theme_specific_frameless_and_rounded(
    monkeypatch,
):
    qt_app = QApplication.instance() or QApplication([])
    state = copy.deepcopy(WINDOWS_RESURFACE_DEFAULTS)
    state["screen_mover_keyboard_hotkeys"]["LEFT"] = "<ctrl>+<left>"
    window = _build_offscreen_window(monkeypatch, state)
    dialogs = []

    def capture_dialog(dialog):
        dialogs.append(dialog)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "exec", capture_dialog)
    try:
        page = window.pages.screen_mover_settings_page
        for is_dark in (False, True):
            window.apply_theme(is_dark)
            page.reset_button.click()
            qt_app.processEvents()

            dialog = dialogs[-1]
            stylesheet = dialog.styleSheet()
            assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
            assert dialog._popup_corner_radius == styles.BUTTON_CORNER_RADIUS
            assert stylesheet == styles.message_box_style(
                radius=styles.BUTTON_CORNER_RADIUS
            )
            assert (
                f"background-color: {styles.qcolor_css(styles.SURFACE_BG)};"
                in stylesheet
            )
            assert f"color: {styles.qcolor_css(styles.CURRENT_TEXT)};" in stylesheet
            assert f"border-radius: {styles.BUTTON_CORNER_RADIUS}px;" in stylesheet
            assert not dialog.mask().isEmpty()
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
        expected_border = styles.qcolor_css(
            styles.SURFACE_BORDER
            if is_dark
            else styles.themed_surface_field_border()
        )

        page = window.pages.screen_mover_settings_page
        for action, edit in page._hotkey_edits.items():
            assert edit.objectName() == "ScreenMoverShortcutEdit"
            assert "QKeySequenceEdit#ScreenMoverShortcutEdit" in edit.styleSheet()
            assert (
                "QKeySequenceEdit#ScreenMoverShortcutEdit QLineEdit"
                in edit.styleSheet()
            )
            assert f"background-color: {expected_background};" in edit.styleSheet()
            assert f"border: 2px solid {expected_border};" in edit.styleSheet()
            assert "background-clip: padding;" not in edit.styleSheet()
            assert "border: none;" in edit.styleSheet()
            assert "border-radius: 4px;" in edit.styleSheet()
            internal_edits = edit.findChildren(QLineEdit)
            assert len(internal_edits) == 1
            assert internal_edits[0].objectName() == "qt_keysequenceedit_lineedit"
            assert internal_edits[0].styleSheet() == ""
            assert edit.height() == styles.PAGE_CONTROL_HEIGHT == 34
            assert page._clear_hotkey_buttons[action].height() == 34
            assert internal_edits[0].geometry().getRect() == (
                0,
                0,
                edit.width(),
                edit.height(),
            )
            image = edit.grab().toImage()
            assert image.pixelColor(
                image.width() // 2,
                image.height() // 2,
            ).name() == expected_background
            assert image.pixelColor(
                image.width() - 10,
                image.height() // 2,
            ).name() == expected_background

            # Exercise both render states so the stylesheet remains valid
            # before capture starts as well as while the field has focus.
            edit.setFocus()
            qt_app.processEvents()
            assert edit.hasFocus()
            focused_image = edit.grab().toImage()
            assert focused_image.pixelColor(
                focused_image.width() - 10,
                focused_image.height() // 2,
            ).name() == expected_background
            edit.clearFocus()
            qt_app.processEvents()

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

        settings_page = window.pages.screen_mover_settings_page
        shortcuts_header = settings_page.shortcuts_header
        shortcuts_container = settings_page.shortcuts_container
        assert shortcuts_container.y() - (
            shortcuts_header.y() + shortcuts_header.height()
        ) == 16
    finally:
        window._quit_requested = True
        window.close()
        window.deleteLater()
        qt_app.processEvents()

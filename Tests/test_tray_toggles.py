import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication

from resurface.core import tray_toggles
from resurface.ui import styles

from resurface.core.tray_toggles import (
    TRAY_ICON_BUNDLE_NAME,
    TRAY_ICON_ENV_VAR,
    TrayIconManager,
    application_icon_candidates,
    application_icon_path,
    resolve_application_icon,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ICON_PATH = PROJECT_ROOT / "Exe Tray Icons" / "Windows_utility_Icon.ico"


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _copy_source_icon(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE_ICON_PATH, path)
    return path


def test_tray_hover_controls_action_syncs_and_dispatches() -> None:
    _app()

    class FakeWindow(QObject):
        def __init__(self):
            super().__init__()
            self.hover_window_controls = SimpleNamespace(enabled=False)
            self.enabled_calls = []

        def set_hover_window_controls_enabled(self, enabled):
            self.enabled_calls.append(enabled)
            self.hover_window_controls.enabled = enabled

    window = FakeWindow()
    manager = TrayIconManager(window)
    manager.hover_controls_action = QAction(
        "Hover Window Controls Enabled", window
    )
    manager.hover_controls_action.setCheckable(True)

    manager.sync_hover_controls_action()
    assert not manager.hover_controls_action.isChecked()

    manager.toggle_hover_controls(True)
    manager.sync_hover_controls_action()

    assert window.enabled_calls == [True]
    assert manager.hover_controls_action.isChecked()


def test_tray_folder_creator_action_opens_or_closes_and_precedes_toggles(monkeypatch) -> None:
    _app()

    class FakeFolderActions:
        def __init__(self):
            self.open_calls = 0

        def open_folder_creator(self):
            self.open_calls += 1

    class FakeFolderCreatorLauncher:
        def __init__(self):
            self.handles = []

        def resolve_project_root(self):
            return Path("C:/project")

        def resolve_launch_target(self, project_dir):
            return project_dir / "main.py"

        def window_handles(self, titles, target):
            assert target.name == "main.py"
            return self.handles

    class FakeWindow(QObject):
        def __init__(self):
            super().__init__()
            self.folder_actions = FakeFolderActions()
            self.folder_creator_launcher = FakeFolderCreatorLauncher()

        def windowIcon(self):
            return QIcon()

    window = FakeWindow()
    manager = TrayIconManager(window)
    manager.create_tray_icon()

    assert manager.menu.actions()[0] is manager.folder_creator_action
    assert manager.folder_creator_action.text() == "Open Folder Creator"
    assert manager.folder_creator_action.isCheckable()
    assert not manager.folder_creator_action.isChecked()
    manager.folder_creator_action.trigger()
    assert window.folder_actions.open_calls == 1

    window.folder_creator_launcher.handles = [42]
    manager.sync_folder_creator_action()
    assert manager.folder_creator_action.isChecked()
    closed_handles = []
    monkeypatch.setattr(
        tray_toggles, "close_window_handles", lambda handles: closed_handles.extend(handles)
    )
    manager.folder_creator_action.trigger()
    assert not manager.folder_creator_action.isChecked()
    assert closed_handles == [42]


def test_tray_menu_restyles_with_live_theme_and_rounded_corners() -> None:
    _app()

    class FakeWindow(QObject):
        def windowIcon(self):
            return QIcon()

    manager = TrayIconManager(FakeWindow())
    manager.create_tray_icon()

    styles.set_theme(True)
    manager.refresh_menu()
    dark_style = manager.menu.styleSheet()
    assert f"border-radius: {styles.BUTTON_CORNER_RADIUS}px;" in dark_style
    assert f"background-color: {styles.qcolor_css(styles.SURFACE_BG)};" in dark_style

    styles.set_theme(False)
    manager.refresh_menu()
    light_style = manager.menu.styleSheet()
    assert f"border-radius: {styles.BUTTON_CORNER_RADIUS}px;" in light_style
    assert f"background-color: {styles.qcolor_css(styles.SURFACE_BG)};" in light_style
    assert light_style != dark_style
    styles.set_theme(True)


def test_tray_theme_action_switches_theme_through_user_interface_page() -> None:
    _app()

    class UserInterfacePage:
        def __init__(self):
            self.enabled_calls = []

        def set_theme_enabled(self, enabled):
            self.enabled_calls.append(enabled)
            window.state["theme_dark"] = enabled

    class FakeWindow(QObject):
        def __init__(self):
            super().__init__()
            self.state = {"theme_dark": True}
            self.pages = SimpleNamespace(user_interface_page=UserInterfacePage())

        def windowIcon(self):
            return QIcon()

    window = FakeWindow()
    manager = TrayIconManager(window)
    manager.create_tray_icon()

    assert manager.menu.actions()[2] is manager.theme_action
    assert manager.theme_action.text() == "Switch to Light Mode"

    manager.theme_action.trigger()

    assert window.pages.user_interface_page.enabled_calls == [False]
    assert window.state["theme_dark"] is False
    assert manager.theme_action.text() == "Switch to Dark Mode"


def test_application_icon_candidates_prioritize_env_var(monkeypatch, tmp_path) -> None:
    env_icon = tmp_path / "from-env.ico"
    fake_exe = tmp_path / "Windows Resurface.exe"
    monkeypatch.setenv(TRAY_ICON_ENV_VAR, str(env_icon))
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    candidates = application_icon_candidates()

    assert candidates[0] == env_icon
    assert candidates[1] == fake_exe.with_name(TRAY_ICON_BUNDLE_NAME)


def test_application_icon_candidates_prioritize_meipass_icon(monkeypatch, tmp_path) -> None:
    fake_exe = tmp_path / "dist" / "Windows Resurface.exe"
    meipass_dir = tmp_path / "bundle"
    monkeypatch.delenv(TRAY_ICON_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass_dir), raising=False)

    candidates = application_icon_candidates()

    assert candidates[0] == meipass_dir / TRAY_ICON_BUNDLE_NAME
    assert candidates[1] == fake_exe.with_name(TRAY_ICON_BUNDLE_NAME)
    assert candidates[2] == fake_exe.parent / "_internal" / TRAY_ICON_BUNDLE_NAME


def test_application_icon_candidates_include_internal_one_folder_icon(
    monkeypatch,
    tmp_path,
) -> None:
    fake_exe = tmp_path / "dist" / "Windows Resurface.exe"
    monkeypatch.delenv(TRAY_ICON_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    candidates = application_icon_candidates()

    assert candidates[0] == fake_exe.with_name(TRAY_ICON_BUNDLE_NAME)
    assert candidates[1] == fake_exe.parent / "_internal" / TRAY_ICON_BUNDLE_NAME


def test_application_icon_path_loads_meipass_before_exe_sibling(
    monkeypatch,
    tmp_path,
) -> None:
    _app()
    fake_exe = tmp_path / "dist" / "Windows Resurface.exe"
    stale_exe_icon = _copy_source_icon(fake_exe.with_name(TRAY_ICON_BUNDLE_NAME))
    meipass_icon = _copy_source_icon(tmp_path / "bundle" / TRAY_ICON_BUNDLE_NAME)
    monkeypatch.delenv(TRAY_ICON_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass_icon.parent), raising=False)

    icon = resolve_application_icon()

    assert stale_exe_icon.is_file()
    assert application_icon_path() == meipass_icon
    assert not icon.isNull()


def test_application_icon_path_loads_nested_meipass_icon(
    monkeypatch,
    tmp_path,
) -> None:
    _app()
    fake_exe = tmp_path / "dist" / "Windows Resurface.exe"
    meipass_dir = tmp_path / "bundle"
    nested_icon = _copy_source_icon(
        meipass_dir / TRAY_ICON_BUNDLE_NAME / "selected.ico"
    )
    monkeypatch.delenv(TRAY_ICON_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass_dir), raising=False)

    icon = resolve_application_icon()

    assert application_icon_path() == nested_icon
    assert not icon.isNull()


def test_application_icon_path_loads_exe_sibling_before_source_fallback(
    monkeypatch,
    tmp_path,
) -> None:
    _app()
    fake_exe = tmp_path / "Windows Resurface.exe"
    bundled_icon = _copy_source_icon(fake_exe.with_name(TRAY_ICON_BUNDLE_NAME))
    monkeypatch.delenv(TRAY_ICON_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    icon = resolve_application_icon()

    assert application_icon_path() == bundled_icon
    assert not icon.isNull()


def test_application_icon_path_loads_nested_internal_icon(
    monkeypatch,
    tmp_path,
) -> None:
    _app()
    fake_exe = tmp_path / "dist" / "Windows Resurface.exe"
    nested_icon = _copy_source_icon(
        fake_exe.parent / "_internal" / TRAY_ICON_BUNDLE_NAME / "selected.ico"
    )
    monkeypatch.delenv(TRAY_ICON_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    icon = resolve_application_icon()

    assert application_icon_path() == nested_icon
    assert not icon.isNull()


def test_application_icon_path_uses_source_fallback_without_bundle(
    monkeypatch,
    tmp_path,
) -> None:
    _app()
    monkeypatch.delenv(TRAY_ICON_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Windows Resurface.exe"))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    icon = resolve_application_icon()

    assert application_icon_path() == PROJECT_ROOT / "Exe Tray Icons" / SOURCE_ICON_PATH.name
    assert not icon.isNull()


def test_tray_manager_uses_existing_window_icon_for_tray() -> None:
    _app()
    icon = QIcon(str(SOURCE_ICON_PATH))

    class FakeWindow(QObject):
        def __init__(self):
            super().__init__()
            self._icon = icon

        def windowIcon(self):
            return self._icon

    manager = TrayIconManager(FakeWindow())

    assert manager._resolve_tray_icon().cacheKey() == icon.cacheKey()


def test_tray_zen_mode_uses_composed_user_interface_page() -> None:
    _app()

    class UserInterfacePage:
        def __init__(self):
            self.enabled_calls = []

        def set_desktop_zen_enabled(self, enabled):
            self.enabled_calls.append(enabled)

    class FakeWindow(QObject):
        def __init__(self):
            super().__init__()
            self.pages = SimpleNamespace(user_interface_page=UserInterfacePage())

    window = FakeWindow()
    manager = TrayIconManager(window)

    manager.toggle_zen_mode(True)

    assert window.pages.user_interface_page.enabled_calls == [True]


def test_tray_monitor_rules_action_syncs_and_dispatches() -> None:
    _app()

    class FakeWindow(QObject):
        def __init__(self):
            super().__init__()
            self.state = {
                "monitor_rules": [
                    {"enabled": True},
                    {"enabled": False},
                ]
            }
            self.enabled_calls = []

        def set_monitor_rules_enabled(self, enabled):
            self.enabled_calls.append(enabled)
            for rule in self.state["monitor_rules"]:
                rule["enabled"] = enabled

    window = FakeWindow()
    manager = TrayIconManager(window)
    manager.monitor_rules_action = QAction("Monitor Rules Enabled", window)
    manager.monitor_rules_action.setCheckable(True)

    manager.sync_monitor_rules_action()
    assert manager.monitor_rules_action.isEnabled()
    assert manager.monitor_rules_action.isChecked()

    manager.toggle_monitor_rules(False)
    manager.sync_monitor_rules_action()
    assert window.enabled_calls == [False]
    assert not manager.monitor_rules_action.isChecked()

    manager.toggle_monitor_rules(True)
    manager.sync_monitor_rules_action()
    assert window.enabled_calls == [False, True]
    assert manager.monitor_rules_action.isChecked()

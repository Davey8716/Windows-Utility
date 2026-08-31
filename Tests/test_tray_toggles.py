import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication

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


def test_tray_screen_mover_action_syncs_and_dispatches() -> None:
    _app()

    class FakeWindow(QObject):
        def __init__(self):
            super().__init__()
            self.state = {"title_bar_dock_enabled": False}
            self.enabled_calls = []

        def set_screen_mover_enabled(self, enabled):
            self.enabled_calls.append(enabled)
            self.state["title_bar_dock_enabled"] = enabled

    window = FakeWindow()
    manager = TrayIconManager(window)
    manager.screen_mover_action = QAction("Screen Mover Enabled", window)
    manager.screen_mover_action.setCheckable(True)

    manager.sync_screen_mover_action()
    assert not manager.screen_mover_action.isChecked()

    manager.toggle_screen_mover(True)
    manager.sync_screen_mover_action()

    assert window.enabled_calls == [True]
    assert manager.screen_mover_action.isChecked()


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

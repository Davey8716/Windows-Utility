import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch
import tray_toggles

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
CODE_DIR = PROJECT_ROOT / "Code"
for path in (PROJECT_ROOT, TESTS_DIR, CODE_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from _stubs import install_dependency_stubs

install_dependency_stubs()




class _DummyIcon:
    def __init__(self, source=None, is_null=False):
        self.source = source
        self._is_null = is_null

    def isNull(self):
        return self._is_null



class TrayIconManagerTests(unittest.TestCase):
    def test_toggle_window_restores_hidden_app(self):
        app = Mock()
        app.isVisible.return_value = False
        manager = tray_toggles.TrayIconManager(app)

        manager.toggle_window()

        app.restore_from_activation.assert_called_once_with()

    def test_resolve_application_icon_prefers_builder_env_icon(self):
        app = Mock()
        app.windowIcon.return_value = _DummyIcon(is_null=True)

        def fake_qicon(source=None):
            if source == r"C:\icons\built.ico":
                return _DummyIcon(source=source, is_null=False)
            return _DummyIcon(source=source, is_null=True)

        with patch.dict(tray_toggles.os.environ, {tray_toggles.TRAY_ICON_ENV_VAR: r"C:\icons\built.ico"}, clear=False), \
             patch.object(tray_toggles, "QIcon", side_effect=fake_qicon), \
             patch.object(tray_toggles.QIcon, "fromTheme", return_value=_DummyIcon(source="theme", is_null=False)):
            icon = tray_toggles.resolve_application_icon(app)

        self.assertEqual(icon.source, r"C:\icons\built.ico")

    def test_resolve_application_icon_falls_back_to_repo_icon(self):
        app = Mock()
        app.windowIcon.return_value = _DummyIcon(is_null=True)

        def fake_qicon(source=None):
            text = str(source)
            if text.endswith("Windows_utility_Icon.ico"):
                return _DummyIcon(source=text, is_null=False)
            return _DummyIcon(source=text, is_null=True)

        with patch.dict(tray_toggles.os.environ, {}, clear=False), \
             patch.object(tray_toggles, "QIcon", side_effect=fake_qicon), \
             patch.object(tray_toggles.QIcon, "fromTheme", return_value=_DummyIcon(source="theme", is_null=False)), \
             patch.object(tray_toggles.Path, "is_file", autospec=True, side_effect=lambda path: str(path).endswith("Windows_utility_Icon.ico")):
            icon = tray_toggles.resolve_application_icon(app)

        self.assertTrue(icon.source.endswith("Windows_utility_Icon.ico"))

    def test_resolve_tray_icon_prefers_window_icon(self):
        app = Mock()
        window_icon = _DummyIcon(source="window", is_null=False)
        app.windowIcon.return_value = window_icon
        manager = tray_toggles.TrayIconManager(app)

        with patch.object(tray_toggles, "resolve_application_icon", return_value=_DummyIcon(source="fallback", is_null=False)):
            icon = manager._resolve_tray_icon()

        self.assertIs(icon, window_icon)

    def test_quit_from_tray_runs_explicit_app_shutdown(self):
        app = Mock()
        manager = tray_toggles.TrayIconManager(app)
        qt_app = Mock()

        with patch.object(tray_toggles.QApplication, "instance", return_value=qt_app):
            manager.quit_from_tray()

        self.assertTrue(app._quit_requested)
        app.prepare_for_shutdown.assert_called_once_with()
        app.close.assert_called_once_with()
        qt_app.quit.assert_called_once_with()

    def test_toggle_zen_mode_uses_optional_minimize_helper_when_enabled(self):
        app = Mock()
        app.desktop_zen_btn = None
        app.state = {}
        app.actions.desktop_zen_mode_toggle.return_value = True
        manager = tray_toggles.TrayIconManager(app)

        manager.toggle_zen_mode(True)

        app._minimize_self_if_configured.assert_called_once_with()
        app.save_all_settings.assert_called_once_with()

    def test_toggle_zen_mode_skips_optional_minimize_helper_when_disabled(self):
        app = Mock()
        app.desktop_zen_btn = None
        app.state = {}
        app.actions.desktop_zen_mode_toggle.return_value = True
        manager = tray_toggles.TrayIconManager(app)

        manager.toggle_zen_mode(False)

        app._minimize_self_if_configured.assert_not_called()
        app.save_all_settings.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

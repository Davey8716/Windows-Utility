import unittest
from unittest.mock import Mock, patch

from _stubs import install_dependency_stubs

install_dependency_stubs()

import tray_toggles


class TrayIconManagerTests(unittest.TestCase):
    def test_toggle_window_restores_hidden_app(self):
        app = Mock()
        app.isVisible.return_value = False
        manager = tray_toggles.TrayIconManager(app)

        manager.toggle_window()

        app.restore_from_activation.assert_called_once_with()

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


if __name__ == "__main__":
    unittest.main()

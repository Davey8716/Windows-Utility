import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _stubs import install_dependency_stubs

install_dependency_stubs()

import app_notifications
import app_paths
import desktop_operations
import external_drive_mixin
from PySide6.QtCore import QPoint


class _PathsApp(app_paths.MasterBackupPathsMixin):
    def __init__(self):
        self.state = {}
        self.backup_path_input = Mock()


class _NotificationsApp(app_notifications.WindowMessageMixin):
    def __init__(self):
        self._active_message_boxes = []


class _DriveApp(external_drive_mixin.ExternalDriveMixin):
    def __init__(self):
        self.state = {"usb_idle_enabled": True, "usb_plug_notify_mode": "on"}
        self._pending_end_session_warning = False
        self._known_external_drives = set()
        self.warning_calls = []
        self.timed_calls = []
        self.connected_drives_field = Mock()

    def _show_connected_drive_warning(self, title, body, on_close=None):
        self.warning_calls.append((title, body, on_close))
        return None

    def _show_timed_message(self, icon, title, text, timeout_ms=10_000):
        self.timed_calls.append((icon, title, text, timeout_ms))
        return None

    def _show_acknowledged_message(self, icon, title, text, on_close=None):
        self.warning_calls.append((title, text, on_close))
        return None

    def _message_box_icon(self, name: str):
        return name

    def _message_box_button(self, name: str):
        return {"Yes": 1, "Cancel": 2}.get(name, 0)


class _DesktopApp(desktop_operations.DesktopOperationsMixin):
    def __init__(self):
        self.state = {
            "folder_to_desktop_name": "Reports",
            "recycle_bin_auto_clean_enabled": False,
            "recycle_bin_age_rule_days": 30,
        }
        self.messages = []
        self.actions = Mock()

    def _message_box_icon(self, name: str):
        return name

    def _show_timed_message(self, icon, title, text, timeout_ms=10_000):
        self.messages.append((icon, title, text, timeout_ms))
        return None


class MasterBackupPathsMixinTests(unittest.TestCase):
    def test_choose_master_backup_dir_uses_dialog_selection(self):
        app = _PathsApp()
        app.state = {"master_backup_output_path": "C:\\initial"}

        with patch.object(app_paths.QFileDialog, "getExistingDirectory", return_value="C:\\chosen"), \
             patch.object(app_paths, "save_state") as save_state_mock:
            app._choose_master_backup_dir()

        self.assertEqual(app.backup_path, "C:\\chosen")
        self.assertEqual(app.state["master_backup_output_path"], "C:\\chosen")
        app.backup_path_input.setText.assert_called_once_with("C:\\chosen")
        save_state_mock.assert_called_once_with(app.state)

    def test_get_default_taskbar_backup_dir_uses_home_when_state_missing(self):
        app = _PathsApp()

        with patch.object(app_paths.Path, "home", return_value=Path("C:/Users/tester")):
            output = app.get_default_taskbar_backup_dir()

        self.assertEqual(output, str(Path("C:/Users/tester") / "TaskBarApps"))


class WindowMessageMixinTests(unittest.TestCase):
    def test_message_box_helpers_fallback_when_stub_lacks_nested_enums(self):
        app = _NotificationsApp()

        self.assertIsNone(app._message_box_icon("Information"))
        self.assertEqual(app._message_box_button("Ok"), 0)

    def test_show_acknowledged_message_calls_on_close_when_message_box_is_stubbed(self):
        app = _NotificationsApp()
        on_close = Mock()

        result = app._show_acknowledged_message(
            icon=None,
            title="Title",
            text="Body",
            on_close=on_close,
        )

        self.assertIsNone(result)
        on_close.assert_called_once_with()


class ExternalDriveMixinTests(unittest.TestCase):
    def test_format_external_drive_message_handles_singular_and_plural(self):
        app = _DriveApp()

        singular = app._format_external_drive_message(("E:\\",))
        plural = app._format_external_drive_message(("E:\\", "F:\\"))

        self.assertEqual(singular, ("drive is", "E:\\"))
        self.assertEqual(plural, ("drives are", "E:\\\nF:\\"))

    def test_block_end_session_schedules_warning_and_sets_pending_flag(self):
        app = _DriveApp()
        app._connected_external_drive_signature = Mock(return_value=("E:\\",))

        with patch.object(external_drive_mixin.QTimer, "singleShot", side_effect=lambda _ms, fn: fn()):
            blocked = app._block_end_session_for_connected_drives("Shutdown")

        self.assertTrue(blocked)
        self.assertTrue(app._pending_end_session_warning)
        self.assertEqual(len(app.warning_calls), 1)
        title, body, on_close = app.warning_calls[0]
        self.assertEqual(title, "Shutdown Blocked")
        self.assertIn("E:\\", body)
        self.assertTrue(callable(on_close))

    def test_check_external_drive_changes_notifies_for_added_and_removed_drives(self):
        app = _DriveApp()
        app._known_external_drives = {"E:\\"}
        app._current_external_drives = Mock(return_value={"F:\\"})

        app._check_external_drive_changes()

        self.assertEqual(app._known_external_drives, {"F:\\"})
        self.assertEqual(
            [(title, text) for _, title, text, _ in app.timed_calls],
            [
                ("Drive Connected", "External drive connected:\nF:\\"),
                ("Drive Removed", "External drive removed:\nE:\\"),
            ],
        )
        app.connected_drives_field.clear.assert_called_once_with()
        app.connected_drives_field.addItem.assert_called_once_with(
            "F:\\ Connected", "F:\\"
        )
        app.connected_drives_field.setCurrentIndex.assert_called_once_with(0)
        app.connected_drives_field.setToolTip.assert_called_once_with(
            "Connected drives:\nF:\\ Connected"
        )

    def test_refresh_connected_drive_status_label_handles_empty_and_populated_states(self):
        app = _DriveApp()

        app._refresh_connected_drive_status_label(set())
        app.connected_drives_field.clear.assert_called_once_with()
        app.connected_drives_field.addItem.assert_not_called()
        app.connected_drives_field.setPlaceholderText.assert_called_once_with(
            "No Drives Connected"
        )
        app.connected_drives_field.setCurrentIndex.assert_called_once_with(-1)
        app.connected_drives_field.setToolTip.assert_called_once_with("No Drives Connected")

        app.connected_drives_field.reset_mock()
        app._refresh_connected_drive_status_label({"F:\\", "E:\\"})
        app.connected_drives_field.clear.assert_called_once_with()
        app.connected_drives_field.setPlaceholderText.assert_called_once_with("")
        self.assertEqual(
            app.connected_drives_field.addItem.call_args_list,
            [
                unittest.mock.call("E:\\ Connected", "E:\\"),
                unittest.mock.call("F:\\ Connected", "F:\\"),
            ],
        )
        app.connected_drives_field.setCurrentIndex.assert_called_once_with(0)
        app.connected_drives_field.setToolTip.assert_called_once_with(
            "Connected drives:\nE:\\ Connected\nF:\\ Connected"
        )

    def test_show_connected_drives_context_menu_uses_right_panel_safe_remove_handler(self):
        app = _DriveApp()
        app.connected_drives_field.mapToGlobal = Mock(return_value=QPoint())
        remove_drive = Mock()
        app.right_tools_panel = type(
            "RightToolsPanel",
            (),
            {"_safely_remove_drive": remove_drive},
        )()
        app._current_external_drives = Mock(return_value={"E:\\"})

        fake_action = object()

        class FakeMenu:
            def __init__(self, *_args, **_kwargs):
                self.actions = []

            def addAction(self, text):
                self.actions.append(text)
                return fake_action

            def exec(self, _pos):
                return fake_action

        with patch.object(external_drive_mixin, "QMenu", FakeMenu):
            app._show_connected_drives_context_menu(QPoint())

        remove_drive.assert_called_once_with("E:\\")


class DesktopOperationsMixinTests(unittest.TestCase):
    def make_temp_dir(self, name: str) -> Path:
        temp_dir = Path(__file__).resolve().parent / ".tmp" / name
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        return temp_dir

    def test_create_desktop_folder_creates_folder_and_persists_state(self):
        app = _DesktopApp()
        folder_input = Mock()
        folder_input.text.return_value = "Reports"
        temp_dir = self.make_temp_dir("desktop-folder-mixin")

        with patch.object(desktop_operations.Path, "home", return_value=temp_dir), \
             patch.object(desktop_operations, "save_state") as save_state_mock:
            app._create_desktop_folder(folder_input)

        self.assertTrue((temp_dir / "Desktop" / "Reports").exists())
        folder_input.clear.assert_called_once_with()
        self.assertEqual(app.state["folder_to_desktop_name"], "")
        save_state_mock.assert_called_once_with(app.state)
        self.assertEqual(app.messages[0][1], "Folder to Desktop")

    def test_run_recycle_bin_auto_cleanup_skips_when_disabled(self):
        app = _DesktopApp()

        app.run_recycle_bin_auto_cleanup()

        app.actions.cleanup_recycle_bin_items_older_than.assert_not_called()

    def test_run_recycle_bin_auto_cleanup_uses_selected_age_rule(self):
        app = _DesktopApp()
        app.state["recycle_bin_auto_clean_enabled"] = True
        app.state["recycle_bin_age_rule_days"] = 14
        app.actions.cleanup_recycle_bin_items_older_than.return_value = 2

        app.run_recycle_bin_auto_cleanup()

        app.actions.cleanup_recycle_bin_items_older_than.assert_called_once_with(14)
        self.assertEqual(app.messages[0][1], "Recycle Bin Auto-Clean")
        self.assertIn("2 Recycle Bin item(s)", app.messages[0][2])


if __name__ == "__main__":
    unittest.main()

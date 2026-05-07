import os
import shutil
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
for path in (PROJECT_ROOT, TESTS_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from _stubs import install_dependency_stubs

install_dependency_stubs()

import utility_toggles


class UtilityTogglesTests(unittest.TestCase):
    def make_temp_dir(self, name: str) -> Path:
        temp_dir = Path(__file__).resolve().parent / ".tmp" / name
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        return temp_dir

    def test_should_skip_true_for_target_window(self):
        self.assertTrue(utility_toggles._should_skip(10, 10))

    def test_should_skip_false_for_visible_toplevel_window_with_title(self):
        with patch.object(utility_toggles.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(utility_toggles.win32gui, "GetWindowText", return_value="Editor"), \
             patch.object(utility_toggles.win32gui, "GetClassName", return_value="Notepad"), \
             patch.object(utility_toggles.win32gui, "GetParent", return_value=0):
            self.assertFalse(utility_toggles._should_skip(11, 10))

    def test_should_skip_true_for_settings_app_window(self):
        with patch.object(utility_toggles.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(utility_toggles.win32gui, "GetWindowText", return_value="Settings"), \
             patch.object(utility_toggles.win32gui, "GetClassName", return_value="ApplicationFrameWindow"), \
             patch.object(utility_toggles.win32gui, "GetParent", return_value=0):
            self.assertTrue(utility_toggles._should_skip(11, 10))

    def test_toggle_power_buttons_saves_settings(self):
        app = SimpleNamespace(save_all_settings=lambda: setattr(app, "saved", True))
        app.saved = False
        manager = utility_toggles.UtilityActionsManager(app)

        enabled = manager.toggle_power_buttons(True)

        self.assertTrue(enabled)
        self.assertTrue(app.saved)

    def test_maximize_all_toggle_restores_windows_when_enabled(self):
        app = SimpleNamespace(
            winId=lambda: 99,
            save_all_settings=lambda: setattr(app, "saved", True),
        )
        app.saved = False
        manager = utility_toggles.UtilityActionsManager(app)

        with patch.object(utility_toggles, "restore_all_except_gui") as restore_mock, \
             patch.object(utility_toggles, "minimize_all_except_gui") as minimize_mock:
            enabled = manager.maximize_all_toggle(True)

        self.assertTrue(enabled)
        restore_mock.assert_called_once_with(99)
        minimize_mock.assert_not_called()
        self.assertTrue(app.saved)

    def test_minimize_all_toggle_keeps_legacy_minimize_semantics(self):
        app = SimpleNamespace(
            winId=lambda: 99,
            save_all_settings=lambda: setattr(app, "saved", True),
        )
        app.saved = False
        manager = utility_toggles.UtilityActionsManager(app)

        with patch.object(utility_toggles, "restore_all_except_gui") as restore_mock, \
             patch.object(utility_toggles, "minimize_all_except_gui") as minimize_mock:
            enabled = manager.minimize_all_toggle(True)

        self.assertTrue(enabled)
        minimize_mock.assert_called_once_with(99)
        restore_mock.assert_not_called()
        self.assertTrue(app.saved)

    def test_backup_pinned_shortcuts_copies_only_shortcuts(self):
        appdata_dir = self.make_temp_dir("appdata")
        backup_dir = self.make_temp_dir("backup")
        pinned_dir = appdata_dir / "Microsoft" / "Internet Explorer" / "Quick Launch" / "User Pinned" / "TaskBar"
        pinned_dir.mkdir(parents=True, exist_ok=True)
        Path(pinned_dir, "alpha.lnk").write_text("a", encoding="utf-8")
        Path(pinned_dir, "notes.txt").write_text("b", encoding="utf-8")
        app = SimpleNamespace(save_all_settings=lambda: None)
        manager = utility_toggles.UtilityActionsManager(app)

        with patch.dict(os.environ, {"APPDATA": str(appdata_dir)}, clear=False):
            count = manager.backup_pinned_shortcuts(str(backup_dir))

        self.assertEqual(count, 1)
        self.assertTrue((backup_dir / "alpha.lnk").exists())
        self.assertFalse((backup_dir / "notes.txt").exists())

    def test_open_backup_folder_returns_false_when_startfile_fails(self):
        app = SimpleNamespace(get_default_taskbar_backup_dir=lambda: "C:\\missing")
        manager = utility_toggles.UtilityActionsManager(app)

        with patch.object(utility_toggles.os, "makedirs"), \
             patch.object(utility_toggles.os, "startfile", side_effect=OSError("blocked"), create=True):
            opened = manager.open_backup_folder()

        self.assertFalse(opened)

    def test_is_backup_folder_open_returns_true_when_matching_explorer_window_exists(self):
        manager = utility_toggles.UtilityActionsManager()

        def enum_windows(callback, extra):
            callback(101, extra)
            callback(202, extra)

        with patch.object(utility_toggles.win32gui, "EnumWindows", side_effect=enum_windows), \
             patch.object(utility_toggles.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(utility_toggles.win32gui, "GetClassName", side_effect=["CabinetWClass", "Notepad"]), \
             patch.object(utility_toggles.win32gui, "GetWindowText", side_effect=["TaskBarApps", "Notes"]):
            self.assertTrue(manager.is_backup_folder_open(r"C:\Backups\TaskBarApps"))

    def test_close_backup_folder_posts_wm_close_to_matching_windows(self):
        manager = utility_toggles.UtilityActionsManager()

        def enum_windows(callback, extra):
            callback(101, extra)
            callback(202, extra)

        with patch.object(utility_toggles.win32gui, "EnumWindows", side_effect=enum_windows), \
             patch.object(utility_toggles.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(utility_toggles.win32gui, "GetClassName", side_effect=["CabinetWClass", "CabinetWClass"]), \
             patch.object(utility_toggles.win32gui, "GetWindowText", side_effect=["TaskBarApps", "Downloads"]), \
             patch.object(utility_toggles.win32gui, "PostMessage") as post_message:
            closed = manager.close_backup_folder(r"C:\Backups\TaskBarApps")

        self.assertTrue(closed)
        post_message.assert_called_once_with(101, utility_toggles.win32con.WM_CLOSE, 0, 0)

    def test_is_this_pc_open_returns_true_when_matching_explorer_window_exists(self):
        manager = utility_toggles.UtilityActionsManager()

        def enum_windows(callback, extra):
            callback(101, extra)
            callback(202, extra)

        with patch.object(utility_toggles.win32gui, "EnumWindows", side_effect=enum_windows), \
             patch.object(utility_toggles.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(utility_toggles.win32gui, "GetClassName", side_effect=["CabinetWClass", "Notepad"]), \
             patch.object(utility_toggles.win32gui, "GetWindowText", side_effect=["This PC", "Notes"]):
            self.assertTrue(manager.is_this_pc_open())

    def test_close_this_pc_posts_wm_close_to_matching_windows(self):
        manager = utility_toggles.UtilityActionsManager()

        def enum_windows(callback, extra):
            callback(101, extra)
            callback(202, extra)

        with patch.object(utility_toggles.win32gui, "EnumWindows", side_effect=enum_windows), \
             patch.object(utility_toggles.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(utility_toggles.win32gui, "GetClassName", side_effect=["CabinetWClass", "CabinetWClass"]), \
             patch.object(utility_toggles.win32gui, "GetWindowText", side_effect=["This PC", "Downloads"]), \
             patch.object(utility_toggles.win32gui, "PostMessage") as post_message:
            closed = manager.close_this_pc()

        self.assertTrue(closed)
        post_message.assert_called_once_with(101, utility_toggles.win32con.WM_CLOSE, 0, 0)

    def test_get_storage_sense_window_state_prefers_tracked_handle_state(self):
        app = SimpleNamespace(_tracked_storage_sense_hwnd=101)
        manager = utility_toggles.UtilityActionsManager(app)

        with patch.object(manager, "_get_tracked_storage_sense_handle", return_value=101), \
             patch.object(manager, "_find_storage_sense_handles", return_value=[101, 202]), \
             patch.object(
                 utility_toggles,
                 "get_window_state_for_handles",
                 side_effect=["minimized", "open"],
             ) as state_mock:
            state = manager.get_storage_sense_window_state()

        self.assertEqual(state, "minimized")
        state_mock.assert_called_once_with([101])

    def test_focus_storage_sense_prefers_tracked_handle_first(self):
        app = SimpleNamespace(_tracked_storage_sense_hwnd=101)
        manager = utility_toggles.UtilityActionsManager(app)

        with patch.object(manager, "_get_tracked_storage_sense_handle", return_value=101), \
             patch.object(manager, "_find_storage_sense_handles", return_value=[202, 101, 303]), \
             patch.object(utility_toggles, "focus_window_handles", return_value=True) as focus_mock:
            focused = manager.focus_storage_sense()

        self.assertTrue(focused)
        focus_mock.assert_called_once_with([101, 202, 303])

    def test_close_storage_sense_prefers_tracked_handle_first(self):
        app = SimpleNamespace(_tracked_storage_sense_hwnd=101)
        manager = utility_toggles.UtilityActionsManager(app)

        with patch.object(manager, "_get_tracked_storage_sense_handle", return_value=101), \
             patch.object(manager, "_find_storage_sense_handles", return_value=[202, 101, 303]), \
             patch.object(utility_toggles, "close_window_handles", return_value=True) as close_mock:
            closed = manager.close_storage_sense()

        self.assertTrue(closed)
        close_mock.assert_called_once_with([101, 202, 303])

    def test_open_or_focus_storage_sense_focuses_existing_window(self):
        manager = utility_toggles.UtilityActionsManager()
        launch = Mock()

        with patch.object(manager, "focus_storage_sense", return_value=True):
            opened = manager.open_or_focus_storage_sense(launch)

        self.assertTrue(opened)
        launch.assert_not_called()

    def test_open_or_focus_storage_sense_launches_when_no_window_exists(self):
        manager = utility_toggles.UtilityActionsManager()
        launch = Mock()

        with patch.object(manager, "focus_storage_sense", return_value=False), \
             patch.object(utility_toggles, "find_windows_by_title_candidates") as title_search:
            opened = manager.open_or_focus_storage_sense(launch)

        self.assertTrue(opened)
        launch.assert_called_once_with()
        title_search.assert_not_called()

    def test_capture_desktop_layout_updates_saved_path(self):
        app = SimpleNamespace(saved_state={}, save_all_settings=lambda: setattr(app, "saved", True))
        app.saved = False
        manager = utility_toggles.UtilityActionsManager(app)

        with patch.object(utility_toggles, "save_desktop_icon_layout", return_value=4):
            count = manager.capture_desktop_layout("layout.json")

        self.assertEqual(count, 4)
        self.assertEqual(app.saved_state["desktop_layout_last_path"], "layout.json")
        self.assertTrue(app.saved)

    def test_restore_desktop_layout_returns_zero_on_error(self):
        manager = utility_toggles.UtilityActionsManager()

        with patch.object(utility_toggles, "restore_desktop_icon_layout", side_effect=RuntimeError("boom")):
            count = manager.restore_desktop_layout("layout.json")

        self.assertEqual(count, 0)

    def test_open_recycle_bin_returns_true_when_explorer_launches(self):
        manager = utility_toggles.UtilityActionsManager()

        with patch.object(utility_toggles.subprocess, "Popen") as popen_mock:
            opened = manager.open_recycle_bin()

        self.assertTrue(opened)
        popen_mock.assert_called_once()

    def test_is_recycle_bin_open_returns_true_when_matching_explorer_window_exists(self):
        manager = utility_toggles.UtilityActionsManager()

        with patch.object(
            utility_toggles,
            "find_recycle_bin_explorer_windows",
            return_value=[{"hwnd": 101, "pid": 3030}],
        ):
            self.assertTrue(manager.is_recycle_bin_open())

    def test_close_recycle_bin_posts_wm_close_to_matching_windows(self):
        manager = utility_toggles.UtilityActionsManager()

        with patch.object(
            utility_toggles,
            "find_recycle_bin_explorer_windows",
            return_value=[{"hwnd": 101, "pid": 3030}, {"hwnd": 202, "pid": 4040}],
        ), patch.object(utility_toggles.win32gui, "PostMessage") as post_message:
            closed = manager.close_recycle_bin()

        self.assertTrue(closed)
        self.assertEqual(post_message.call_count, 2)
        post_message.assert_any_call(101, utility_toggles.win32con.WM_CLOSE, 0, 0)
        post_message.assert_any_call(202, utility_toggles.win32con.WM_CLOSE, 0, 0)

    def test_find_recycle_bin_explorer_windows_returns_hwnd_and_pid(self):
        manager = utility_toggles.UtilityActionsManager()

        recycle_bin_window = Mock()
        recycle_bin_window.HWND = 123
        recycle_bin_window.Document.Folder.Self.Path = (
            f"::{utility_toggles.RECYCLE_BIN_CLSID}"
        )
        recycle_bin_window.Document.Folder.Self.Name = "Recycle Bin"

        downloads_window = Mock()
        downloads_window.HWND = 456
        downloads_window.Document.Folder.Self.Path = r"C:\Users\tester\Downloads"
        downloads_window.Document.Folder.Self.Name = "Downloads"

        shell = Mock()
        shell.Windows.return_value = [recycle_bin_window, downloads_window]

        with patch.object(utility_toggles.pythoncom, "CoInitialize"), \
             patch.object(utility_toggles.win32com.client, "Dispatch", return_value=shell), \
             patch.object(
                 utility_toggles.win32process,
                 "GetWindowThreadProcessId",
                 return_value=(99, 7777),
             ):
            windows = utility_toggles.find_recycle_bin_explorer_windows()

        self.assertEqual(windows, [{"hwnd": 123, "pid": 7777}])

    def test_cleanup_recycle_bin_items_older_than_deletes_only_expired_entries(self):
        manager = utility_toggles.UtilityActionsManager()
        old_item = Path("C:/old/$I123")
        new_item = Path("C:/new/$I456")
        now = datetime.now(timezone.utc)

        with patch.object(
            utility_toggles,
            "_iter_recycle_bin_metadata_files",
            return_value=iter([old_item, new_item]),
        ), patch.object(
            utility_toggles,
            "_read_recycle_bin_deleted_at",
            side_effect=[now - timedelta(days=31), now - timedelta(days=2)],
        ), patch.object(
            utility_toggles,
            "_delete_recycle_bin_entry",
            return_value=True,
        ) as delete_mock:
            deleted_count = manager.cleanup_recycle_bin_items_older_than(30)

        self.assertEqual(deleted_count, 1)
        delete_mock.assert_called_once_with(old_item)


if __name__ == "__main__":
    unittest.main()

import os
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()

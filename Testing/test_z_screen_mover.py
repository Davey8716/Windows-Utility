import sys
import unittest
from unittest.mock import patch


sys.modules.pop("screen_mover", None)

import screen_mover


class ScreenMoverEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.worker = screen_mover.ScreenMoverWorker()
        self.worker.app_hwnd = 999

    def test_window_eligible_allows_file_explorer_folder_window(self):
        with patch.object(screen_mover.win32gui, "IsWindow", return_value=True, create=True), \
             patch.object(screen_mover.win32gui, "IsWindowVisible", return_value=True, create=True), \
             patch.object(screen_mover.win32gui, "GetWindowText", return_value="Downloads", create=True), \
             patch.object(screen_mover.win32gui, "GetClassName", return_value="CabinetWClass", create=True), \
             patch.object(self.worker, "_get_window_exe", return_value="explorer.exe"):
            self.assertTrue(self.worker._is_window_eligible(101))

    def test_window_eligible_still_blocks_explorer_shell_windows(self):
        with patch.object(screen_mover.win32gui, "IsWindow", return_value=True, create=True), \
             patch.object(screen_mover.win32gui, "IsWindowVisible", return_value=True, create=True), \
             patch.object(screen_mover.win32gui, "GetWindowText", return_value="Taskbar", create=True), \
             patch.object(screen_mover.win32gui, "GetClassName", return_value="Shell_TrayWnd", create=True), \
             patch.object(self.worker, "_get_window_exe", return_value="explorer.exe"):
            self.assertFalse(self.worker._is_window_eligible(202))


if __name__ == "__main__":
    unittest.main()

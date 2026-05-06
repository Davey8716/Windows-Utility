import copy
import shutil
import sys
import unittest
import uuid
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent

for path in (PROJECT_ROOT, TESTS_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QMessageBox, QPushButton

import app_paths
import desktop_operations
import main
import right_utility_gui


class _FakeTrayIconManager:
    def __init__(self, app):
        self.app = app
        self.tray = None

    def create_tray_icon(self):
        return None


class _SafeUtilityControlApp(main.UtilityControlApp):
    def _apply_fixed_window_style(self):
        return None

    def _register_session_notifications(self):
        return None

    def _current_external_drives(self):
        return set()

    def run_recycle_bin_auto_cleanup(self):
        return None


@unittest.skipUnless(sys.platform.startswith("win"), "Windows-only live GUI smoke test")
class GuiMinimizeAfterUseLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        scratch_root = Path(__file__).resolve().parent / ".tmp"
        scratch_root.mkdir(parents=True, exist_ok=True)
        self.base_dir = scratch_root / f"gui-minimize-after-use-{uuid.uuid4().hex}"
        self.base_dir.mkdir(parents=True, exist_ok=False)
        self.desktop_home = self.base_dir / "home"
        (self.desktop_home / "Desktop").mkdir(parents=True, exist_ok=True)
        self.output_dir = self.base_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.messages = []
        self.invocations = []
        self.backup_dialog_count = 0
        self.patches = ExitStack()

        self.state = {
            "advanced_panel_open": True,
            "tooltips_enabled": False,
            "theme_dark": True,
            "main_always_on_top_enabled": False,
            "minimize_after_use_enabled": True,
            "desktop_zen_mode_enabled": False,
            "recycle_bin_auto_clean_enabled": False,
            "recycle_bin_age_rule_days": 30,
            "master_backup_output_path": str(self.output_dir),
            "backup_output_path": str(self.output_dir),
            "backup_folder_path": str(self.output_dir),
            "left_section_states": {
                "user_interface": True,
                "screen_mover": True,
                "drive_reminder_options": True,
                "organising_utilities": True,
                "recycle_bin_actions": True,
            },
            "right_section_states": {
                "windows_utilities": True,
                "sidebar_utils_section": True,
                "drive_space_display": True,
            },
        }

        self._install_patches()
        self.window = _SafeUtilityControlApp()
        self.panel = self.window.right_tools_panel
        self._stop_background_timers()
        self._patch_runtime_hooks()

        self.app_minimize = Mock(name="app_showMinimized")
        self.panel_minimize = Mock(name="panel_showMinimized")
        self.window.showMinimized = self.app_minimize
        self.panel.showMinimized = self.panel_minimize

        self.window.raise_()
        self.window.activateWindow()
        self._wait(150)

    def tearDown(self):
        try:
            self._stop_background_timers()
            if hasattr(self, "window"):
                self.window.hide()
                self._wait(250)
                self.window.deleteLater()
                self._wait(50)
        finally:
            self.patches.close()
            shutil.rmtree(self.base_dir, ignore_errors=True)

    def _install_patches(self):
        self.patches.enter_context(
            patch.object(main, "load_state", side_effect=lambda: copy.deepcopy(self.state))
        )
        self.patches.enter_context(patch.object(main, "save_state", side_effect=lambda *_a, **_k: None))
        self.patches.enter_context(
            patch.object(right_utility_gui, "save_state", side_effect=lambda *_a, **_k: None)
        )
        self.patches.enter_context(
            patch.object(desktop_operations, "save_state", side_effect=lambda *_a, **_k: None)
        )
        self.patches.enter_context(
            patch.object(app_paths, "save_state", side_effect=lambda *_a, **_k: None)
        )
        self.patches.enter_context(patch.object(main, "TrayIconManager", _FakeTrayIconManager))
        self.patches.enter_context(
            patch.object(main.SCREEN_MOVER, "configure", side_effect=lambda *_a, **_k: None)
        )
        self.patches.enter_context(
            patch.object(main.SCREEN_MOVER, "start", side_effect=lambda *_a, **_k: None)
        )
        self.patches.enter_context(
            patch.object(main.ctypes.windll.user32, "SetWindowPos", side_effect=lambda *_a, **_k: 1)
        )
        self.patches.enter_context(
            patch.object(main.UtilityActionsManager, "desktop_icons_visible", side_effect=lambda *_a, **_k: True)
        )
        self.patches.enter_context(
            patch.object(main.UtilityActionsManager, "is_backup_folder_open", side_effect=lambda *_a, **_k: False)
        )
        self.patches.enter_context(
            patch.object(main.UtilityActionsManager, "is_this_pc_open", side_effect=lambda *_a, **_k: False)
        )
        self.patches.enter_context(
            patch.object(
                main.UtilityActionsManager,
                "open_router_page",
                lambda _manager: self._record(
                    "router_login",
                    "192.168.0.1",
                    return_value="192.168.0.1",
                ),
            )
        )
        self.patches.enter_context(
            patch.object(right_utility_gui, "get_drive_info", side_effect=self._fake_drive_info)
        )
        self.patches.enter_context(
            patch.object(desktop_operations.Path, "home", side_effect=lambda: self.desktop_home)
        )
        self.patches.enter_context(
            patch.object(app_paths.QFileDialog, "getExistingDirectory", side_effect=self._fake_directory_dialog)
        )
        self.patches.enter_context(
            patch.object(right_utility_gui.subprocess, "Popen", side_effect=self._fake_popen)
        )
        self.patches.enter_context(
            patch.object(right_utility_gui.os, "startfile", side_effect=self._fake_startfile)
        )
        self.patches.enter_context(
            patch.object(
                right_utility_gui.ctypes.windll.shell32,
                "ShellExecuteW",
                side_effect=self._fake_shell_execute,
            )
        )
        self.patches.enter_context(
            patch.object(
                right_utility_gui.BraveBookmarksExporter,
                "export_to_file",
                side_effect=self._fake_bookmark_export,
            )
        )

    def _patch_runtime_hooks(self):
        self.window._show_timed_message = self._fake_timed_message
        self.window._show_modal_message = self._fake_modal_message
        self.window._capture_desktop_screenshot = (
            lambda: self._record("desktop_screenshot", return_value=None)
        )
        self.panel._run_and_output = (
            lambda command, **_kwargs: self._record("sidebar_command", command, return_value=None)
        )
        self.panel._run_elevated_and_output = (
            lambda command, **_kwargs: self._record("sidebar_command", command, return_value=None)
        )

        self.window.actions.backup_pinned_shortcuts = Mock(
            side_effect=lambda path: self._record("backup_taskbar", path, return_value=2)
        )
        self.window.actions.open_backup_folder = Mock(
            side_effect=lambda path: self._record("open_backup_folder", path, return_value=True)
        )
        self.window.actions.is_backup_folder_open = Mock(return_value=False)
        self.window.actions.capture_desktop_layout = Mock(
            side_effect=lambda path: self._record("capture_desktop_layout", path, return_value=4)
        )
        self.window.actions.restore_desktop_layout = Mock(
            side_effect=lambda path: self._record("restore_desktop_layout", path, return_value=4)
        )
        self.window.actions.open_recycle_bin = Mock(
            side_effect=lambda: self._record("open_recycle_bin", return_value=True)
        )
        self.window.actions.cleanup_recycle_bin_items_older_than = Mock(
            side_effect=lambda days: self._record("cleanup_recycle_bin", days, return_value=1)
        )
        self.window.actions.empty_recycle_bin = Mock(
            side_effect=lambda: self._record("empty_recycle_bin", return_value=True)
        )
        self.window.actions.is_this_pc_open = Mock(return_value=False)
        self.window.actions.close_this_pc = Mock(return_value=False)

    def _stop_background_timers(self):
        for timer_name in (
            "_drive_change_timer",
            "_taskbar_backup_folder_timer",
        ):
            timer = getattr(getattr(self, "window", None), timer_name, None)
            if timer is not None:
                timer.stop()

        panel = getattr(self, "panel", None)
        for timer_name in ("this_pc_button_timer", "drive_refresh_timer"):
            timer = getattr(panel, timer_name, None)
            if timer is not None:
                timer.stop()

    def _fake_drive_info(self):
        return [
            {
                "drive": "Z:\\",
                "total": 100 * 1024 * 1024,
                "free": 40 * 1024 * 1024,
                "used": 60 * 1024 * 1024,
                "ejectable": True,
            }
        ]

    def _fake_directory_dialog(self, *_args, **_kwargs):
        chosen_dir = self.output_dir / f"picked-backup-{self.backup_dialog_count}"
        self.backup_dialog_count += 1
        chosen_dir.mkdir(parents=True, exist_ok=True)
        self._record("directory_picker", str(chosen_dir), return_value=None)
        return str(chosen_dir)

    def _fake_popen(self, args, *unused_args, **unused_kwargs):
        return self._record("popen", tuple(args) if isinstance(args, list) else args, return_value=SimpleNamespace())

    def _fake_startfile(self, path, *unused_args, **unused_kwargs):
        return self._record("startfile", path, return_value=None)

    def _fake_shell_execute(self, _hwnd, _operation, target, parameters, _directory, _show):
        return self._record("shell_execute", target, parameters, return_value=33)

    def _fake_bookmark_export(self, path):
        return self._record("export_bookmarks", path, return_value=True)

    def _fake_timed_message(self, icon, title, text, timeout_ms=10_000, **_kwargs):
        self.messages.append((icon, title, text, timeout_ms))
        return None

    def _fake_modal_message(self, _icon, title, text, _buttons, default_button):
        self.messages.append(("modal", title, text))
        if title == "Export Bookmarks":
            return QMessageBox.StandardButton.Save
        if "Recycle Bin" in title:
            return self.window._message_box_button("Yes")
        return default_button

    def _record(self, name, *payload, return_value):
        self.invocations.append((name, *payload))
        return return_value

    def _wait(self, ms):
        QTest.qWait(ms)
        self.qt_app.processEvents()

    def _ensure_visible(self, widget):
        if hasattr(self.window, "main_frame") and self.window.main_frame.isAncestorOf(widget):
            self.window.main_scroll.ensureWidgetVisible(widget, 20, 20)
        elif hasattr(self.panel, "side_frame") and self.panel.side_frame.isAncestorOf(widget):
            self.panel.scroll.ensureWidgetVisible(widget, 20, 20)
        self._wait(40)

    def _find_button_prefix(self, prefix):
        for button in self.window.findChildren(QPushButton):
            if button.text().startswith(prefix):
                return button
        self.fail(f"Could not find button starting with {prefix!r}.")

    def _find_combo(self, placeholder):
        for combo in self.window.findChildren(QComboBox):
            if combo.itemText(0).strip() == placeholder:
                return combo
        self.fail(f"Could not find combo with placeholder {placeholder!r}.")

    def _find_line_edit(self, placeholder):
        for line_edit in self.window.findChildren(QLineEdit):
            if line_edit.placeholderText() == placeholder:
                return line_edit
        self.fail(f"Could not find line edit with placeholder {placeholder!r}.")

    def _click_button(self, button):
        self._ensure_visible(button)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        self._wait(60)

    def _select_combo_item(self, combo, text):
        self._ensure_visible(combo)
        QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
        self._wait(60)
        if combo.findText(text) < 0:
            self.fail(f"Could not find combo item {text!r}.")
        combo.setCurrentText(text)
        self._wait(80)

    def _double_click_drive_item(self, row=0):
        drive_list = self.panel.drive_space_list
        self._ensure_visible(drive_list)
        item = drive_list.item(row)
        self.assertIsNotNone(item, "Expected a drive list item for the live double-click test.")
        rect = drive_list.visualItemRect(item)
        QTest.mouseClick(
            drive_list.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            rect.center(),
        )
        self._wait(50)
        QTest.mouseDClick(
            drive_list.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            rect.center(),
        )
        self._wait(80)

    def _fill_line_edit(self, line_edit, text):
        self._ensure_visible(line_edit)
        line_edit.clear()
        QTest.mouseClick(line_edit, Qt.MouseButton.LeftButton)
        QTest.keyClicks(line_edit, text)
        self._wait(50)

    def _set_minimize_after_use(self, enabled):
        toggle = self._find_button_prefix("Minimize After Use")
        self.assertEqual(toggle.isChecked(), self.window.state["minimize_after_use_enabled"])
        if toggle.isChecked() != enabled:
            self._click_button(toggle)
        self.assertEqual(toggle.isChecked(), enabled)
        self.assertEqual(self.window.state["minimize_after_use_enabled"], enabled)

    def _assert_action(self, label, trigger, *, expected_app, expected_panel, wait_ms=80, after=None):
        before_app = self.app_minimize.call_count
        before_panel = self.panel_minimize.call_count
        before_invocations = len(self.invocations)

        trigger()
        self._wait(wait_ms)

        self.assertEqual(
            self.app_minimize.call_count - before_app,
            expected_app,
            f"{label} app minimize delta mismatch.",
        )
        self.assertEqual(
            self.panel_minimize.call_count - before_panel,
            expected_panel,
            f"{label} panel minimize delta mismatch.",
        )

        if after is not None:
            after(before_invocations)
            return

        self.assertGreater(
            len(self.invocations),
            before_invocations,
            f"{label} did not run its patched action.",
        )

    def _assert_invocation_name(self, before_invocations, expected_name):
        self.assertGreater(len(self.invocations), before_invocations)
        self.assertEqual(self.invocations[-1][0], expected_name)

    def test_minimize_after_use_live_click_paths(self):
        desktop_actions = self._find_combo("Desktop Actions")
        taskbar_actions = self._find_combo("Taskbar Actions")
        cleanup_actions = self._find_combo("Cleanup Actions")
        system_combo = self._find_combo("System")
        hardware_combo = self._find_combo("Hardware")
        network_combo = self._find_combo("Network")
        startup_power_combo = self._find_combo("Startup & Power")
        quick_open_combo = self._find_combo("Quick Open")
        folder_input = self._find_line_edit("Folder name")

        scenarios = [
            ("On", True, 1, 1),
            ("Off", False, 0, 0),
        ]

        for label, enabled, expected_app_minimize, expected_panel_minimize in scenarios:
            self._set_minimize_after_use(enabled)

            self._assert_action(
                f"{label}: Desktop Screenshot",
                lambda: self._click_button(self._find_button_prefix("Desktop Screenshot")),
                expected_app=expected_app_minimize,
                expected_panel=0,
                wait_ms=320 if enabled else 80,
                after=lambda before: self._assert_invocation_name(before, "desktop_screenshot"),
            )
            self._assert_action(
                f"{label}: Capture Layout",
                lambda: self._select_combo_item(desktop_actions, "Capture Layout"),
                expected_app=expected_app_minimize,
                expected_panel=0,
                after=lambda before: self._assert_invocation_name(before, "capture_desktop_layout"),
            )
            self._assert_action(
                f"{label}: Restore Layout",
                lambda: self._select_combo_item(desktop_actions, "Restore Layout"),
                expected_app=expected_app_minimize,
                expected_panel=0,
                after=lambda before: self._assert_invocation_name(before, "restore_desktop_layout"),
            )

            folder_name = f"SmokeTestFolder{label}"
            self._fill_line_edit(folder_input, folder_name)
            self._assert_action(
                f"{label}: Folder to Desktop",
                lambda: self._click_button(self._find_button_prefix("Folder → Desktop")),
                expected_app=expected_app_minimize,
                expected_panel=0,
                after=lambda _before: self.assertTrue(
                    (self.desktop_home / "Desktop" / folder_name).exists(),
                    "Folder-to-desktop action did not create the expected test folder.",
                ),
            )

            self._assert_action(
                f"{label}: Export Bookmarks",
                lambda: self._click_button(self._find_button_prefix("Export Bookmarks")),
                expected_app=expected_app_minimize,
                expected_panel=0,
                after=lambda before: self._assert_invocation_name(before, "export_bookmarks"),
            )
            self._assert_action(
                f"{label}: Backup Taskbar",
                lambda: self._select_combo_item(taskbar_actions, "Backup Taskbar"),
                expected_app=expected_app_minimize,
                expected_panel=0,
                after=lambda before: self._assert_invocation_name(before, "backup_taskbar"),
            )
            self._assert_action(
                f"{label}: Open Backup Folder",
                lambda: self._select_combo_item(taskbar_actions, "Open Backup Folder"),
                expected_app=expected_app_minimize,
                expected_panel=0,
                after=lambda before: self._assert_invocation_name(before, "open_backup_folder"),
            )
            self._assert_action(
                f"{label}: Master Backup Path",
                lambda: self._click_button(self._find_button_prefix("Master Backup Path")),
                expected_app=expected_app_minimize,
                expected_panel=0,
                after=lambda before: self.assertEqual(
                    self.invocations[before][0],
                    "directory_picker",
                    "Master Backup Path did not use the patched directory picker.",
                ),
            )

            self._assert_action(
                f"{label}: Open Recycle Bin",
                lambda: self._select_combo_item(cleanup_actions, "Open Recycle Bin"),
                expected_app=expected_app_minimize,
                expected_panel=0,
                after=lambda before: self._assert_invocation_name(before, "open_recycle_bin"),
            )
            self._assert_action(
                f"{label}: Run Auto-Clean Now",
                lambda: self._select_combo_item(cleanup_actions, "Run Auto-Clean Now"),
                expected_app=expected_app_minimize,
                expected_panel=0,
                after=lambda before: self._assert_invocation_name(before, "cleanup_recycle_bin"),
            )
            self._assert_action(
                f"{label}: Empty Recycle Bin",
                lambda: self._select_combo_item(cleanup_actions, "Empty Recycle Bin"),
                expected_app=expected_app_minimize,
                expected_panel=0,
                after=lambda before: self._assert_invocation_name(before, "empty_recycle_bin"),
            )

            self._assert_action(
                f"{label}: Open This PC",
                lambda: self._click_button(self._find_button_prefix("Open This PC")),
                expected_app=expected_app_minimize,
                expected_panel=expected_panel_minimize,
                after=lambda before: self._assert_invocation_name(before, "popen"),
            )
            self._assert_action(
                f"{label}: Drive Double-Click",
                self._double_click_drive_item,
                expected_app=expected_app_minimize,
                expected_panel=expected_panel_minimize,
                after=lambda before: self._assert_invocation_name(before, "startfile"),
            )

            for action_name in ("Control Panel", "System Settings", "System Information", "Task Manager"):
                self._assert_action(
                    f"{label}: System -> {action_name}",
                    lambda action_name=action_name: self._select_combo_item(system_combo, action_name),
                    expected_app=expected_app_minimize,
                    expected_panel=expected_panel_minimize,
                )

            for action_name in ("Device Manager", "Disk Management", "Services", "Event Viewer"):
                self._assert_action(
                    f"{label}: Hardware -> {action_name}",
                    lambda action_name=action_name: self._select_combo_item(hardware_combo, action_name),
                    expected_app=expected_app_minimize,
                    expected_panel=expected_panel_minimize,
                )

            for action_name in ("Network Connections", "Firewall", "Router Login"):
                self._assert_action(
                    f"{label}: Network -> {action_name}",
                    lambda action_name=action_name: self._select_combo_item(network_combo, action_name),
                    expected_app=expected_app_minimize,
                    expected_panel=expected_panel_minimize,
                )

            self._assert_action(
                f"{label}: Network -> IP Configuration",
                lambda: self._select_combo_item(network_combo, "IP Configuration"),
                expected_app=0,
                expected_panel=0,
                after=lambda before: self._assert_invocation_name(before, "sidebar_command"),
            )

            for action_name in ("Startup Apps", "Power Options"):
                self._assert_action(
                    f"{label}: Startup & Power -> {action_name}",
                    lambda action_name=action_name: self._select_combo_item(startup_power_combo, action_name),
                    expected_app=expected_app_minimize,
                    expected_panel=expected_panel_minimize,
                )

            for action_name in ("Open Downloads Folder", "Open Startup Folder", "Clipboard History"):
                self._assert_action(
                    f"{label}: Quick Open -> {action_name}",
                    lambda action_name=action_name: self._select_combo_item(quick_open_combo, action_name),
                    expected_app=expected_app_minimize,
                    expected_panel=expected_panel_minimize,
                )


if __name__ == "__main__":
    unittest.main()

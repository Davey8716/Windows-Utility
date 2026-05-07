import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _stubs import install_dependency_stubs

install_dependency_stubs()

import right_utility_gui


class _FakeSignal:
    def connect(self, *_args, **_kwargs):
        return None


class _FakeSidebarOutput:
    def __init__(self):
        self.text = ""

    def clear(self):
        self.text = ""

    def append(self, text):
        if self.text:
            self.text = f"{self.text}\n{text}"
        else:
            self.text = text

    def setPlainText(self, text):
        self.text = text

    def toPlainText(self):
        return self.text


class _FakeQProcess:
    class ProcessChannelMode:
        SeparateChannels = 0

    instances = []

    def __init__(self, *_args, **_kwargs):
        self.readyReadStandardOutput = _FakeSignal()
        self.readyReadStandardError = _FakeSignal()
        self.finished = _FakeSignal()
        self.start_command = None
        self.start_program = None
        self.start_args = None
        _FakeQProcess.instances.append(self)

    def setProcessChannelMode(self, _mode):
        return None

    def startCommand(self, command):
        self.start_command = command

    def start(self, program, args):
        self.start_program = program
        self.start_args = args

    def waitForStarted(self, _timeout):
        return True


class RightUtilityGuiTests(unittest.TestCase):
    def make_panel(self):
        panel = right_utility_gui.AdvancedToolsPanel.__new__(
            right_utility_gui.AdvancedToolsPanel
        )
        panel.app = SimpleNamespace(
            showMinimized=Mock(),
            actions=SimpleNamespace(
                open_router_page=Mock(),
                open_or_focus_explorer_title=Mock(
                    side_effect=lambda _title, launcher: launcher()
                ),
            ),
            state={"minimize_after_use_enabled": True},
            _show_modal_message=Mock(),
            _message_box_button=lambda name: {"Yes": 1, "No": 2, "Cancel": 3}.get(name, 0),
            _message_box_icon=lambda name: name,
        )
        panel.showMinimized = Mock()
        return panel

    def test_system_utilities_actions_use_expected_launchers(self):
        panel = self.make_panel()
        open_or_focus_window_titles = Mock(side_effect=lambda _titles, launcher: launcher())
        panel.app.actions.open_or_focus_window_titles = open_or_focus_window_titles
        open_or_focus_explorer_title = panel.app.actions.open_or_focus_explorer_title
        with patch.object(panel, "open_system_settings") as open_settings, \
             patch.object(panel, "_shell_execute") as shell_execute, \
             patch.object(right_utility_gui.subprocess, "Popen") as popen:
            actions = panel._system_utilities()

            actions["Control Panel"]()
            actions["Local Users and Groups"]()
            actions["System Restore"]()
            actions["System Settings"]()
            actions["System Information"]()

        open_settings.assert_called_once_with()
        open_or_focus_explorer_title.assert_called_once()
        self.assertEqual(open_or_focus_window_titles.call_count, 3)
        self.assertEqual(
            shell_execute.call_args_list,
            [
                unittest.mock.call(
                    "explorer.exe",
                    "shell:ControlPanelFolder",
                ),
                unittest.mock.call("lusrmgr.msc"),
                unittest.mock.call("rstrui.exe"),
            ],
        )
        self.assertEqual(
            popen.call_args_list,
            [
                unittest.mock.call(["msinfo32"]),
            ],
        )

    def test_hardware_utilities_actions_use_shell_open_helpers(self):
        panel = self.make_panel()
        with patch.object(panel, "open_device_manager") as open_device_manager, \
             patch.object(panel, "open_disk_management") as open_disk_management, \
             patch.object(panel, "open_services") as open_services, \
             patch.object(panel, "open_event_viewer") as open_event_viewer:
            actions = panel._hardware_utilities()

            actions["Device Manager"]()
            actions["Disk Management"]()
            actions["Services"]()
            actions["Event Viewer"]()

        open_device_manager.assert_called_once_with()
        open_disk_management.assert_called_once_with()
        open_services.assert_called_once_with()
        open_event_viewer.assert_called_once_with()

    def test_network_utilities_actions_use_expected_launchers(self):
        panel = self.make_panel()
        with patch.object(panel, "open_network_connections") as open_network_connections, \
             patch.object(panel, "open_firewall") as open_firewall, \
             patch.object(panel, "show_ip_config") as show_ip_config, \
             patch.object(right_utility_gui.subprocess, "Popen") as popen:
            actions = panel._network_utilities()

            actions["Network Connections"]()
            actions["Firewall"]()
            actions["IP Configuration"]()
            actions["Router Login"]()

        open_network_connections.assert_called_once_with()
        open_firewall.assert_called_once_with()
        show_ip_config.assert_called_once_with()
        self.assertEqual(popen.call_args_list, [])
        panel.app.actions.open_router_page.assert_called_once_with()

    def test_network_ip_configuration_action_skips_minimize_flag(self):
        panel = self.make_panel()

        actions = panel._network_utilities()

        self.assertTrue(getattr(actions["IP Configuration"], "skip_minimize_after_use", False))

    def test_startup_power_utilities_actions_use_expected_launchers(self):
        panel = self.make_panel()
        with patch.object(panel, "open_startup_apps") as open_startup_apps, \
             patch.object(panel, "open_power_options") as open_power_options:
            actions = panel._startup_power_utilities()

            actions["Startup Apps"]()
            actions["Power Options"]()

        open_startup_apps.assert_called_once_with()
        open_power_options.assert_called_once_with()

    def test_sidebar_network_actions_use_dhcp_lease_label(self):
        panel = self.make_panel()

        actions = panel._sidebar_network_actions()

        self.assertIn("Renew DHCP Lease", actions)
        self.assertIs(actions["Renew DHCP Lease"].__self__, panel)
        self.assertIs(actions["Renew DHCP Lease"].__func__, panel.renew_ip.__func__)
        self.assertNotIn("Renew IP", actions)
        self.assertNotIn("IP Config", actions)

    def test_shell_open_uses_shell_execute_without_parameters(self):
        panel = self.make_panel()
        with patch.object(
            right_utility_gui.ctypes.windll.shell32, "ShellExecuteW"
        ) as shell_execute:
            panel._shell_open("wf.msc")

        shell_execute.assert_called_once_with(None, "open", "wf.msc", None, None, 1)

    def test_shell_execute_passes_parameters(self):
        panel = self.make_panel()
        with patch.object(
            right_utility_gui.ctypes.windll.shell32, "ShellExecuteW"
        ) as shell_execute:
            panel._shell_execute("control.exe", "ncpa.cpl")

        shell_execute.assert_called_once_with(
            None, "open", "control.exe", "ncpa.cpl", None, 1
        )

    def test_minimize_and_run_minimizes_both_windows_before_action(self):
        panel = self.make_panel()
        action = Mock()

        panel._minimize_and_run(action)

        panel.app.showMinimized.assert_called_once_with()
        panel.showMinimized.assert_called_once_with()
        action.assert_called_once_with()

    def test_minimize_and_run_skips_minimizing_when_disabled(self):
        panel = self.make_panel()
        panel.app.state["minimize_after_use_enabled"] = False
        action = Mock()

        panel._minimize_and_run(action)

        panel.app.showMinimized.assert_not_called()
        panel.showMinimized.assert_not_called()
        action.assert_called_once_with()

    def test_open_this_pc_launches_expected_explorer_target(self):
        panel = self.make_panel()
        with patch.object(right_utility_gui.subprocess, "Popen") as popen:
            panel._open_this_pc()

        popen.assert_called_once_with(["explorer", "shell:MyComputerFolder"])

    def test_open_clipboard_history_uses_shell_open(self):
        panel = self.make_panel()
        panel.sidebar_output = _FakeSidebarOutput()

        with patch.object(panel, "_shell_open") as shell_open:
            panel.open_clipboard_history()

        shell_open.assert_called_once_with("ms-settings:clipboard")
        self.assertEqual(panel.sidebar_output.toPlainText(), "Opened Clipboard History.")

    def test_run_sleep_launches_expected_command(self):
        panel = self.make_panel()
        with patch.object(right_utility_gui.subprocess, "Popen") as popen:
            panel.run_sleep()

        popen.assert_called_once_with(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
        )

    def test_run_lock_pc_calls_lock_workstation(self):
        panel = self.make_panel()
        with patch.object(right_utility_gui.ctypes.windll.user32, "LockWorkStation") as lock_workstation:
            panel.run_lock_pc()

        lock_workstation.assert_called_once_with()

    def test_run_restart_launches_expected_command(self):
        panel = self.make_panel()
        with patch.object(right_utility_gui.subprocess, "Popen") as popen:
            panel.run_restart()

        popen.assert_called_once_with(["shutdown", "/r", "/t", "0"])

    def test_run_logout_launches_expected_command(self):
        panel = self.make_panel()
        with patch.object(right_utility_gui.subprocess, "Popen") as popen:
            panel.run_logout()

        popen.assert_called_once_with(["shutdown", "/l"])

    def test_run_shutdown_launches_expected_command(self):
        panel = self.make_panel()
        with patch.object(right_utility_gui.subprocess, "Popen") as popen:
            panel.run_shutdown()

        popen.assert_called_once_with(["shutdown", "/s", "/t", "0"])

    def test_sidebar_quick_open_actions_use_minimize_controller(self):
        panel = self.make_panel()
        with patch.object(panel, "_minimize_and_run") as minimize_and_run:
            actions = panel._sidebar_quick_open_actions()

            actions["Open Downloads Folder"]()
            actions["Open Startup Folder"]()
            actions["Clipboard History"]()

        self.assertEqual(minimize_and_run.call_count, 3)

    def test_run_sfc_scannow_uses_plain_command_arguments(self):
        panel = self.make_panel()
        with patch.object(panel, "_is_admin", return_value=True), \
             patch.object(panel, "_run_and_output") as run_and_output:
            panel.run_sfc_scannow()

        run_and_output.assert_called_once_with(["sfc", "/scannow"])

    def test_run_chkdsk_uses_plain_command_arguments(self):
        panel = self.make_panel()
        with patch.dict(right_utility_gui.os.environ, {"SystemDrive": "C:"}), \
             patch.object(panel, "_is_admin", return_value=True), \
             patch.object(panel, "_run_and_output") as run_and_output:
            panel.run_chkdsk()

        run_and_output.assert_called_once_with(["chkdsk", "C:"])

    def test_run_sfc_scannow_uses_elevated_runner_when_not_admin(self):
        panel = self.make_panel()
        with patch.object(panel, "_is_admin", return_value=False), \
             patch.object(panel, "_run_elevated_and_output") as run_elevated:
            panel.run_sfc_scannow()

        run_elevated.assert_called_once_with(["sfc", "/scannow"])

    def test_run_chkdsk_uses_elevated_runner_when_not_admin(self):
        panel = self.make_panel()
        with patch.dict(right_utility_gui.os.environ, {"SystemDrive": "C:"}), \
             patch.object(panel, "_is_admin", return_value=False), \
             patch.object(panel, "_run_elevated_and_output") as run_elevated:
            panel.run_chkdsk()

        run_elevated.assert_called_once_with(["chkdsk", "C:"])

    def test_clear_temp_uses_completion_handler_when_not_admin(self):
        panel = self.make_panel()
        with patch.object(panel, "_is_admin", return_value=False), \
             patch.dict(right_utility_gui.os.environ, {"LOCALAPPDATA": r"C:\Users\davey\AppData\Local"}), \
             patch.object(panel, "_run_and_output") as run_and_output:
            panel.clear_temp()

        run_and_output.assert_called_once()
        args, kwargs = run_and_output.call_args
        self.assertEqual(
            args,
            (
                [
                    "powershell.exe",
                    "-WindowStyle",
                    "Hidden",
                    "-NoProfile",
                    "-Command",
                    "$tempDir = 'C:\\Users\\davey\\AppData\\Local\\Temp'; "
                    "if (Test-Path -LiteralPath $tempDir) { "
                    "$accessDenied = 0; "
                    "$inUse = 0; "
                    "$other = 0; "
                    "Get-ChildItem -LiteralPath $tempDir -Force -Recurse -ErrorAction SilentlyContinue | "
                    "ForEach-Object { "
                    "try { "
                    "Remove-Item -LiteralPath $_.FullName -Force -Recurse -ErrorAction Stop "
                    "} catch { "
                    "$message = $_.Exception.Message; "
                    "if ($message -match 'Access to the path .* is denied|Access is denied') { $accessDenied++ } "
                    "elseif ($message -match 'being used by another process') { $inUse++ } "
                    "else { $other++ } "
                    "} "
                    "}; "
                    "if ($accessDenied -gt 0) { Write-Output \"Access is denied for $accessDenied item(s).\" } "
                    "if ($inUse -gt 0) { Write-Output \"In-use files were skipped: $inUse item(s).\" } "
                    "if ($other -gt 0) { Write-Output \"Additional cleanup errors: $other item(s).\" } "
                    "}",
                ],
            ),
        )
        self.assertNotIn("shell", kwargs)
        self.assertIs(
            kwargs["finished_handler"].__func__,
            panel._handle_clear_temp_finished.__func__,
        )

    def test_handle_clear_temp_finished_prompts_and_reruns_elevated_on_access_denied(self):
        panel = self.make_panel()
        panel.app._show_modal_message.return_value = 1

        with patch.object(panel, "_is_admin", return_value=False), \
             patch.dict(right_utility_gui.os.environ, {"LOCALAPPDATA": r"C:\Users\davey\AppData\Local"}), \
             patch.object(panel, "_run_elevated_and_output") as run_elevated:
            panel._handle_clear_temp_finished(
                0,
                "Access is denied.\n\n[Process finished with exit code 0]",
            )

        panel.app._show_modal_message.assert_called_once()
        self.assertEqual(panel.app._show_modal_message.call_args.args[0], "NoIcon")
        run_elevated.assert_called_once_with(
            [
                "powershell.exe",
                "-WindowStyle",
                "Hidden",
                "-NoProfile",
                "-Command",
                "$tempDir = 'C:\\Users\\davey\\AppData\\Local\\Temp'; "
                "if (Test-Path -LiteralPath $tempDir) { "
                "$accessDenied = 0; "
                "$inUse = 0; "
                "$other = 0; "
                "Get-ChildItem -LiteralPath $tempDir -Force -Recurse -ErrorAction SilentlyContinue | "
                "ForEach-Object { "
                "try { "
                "Remove-Item -LiteralPath $_.FullName -Force -Recurse -ErrorAction Stop "
                "} catch { "
                "$message = $_.Exception.Message; "
                "if ($message -match 'Access to the path .* is denied|Access is denied') { $accessDenied++ } "
                "elseif ($message -match 'being used by another process') { $inUse++ } "
                "else { $other++ } "
                "} "
                "}; "
                "if ($accessDenied -gt 0) { Write-Output \"Access is denied for $accessDenied item(s).\" } "
                "if ($inUse -gt 0) { Write-Output \"In-use files were skipped: $inUse item(s).\" } "
                "if ($other -gt 0) { Write-Output \"Additional cleanup errors: $other item(s).\" } "
                "}",
            ]
        )

    def test_handle_clear_temp_finished_ignores_in_use_only_errors(self):
        panel = self.make_panel()
        with patch.object(panel, "_is_admin", return_value=False), \
             patch.object(panel, "_run_elevated_and_output") as run_elevated:
            panel._handle_clear_temp_finished(
                0,
                "The process cannot access the file because it is being used by another process.",
            )

        panel.app._show_modal_message.assert_not_called()
        run_elevated.assert_not_called()

    def test_run_and_output_shows_full_string_command_in_status_line(self):
        panel = self.make_panel()
        panel.sidebar_output = _FakeSidebarOutput()
        panel._reset_sidebar_process = Mock()
        panel._read_process_output = Mock()
        _FakeQProcess.instances.clear()

        with patch.object(right_utility_gui, "QProcess", _FakeQProcess):
            panel._run_and_output("ipconfig /flushdns")

        self.assertEqual(panel.sidebar_output.text, "Running: ipconfig /flushdns\n")
        self.assertEqual(_FakeQProcess.instances[-1].start_command, "ipconfig /flushdns")

    def test_restart_explorer_uses_shell_execution(self):
        panel = self.make_panel()
        with patch.object(panel, "_run_and_output") as run_and_output:
            panel.restart_explorer()

        run_and_output.assert_called_once_with(
            "taskkill /f /im explorer.exe && start explorer",
            shell=True,
        )


if __name__ == "__main__":
    unittest.main()

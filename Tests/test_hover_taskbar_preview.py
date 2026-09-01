import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from resurface.features.hover_window_controls.platform.taskbar_preview import (
    BUTTON_CONTROL_TYPE,
    ElementInfo,
    InstalledAutoHotkeyRunner,
    TaskbarButtonTarget,
    TaskbarDwellEngine,
    TaskbarObservation,
    TaskbarRestoreMonitor,
    TaskbarRestoreTarget,
    WindowInfo,
    WindowsTaskbarAutomation,
    _resource_path,
    taskbar_button_from_path,
    unambiguous_restore_target,
    window_matches_button,
)


SHELL_PID = 100


def element(
    runtime_id=(1,),
    *,
    control_type=BUTTON_CONTROL_TYPE,
    process_id=SHELL_PID,
    enabled=True,
    offscreen=False,
    rect=(0, 0, 44, 48),
    name="Notepad - 1 running window pinned",
    automation_id="Appid: Microsoft.WindowsNotepad",
    has_action=True,
):
    return ElementInfo(
        runtime_id,
        control_type,
        process_id,
        enabled,
        offscreen,
        rect,
        name,
        automation_id,
        has_action,
    )


def button(runtime_id=(1,), *, name="Notepad - 1 running window pinned"):
    return TaskbarButtonTarget(
        runtime_id,
        (100, 1000, 144, 1048),
        name,
        "Appid: Microsoft.WindowsNotepad",
    )


def target(runtime_id=(1,), hwnd=50):
    return TaskbarRestoreTarget(
        runtime_id,
        hwnd,
        (100, 1000, 144, 1048),
        (0, 1000, 1920, 1048),
        SHELL_PID,
        (122, 1024),
    )


class TaskbarClassifierTests(unittest.TestCase):
    def test_taskbar_button_requires_safe_application_control(self):
        self.assertEqual(
            taskbar_button_from_path(
                [element(rect=(100, 1000, 144, 1048))], SHELL_PID
            ),
            button(),
        )
        for invalid in (
            element(process_id=999),
            element(enabled=False),
            element(offscreen=True),
            element(rect=(0, 0, 20, 20)),
            element(has_action=False),
            element(name=""),
            element(automation_id="SystemTrayIcon"),
        ):
            with self.subTest(invalid=invalid):
                self.assertIsNone(
                    taskbar_button_from_path([invalid], SHELL_PID)
                )

    def test_matches_process_or_friendly_application_identity(self):
        notepad = WindowInfo(
            50, "Notes.txt - Notepad", "Notepad", "Notepad", True
        )
        github = WindowInfo(
            51,
            "Repository - GitHub Desktop",
            "GitHubDesktop",
            "GitHub Desktop",
            True,
        )
        self.assertTrue(window_matches_button(notepad, button()))
        self.assertTrue(
            window_matches_button(
                github,
                button(name="GitHub Desktop - 1 running window pinned"),
            )
        )

    def test_unambiguous_minimized_window_creates_restore_target(self):
        result = unambiguous_restore_target(
            button(),
            [WindowInfo(50, "Notes - Notepad", "Notepad", "Notepad", True)],
            taskbar_rect=(0, 1000, 1920, 1048),
            shell_process_id=SHELL_PID,
            original_point=(122, 1024),
        )
        self.assertEqual(result, target())

    def test_rejects_restored_pinned_and_unrelated_windows(self):
        cases = (
            [WindowInfo(50, "Notes - Notepad", "Notepad", "Notepad", False)],
            [],
            [WindowInfo(50, "Browser", "Brave", "Brave", True)],
        )
        for windows in cases:
            with self.subTest(windows=windows):
                self.assertIsNone(
                    unambiguous_restore_target(
                        button(),
                        windows,
                        taskbar_rect=(0, 1000, 1920, 1048),
                        shell_process_id=SHELL_PID,
                        original_point=(122, 1024),
                    )
                )

    def test_rejects_grouped_app_even_if_only_one_window_is_minimized(self):
        windows = [
            WindowInfo(50, "One - Notepad", "Notepad", "Notepad", True),
            WindowInfo(51, "Two - Notepad", "Notepad", "Notepad", False),
        ]
        self.assertIsNone(
            unambiguous_restore_target(
                button(),
                windows,
                taskbar_rect=(0, 1000, 1920, 1048),
                shell_process_id=SHELL_PID,
                original_point=(122, 1024),
            )
        )


class TaskbarDwellEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = TaskbarDwellEngine(750)
        self.button = button()
        self.target = target()

    def observation(self, restore_target=None):
        return TaskbarObservation(self.button, restore_target)

    def test_fires_after_dwell_when_mapping_is_available(self):
        self.assertIsNone(self.engine.observe(self.observation(self.target), 0))
        self.assertIsNone(self.engine.observe(self.observation(self.target), 749))
        self.assertEqual(
            self.engine.observe(self.observation(self.target), 750), self.target
        )

    def test_waits_after_dwell_until_mapping_becomes_available(self):
        self.engine.observe(self.observation(), 0)
        self.assertIsNone(self.engine.observe(self.observation(), 750))
        self.assertEqual(
            self.engine.observe(self.observation(self.target), 900), self.target
        )

    def test_attempt_rearms_after_a_fresh_dwell_without_pointer_exit(self):
        self.engine.observe(self.observation(self.target), 0)
        self.assertEqual(
            self.engine.observe(self.observation(self.target), 750), self.target
        )
        self.engine.rearm_after_attempt(800)
        self.assertIsNone(self.engine.observe(self.observation(self.target), 1549))
        self.assertEqual(
            self.engine.observe(self.observation(self.target), 1550), self.target
        )

    def test_leaving_still_restarts_the_dwell(self):
        self.engine.observe(self.observation(self.target), 0)
        self.engine.observe(TaskbarObservation(), 1501)
        self.engine.observe(self.observation(self.target), 1502)
        self.assertEqual(
            self.engine.observe(self.observation(self.target), 2252), self.target
        )


class AutoHotkeyRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.runtime = root / "AutoHotkey64.exe"
        self.script = root / "taskbar_restore.ahk"
        self.runtime.touch()
        self.script.touch()
        self.runner = InstalledAutoHotkeyRunner(
            self.runtime, self.script, timeout_s=1
        )

    @patch("resurface.features.hover_window_controls.platform.taskbar_preview.subprocess.run")
    def test_passes_validated_target_as_hidden_one_shot_arguments(self, run):
        run.return_value = SimpleNamespace(returncode=0)
        self.assertTrue(self.runner.run(target()))
        command = run.call_args.args[0]
        self.assertEqual(command[:3], [str(self.runtime), "/ErrorStdOut=UTF-8", str(self.script)])
        self.assertEqual(command[3:], [
            "50", "122", "1024", "100", "1000", "144", "1048",
            "0", "1000", "1920", "1048", "100",
        ])
        self.assertEqual(run.call_args.kwargs["timeout"], 1)
        self.assertIn("creationflags", run.call_args.kwargs)

    @patch("resurface.features.hover_window_controls.platform.taskbar_preview.subprocess.run")
    def test_timeout_and_nonzero_exit_are_failures(self, run):
        run.side_effect = subprocess.TimeoutExpired("ahk", 1)
        self.assertFalse(self.runner.run(target()))
        run.side_effect = None
        run.return_value = SimpleNamespace(returncode=6)
        self.assertFalse(self.runner.run(target()))

    def test_missing_runtime_disables_only_runner(self):
        self.assertFalse(
            InstalledAutoHotkeyRunner(
                Path(self.temp.name) / "missing.exe", self.script
            ).available()
        )

    def test_resource_path_uses_frozen_bundle_root(self):
        bundle_root = Path(self.temp.name) / "bundle"
        relative_path = Path("resources") / "taskbar_restore.ahk"

        with patch.object(sys, "_MEIPASS", str(bundle_root), create=True):
            self.assertEqual(
                _resource_path(relative_path),
                bundle_root
                / "resurface"
                / "features"
                / "hover_window_controls"
                / relative_path,
            )


class FakeBackend:
    def __init__(self, guard, samples, *, raises=False):
        self.samples = list(samples)
        self.raises = raises
        self.initialized = threading.Event()
        self.uninitialized = threading.Event()
        self.restored = threading.Event()
        self.targets = []

    def initialize(self):
        self.initialized.set()

    def uninitialize(self):
        self.uninitialized.set()

    def sample(self):
        if self.raises:
            raise OSError("provider failed")
        return self.samples.pop(0) if self.samples else TaskbarObservation()

    def restore_if_current(self, restore_target):
        self.targets.append(restore_target)
        self.restored.set()
        return True


class TaskbarRestoreMonitorTests(unittest.TestCase):
    def test_worker_restores_once_and_releases_backend(self):
        holder = {}

        def factory(guard):
            backend = FakeBackend(
                guard,
                [
                    TaskbarObservation(button(), target()),
                    TaskbarObservation(button(), target()),
                ],
            )
            holder["backend"] = backend
            return backend

        monitor = TaskbarRestoreMonitor(factory, poll_interval_ms=1, dwell_ms=0)
        monitor.start()
        backend = holder["backend"]
        try:
            self.assertTrue(backend.initialized.wait(1))
            self.assertTrue(backend.restored.wait(1))
            self.assertEqual(backend.targets, [target()])
        finally:
            monitor.stop()
        self.assertTrue(backend.uninitialized.wait(1))

    def test_worker_survives_sampling_errors(self):
        holder = {}

        def factory(guard):
            holder["backend"] = FakeBackend(guard, [], raises=True)
            return holder["backend"]

        monitor = TaskbarRestoreMonitor(factory, poll_interval_ms=1)
        monitor.start()
        self.assertTrue(holder["backend"].initialized.wait(1))
        monitor.stop()
        self.assertTrue(holder["backend"].uninitialized.wait(1))


class AutoHotkeyTransactionTests(unittest.TestCase):
    def test_revalidates_runs_helper_and_restores_pointer(self):
        guard = threading.Event()
        runner = MagicMock()
        runner.run.return_value = True
        backend = WindowsTaskbarAutomation.__new__(WindowsTaskbarAutomation)
        backend.pointer_controlled = guard
        backend._runner = runner
        backend._user32 = MagicMock()
        backend._cursor_position = MagicMock(return_value=wintypes.POINT(122, 1024))
        backend._is_minimized = MagicMock(return_value=True)
        backend.sample = MagicMock(
            return_value=TaskbarObservation(button(), target())
        )

        self.assertTrue(backend.restore_if_current(target()))

        runner.run.assert_called_once_with(target())
        backend._user32.SetCursorPos.assert_called_once_with(122, 1024)
        self.assertFalse(guard.is_set())

    def test_stale_target_never_launches_helper(self):
        backend = WindowsTaskbarAutomation.__new__(WindowsTaskbarAutomation)
        backend.pointer_controlled = threading.Event()
        backend._runner = MagicMock()
        backend._user32 = MagicMock()
        backend._cursor_position = MagicMock(return_value=wintypes.POINT(122, 1024))
        backend._is_minimized = MagicMock(return_value=False)
        backend.sample = MagicMock(return_value=TaskbarObservation())

        self.assertFalse(backend.restore_if_current(target()))
        backend._runner.run.assert_not_called()


@unittest.skipUnless(
    Path(r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe").is_file()
    and os.environ.get("RUN_HOVER_AHK_INTEGRATION") == "1",
    "set RUN_HOVER_AHK_INTEGRATION=1 to run the pointer-affecting AutoHotkey test",
)
class AutoHotkeyScriptTests(unittest.TestCase):
    def test_missing_arguments_and_stale_window_have_distinct_exit_codes(self):
        runtime = r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe"
        script = str(
            Path(__file__).resolve().parents[1]
            / "Code Windows Resurface"
            / "resurface"
            / "features"
            / "hover_window_controls"
            / "resources"
            / "taskbar_restore.ahk"
        )
        missing = subprocess.run([runtime, script], check=False)
        self.assertEqual(missing.returncode, 2)
        point = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        stale = subprocess.run(
            [runtime, script, "99999999", str(point.x), str(point.y), "0", "1000", "44", "1048",
             "0", "1000", "1920", "1048", "100"],
            check=False,
        )
        self.assertEqual(stale.returncode, 4)


if __name__ == "__main__":
    unittest.main()

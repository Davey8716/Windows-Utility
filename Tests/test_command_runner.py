import sys
from types import SimpleNamespace

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from resurface.features.system import command_runner
from resurface.features.system.command_runner import CommandRunner


def _application():
    return QApplication.instance() or QApplication([])


def test_command_runner_streams_output_and_reports_completion():
    _application()
    runner = CommandRunner()
    chunks = []
    result = []
    loop = QEventLoop()
    runner.output_appended.connect(chunks.append)
    runner.finished.connect(lambda code, output: (result.append((code, output)), loop.quit()))
    runner.run([sys.executable, "-c", "print('runner-output')"])
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert result and result[0][0] == 0
    assert "runner-output" in "".join(chunks)
    assert "Process finished with exit code 0" in result[0][1]


def test_command_runner_emits_failure_for_missing_executable():
    _application()
    runner = CommandRunner()
    failures = []
    runner.failed.connect(failures.append)
    runner.run(["windows-resurface-command-that-does-not-exist.exe"])
    assert failures == ["Could not start process."]


def test_elevation_request_failure_replaces_raw_output_and_calls_handler(monkeypatch):
    _application()
    shell32 = SimpleNamespace(ShellExecuteExW=lambda *_args: False)
    monkeypatch.setattr(
        command_runner.ctypes,
        "windll",
        SimpleNamespace(shell32=shell32),
    )
    runner = CommandRunner()
    chunks = []
    finished = []
    runner.output_appended.connect(chunks.append)

    runner.run_elevated(
        ["chkdsk", "C:", "/scan"],
        finished=lambda code, output: finished.append((code, output)),
    )

    assert "Administrator approval was cancelled" in "".join(chunks)
    assert finished[0][0] == 1223
    assert "The command was not run." in finished[0][1]


def test_command_runner_marks_a_task_stopped_only_after_confirmed_exit():
    _application()
    runner = CommandRunner()
    chunks = []
    states = []
    runner.output_appended.connect(chunks.append)
    runner.running_changed.connect(states.append)

    runner._process = SimpleNamespace(deleteLater=lambda: None)
    runner._set_stopping(True)
    runner._stop_command_succeeded = True
    runner._pending_exit_code = 1
    runner._complete_stopped_task_if_ready()

    assert not runner.is_running
    assert states == [False]
    assert "[Task stopped by user.]" in "".join(chunks)


def test_command_runner_stops_tracked_elevated_task(monkeypatch):
    _application()
    launched = []

    def launch_stop_process(execute_info_ptr):
        execute_info_ptr._obj.hProcess = 789
        launched.append(True)
        return True

    def get_exit_code(_handle, exit_code_ptr):
        exit_code_ptr._obj.value = 0
        return 1

    kernel32 = SimpleNamespace(
        GetProcessId=lambda _handle: 456,
        WaitForSingleObject=lambda _handle, _timeout: 0,
        GetExitCodeProcess=get_exit_code,
        CloseHandle=lambda _handle: 1,
    )
    monkeypatch.setattr(
        command_runner.ctypes,
        "windll",
        SimpleNamespace(
            kernel32=kernel32,
            shell32=SimpleNamespace(ShellExecuteExW=launch_stop_process),
        ),
    )
    runner = CommandRunner()
    chunks = []
    states = []
    runner.output_appended.connect(chunks.append)
    runner.running_changed.connect(states.append)
    runner._elevated_process_handle = 456

    assert runner.cancel() is True
    assert launched == [True]
    assert runner.is_stopping
    runner._handle_task_exit(1)
    runner._poll_elevated_stop_process()
    assert not runner.is_running
    assert states == [False]
    assert "[Task stopped by user.]" in "".join(chunks)


def test_command_runner_reports_when_elevated_task_cannot_be_stopped(monkeypatch):
    _application()
    kernel32 = SimpleNamespace(GetProcessId=lambda _handle: 456)
    monkeypatch.setattr(
        command_runner.ctypes,
        "windll",
        SimpleNamespace(
            kernel32=kernel32,
            shell32=SimpleNamespace(ShellExecuteExW=lambda *_args: False),
        ),
    )
    runner = CommandRunner()
    chunks = []
    runner.output_appended.connect(chunks.append)
    runner._elevated_process_handle = 456

    assert runner.cancel() is False
    assert runner.is_running
    assert "Administrator approval was cancelled" in "".join(chunks)

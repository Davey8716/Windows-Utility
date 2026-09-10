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


def test_elevation_request_failure_replaces_raw_output_with_clear_message():
    _application()
    runner = CommandRunner()
    chunks = []
    finished = []
    runner.output_appended.connect(chunks.append)
    runner.finished.connect(lambda code, output: finished.append((code, output)))
    runner._output_parts = [
        "Running: chkdsk C:\\n",
        CommandRunner.ELEVATION_FAILURE_MARKER,
    ]

    runner._on_process_finished(1223, None)

    assert "Administrator approval was cancelled" in "".join(chunks)
    assert CommandRunner.ELEVATION_FAILURE_MARKER not in "".join(chunks)
    assert finished[0][0] == 1223
    assert "The command was not run." in finished[0][1]


def test_visible_elevation_opens_an_administrator_console(monkeypatch):
    _application()
    calls = []
    shell32 = SimpleNamespace(
        ShellExecuteW=lambda *args: calls.append(args) or 33,
    )
    monkeypatch.setattr(
        command_runner.ctypes,
        "windll",
        SimpleNamespace(shell32=shell32),
    )
    runner = CommandRunner()
    chunks = []
    runner.output_appended.connect(chunks.append)

    runner.run_elevated_visible(["chkdsk", "C:", "/scan"])

    assert calls == [
        (None, "runas", command_runner.os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"), "/k chkdsk C: /scan", None, 1)
    ]
    assert "Opened an elevated Command Prompt" in "".join(chunks)

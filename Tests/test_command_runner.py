import sys

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

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

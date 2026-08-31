from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


FinishedHandler = Callable[[int, str], None]


class CommandRunner(QObject):
    output_reset = Signal()
    output_appended = Signal(str)
    finished = Signal(int, str)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._process: QProcess | None = None
        self._finished_handler: FinishedHandler | None = None
        self._output_timer: QTimer | None = None
        self._output_path: Path | None = None
        self._output_offset = 0
        self._output_parts: list[str] = []

    @staticmethod
    def command_display_text(command) -> str:
        if isinstance(command, str):
            return command
        return subprocess.list2cmdline([str(part) for part in command])

    def set_output(self, text: str):
        self.reset()
        self.output_reset.emit()
        self._emit_output(text)

    def run(self, command, *, shell: bool = False, finished: FinishedHandler | None = None):
        self.reset()
        self.output_reset.emit()
        self._finished_handler = finished
        process = self._new_process()

        if isinstance(command, str):
            if shell:
                process.start("cmd.exe", ["/c", command])
            else:
                process.startCommand(command)
        else:
            process.start(str(command[0]), [str(part) for part in command[1:]])

        if not process.waitForStarted(3000):
            self._fail_start(process, "Could not start process.")
            return

        self._emit_output(f"Running: {self.command_display_text(command)}\n")

    def run_elevated(self, command: list[str]):
        self.reset()
        self.output_reset.emit()

        output_path = Path(tempfile.gettempdir()) / f"windows_resurface_{uuid.uuid4().hex}.log"
        output_path.write_text("", encoding="utf-8")
        self._output_path = output_path

        cmd_text = subprocess.list2cmdline([str(part) for part in command])
        log_text = subprocess.list2cmdline([str(output_path)])
        cmd_wrapper = f"{cmd_text} > {log_text} 2>&1"

        def quote_ps(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"

        quoted_args = ", ".join(quote_ps(arg) for arg in ["/c", cmd_wrapper])
        ps_command = (
            "$p = Start-Process -FilePath 'cmd.exe' "
            f"-ArgumentList @({quoted_args}) -Verb RunAs -WindowStyle Hidden "
            "-PassThru -Wait; exit $p.ExitCode"
        )

        process = self._new_process()
        timer = QTimer(self)
        timer.timeout.connect(self._poll_elevated_output)
        timer.start(250)
        self._output_timer = timer
        process.start("powershell.exe", ["-NoProfile", "-Command", ps_command])

        if not process.waitForStarted(3000):
            self._fail_start(process, "Could not start elevated process.")
            return

        self._emit_output(
            f"Running: {self.command_display_text(command)}\n"
            "Waiting for administrator approval if prompted...\n\n"
        )

    def reset(self):
        process = self._process
        self._process = None
        if process is not None:
            try:
                process.readyReadStandardOutput.disconnect(self._read_process_output)
                process.readyReadStandardError.disconnect(self._read_process_output)
                process.finished.disconnect(self._on_process_finished)
            except (RuntimeError, TypeError):
                pass
            process.kill()
            process.deleteLater()
        self._finished_handler = None
        if self._output_timer is not None:
            self._output_timer.stop()
            self._output_timer.deleteLater()
            self._output_timer = None
        self._delete_output_file()
        self._output_offset = 0
        self._output_parts = []

    def _new_process(self) -> QProcess:
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_process_output)
        process.readyReadStandardError.connect(self._read_process_output)
        process.finished.connect(self._on_process_finished)
        self._process = process
        return process

    def _emit_output(self, text: str):
        if text:
            self._output_parts.append(text)
            self.output_appended.emit(text)

    def _read_process_output(self):
        process = self._process
        if process is None:
            return
        self._emit_output(bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace"))
        self._emit_output(bytes(process.readAllStandardError()).decode("utf-8", errors="replace"))

    def _poll_elevated_output(self):
        path = self._output_path
        if path is None or not path.exists():
            return
        try:
            with path.open("rb") as handle:
                handle.seek(self._output_offset)
                chunk = handle.read()
        except OSError:
            return
        if chunk:
            self._output_offset += len(chunk)
            self._emit_output(chunk.decode("utf-8", errors="replace"))

    def _on_process_finished(self, exit_code: int, _exit_status):
        self._read_process_output()
        self._poll_elevated_output()
        if "".join(self._output_parts).strip():
            self._emit_output(f"\n\n[Process finished with exit code {exit_code}]")
        else:
            self._emit_output(f"[no output]\n\n[Process finished with exit code {exit_code}]")
        output = "".join(self._output_parts)
        handler = self._finished_handler
        self._finish_cleanup()
        self.finished.emit(exit_code, output)
        if callable(handler):
            handler(exit_code, output)

    def _fail_start(self, process: QProcess, message: str):
        if self._process is process:
            self._process = None
        process.deleteLater()
        self._finished_handler = None
        if self._output_timer is not None:
            self._output_timer.stop()
            self._output_timer.deleteLater()
            self._output_timer = None
        self._delete_output_file()
        self._emit_output(message)
        self.failed.emit(message)

    def _finish_cleanup(self):
        process = self._process
        self._process = None
        self._finished_handler = None
        if process is not None:
            process.deleteLater()
        if self._output_timer is not None:
            self._output_timer.stop()
            self._output_timer.deleteLater()
            self._output_timer = None
        self._delete_output_file()
        self._output_offset = 0

    def _delete_output_file(self):
        path = self._output_path
        self._output_path = None
        if path is not None:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            except OSError:
                pass

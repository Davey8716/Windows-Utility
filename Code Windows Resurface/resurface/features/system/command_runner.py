from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


FinishedHandler = Callable[[int, str], None]


class _ShellExecuteInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", ctypes.c_void_p),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", ctypes.c_void_p),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", ctypes.c_void_p),
        ("hProcess", ctypes.c_void_p),
    ]


class CommandRunner(QObject):
    ELEVATION_FAILURE_MARKER = "__WINDOWS_RESURFACE_ELEVATION_FAILED__"
    _SEE_MASK_NOCLOSEPROCESS = 0x00000040
    _SEE_MASK_NOASYNC = 0x00000100
    _SW_HIDE = 0
    _WAIT_OBJECT_0 = 0
    _WAIT_TIMEOUT = 258
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
        self._elevated_process_handle: int | None = None

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

        self._emit_output(
            f"Running: {self.command_display_text(command)}\n"
            "Waiting for administrator approval if prompted...\n\n"
        )
        execute_info = _ShellExecuteInfo()
        execute_info.cbSize = ctypes.sizeof(_ShellExecuteInfo)
        execute_info.fMask = self._SEE_MASK_NOCLOSEPROCESS | self._SEE_MASK_NOASYNC
        execute_info.lpVerb = "runas"
        execute_info.lpFile = "cmd.exe"
        execute_info.lpParameters = f"/d /c {cmd_wrapper}"
        execute_info.nShow = self._SW_HIDE

        try:
            launched = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(execute_info))
        except (AttributeError, OSError):
            launched = False
        if not launched or not execute_info.hProcess:
            self._replace_elevation_failure_output()
            self._complete_process(1223)
            return

        self._elevated_process_handle = int(execute_info.hProcess)
        timer = QTimer(self)
        timer.timeout.connect(self._poll_elevated_process)
        timer.start(250)
        self._output_timer = timer

    def run_elevated_visible(self, command: list[str]):
        """Run a command in an elevated console and leave its result visible."""
        self.reset()
        self.output_reset.emit()
        command_text = self.command_display_text(command)
        command_prompt = os.environ.get(
            "COMSPEC", os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
        )
        try:
            shell_execute = ctypes.windll.shell32.ShellExecuteW
            shell_execute.argtypes = [
                wintypes.HWND,
                wintypes.LPCWSTR,
                wintypes.LPCWSTR,
                wintypes.LPCWSTR,
                wintypes.LPCWSTR,
                ctypes.c_int,
            ]
            shell_execute.restype = ctypes.c_void_p
            result = shell_execute(
                None,
                "runas",
                command_prompt,
                f"/k {command_text}",
                None,
                1,
            )
        except (AttributeError, OSError):
            result = 0
        if not result or int(result) <= 32:
            self._emit_output(
                "Administrator approval was cancelled or could not be obtained. "
                "The command was not run."
            )
            return
        self._emit_output(
            f"Opened an elevated Command Prompt for: {command_text}\n"
            "Follow the command's progress and result in that window."
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
        self._close_elevated_process_handle()
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

    def _poll_elevated_process(self):
        handle = self._elevated_process_handle
        if handle is None:
            return
        try:
            wait_result = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
        except (AttributeError, OSError):
            self._replace_elevation_failure_output()
            self._complete_process(1)
            return
        if wait_result == self._WAIT_TIMEOUT:
            self._poll_elevated_output()
            return
        if wait_result != self._WAIT_OBJECT_0:
            self._replace_elevation_failure_output()
            self._complete_process(1)
            return
        exit_code = wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        self._poll_elevated_output()
        self._complete_process(int(exit_code.value))

    def _on_process_finished(self, exit_code: int, _exit_status):
        self._read_process_output()
        self._poll_elevated_output()
        self._complete_process(exit_code)

    def _replace_elevation_failure_output(self):
        self._output_parts = []
        self.output_reset.emit()
        self._emit_output(
            "Administrator approval was cancelled or could not be obtained. "
            "The command was not run."
        )

    def _complete_process(self, exit_code: int):
        if self.ELEVATION_FAILURE_MARKER in "".join(self._output_parts):
            self._replace_elevation_failure_output()
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
        self._close_elevated_process_handle()
        self._output_offset = 0

    def _close_elevated_process_handle(self):
        handle = self._elevated_process_handle
        self._elevated_process_handle = None
        if handle is not None:
            try:
                ctypes.windll.kernel32.CloseHandle(handle)
            except (AttributeError, OSError):
                pass

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

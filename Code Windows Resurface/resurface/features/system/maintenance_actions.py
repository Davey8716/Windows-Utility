from __future__ import annotations

import ctypes
import os
import subprocess
import tempfile

import psutil
from PySide6.QtCore import QObject, Signal

from resurface.features.system.command_runner import CommandRunner


class MaintenanceActions(QObject):
    temp_cleanup_admin_required = Signal()
    admin_access_required = Signal(str, object, object)
    chkdsk_blocked_by_vanguard = Signal()
    chkdsk_access_denied = Signal()

    def __init__(self, runner: CommandRunner, explorer_windows, windows, parent: QObject | None = None):
        super().__init__(parent)
        self.runner = runner
        self.explorer_windows = explorer_windows
        self.windows = windows

    @staticmethod
    def is_admin() -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    @staticmethod
    def shell_open(target: str):
        ctypes.windll.shell32.ShellExecuteW(None, "open", target, None, None, 1)

    @staticmethod
    def shell_execute(target: str, parameters: str | None = None):
        ctypes.windll.shell32.ShellExecuteW(None, "open", target, parameters, None, 1)

    @staticmethod
    def shell_execute_elevated(target: str, parameters: str | None = None):
        ctypes.windll.shell32.ShellExecuteW(None, "runas", target, parameters, None, 1)

    def flush_dns(self):
        self.runner.run("ipconfig /flushdns")

    def renew_ip(self):
        self.runner.run("ipconfig /renew")

    def show_ip_config(self):
        self.runner.run("ipconfig")

    def restart_explorer(self):
        self.runner.run("taskkill /f /im explorer.exe && start explorer", shell=True)

    def restart_bluetooth(self):
        self.runner.run("powershell Restart-Service bthserv -Force")

    @staticmethod
    def clear_temp_command() -> list[str]:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        temp_dir = os.path.join(local_app_data, "Temp") if local_app_data else tempfile.gettempdir()
        temp_dir = temp_dir.rstrip("\\/")
        quoted_temp_dir = "'" + temp_dir.replace("'", "''") + "'"
        command = (
            f"$tempDir = {quoted_temp_dir}; "
            "if (Test-Path -LiteralPath $tempDir) { "
            "$accessDenied = 0; $inUse = 0; $other = 0; "
            "Get-ChildItem -LiteralPath $tempDir -Force -Recurse -ErrorAction SilentlyContinue | "
            "ForEach-Object { try { Remove-Item -LiteralPath $_.FullName -Force -Recurse -ErrorAction Stop "
            "} catch { $message = $_.Exception.Message; "
            "if ($message -match 'Access to the path .* is denied|Access is denied') { $accessDenied++ } "
            "elseif ($message -match 'being used by another process') { $inUse++ } else { $other++ } } }; "
            "if ($accessDenied -gt 0) { Write-Output \"Access is denied for $accessDenied item(s).\" } "
            "if ($inUse -gt 0) { Write-Output \"In-use files were skipped: $inUse item(s).\" } "
            "if ($other -gt 0) { Write-Output \"Additional cleanup errors: $other item(s).\" } }"
        )
        return ["powershell.exe", "-WindowStyle", "Hidden", "-NoProfile", "-Command", command]

    def clear_temp(self):
        finished = None if self.is_admin() else self._handle_clear_temp_finished
        self.runner.run(self.clear_temp_command(), finished=finished)

    def _handle_clear_temp_finished(self, _exit_code: int, output_text: str):
        if not self.is_admin() and "access is denied" in output_text.lower():
            self.temp_cleanup_admin_required.emit()

    def retry_temp_cleanup_elevated(self):
        self.runner.run_elevated(self.clear_temp_command())

    def clear_clipboard(self):
        self.runner.run("cmd /c echo off | clip")

    def _report_open(self, opened: bool, success: str, failure: str):
        self.runner.set_output(success if opened else failure)

    def open_advanced_display_settings(self):
        self.windows.open_or_focus_titles(
            ["Advanced display"],
            lambda: self.shell_open("ms-settings:display-advanced"),
        )

    def open_display_settings(self):
        self.shell_open("ms-settings:display")
        self.runner.set_output("Opened Display Settings.")

    def open_downloads(self):
        opened = self.explorer_windows.open_or_focus_title(
            "Downloads", lambda: subprocess.Popen(["explorer", "shell:downloads"])
        )
        self._report_open(opened, "Opened Downloads folder.", "Could not open Downloads folder.")

    def open_startup_folder(self):
        path = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
        opened = self.explorer_windows.open_or_focus_folder(path, lambda: os.startfile(path))
        self._report_open(opened, "Opened Startup folder.", "Could not open Startup folder.")

    def open_sound_settings(self):
        self.shell_open("ms-settings:sound")
        self.runner.set_output("Opened Sound Settings.")

    def open_temp_folder(self):
        path = tempfile.gettempdir()
        opened = self.explorer_windows.open_or_focus_folder(path, lambda: os.startfile(path))
        self._report_open(opened, "Opened Temp folder.", "Could not open Temp folder.")

    def open_prefetch_folder(self):
        path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Prefetch")
        opened = self.explorer_windows.open_or_focus_folder(path, lambda: os.startfile(path))
        self._report_open(opened, "Opened Prefetch folder.", "Could not open Prefetch folder.")

    def open_clipboard_history(self):
        self.shell_open("ms-settings:clipboard")
        self.runner.set_output("Opened Clipboard History.")

    def open_task_manager(self):
        self.shell_execute("taskmgr")
        self.runner.set_output("Opened Task Manager.")

    def run_dism_restorehealth(self):
        self._run_admin_command(
            "DISM Repair", ["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"]
        )

    def run_sfc_scannow(self):
        self._run_admin_command("System File Checker (SFC)", ["sfc", "/scannow"])

    def run_chkdsk(self):
        if self.is_service_running("vgk"):
            self.chkdsk_blocked_by_vanguard.emit()
            return
        self._run_admin_command(
            "Check Disk (CHKDSK)",
            ["chkdsk", os.environ.get("SystemDrive", "C:"), "/scan"],
            finished=self._handle_chkdsk_finished,
        )

    @staticmethod
    def is_service_running(service_name: str) -> bool:
        try:
            return psutil.win_service_get(service_name).status().casefold() == "running"
        except (AttributeError, OSError, psutil.Error):
            return False

    def _handle_chkdsk_finished(self, exit_code: int, output_text: str):
        if exit_code != 0 and "access is denied" in output_text.casefold():
            self.chkdsk_access_denied.emit()

    def _run_admin_command(
        self,
        action_name: str,
        command: list[str],
        *,
        finished=None,
    ):
        if self.is_admin():
            self.runner.run(command, finished=finished)
        else:
            self.admin_access_required.emit(action_name, command, finished)

    def run_admin_command_elevated(self, command: list[str], *, finished=None):
        self.runner.run_elevated(command, finished=finished)

    @staticmethod
    def run_sleep():
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])

    @staticmethod
    def run_lock_pc():
        ctypes.windll.user32.LockWorkStation()

    @staticmethod
    def run_restart():
        subprocess.Popen(["shutdown", "/r", "/t", "0"])

    @staticmethod
    def run_logout():
        subprocess.Popen(["shutdown", "/l"])

    @staticmethod
    def run_shutdown():
        subprocess.Popen(["shutdown", "/s", "/t", "0"])

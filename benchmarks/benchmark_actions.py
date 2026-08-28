from __future__ import annotations

import argparse
import builtins
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from unittest.mock import patch

BENCHMARK_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BENCHMARK_DIR.parent
APP_DIR = PROJECT_ROOT / "Code Windows Resurface"
for path in (PROJECT_ROOT, APP_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from resurface.features.desktop.desktop_operations import DesktopOperationsMixin
from resurface.features.drives import external_drive_mixin
from resurface.features.drives.external_drive_mixin import ExternalDriveMixin
from resurface.features.bookmarks.universal_bookmarks_export import BraveBookmarksExporter
from resurface.features.system import utility_toggles
from resurface.features.system.utility_toggles import UtilityActionsManager
from resurface.ui import right_utility_gui


POWERSHELL = "powershell.exe"
STEP_TAX_MS = 250.0
WORKFLOW_STEPS = {
    "quick_launcher": 5,
    "inventory": 6,
    "file_task": 8,
    "maintenance": 6,
}
USB_DRIVE_PS_PIPELINE = (
    "Get-CimInstance Win32_DiskDrive | "
    "Where-Object { $_.InterfaceType -eq 'USB' } | "
    "ForEach-Object { "
    "Get-CimAssociatedInstance -InputObject $_ "
    "-Association Win32_DiskDriveToDiskPartition | "
    "ForEach-Object { "
    "Get-CimAssociatedInstance -InputObject $_ "
    "-Association Win32_LogicalDiskToPartition | "
    "ForEach-Object { $_.DeviceID } } }"
)
USB_DRIVE_PS = (
    "$ErrorActionPreference = 'SilentlyContinue'; "
    "try { "
    + USB_DRIVE_PS_PIPELINE
    + " } catch { }"
)
ROUTER_GATEWAY_PS = (
    "$gateway = ipconfig | "
    "Select-String 'Default Gateway' | "
    "ForEach-Object { ($_ -split ':')[-1].Trim() } | "
    "Where-Object { $_ -and $_ -ne '0.0.0.0' } | "
    "Select-Object -First 1; "
    "if ($gateway) { [void]$gateway }"
)
DRIVE_INFO_PS = (
    "$ErrorActionPreference = 'SilentlyContinue'; "
    "$usb = @(); "
    "try { $usb = @("
    + USB_DRIVE_PS_PIPELINE
    + ") } catch { $usb = @() }; "
    "$letters = [char[]](65..90 | ForEach-Object { [char]$_ }); "
    "foreach ($letter in $letters) { "
    "$path = \"$letter:\\\"; "
    "if (-not (Test-Path $path)) { continue } "
    "$disk = Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='$letter:'\" -ErrorAction SilentlyContinue; "
    "if ($null -eq $disk) { continue } "
    "$drive = New-Object System.IO.DriveInfo($path); "
    "if (-not $drive.IsReady) { continue } "
    "$ejectable = ($disk.DriveType -eq 2) -or ($usb -contains $path); "
    "[void]$drive.TotalSize; "
    "[void]$drive.TotalFreeSpace; "
    "[void]$ejectable }"
)


def save_state(_state):
    return None


@dataclass
class Execution:
    run: Callable[[], object]
    cleanup: Callable[[], None] | None = None


@dataclass
class BenchmarkCase:
    slug: str
    name: str
    category: str
    kind: str
    workflow_class: str | None
    iterations: int
    notes: str
    make_app_execution: Callable[[Path, int], Execution]
    make_shell_execution: Callable[[Path, int], Execution] | None = None


@dataclass
class SampleSummary:
    iterations: int
    min_ms: float
    median_ms: float
    mean_ms: float
    p95_ms: float
    max_ms: float


@dataclass
class BenchmarkResult:
    slug: str
    name: str
    category: str
    kind: str
    workflow_class: str | None
    notes: str
    app: SampleSummary
    shell: SampleSummary | None
    workflow_tax_ms: float | None
    agentic_estimate_ms: float | None
    speedup_vs_shell: float | None
    speedup_vs_agentic: float | None


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def reset_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def summarize(samples_ms: list[float]) -> SampleSummary:
    return SampleSummary(
        iterations=len(samples_ms),
        min_ms=min(samples_ms),
        median_ms=statistics.median(samples_ms),
        mean_ms=statistics.fmean(samples_ms),
        p95_ms=percentile(samples_ms, 0.95),
        max_ms=max(samples_ms),
    )


def timed_ms(fn: Callable[[], object]) -> float:
    start = time.perf_counter_ns()
    fn()
    end = time.perf_counter_ns()
    return (end - start) / 1_000_000


def run_samples(
    make_execution: Callable[[Path, int], Execution],
    case_root: Path,
    iterations: int,
    warmup: int,
) -> list[float]:
    samples: list[float] = []
    for index in range(iterations + warmup):
        execution = make_execution(case_root, index)
        try:
            if index < warmup:
                execution.run()
            else:
                samples.append(timed_ms(execution.run))
        finally:
            if execution.cleanup is not None:
                execution.cleanup()
    return samples


def workflow_tax_ms(workflow_class: str | None) -> float | None:
    if workflow_class is None:
        return None
    return WORKFLOW_STEPS[workflow_class] * STEP_TAX_MS


def make_result(
    case: BenchmarkCase,
    app_samples: list[float],
    shell_samples: list[float] | None,
) -> BenchmarkResult:
    app_summary = summarize(app_samples)
    shell_summary = summarize(shell_samples) if shell_samples else None

    tax_ms = workflow_tax_ms(case.workflow_class)
    execution_floor_ms = (
        shell_summary.median_ms if shell_summary is not None else app_summary.median_ms
    )
    agentic_estimate_ms = (
        execution_floor_ms + tax_ms if tax_ms is not None else None
    )
    speedup_vs_shell = (
        shell_summary.median_ms / app_summary.median_ms
        if shell_summary is not None and app_summary.median_ms > 0
        else None
    )
    speedup_vs_agentic = (
        agentic_estimate_ms / app_summary.median_ms
        if agentic_estimate_ms is not None and app_summary.median_ms > 0
        else None
    )

    return BenchmarkResult(
        slug=case.slug,
        name=case.name,
        category=case.category,
        kind=case.kind,
        workflow_class=case.workflow_class,
        notes=case.notes,
        app=app_summary,
        shell=shell_summary,
        workflow_tax_ms=tax_ms,
        agentic_estimate_ms=agentic_estimate_ms,
        speedup_vs_shell=speedup_vs_shell,
        speedup_vs_agentic=speedup_vs_agentic,
    )


def make_subprocess_execution(command: list[str], *, check: bool = True) -> Execution:
    def run():
        subprocess.run(
            command,
            check=check,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    return Execution(run)


def write_dummy_files(path: Path, count: int, suffix: str, size_bytes: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    payload = (b"0" * size_bytes) or b"0"
    for index in range(count):
        (path / f"item_{index:02d}{suffix}").write_bytes(payload)


def build_bookmarks_payload(profile_index: int, urls_per_folder: int = 160) -> dict:
    def make_urls(prefix: str) -> list[dict]:
        urls = []
        for index in range(urls_per_folder):
            urls.append(
                {
                    "type": "url",
                    "name": f"{prefix} Link {index}",
                    "url": f"https://example.com/{profile_index}/{prefix}/{index}",
                    "date_added": str(13370000000000000 + index),
                }
            )
        return urls

    folder = {
        "type": "folder",
        "name": f"Folder {profile_index}",
        "date_added": "13370000000000000",
        "children": make_urls("folder"),
    }
    return {
        "roots": {
            "bookmark_bar": {
                "children": [
                    folder,
                    *make_urls("bar"),
                ]
            },
            "other": {
                "children": make_urls("other"),
            },
            "synced": {
                "children": make_urls("synced"),
            },
        }
    }


def seed_bookmarks_profiles(base: Path, profile_count: int = 3) -> Path:
    user_data = (
        base
        / "BraveSoftware"
        / "Brave-Browser"
        / "User Data"
    )
    for profile_index in range(profile_count):
        profile_name = "Default" if profile_index == 0 else f"Profile {profile_index}"
        profile_dir = user_data / profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)
        bookmarks_path = profile_dir / "Bookmarks"
        bookmarks_path.write_text(
            json.dumps(build_bookmarks_payload(profile_index)),
            encoding="utf-8",
        )
    return user_data


def write_recycle_metadata(path: Path, deleted_at: datetime) -> None:
    unix_epoch_offset = 116444736000000000
    filetime = int(deleted_at.timestamp() * 10_000_000) + unix_epoch_offset
    header = (
        (2).to_bytes(8, "little")
        + (0).to_bytes(8, "little")
        + filetime.to_bytes(8, "little")
    )
    path.write_bytes(header)


class DummyFolderInput:
    def __init__(self, text: str):
        self._text = text
        self.cleared = False

    def text(self) -> str:
        return self._text

    def clear(self) -> None:
        self._text = ""
        self.cleared = True


class DummyDesktopApp(DesktopOperationsMixin):
    def __init__(self):
        self.state = {}
        self.messages: list[tuple] = []

    def _show_organizing_timed_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    def _message_box_icon(self, name: str) -> str:
        return name


class DummyComboBox:
    def __init__(self):
        self.items: list[tuple[str, str | None]] = []
        self._placeholder = ""
        self._current_index = -1
        self._tooltip = ""

    def clear(self) -> None:
        self.items.clear()

    def setPlaceholderText(self, text: str) -> None:
        self._placeholder = text

    def placeholderText(self) -> str:
        return self._placeholder

    def addItem(self, text: str, data=None) -> None:
        self.items.append((text, data))

    def setCurrentIndex(self, index: int) -> None:
        self._current_index = index

    def currentText(self) -> str:
        if 0 <= self._current_index < len(self.items):
            return self.items[self._current_index][0]
        return ""

    def itemData(self, row: int):
        return self.items[row][1]

    def setToolTip(self, text: str) -> None:
        self._tooltip = text

    def width(self) -> int:
        return 240

    def setProperty(self, _name: str, _value) -> None:
        return None

    def setStyleSheet(self, _style: str) -> None:
        return None


class DummyDriveApp(ExternalDriveMixin):
    def __init__(self, current_drives: set[str], known_drives: set[str]):
        self.state = {
            "usb_plug_notify_mode": "on",
            "usb_idle_enabled": True,
        }
        self._known_external_drives = set(known_drives)
        self._drives = set(current_drives)
        self.connected_drives_field = DummyComboBox()
        self.notifications: list[tuple[str, str]] = []

    def _current_external_drives(self) -> set[str]:
        return set(self._drives)

    def _show_timed_message(
        self,
        _icon,
        title: str,
        text: str,
        timeout_ms: int = 0,
    ) -> None:
        self.notifications.append((title, text))

    def _message_box_icon(self, name: str) -> str:
        return name

    def _apply_connected_drives_field_style(self) -> None:
        return None


def make_router_gateway_app_execution(_root: Path, _index: int) -> Execution:
    manager = UtilityActionsManager()
    patcher = patch.object(utility_toggles.webbrowser, "open", lambda *_a, **_k: True)
    print_patcher = patch.object(builtins, "print", lambda *_a, **_k: None)
    patcher.start()
    print_patcher.start()

    def cleanup():
        print_patcher.stop()
        patcher.stop()

    return Execution(manager.open_router_page, cleanup)


def make_router_gateway_shell_execution(_root: Path, _index: int) -> Execution:
    return make_subprocess_execution(
        [POWERSHELL, "-NoProfile", "-Command", ROUTER_GATEWAY_PS]
    )


def make_usb_drive_app_execution(_root: Path, _index: int) -> Execution:
    original = right_utility_gui.subprocess.check_output

    def silent_check_output(*args, **kwargs):
        kwargs.setdefault("stderr", subprocess.DEVNULL)
        return original(*args, **kwargs)

    patcher = patch.object(right_utility_gui.subprocess, "check_output", silent_check_output)
    patcher.start()
    return Execution(right_utility_gui.get_usb_drive_letters, patcher.stop)


def make_usb_drive_shell_execution(_root: Path, _index: int) -> Execution:
    return make_subprocess_execution(
        [POWERSHELL, "-NoProfile", "-Command", USB_DRIVE_PS],
        check=False,
    )


def make_drive_inventory_app_execution(_root: Path, _index: int) -> Execution:
    original = right_utility_gui.subprocess.check_output

    def silent_check_output(*args, **kwargs):
        kwargs.setdefault("stderr", subprocess.DEVNULL)
        return original(*args, **kwargs)

    patcher = patch.object(right_utility_gui.subprocess, "check_output", silent_check_output)
    patcher.start()
    return Execution(right_utility_gui.get_drive_info, patcher.stop)


def make_drive_inventory_shell_execution(_root: Path, _index: int) -> Execution:
    return make_subprocess_execution(
        [POWERSHELL, "-NoProfile", "-Command", DRIVE_INFO_PS],
        check=False,
    )


def make_desktop_folder_app_execution(root: Path, index: int) -> Execution:
    temp_home = reset_dir(root / "desktop-folder" / f"app_{index}")
    (temp_home / "Desktop").mkdir(parents=True, exist_ok=True)
    folder_name = f"Reports_{index}"
    app = DummyDesktopApp()
    app.state = {"folder_to_desktop_name": folder_name}
    folder_input = DummyFolderInput(folder_name)
    patcher = patch.object(Path, "home", return_value=temp_home)
    patcher.start()

    def cleanup():
        patcher.stop()
        shutil.rmtree(temp_home, ignore_errors=True)

    return Execution(lambda: app._create_desktop_folder(folder_input), cleanup)


def make_desktop_folder_shell_execution(root: Path, index: int) -> Execution:
    temp_home = reset_dir(root / "desktop-folder" / f"shell_{index}")
    desktop = temp_home / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    folder_path = desktop / f"Reports_{index}"
    command = (
        f"New-Item -ItemType Directory -Path {ps_quote(str(folder_path))} | Out-Null"
    )

    def cleanup():
        shutil.rmtree(temp_home, ignore_errors=True)

    return Execution(
        lambda: subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", command],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
        cleanup,
    )


def make_taskbar_backup_app_execution(root: Path, index: int) -> Execution:
    temp_root = reset_dir(root / "taskbar-backup" / f"app_{index}")
    appdata = temp_root / "AppData" / "Roaming"
    pinned_dir = (
        appdata
        / "Microsoft"
        / "Internet Explorer"
        / "Quick Launch"
        / "User Pinned"
        / "TaskBar"
    )
    write_dummy_files(pinned_dir, count=40, suffix=".lnk", size_bytes=1024)
    write_dummy_files(pinned_dir, count=10, suffix=".txt", size_bytes=256)
    destination = temp_root / "Backup"
    manager = UtilityActionsManager()
    patcher = patch.dict(os.environ, {"APPDATA": str(appdata)})
    print_patcher = patch.object(builtins, "print", lambda *_a, **_k: None)
    patcher.start()
    print_patcher.start()

    def cleanup():
        print_patcher.stop()
        patcher.stop()
        shutil.rmtree(temp_root, ignore_errors=True)

    return Execution(lambda: manager.backup_pinned_shortcuts(str(destination)), cleanup)


def make_taskbar_backup_shell_execution(root: Path, index: int) -> Execution:
    temp_root = reset_dir(root / "taskbar-backup" / f"shell_{index}")
    appdata = temp_root / "AppData" / "Roaming"
    pinned_dir = (
        appdata
        / "Microsoft"
        / "Internet Explorer"
        / "Quick Launch"
        / "User Pinned"
        / "TaskBar"
    )
    write_dummy_files(pinned_dir, count=40, suffix=".lnk", size_bytes=1024)
    write_dummy_files(pinned_dir, count=10, suffix=".txt", size_bytes=256)
    destination = temp_root / "Backup"
    command = (
        f"New-Item -ItemType Directory -Force -Path {ps_quote(str(destination))} | Out-Null; "
        f"Get-ChildItem -LiteralPath {ps_quote(str(pinned_dir))} -Filter '*.lnk' -File | "
        f"Copy-Item -Destination {ps_quote(str(destination))} -Force"
    )

    def cleanup():
        shutil.rmtree(temp_root, ignore_errors=True)

    return Execution(
        lambda: subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", command],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
        cleanup,
    )


def make_bookmarks_export_app_execution(root: Path, index: int) -> Execution:
    temp_root = reset_dir(root / "bookmarks-export" / f"app_{index}")
    local_appdata = temp_root / "LocalAppData"
    seed_bookmarks_profiles(local_appdata)
    out_path = temp_root / "BookmarksExport.html"
    exporter = BraveBookmarksExporter()
    patcher = patch.dict(os.environ, {"LOCALAPPDATA": str(local_appdata)})
    patcher.start()

    def cleanup():
        patcher.stop()
        shutil.rmtree(temp_root, ignore_errors=True)

    return Execution(lambda: exporter.export_to_file(str(out_path)), cleanup)


def make_recycle_cleanup_app_execution(root: Path, index: int) -> Execution:
    temp_root = reset_dir(root / "recycle-cleanup" / f"app_{index}")
    drives = [temp_root / "C_drive", temp_root / "D_drive"]
    now = datetime.now(timezone.utc)
    old_deleted_at = now - timedelta(days=45)
    recent_deleted_at = now - timedelta(days=7)

    for drive_index, drive_root in enumerate(drives):
        recycle_root = drive_root / "$Recycle.Bin" / f"SID_{drive_index}"
        recycle_root.mkdir(parents=True, exist_ok=True)
        for item_index in range(6):
            item_name = f"{drive_index:02d}{item_index:04d}"
            metadata = recycle_root / f"$I{item_name}"
            resource = recycle_root / f"$R{item_name}"
            write_recycle_metadata(metadata, old_deleted_at)
            resource.write_text("old item", encoding="utf-8")
        for item_index in range(4):
            item_name = f"{drive_index:02d}{item_index + 6000:04d}"
            metadata = recycle_root / f"$I{item_name}"
            resource = recycle_root / f"$R{item_name}"
            write_recycle_metadata(metadata, recent_deleted_at)
            resource.write_text("recent item", encoding="utf-8")

    manager = UtilityActionsManager()
    patcher = patch.object(utility_toggles, "_iter_windows_drive_roots", lambda: drives)
    patcher.start()

    def cleanup():
        patcher.stop()
        shutil.rmtree(temp_root, ignore_errors=True)

    return Execution(lambda: manager.cleanup_recycle_bin_items_older_than(30), cleanup)


def make_drive_poll_app_execution(root: Path, index: int) -> Execution:
    temp_root = reset_dir(root / "drive-poll" / f"app_{index}")
    app = DummyDriveApp(
        current_drives={"E:\\", "F:\\"},
        known_drives={"F:\\", "G:\\"},
    )
    patcher = patch.object(external_drive_mixin.QTimer, "singleShot", lambda *_a, **_k: None)
    patcher.start()

    def cleanup():
        patcher.stop()
        shutil.rmtree(temp_root, ignore_errors=True)

    return Execution(app._check_external_drive_changes, cleanup)


BENCHMARK_CASES = [
    BenchmarkCase(
        slug="router_gateway_detection",
        name="Router Gateway Detection",
        category="Quick Action",
        kind="interactive",
        workflow_class="quick_launcher",
        iterations=7,
        notes="Runs the real ipconfig parse path and suppresses browser launch.",
        make_app_execution=make_router_gateway_app_execution,
        make_shell_execution=make_router_gateway_shell_execution,
    ),
    BenchmarkCase(
        slug="usb_drive_letter_detection",
        name="USB Drive Letter Detection",
        category="Inventory",
        kind="interactive",
        workflow_class="inventory",
        iterations=5,
        notes="Benchmarks the PowerShell-backed USB drive discovery helper used by drive features.",
        make_app_execution=make_usb_drive_app_execution,
        make_shell_execution=make_usb_drive_shell_execution,
    ),
    BenchmarkCase(
        slug="drive_inventory_scan",
        name="Drive Inventory Scan",
        category="Inventory",
        kind="interactive",
        workflow_class="inventory",
        iterations=5,
        notes="Measures the app-side drive scan with total/free space and ejectable detection.",
        make_app_execution=make_drive_inventory_app_execution,
        make_shell_execution=make_drive_inventory_shell_execution,
    ),
    BenchmarkCase(
        slug="desktop_folder_creation",
        name="Desktop Folder Creation",
        category="File Task",
        kind="interactive",
        workflow_class="file_task",
        iterations=12,
        notes="Uses a synthetic Desktop folder so the benchmark does not touch the real user profile.",
        make_app_execution=make_desktop_folder_app_execution,
        make_shell_execution=make_desktop_folder_shell_execution,
    ),
    BenchmarkCase(
        slug="taskbar_shortcut_backup",
        name="Taskbar Shortcut Backup",
        category="File Task",
        kind="interactive",
        workflow_class="file_task",
        iterations=10,
        notes="Copies 40 synthetic shortcut files and ignores non-shortcut files like the app does.",
        make_app_execution=make_taskbar_backup_app_execution,
        make_shell_execution=make_taskbar_backup_shell_execution,
    ),
    BenchmarkCase(
        slug="bookmarks_export",
        name="Brave Bookmarks Export",
        category="File Task",
        kind="interactive",
        workflow_class="file_task",
        iterations=8,
        notes="Exports three synthetic Brave profiles with nested folders and hundreds of URLs.",
        make_app_execution=make_bookmarks_export_app_execution,
    ),
    BenchmarkCase(
        slug="recycle_bin_age_cleanup",
        name="Recycle Bin Age Cleanup",
        category="Maintenance",
        kind="interactive",
        workflow_class="maintenance",
        iterations=8,
        notes="Deletes old items from a synthetic recycle-bin fixture across two fake drives.",
        make_app_execution=make_recycle_cleanup_app_execution,
    ),
    BenchmarkCase(
        slug="drive_poll_refresh",
        name="External Drive Poll Refresh",
        category="Resident Automation",
        kind="resident",
        workflow_class=None,
        iterations=40,
        notes="Resident poll path that refreshes connected-drive state and notification deltas.",
        make_app_execution=make_drive_poll_app_execution,
    ),
]


def run_case(case: BenchmarkCase, workspace_root: Path, warmup: int) -> BenchmarkResult:
    case_root = workspace_root / case.slug
    case_root.mkdir(parents=True, exist_ok=True)

    app_samples = run_samples(
        case.make_app_execution,
        case_root,
        iterations=case.iterations,
        warmup=warmup,
    )
    shell_samples = None
    if case.make_shell_execution is not None:
        shell_samples = run_samples(
            case.make_shell_execution,
            case_root,
            iterations=case.iterations,
            warmup=warmup,
        )

    return make_result(case, app_samples, shell_samples)


def format_ms(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def format_ratio(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1f}x"


def results_to_payload(results: list[BenchmarkResult]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "step_tax_ms": STEP_TAX_MS,
        "workflow_steps": WORKFLOW_STEPS,
        "results": [asdict(result) for result in results],
    }


def render_markdown(results: list[BenchmarkResult]) -> str:
    lines = [
        "# Windows Utility Benchmark Snapshot",
        "",
        "Interactive comparison uses a local-agent lower-bound model.",
        "Agentic estimate = shell-equivalent median when available, otherwise app median, plus workflow tax.",
        f"Workflow tax uses {STEP_TAX_MS:.0f} ms per orchestration step.",
        "",
        "| Action | Category | App median ms | App p95 ms | Shell median ms | Agentic estimate ms | Speedup vs agentic | Notes |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]

    for result in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    result.name,
                    result.category,
                    format_ms(result.app.median_ms),
                    format_ms(result.app.p95_ms),
                    format_ms(result.shell.median_ms if result.shell else None),
                    format_ms(result.agentic_estimate_ms),
                    format_ratio(result.speedup_vs_agentic),
                    result.notes,
                ]
            )
            + " |"
        )

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark representative Windows Utility actions."
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
        help="Warmup iterations to discard before recording samples.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path for JSON output.",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=None,
        help="Optional path for Markdown output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace_root = reset_dir(BENCHMARK_DIR / ".tmp")
    results: list[BenchmarkResult] = []

    try:
        for case in BENCHMARK_CASES:
            results.append(run_case(case, workspace_root, warmup=args.warmup))
    finally:
        shutil.rmtree(workspace_root, ignore_errors=True)

    payload = results_to_payload(results)
    markdown = render_markdown(results)

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.markdown_out is not None:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(markdown + "\n", encoding="utf-8")

    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

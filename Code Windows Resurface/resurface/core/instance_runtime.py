"""Windows Resurface single-instance and activation support."""

from __future__ import annotations

import ctypes
import hashlib
import sys
import time
from pathlib import Path

import psutil
import win32gui
import win32process


MUTEX_BASE_NAME = "Windows Resurface"
WM_APP_RESTORE_INSTANCE = 0x8001


def _normalized_identity_path(path: Path) -> str:
    return str(path.resolve()).casefold()


def _path_identity_hash(path: Path) -> str:
    return hashlib.sha256(
        _normalized_identity_path(path).encode("utf-8")
    ).hexdigest()[:16]


def _is_packaged_execution() -> bool:
    if getattr(sys, "frozen", False):
        return True
    executable_name = Path(sys.executable).name.lower()
    return executable_name.endswith(".exe") and not executable_name.startswith(
        ("python", "py.")
    )


def current_instance_scope(entrypoint_path: Path | None = None) -> tuple[str, Path]:
    """Return the executable or source-project identity for this launch."""
    if _is_packaged_execution():
        return ("exe", Path(sys.executable).resolve())
    entrypoint_path = entrypoint_path or Path(__file__).resolve().parents[2] / "main.py"
    return ("source", entrypoint_path.resolve().parent.parent)


def instance_mutex_name(scope: tuple[str, Path] | None = None) -> str:
    scope_kind, scope_path = scope or current_instance_scope()
    return f"{MUTEX_BASE_NAME}:{scope_kind}:{_path_identity_hash(scope_path)}"


def _source_entrypoint_for_root(project_root: Path) -> Path:
    return project_root / "Code Windows Resurface" / "main.py"


def _cmdline_references_path(
    cmdline: list[str], cwd: str | None, target_path: Path
) -> bool:
    normalized_target = _normalized_identity_path(target_path)
    cwd_path = Path(cwd) if cwd else None
    for arg in cmdline:
        if not arg:
            continue
        arg_path = Path(arg.strip('"'))
        paths_to_check = [arg_path]
        if not arg_path.is_absolute() and cwd_path is not None:
            paths_to_check.append(cwd_path / arg_path)
        for path_to_check in paths_to_check:
            try:
                if _normalized_identity_path(path_to_check) == normalized_target:
                    return True
            except OSError:
                continue
    return False


def _window_matches_instance_scope(
    hwnd: int, scope: tuple[str, Path] | None = None
) -> bool:
    scope_kind, scope_path = scope or current_instance_scope()
    try:
        _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
    except Exception:
        return False
    if scope_kind == "exe":
        try:
            return _normalized_identity_path(Path(process.exe())) == _normalized_identity_path(
                scope_path
            )
        except Exception:
            return False
    try:
        return _cmdline_references_path(
            process.cmdline(), process.cwd(), _source_entrypoint_for_root(scope_path)
        )
    except Exception:
        return False


def bring_existing_instance_to_front(
    scope: tuple[str, Path] | None = None,
    *, attempts: int = 40, retry_delay_seconds: float = 0.1
) -> bool:
    """Ask a matching existing process to restore its main window."""
    scope = scope or current_instance_scope()
    for attempt in range(max(1, attempts)):
        target_hwnd = None

        def enum_handler(hwnd, _):
            nonlocal target_hwnd
            try:
                title = win32gui.GetWindowText(hwnd)
            except Exception:
                return True
            if "Windows Resurface" in title and hwnd and _window_matches_instance_scope(
                hwnd, scope
            ):
                target_hwnd = hwnd
                return False
            return True

        try:
            ctypes.windll.kernel32.SetLastError(0)
            win32gui.EnumWindows(enum_handler, None)
        except Exception as exc:
            print("[RESTORE] enumeration failed:", exc)
            return False
        if target_hwnd:
            try:
                win32gui.PostMessage(target_hwnd, WM_APP_RESTORE_INSTANCE, 0, 0)
                return True
            except Exception as exc:
                print("[RESTORE] failed:", exc)
                return False
        if attempt < attempts - 1:
            time.sleep(retry_delay_seconds)
    print("[RESTORE] existing instance did not create a window in time.")
    return False


def ensure_single_instance(entrypoint_path: Path | None = None):
    scope = current_instance_scope(entrypoint_path)
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, instance_mutex_name(scope))
    if kernel32.GetLastError() == 183:
        bring_existing_instance_to_front(scope)
        raise SystemExit(0)
    return mutex

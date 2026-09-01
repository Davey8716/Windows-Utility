"""Taskbar hover detection with an AutoHotkey pointer transaction."""

from __future__ import annotations

import ctypes
import importlib
import os
import shutil
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol, Sequence

GA_ROOT = 2
BUTTON_CONTROL_TYPE = 50000
LIST_ITEM_CONTROL_TYPE = 50007
INVOKE_PATTERN_ID = 10000
SELECTION_ITEM_PATTERN_ID = 10010
LEGACY_ACCESSIBLE_PATTERN_ID = 10018
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TASKBAR_CLASSES = frozenset({"Shell_TrayWnd", "Shell_SecondaryTrayWnd"})


@dataclass(frozen=True)
class ElementInfo:
    runtime_id: tuple[int, ...]
    control_type: int
    process_id: int
    enabled: bool
    offscreen: bool
    rect: tuple[int, int, int, int]
    name: str
    automation_id: str
    has_action: bool

    @property
    def width(self) -> int:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> int:
        return self.rect[3] - self.rect[1]


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    process_name: str
    application_name: str
    minimized: bool


@dataclass(frozen=True)
class TaskbarButtonTarget:
    runtime_id: tuple[int, ...]
    rect: tuple[int, int, int, int]
    name: str
    automation_id: str


@dataclass(frozen=True)
class TaskbarRestoreTarget:
    button_runtime_id: tuple[int, ...]
    hwnd: int
    button_rect: tuple[int, int, int, int]
    taskbar_rect: tuple[int, int, int, int]
    shell_process_id: int
    original_point: tuple[int, int]


@dataclass(frozen=True)
class TaskbarObservation:
    button: Optional[TaskbarButtonTarget] = None
    target: Optional[TaskbarRestoreTarget] = None


def _normalized_identity(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def taskbar_button_from_path(
    path: Sequence[ElementInfo], shell_process_id: int
) -> Optional[TaskbarButtonTarget]:
    """Find an enabled taskbar application button in a leaf-to-root path."""
    for element in path:
        if (
            element.process_id == shell_process_id
            and element.control_type
            in (BUTTON_CONTROL_TYPE, LIST_ITEM_CONTROL_TYPE)
            and element.runtime_id
            and element.enabled
            and not element.offscreen
            and element.width >= 24
            and element.height >= 24
            and element.has_action
            and element.name
            and not element.automation_id.startswith("SystemTray")
        ):
            return TaskbarButtonTarget(
                element.runtime_id,
                element.rect,
                element.name,
                element.automation_id,
            )
    return None


def window_matches_button(
    window: WindowInfo, button: TaskbarButtonTarget
) -> bool:
    button_identity = _normalized_identity(
        f"{button.name} {button.automation_id}"
    )
    if not button_identity:
        return False
    identities = {
        _normalized_identity(window.process_name),
        _normalized_identity(window.application_name),
    }
    title = _normalized_identity(window.title)
    identities.discard("")
    if any(len(identity) >= 4 and identity in button_identity for identity in identities):
        return True
    # Some packaged applications expose only their full window title to the
    # taskbar provider. Exact normalized containment remains conservative.
    return len(title) >= 6 and title in button_identity


def unambiguous_restore_target(
    button: TaskbarButtonTarget,
    windows: Sequence[WindowInfo],
    *,
    taskbar_rect: tuple[int, int, int, int],
    shell_process_id: int,
    original_point: tuple[int, int],
) -> Optional[TaskbarRestoreTarget]:
    matches = [window for window in windows if window_matches_button(window, button)]
    if len(matches) != 1 or not matches[0].minimized:
        return None
    return TaskbarRestoreTarget(
        button.runtime_id,
        matches[0].hwnd,
        button.rect,
        taskbar_rect,
        shell_process_id,
        original_point,
    )


class TaskbarDwellEngine:
    """Fire repeatedly, with a full dwell between attempts, while hovering."""

    def __init__(self, dwell_ms: int) -> None:
        self.set_dwell_ms(dwell_ms)

    def set_dwell_ms(self, dwell_ms: int) -> None:
        if dwell_ms < 0:
            raise ValueError("dwell_ms must not be negative")
        self.dwell_ms = dwell_ms
        self.reset()

    def reset(self) -> None:
        self._button: Optional[TaskbarButtonTarget] = None
        self._since_ms = 0.0
        self._attempted = False

    def observe(
        self, observation: TaskbarObservation, now_ms: float
    ) -> Optional[TaskbarRestoreTarget]:
        button = observation.button
        if button is None:
            self.reset()
            return None
        if button != self._button:
            self._button = button
            self._since_ms = now_ms
            self._attempted = False
            return None
        if self._attempted or now_ms - self._since_ms < self.dwell_ms:
            return None
        target = observation.target
        if target is None or target.button_runtime_id != button.runtime_id:
            return None
        self._attempted = True
        return target

    def rearm_after_attempt(self, now_ms: float) -> None:
        """Allow another attempt after a fresh dwell on the current button."""
        if self._button is not None:
            self._since_ms = now_ms
            self._attempted = False


class AutoHotkeyRunner(Protocol):
    def available(self) -> bool: ...

    def run(self, target: TaskbarRestoreTarget) -> bool: ...


def _resource_path(relative_path: Path) -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        return (
            Path(bundle_root)
            / "resurface"
            / "features"
            / "hover_window_controls"
            / relative_path
        )
    return Path(__file__).resolve().parents[1] / relative_path


class InstalledAutoHotkeyRunner:
    """Launch the bundled one-shot script with an installed AHK v2 runtime."""

    DEFAULT_RUNTIME = Path(r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe")
    SCRIPT_PATH = Path("resources") / "taskbar_restore.ahk"

    def __init__(
        self,
        runtime: Optional[Path] = None,
        script: Optional[Path] = None,
        *,
        timeout_s: float = 2.5,
    ) -> None:
        self.runtime = runtime or self._find_runtime()
        self.script = script or _resource_path(self.SCRIPT_PATH)
        self.timeout_s = timeout_s

    @classmethod
    def _find_runtime(cls) -> Optional[Path]:
        if cls.DEFAULT_RUNTIME.is_file():
            return cls.DEFAULT_RUNTIME
        discovered = shutil.which("AutoHotkey64.exe")
        return Path(discovered) if discovered else None

    def available(self) -> bool:
        return bool(
            self.runtime
            and self.runtime.is_file()
            and self.script.is_file()
        )

    def run(self, target: TaskbarRestoreTarget) -> bool:
        if not self.available() or self.runtime is None:
            return False
        values = (
            target.hwnd,
            *target.original_point,
            *target.button_rect,
            *target.taskbar_rect,
            target.shell_process_id,
        )
        command = [
            str(self.runtime),
            "/ErrorStdOut=UTF-8",
            str(self.script),
            *(str(value) for value in values),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                timeout=self.timeout_s,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0


class TaskbarBackend(Protocol):
    def initialize(self) -> None: ...

    def uninitialize(self) -> None: ...

    def sample(self) -> TaskbarObservation: ...

    def restore_if_current(self, target: TaskbarRestoreTarget) -> bool: ...


class TaskbarRestoreMonitor:
    """Own the taskbar UIA worker and expose a pointer-control guard."""

    def __init__(
        self,
        backend_factory: Optional[Callable[[threading.Event], TaskbarBackend]] = None,
        *,
        poll_interval_ms: int = 50,
        dwell_ms: int = 750,
        shutdown_timeout_s: float = 1.0,
    ) -> None:
        self.pointer_controlled = threading.Event()
        self._backend_factory = backend_factory or WindowsTaskbarAutomation
        self._poll_interval_s = poll_interval_ms / 1000.0
        self._dwell_ms = dwell_ms
        self._shutdown_timeout_s = shutdown_timeout_s
        self._stop_event = threading.Event()
        self._enabled = threading.Event()
        self._enabled.set()
        self._settings_lock = threading.Lock()
        self._state_version = 0
        self._thread: Optional[threading.Thread] = None

    def pointer_is_controlled(self) -> bool:
        return self.pointer_controlled.is_set()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._enabled.set()
        self._thread = threading.Thread(
            target=self._run,
            name="TaskbarRestoreAutomation",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._enabled.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(self._shutdown_timeout_s)
        if thread is None or not thread.is_alive():
            self._thread = None
        self.pointer_controlled.clear()

    def suspend(self) -> None:
        self._enabled.clear()
        with self._settings_lock:
            self._state_version += 1

    def resume(self) -> None:
        with self._settings_lock:
            self._state_version += 1
        self._enabled.set()

    def set_dwell_ms(self, dwell_ms: int) -> None:
        if dwell_ms < 0:
            raise ValueError("dwell_ms must not be negative")
        with self._settings_lock:
            self._dwell_ms = dwell_ms
            self._state_version += 1

    def _run(self) -> None:
        backend: Optional[TaskbarBackend] = None
        engine: Optional[TaskbarDwellEngine] = None
        active_dwell = -1
        active_version = -1
        try:
            backend = self._backend_factory(self.pointer_controlled)
            backend.initialize()
            while not self._stop_event.is_set():
                with self._settings_lock:
                    dwell_ms = self._dwell_ms
                    state_version = self._state_version
                if engine is None or dwell_ms != active_dwell:
                    engine = TaskbarDwellEngine(dwell_ms)
                    active_dwell = dwell_ms
                elif state_version != active_version:
                    engine.reset()
                active_version = state_version
                if not self._enabled.is_set():
                    engine.reset()
                else:
                    try:
                        observation = backend.sample()
                    except Exception:
                        observation = TaskbarObservation()
                    decision = engine.observe(
                        observation, time.monotonic() * 1000.0
                    )
                    if decision is not None:
                        try:
                            backend.restore_if_current(decision)
                        except Exception:
                            pass
                        finally:
                            engine.rearm_after_attempt(
                                time.monotonic() * 1000.0
                            )
                self._stop_event.wait(self._poll_interval_s)
        except Exception:
            return
        finally:
            self.pointer_controlled.clear()
            if backend is not None:
                try:
                    backend.uninitialize()
                except Exception:
                    pass


class WindowsTaskbarAutomation:
    """Read taskbar/window identity and delegate physical input to AHK."""

    MAX_ANCESTORS = 10

    def __init__(
        self,
        pointer_controlled: threading.Event,
        runner: Optional[AutoHotkeyRunner] = None,
    ) -> None:
        if os.name != "nt":
            raise OSError("Taskbar preview monitoring only supports Windows")
        self.pointer_controlled = pointer_controlled
        self._runner = runner or InstalledAutoHotkeyRunner()
        self._automation = None
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_win32()

    def _configure_win32(self) -> None:
        user32 = self._user32
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self._enum_callback_type = callback
        user32.EnumWindows.argtypes = [callback, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        self._kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self._kernel32.OpenProcess.restype = wintypes.HANDLE
        self._kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL

    def initialize(self) -> None:
        if not self._runner.available():
            raise OSError("AutoHotkey v2 is not available")
        automation = importlib.import_module("uiautomation")
        automation.InitializeUIAutomationInCurrentThread()
        self._automation = automation

    def uninitialize(self) -> None:
        if self._automation is not None:
            self._automation.UninitializeUIAutomationInCurrentThread()
            self._automation = None

    def sample(self) -> TaskbarObservation:
        point = self._cursor_position()
        if point is None:
            return TaskbarObservation()
        child = self._user32.WindowFromPoint(point)
        root = self._user32.GetAncestor(child, GA_ROOT) if child else 0
        if not root or self._window_class(root) not in TASKBAR_CLASSES:
            return TaskbarObservation()
        shell_process_id = self._window_process_id(root)
        button = taskbar_button_from_path(
            self._element_path(point), shell_process_id
        )
        if button is None:
            return TaskbarObservation()
        taskbar_rect = self._window_bounds(root)
        if taskbar_rect is None:
            return TaskbarObservation(button)
        target = unambiguous_restore_target(
            button,
            self._window_inventory(),
            taskbar_rect=taskbar_rect,
            shell_process_id=shell_process_id,
            original_point=(point.x, point.y),
        )
        return TaskbarObservation(button, target)

    def restore_if_current(self, target: TaskbarRestoreTarget) -> bool:
        original = self._cursor_position()
        if original is None:
            return False
        current = self.sample()
        if (
            current.target is None
            or current.target.hwnd != target.hwnd
            or current.target.button_runtime_id != target.button_runtime_id
            or not self._is_minimized(wintypes.HWND(target.hwnd))
        ):
            return False
        transaction = TaskbarRestoreTarget(
            target.button_runtime_id,
            target.hwnd,
            target.button_rect,
            target.taskbar_rect,
            target.shell_process_id,
            (original.x, original.y),
        )
        self.pointer_controlled.set()
        try:
            return self._runner.run(transaction)
        finally:
            try:
                self._user32.SetCursorPos(original.x, original.y)
            finally:
                self.pointer_controlled.clear()

    def _element_path(self, point: wintypes.POINT) -> list[ElementInfo]:
        if self._automation is None:
            return []
        try:
            current = self._automation.ControlFromPoint(point.x, point.y)
        except Exception:
            return []
        result = []
        for _ in range(self.MAX_ANCESTORS):
            if current is None:
                break
            info = self._element_info(current)
            if info is None:
                break
            result.append(info)
            try:
                current = current.GetParentControl()
            except Exception:
                break
        return result

    @staticmethod
    def _element_info(control: object) -> Optional[ElementInfo]:
        try:
            bounds = control.BoundingRectangle
            has_action = any(
                control.GetPattern(pattern_id) is not None
                for pattern_id in (
                    INVOKE_PATTERN_ID,
                    LEGACY_ACCESSIBLE_PATTERN_ID,
                    SELECTION_ITEM_PATTERN_ID,
                )
            )
            return ElementInfo(
                tuple(int(value) for value in control.GetRuntimeId()),
                int(control.ControlType),
                int(control.ProcessId),
                bool(control.IsEnabled),
                bool(control.IsOffscreen),
                (
                    int(bounds.left),
                    int(bounds.top),
                    int(bounds.right),
                    int(bounds.bottom),
                ),
                str(control.Name or ""),
                str(control.AutomationId or ""),
                has_action,
            )
        except Exception:
            return None

    def _window_inventory(self) -> list[WindowInfo]:
        result = []

        def collect(hwnd: int, _lparam: int) -> bool:
            native = wintypes.HWND(hwnd)
            if not self._user32.IsWindowVisible(native):
                return True
            title = self._window_title(native)
            if not title or self._window_class(native) in TASKBAR_CLASSES:
                return True
            process_name = self._process_name(self._window_process_id(native))
            result.append(
                WindowInfo(
                    int(hwnd),
                    title,
                    process_name,
                    process_name,
                    bool(self._user32.IsIconic(native)),
                )
            )
            return True

        callback = self._enum_callback_type(collect)
        self._user32.EnumWindows(callback, 0)
        return result

    def _cursor_position(self) -> Optional[wintypes.POINT]:
        point = wintypes.POINT()
        if not self._user32.GetCursorPos(ctypes.byref(point)):
            return None
        return point

    def _is_minimized(self, hwnd: wintypes.HWND) -> bool:
        return bool(
            self._user32.IsWindow(hwnd)
            and self._user32.IsWindowVisible(hwnd)
            and self._user32.IsIconic(hwnd)
        )

    def _window_bounds(
        self, hwnd: int
    ) -> Optional[tuple[int, int, int, int]]:
        rect = wintypes.RECT()
        if not self._user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return rect.left, rect.top, rect.right, rect.bottom

    def _window_process_id(self, hwnd: int) -> int:
        process_id = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        return int(process_id.value)

    def _window_class(self, hwnd: int) -> str:
        buffer = ctypes.create_unicode_buffer(256)
        if not self._user32.GetClassNameW(hwnd, buffer, len(buffer)):
            return ""
        return buffer.value

    def _window_title(self, hwnd: wintypes.HWND) -> str:
        length = int(self._user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        if not self._user32.GetWindowTextW(hwnd, buffer, len(buffer)):
            return ""
        return buffer.value.strip()

    def _process_name(self, process_id: int) -> str:
        handle = self._kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, process_id
        )
        if not handle:
            return ""
        try:
            capacity = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(capacity.value)
            if not self._kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(capacity)
            ):
                return ""
            return Path(buffer.value).stem
        finally:
            self._kernel32.CloseHandle(handle)

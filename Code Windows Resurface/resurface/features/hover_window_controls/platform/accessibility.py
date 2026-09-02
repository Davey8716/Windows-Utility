"""Detection-only UI Automation support for custom caption buttons."""

from __future__ import annotations

import importlib
import queue
import threading
from dataclasses import dataclass
from typing import Optional, Sequence

from resurface.features.hover_window_controls.core.hover_controller import CaptionAction

BUTTON_CONTROL_TYPE = 50000
MAX_ANCESTORS = 4
MAX_ROOT_ANCESTORS = 12


def normalize_accessible_text(value: object) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


_ACTION_TOKENS = {
    CaptionAction.MINIMIZE: frozenset(
        {
            "minimize",
            "minimizebutton",
            "windowminimizebutton",
            "titlebarminimizebutton",
            "btnminimize",
            "minbutton",
            "partminimizebutton",
        }
    ),
    CaptionAction.MAXIMIZE_RESTORE: frozenset(
        {
            "maximize",
            "maximizebutton",
            "windowmaximizebutton",
            "titlebarmaximizebutton",
            "btnmaximize",
            "maxbutton",
            "partmaximizebutton",
            "restore",
            "restorebutton",
            "windowrestorebutton",
            "titlebarrestorebutton",
            "btnrestore",
            "partrestorebutton",
        }
    ),
    CaptionAction.CLOSE: frozenset(
        {
            "close",
            "closebutton",
            "windowclosebutton",
            "titlebarclosebutton",
            "btnclose",
            "partclosebutton",
        }
    ),
}


def action_from_accessible_metadata(
    values: Sequence[object],
) -> Optional[CaptionAction]:
    matches: set[CaptionAction] = set()
    for value in values:
        token = normalize_accessible_text(value)
        if not token:
            continue
        for action, allowed in _ACTION_TOKENS.items():
            if token in allowed:
                matches.add(action)
    if len(matches) != 1:
        return None
    return next(iter(matches))


@dataclass(frozen=True)
class AccessibleCaptionTarget:
    action: CaptionAction
    runtime_id: tuple[int, ...]
    rect: tuple[int, int, int, int] = ()


@dataclass(frozen=True)
class AccessibilityProbe:
    target: Optional[AccessibleCaptionTarget] = None
    transient: bool = False

    @classmethod
    def unavailable(cls) -> "AccessibilityProbe":
        return cls(transient=True)


@dataclass
class _ProbeRequest:
    point: tuple[int, int]
    root_hwnd: int
    process_id: int
    root_bounds: tuple[int, int, int, int]
    caption_band_height: int
    completed: threading.Event
    result: Optional[AccessibilityProbe] = None


class CaptionAccessibilityDetector:
    """Runs UI Automation caption metadata reads on one bounded worker."""

    def __init__(self, *, shutdown_timeout_s: float = 0.5) -> None:
        self._shutdown_timeout_s = shutdown_timeout_s
        self._requests: queue.Queue[Optional[_ProbeRequest]] = queue.Queue(
            maxsize=1
        )
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._request_lock = threading.Lock()
        self._busy = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="CaptionAccessibility",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._requests.put_nowait(None)
        except queue.Full:
            pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(self._shutdown_timeout_s)
        if thread is None or not thread.is_alive():
            self._thread = None

    def probe(
        self,
        *,
        point: tuple[int, int],
        root_hwnd: int,
        process_id: int,
        root_bounds: tuple[int, int, int, int],
        caption_band_height: int,
        timeout_ms: int,
    ) -> AccessibilityProbe:
        with self._request_lock:
            if self._busy:
                return AccessibilityProbe.unavailable()
            self._busy = True

        request = _ProbeRequest(
            point,
            root_hwnd,
            process_id,
            root_bounds,
            caption_band_height,
            threading.Event(),
        )
        try:
            self._requests.put_nowait(request)
        except queue.Full:
            with self._request_lock:
                self._busy = False
            return AccessibilityProbe.unavailable()

        if not request.completed.wait(max(timeout_ms, 0) / 1000.0):
            return AccessibilityProbe.unavailable()
        return request.result or AccessibilityProbe.unavailable()

    def _run(self) -> None:
        automation = None
        try:
            automation = importlib.import_module("uiautomation")
            automation.InitializeUIAutomationInCurrentThread()
            while not self._stop_event.is_set():
                request = self._requests.get()
                if request is None:
                    break
                try:
                    request.result = self._probe_current(
                        automation,
                        request,
                    )
                except Exception:
                    request.result = AccessibilityProbe.unavailable()
                finally:
                    request.completed.set()
                    with self._request_lock:
                        self._busy = False
        except Exception:
            return
        finally:
            with self._request_lock:
                self._busy = False
            if automation is not None:
                try:
                    automation.UninitializeUIAutomationInCurrentThread()
                except Exception:
                    pass

    @staticmethod
    def _probe_current(
        automation: object,
        request: _ProbeRequest,
    ) -> AccessibilityProbe:
        control = automation.ControlFromPoint(*request.point)
        left, top, right, _bottom = request.root_bounds
        band_bottom = top + request.caption_band_height

        path = []
        current = control
        for _ in range(MAX_ROOT_ANCESTORS):
            if current is None:
                break
            path.append(current)
            try:
                current = current.GetParentControl()
            except Exception:
                return AccessibilityProbe.unavailable()

        belongs_to_root = False
        for candidate in path:
            try:
                if int(candidate.NativeWindowHandle) == request.root_hwnd:
                    belongs_to_root = True
                    break
            except Exception:
                continue
        if not belongs_to_root:
            return AccessibilityProbe()

        for control in path[:MAX_ANCESTORS]:
            if control is None:
                break
            try:
                bounds = control.BoundingRectangle
                control_bounds = (
                    int(bounds.left),
                    int(bounds.top),
                    int(bounds.right),
                    int(bounds.bottom),
                )
                within_root_band = (
                    left <= control_bounds[0] < control_bounds[2] <= right
                    and top <= control_bounds[1] < control_bounds[3]
                    <= band_bottom
                )
                if (
                    int(control.ProcessId) == request.process_id
                    and int(control.ControlType) == BUTTON_CONTROL_TYPE
                    and bool(control.IsEnabled)
                    and not bool(control.IsOffscreen)
                    and within_root_band
                ):
                    action = action_from_accessible_metadata(
                        (
                            control.Name,
                            control.AutomationId,
                            control.ClassName,
                            control.HelpText,
                        )
                    )
                    runtime_id = tuple(
                        int(value) for value in control.GetRuntimeId()
                    )
                    if action is not None and runtime_id:
                        return AccessibilityProbe(
                            AccessibleCaptionTarget(
                                action,
                                runtime_id,
                                control_bounds,
                            )
                        )
            except Exception:
                return AccessibilityProbe.unavailable()
        return AccessibilityProbe()

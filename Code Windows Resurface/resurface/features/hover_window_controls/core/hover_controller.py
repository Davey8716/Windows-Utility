"""Hover dwell tracking and Qt-based pointer monitoring."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Protocol

from PySide6.QtCore import QObject, QTimer, Qt

from resurface.features.hover_window_controls.app.identity import DEFAULT_DWELL_MS


class CaptionAction(Enum):
    MINIMIZE = auto()
    MAXIMIZE_RESTORE = auto()
    CLOSE = auto()


class DetectionSource(Enum):
    NATIVE = auto()
    ACCESSIBILITY = auto()
    VISION = auto()
    GEOMETRY = auto()


@dataclass(frozen=True)
class HoverTarget:
    hwnd: int
    action: CaptionAction
    source: DetectionSource = DetectionSource.NATIVE
    runtime_id: tuple[int, ...] = ()
    vision_id: str = ""


class ProbeStatus(Enum):
    TARGET = auto()
    NO_TARGET = auto()
    TRANSIENT_FAILURE = auto()


@dataclass(frozen=True)
class HoverProbe:
    status: ProbeStatus
    hwnd: int = 0
    target: Optional[HoverTarget] = None

    @classmethod
    def confirmed(cls, target: HoverTarget) -> "HoverProbe":
        return cls(ProbeStatus.TARGET, target.hwnd, target)

    @classmethod
    def no_target(cls, hwnd: int = 0) -> "HoverProbe":
        return cls(ProbeStatus.NO_TARGET, hwnd)

    @classmethod
    def transient(cls, hwnd: int = 0) -> "HoverProbe":
        return cls(ProbeStatus.TRANSIENT_FAILURE, hwnd)


class WindowApi(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def probe_at_cursor(
        self, timeout_ms: Optional[int] = None
    ) -> HoverProbe: ...

    def is_action_available(self, target: HoverTarget) -> bool: ...

    def execute(self, target: HoverTarget) -> bool: ...


class AuxiliaryHoverMonitor(Protocol):
    """Lifecycle contract for independent pointer-hover automation."""

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def suspend(self) -> None: ...

    def resume(self) -> None: ...

    def set_dwell_ms(self, dwell_ms: int) -> None: ...

    def pointer_is_controlled(self) -> bool: ...


class HoverDecisionEngine:
    """Turns a stream of hover samples into one-shot action decisions."""

    def __init__(
        self,
        dwell_ms: int = DEFAULT_DWELL_MS,
        *,
        transient_grace_ms: int = 200,
    ) -> None:
        if dwell_ms < 0:
            raise ValueError("dwell_ms must not be negative")
        if transient_grace_ms < 0:
            raise ValueError("transient_grace_ms must not be negative")
        self.dwell_ms = dwell_ms
        self.transient_grace_ms = transient_grace_ms
        self._candidate: Optional[HoverTarget] = None
        self._candidate_since_ms = 0.0
        self._latched: Optional[HoverTarget] = None

    def set_dwell_ms(self, dwell_ms: int) -> None:
        if dwell_ms < 0:
            raise ValueError("dwell_ms must not be negative")
        self.dwell_ms = dwell_ms
        self.reset()
        self._transient_since_ms: Optional[float] = None

    def reset(self) -> None:
        self._candidate = None
        self._candidate_since_ms = 0.0
        self._latched = None
        self._transient_since_ms = None

    def observe(
        self, probe: HoverProbe, now_ms: float
    ) -> Optional[HoverTarget]:
        if self._latched is not None:
            if probe.target == self._latched:
                return None
            if (
                probe.status is ProbeStatus.TRANSIENT_FAILURE
                and (probe.hwnd == 0 or probe.hwnd == self._latched.hwnd)
            ):
                # Never infer that the pointer left a fired button from an
                # inconclusive probe. That could allow an accidental repeat.
                return None
            # Leaving the fired button rearms it, including movement to another
            # caption button on the same window.
            self._latched = None

        if probe.status is ProbeStatus.TRANSIENT_FAILURE:
            if self._candidate is None:
                return None
            if probe.hwnd not in (0, self._candidate.hwnd):
                self._clear_candidate()
                return None
            if self._transient_since_ms is None:
                self._transient_since_ms = now_ms
                return None
            if (
                now_ms - self._transient_since_ms
                <= self.transient_grace_ms
            ):
                return None
            self._clear_candidate()
            return None

        self._transient_since_ms = None
        target = probe.target
        if probe.status is ProbeStatus.NO_TARGET or target is None:
            self._clear_candidate()
            return None

        if target != self._candidate:
            self._candidate = target
            self._candidate_since_ms = now_ms
            return None

        if now_ms - self._candidate_since_ms < self.dwell_ms:
            return None

        # The controller must revalidate and successfully execute before
        # committing the one-shot latch.
        return target

    def commit(self, target: HoverTarget) -> None:
        if self._candidate != target:
            return
        self._clear_candidate()
        self._latched = target

    def reject(self, target: HoverTarget) -> None:
        if self._candidate == target:
            self._clear_candidate()

    def _clear_candidate(self) -> None:
        if self._candidate is not None:
            self._candidate = None
        self._candidate_since_ms = 0.0
        self._transient_since_ms = None


class HoverController(QObject):
    """Samples the pointer with a Qt timer and executes dwell decisions."""

    FINAL_VALIDATION_TIMEOUT_MS = 250

    def __init__(
        self,
        window_api: WindowApi,
        *,
        auxiliary_monitor: Optional[AuxiliaryHoverMonitor] = None,
        poll_interval_ms: int = 50,
        dwell_ms: int = DEFAULT_DWELL_MS,
        transient_grace_ms: int = 200,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._window_api = window_api
        self._auxiliary_monitor = auxiliary_monitor
        self._engine = HoverDecisionEngine(
            dwell_ms,
            transient_grace_ms=transient_grace_ms,
        )
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(poll_interval_ms)
        self._timer.timeout.connect(self._poll)

    def start(self) -> None:
        self._engine.reset()
        self._window_api.start()
        if self._auxiliary_monitor is not None:
            self._auxiliary_monitor.start()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        if self._auxiliary_monitor is not None:
            self._auxiliary_monitor.stop()
        self._window_api.stop()
        self._engine.reset()

    def suspend(self) -> None:
        self._timer.stop()
        if self._auxiliary_monitor is not None:
            self._auxiliary_monitor.suspend()
        self._engine.reset()

    def resume(self) -> None:
        self._engine.reset()
        if self._auxiliary_monitor is not None:
            self._auxiliary_monitor.resume()
        self._timer.start()

    def set_dwell_ms(self, dwell_ms: int) -> None:
        self._engine.set_dwell_ms(dwell_ms)
        if self._auxiliary_monitor is not None:
            self._auxiliary_monitor.set_dwell_ms(dwell_ms)

    def _poll(self) -> None:
        if (
            self._auxiliary_monitor is not None
            and self._auxiliary_monitor.pointer_is_controlled()
        ):
            self._engine.reset()
            return
        try:
            probe = self._window_api.probe_at_cursor()
        except OSError:
            probe = HoverProbe.transient()

        decision = self._engine.observe(
            probe,
            time.monotonic() * 1000.0,
        )
        if decision is None:
            return

        # Re-check immediately before posting the command. The window may have
        # moved, closed, or changed its enabled caption controls during dwell.
        try:
            final_probe = self._window_api.probe_at_cursor(
                self.FINAL_VALIDATION_TIMEOUT_MS
            )
            if final_probe.status is ProbeStatus.TRANSIENT_FAILURE:
                self._engine.observe(
                    final_probe,
                    time.monotonic() * 1000.0,
                )
                return
            if final_probe.target != decision:
                self._engine.observe(
                    final_probe,
                    time.monotonic() * 1000.0,
                )
                return
            if not self._window_api.is_action_available(decision):
                self._engine.reject(decision)
                return
            if self._window_api.execute(decision):
                self._engine.commit(decision)
        except OSError:
            # Native failures are transient and must never terminate the tray app.
            return

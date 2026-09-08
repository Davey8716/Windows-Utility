"""Background watcher that applies monitor placement rules."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import threading
import time

from .rule_schema import first_matching_rule, normalize_monitor_rules
from .win32_windows import (
    _left_mouse_pressed,
    apply_monitor_rule,
    enumerate_eligible_windows,
    window_details,
    window_monitor_device,
)

POLL_INTERVAL_SECONDS = 0.5
MATCH_RETRY_SECONDS = 15.0
REAPPLY_SETTLE_SECONDS = 0.6


def _identity(details):
    return (
        int(details.get("process_id", 0)),
        float(details.get("process_started_at", 0.0)),
    )


def _behavior(rule):
    if rule is None:
        return None
    return {
        key: value for key, value in rule.items()
        if key not in {"id", "name", "target_label"}
    }


def _placement(rule):
    if rule is None:
        return None
    return (
        rule["target_device"].casefold(),
        rule["placement_mode"],
        rule["saved_geometry"] if rule["placement_mode"] == "saved_geometry" else None,
    )


@dataclass
class _Recovery:
    identity: tuple[int, float]
    deadline: float
    force_initial: bool
    placed: bool = False


class MonitorRuleWatcher:
    """Poll top-level windows without blocking Qt's UI thread."""

    def __init__(self, *, name="MonitorRuleWatcher"):
        self.name = name
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread = None
        self._configured_rules: list[dict] = []
        self._rules: list[dict] = []
        self._previous_rules: list[dict] | None = None
        self._revision = 0
        self._app_hwnd = None
        self._baseline_pending = True
        self._seen: dict[int, tuple[int, float]] = {}
        self._pending: dict[int, _Recovery] = {}
        self._managed: dict[int, str] = {}
        self._off_target_since: dict[int, float] = {}
        self._apply_existing_once = False
        self._apply_rule_ids: set[str] = set()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive())

    def update_rules(
        self, rules, app_hwnd=None, *, apply_existing=False, apply_rule_ids=None
    ) -> None:
        normalized = normalize_monitor_rules(copy.deepcopy(rules))
        enabled = [rule for rule in normalized if rule["enabled"]]
        requested_ids = set(apply_rule_ids or ()) & {rule["id"] for rule in enabled}
        with self._lock:
            changed = enabled != self._rules
            if changed:
                # Compare the last scanned configuration with the latest edit,
                # including reorder-only changes and rapid successive edits.
                if self._previous_rules is None:
                    self._previous_rules = self._rules
            # A save is an explicit action even when all rule values are unchanged.
            if changed or requested_ids:
                self._revision += 1
            self._apply_rule_ids.update(requested_ids)
            self._apply_rule_ids.intersection_update(rule["id"] for rule in enabled)
            self._configured_rules = normalized
            self._rules = enabled
            if app_hwnd is not None:
                self._app_hwnd = int(app_hwnd)
            running = bool(self._thread and self._thread.is_alive())
            by_id = {rule["id"]: rule for rule in enabled}
            for hwnd, rule_id in list(self._managed.items()):
                # Retain removed IDs until the scan can transfer management
                # to an equivalent winning rule, or discard it if no rule wins.
                if rule_id in by_id and not by_id[rule_id]["reapply_if_moved"]:
                    self._managed.pop(hwnd, None)
                    self._off_target_since.pop(hwnd, None)
            if not enabled:
                # The stopped watcher will not scan the disabled configuration.
                self._previous_rules = []
                self._pending.clear()
                self._managed.clear()
                self._off_target_since.clear()
                self._apply_existing_once = False
            elif apply_existing:
                self._apply_existing_once = True

        if enabled and not running:
            self.start()
        elif not enabled:
            self.stop()
        elif changed or apply_existing or requested_ids:
            self._wake_event.set()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            if not self._rules:
                return
            self._stop_event = threading.Event()
            self._wake_event = threading.Event()
            self._seen.clear()
            self._pending.clear()
            self._managed.clear()
            self._off_target_since.clear()
            self._baseline_pending = True
            self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
            thread = self._thread
        thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            if not thread or not thread.is_alive():
                self._thread = None
                return
            self._stop_event.set()
            self._wake_event.set()
        if thread is not threading.current_thread():
            thread.join(timeout=1.5)
        with self._lock:
            if not thread.is_alive():
                self._thread = None

    def note_manual_move(self, hwnd: int) -> None:
        """Apply rule precedence after a shortcut moves a window."""
        now = time.monotonic()
        should_wake = False
        with self._lock:
            details = window_details(hwnd, app_hwnd=self._app_hwnd)
            rule = first_matching_rule(self._rules, details) if details else None
            if rule is None:
                return

            self._seen[hwnd] = _identity(details)
            self._pending.pop(hwnd, None)
            if not rule["reapply_if_moved"]:
                self._managed.pop(hwnd, None)
                self._off_target_since.pop(hwnd, None)
                return

            self._managed[hwnd] = rule["id"]
            self._off_target_since[hwnd] = now
            should_wake = True

        if should_wake:
            self._wake_event.set()

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                self._wake_event.clear()
                self._scan_once()
                self._wake_event.wait(POLL_INTERVAL_SECONDS)
        except Exception as exc:
            print(f"[MONITOR_RULES] Watcher stopped unexpectedly: {exc}")
        finally:
            with self._lock:
                if threading.current_thread() is self._thread:
                    self._thread = None

    def _scan_once(self) -> None:
        with self._lock:
            if not self._rules:
                return
            app_hwnd = self._app_hwnd
        details_by_hwnd = {
            details["hwnd"]: details
            for details in enumerate_eligible_windows(app_hwnd=app_hwnd)
        }
        now = time.monotonic()
        with self._lock:
            rules = self._rules
            previous = self._previous_rules
            self._previous_rules = None
            revision = self._revision
            apply_existing = self._apply_existing_once
            self._apply_existing_once = False
            apply_rule_ids = self._apply_rule_ids
            self._apply_rule_ids = set()
            identities = {
                hwnd: _identity(details) for hwnd, details in details_by_hwnd.items()
            }
            for hwnd, identity in self._seen.items():
                if identities.get(hwnd) != identity:
                    self._pending.pop(hwnd, None)
                    self._managed.pop(hwnd, None)
                    self._off_target_since.pop(hwnd, None)

            for hwnd, details in details_by_hwnd.items():
                identity = identities[hwnd]
                is_new = not self._baseline_pending and self._seen.get(hwnd) != identity
                rule = first_matching_rule(rules, details)
                old_rule = first_matching_rule(previous, details) if previous is not None else rule
                changed = _behavior(old_rule) != _behavior(rule)
                explicitly_saved = rule is not None and rule["id"] in apply_rule_ids
                if (
                    explicitly_saved or apply_existing or is_new
                    or (changed and rule is not None)
                ):
                    # Startup skips already-correct windows. New windows and
                    # explicit placement changes must also apply the size/mode.
                    force = explicitly_saved or is_new or (
                        not apply_existing and changed
                        and _placement(old_rule) != _placement(rule)
                    )
                    self._pending[hwnd] = _Recovery(
                        identity, now + MATCH_RETRY_SECONDS, force
                    )
                if changed:
                    self._managed.pop(hwnd, None)
                    self._off_target_since.pop(hwnd, None)
                    if rule is None:
                        self._pending.pop(hwnd, None)
                elif hwnd in self._managed and rule is not None:
                    # Equivalent rules may have different IDs after reordering.
                    self._managed[hwnd] = rule["id"]

            self._seen = identities
            self._baseline_pending = False
            for hwnd, recovery in list(self._pending.items()):
                if now >= recovery.deadline:
                    self._pending.pop(hwnd, None)
            candidates = set(self._pending) | set(self._managed)

        for hwnd in candidates:
            self._place_window(hwnd, revision, now)

    def _place_window(self, hwnd: int, revision: int, now: float) -> None:
        # Refresh identity and matching details immediately before acting. Hold
        # the lock through placement so a concurrent edit cannot apply an old rule.
        with self._lock:
            if revision != self._revision:
                return
            details = window_details(hwnd, app_hwnd=self._app_hwnd)
            if details is None or _identity(details) != self._seen.get(hwnd):
                self._seen.pop(hwnd, None)
                self._pending.pop(hwnd, None)
                self._managed.pop(hwnd, None)
                self._off_target_since.pop(hwnd, None)
                return
            rule = first_matching_rule(self._rules, details)
            if rule is None:
                self._managed.pop(hwnd, None)
                self._off_target_since.pop(hwnd, None)
                return
            recovery = self._pending.get(hwnd)
            if recovery is not None and recovery.identity != _identity(details):
                self._pending.pop(hwnd, None)
                return
            if rule["reapply_if_moved"]:
                # Keep enforcement available even if a display is currently absent.
                self._managed[hwnd] = rule["id"]
            else:
                self._managed.pop(hwnd, None)
            on_target = window_monitor_device(hwnd).casefold() == rule["target_device"].casefold()
            force = recovery is not None and recovery.force_initial and not recovery.placed
            if on_target and not force:
                self._off_target_since.pop(hwnd, None)
                return
            if _left_mouse_pressed():
                self._off_target_since.pop(hwnd, None)
                # A successful placement remains under short-term recovery so
                # applications that restore their own position can be corrected.
                # If the user is now dragging that window and reapply is off,
                # treat the manual move as authoritative and end its recovery.
                if recovery is not None and recovery.placed and not rule["reapply_if_moved"]:
                    self._pending.pop(hwnd, None)
                return
            if recovery is None:
                if not rule["reapply_if_moved"]:
                    return
                since = self._off_target_since.setdefault(hwnd, now)
                if now - since < REAPPLY_SETTLE_SECONDS:
                    return
            placed = apply_monitor_rule(hwnd, rule)
            # Also guard against reentrant callbacks changing the configuration.
            if revision != self._revision:
                return
            fresh = window_details(hwnd, app_hwnd=self._app_hwnd)
            if fresh is None or _identity(fresh) != self._seen.get(hwnd):
                self._seen.pop(hwnd, None)
                self._pending.pop(hwnd, None)
                self._managed.pop(hwnd, None)
                self._off_target_since.pop(hwnd, None)
                return
            if _behavior(first_matching_rule(self._rules, fresh)) != _behavior(rule):
                return
            if placed:
                if recovery is not None:
                    recovery.placed = True
                self._off_target_since.pop(hwnd, None)

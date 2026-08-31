"""Background watcher that applies monitor placement rules."""

from __future__ import annotations

import copy
import threading
import time

from .rule_schema import first_matching_rule, normalize_monitor_rules
from .win32_windows import (
    _left_mouse_pressed,
    _window_exists,
    apply_monitor_rule,
    enumerate_eligible_windows,
    window_monitor_device,
)


POLL_INTERVAL_SECONDS = 0.5
MATCH_RETRY_SECONDS = 5.0
REAPPLY_SETTLE_SECONDS = 0.6


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
        self._app_hwnd = None
        self._baseline_pending = True
        self._seen: dict[int, tuple[int, float]] = {}
        self._pending: dict[int, float] = {}
        self._managed: dict[int, str] = {}
        self._off_target_since: dict[int, float] = {}
        self._enroll_rule_ids: set[str] = set()
        self._immediate_rule_ids: set[str] = set()
        self._apply_existing_once = False

    @property
    def is_running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive())

    def update_rules(self, rules, app_hwnd=None, *, apply_existing=False) -> None:
        normalized = normalize_monitor_rules(copy.deepcopy(rules))
        enabled = [rule for rule in normalized if rule["enabled"]]
        with self._lock:
            old_configured_by_id = {
                rule["id"]: rule for rule in self._configured_rules
            }
            new_configured_by_id = {rule["id"]: rule for rule in normalized}
            old_by_id = {rule["id"]: rule for rule in self._rules}
            new_by_id = {rule["id"]: rule for rule in enabled}
            changed_ids = {
                rule_id
                for rule_id in set(old_by_id) | set(new_by_id)
                if old_by_id.get(rule_id) != new_by_id.get(rule_id)
            }
            self._configured_rules = normalized
            self._rules = enabled
            if app_hwnd is not None:
                self._app_hwnd = int(app_hwnd)
            running = bool(self._thread and self._thread.is_alive())
            for hwnd, rule_id in list(self._managed.items()):
                if rule_id in changed_ids:
                    self._managed.pop(hwnd, None)
                    self._off_target_since.pop(hwnd, None)
            for rule_id in changed_ids:
                old_rule = old_by_id.get(rule_id)
                new_rule = new_by_id.get(rule_id)
                old_configured_rule = old_configured_by_id.get(rule_id)
                was_reenabled = (
                    old_configured_rule is not None
                    and not old_configured_rule.get("enabled")
                    and new_rule is not None
                    and new_rule.get("reapply_if_moved")
                )
                should_enroll = was_reenabled or (
                    old_rule is not None
                    and new_rule is not None
                    and new_rule.get("reapply_if_moved")
                )
                if should_enroll:
                    self._enroll_rule_ids.add(rule_id)
                    if was_reenabled:
                        self._immediate_rule_ids.add(rule_id)
                else:
                    self._enroll_rule_ids.discard(rule_id)
                    self._immediate_rule_ids.discard(rule_id)
            removed_ids = set(old_configured_by_id) - set(new_configured_by_id)
            for rule_id in removed_ids:
                self._enroll_rule_ids.discard(rule_id)
                self._immediate_rule_ids.discard(rule_id)
            if changed_ids and running:
                # Treat ordinary edits as a fresh baseline. Explicit reapply
                # enrollment requests are handled separately below.
                self._pending.clear()
                self._baseline_pending = True
            should_start = bool(enabled)
            if not should_start:
                self._enroll_rule_ids.clear()
                self._immediate_rule_ids.clear()
                self._apply_existing_once = False
            elif apply_existing:
                self._apply_existing_once = True
            if should_start and not running:
                self._baseline_pending = True

        if should_start and not running:
            self.start()
        elif not should_start:
            self.stop()
        elif changed_ids:
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

    def _snapshot(self):
        with self._lock:
            return (
                copy.deepcopy(self._rules),
                self._app_hwnd,
                set(self._enroll_rule_ids),
                set(self._immediate_rule_ids),
            )

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
        rules, app_hwnd, enroll_rule_ids, immediate_rule_ids = self._snapshot()
        if not rules:
            return
        details_by_hwnd = {
            details["hwnd"]: details
            for details in enumerate_eligible_windows(app_hwnd=app_hwnd)
        }
        eligible_identities = {
            hwnd: (
                int(details.get("process_id", 0)),
                float(details.get("process_started_at", 0.0)),
            )
            for hwnd, details in details_by_hwnd.items()
        }
        now = time.monotonic()

        with self._lock:
            apply_existing = self._apply_existing_once
            self._apply_existing_once = False
            if self._baseline_pending:
                new_identities = set()
                self._baseline_pending = False
            else:
                new_identities = {
                    hwnd
                    for hwnd, identity in eligible_identities.items()
                    if self._seen.get(hwnd) != identity
                }

            for hwnd in list(self._seen):
                if self._seen[hwnd] != eligible_identities.get(hwnd):
                    self._pending.pop(hwnd, None)
                    self._managed.pop(hwnd, None)
                    self._off_target_since.pop(hwnd, None)

            self._seen = dict(eligible_identities)
            for hwnd in new_identities:
                self._pending[hwnd] = now + MATCH_RETRY_SECONDS

            pending = dict(self._pending)

        if apply_existing:
            for hwnd, details in details_by_hwnd.items():
                rule = first_matching_rule(rules, details)
                if rule is None:
                    continue
                already_on_target = (
                    window_monitor_device(hwnd).casefold()
                    == rule["target_device"].casefold()
                )
                placed = already_on_target or apply_monitor_rule(hwnd, rule)
                if placed and rule.get("reapply_if_moved"):
                    with self._lock:
                        self._managed[hwnd] = rule["id"]

        for hwnd, deadline in pending.items():
            details = details_by_hwnd.get(hwnd)
            rule = first_matching_rule(rules, details) if details else None
            if rule is not None:
                placed = apply_monitor_rule(hwnd, rule)
                with self._lock:
                    self._pending.pop(hwnd, None)
                    if placed and rule["reapply_if_moved"]:
                        self._managed[hwnd] = rule["id"]
            elif now >= deadline:
                with self._lock:
                    self._pending.pop(hwnd, None)

        if enroll_rule_ids:
            rules = self._enroll_existing_windows(
                details_by_hwnd,
                enroll_rule_ids,
                immediate_rule_ids,
            )
        self._enforce_managed_windows(rules, now)

    def _enroll_existing_windows(
        self,
        details_by_hwnd: dict[int, dict],
        requested_rule_ids: set[str],
        immediate_rule_ids: set[str] | None = None,
    ) -> list[dict]:
        immediate_rule_ids = immediate_rule_ids or set()
        candidates = []
        with self._lock:
            active_requests = requested_rule_ids & self._enroll_rule_ids
            active_immediate = active_requests & immediate_rule_ids
            current_rules = copy.deepcopy(self._rules)
            if not active_requests:
                return current_rules

            for hwnd, details in details_by_hwnd.items():
                rule = first_matching_rule(current_rules, details)
                if (
                    rule is not None
                    and rule["id"] in active_requests
                    and rule.get("reapply_if_moved")
                ):
                    self._managed[hwnd] = rule["id"]
                    self._off_target_since.pop(hwnd, None)
                    if rule["id"] in active_immediate:
                        candidates.append((hwnd, rule))

            self._enroll_rule_ids.difference_update(active_requests)
            self._immediate_rule_ids.difference_update(active_requests)

        for hwnd, rule in candidates:
            if (
                window_monitor_device(hwnd).casefold()
                != rule["target_device"].casefold()
            ):
                apply_monitor_rule(hwnd, rule)
        return current_rules

    def _enforce_managed_windows(self, rules: list[dict], now: float) -> None:
        by_id = {rule["id"]: rule for rule in rules}
        with self._lock:
            managed = dict(self._managed)
        dragging = _left_mouse_pressed()
        for hwnd, rule_id in managed.items():
            rule = by_id.get(rule_id)
            if rule is None or not rule.get("reapply_if_moved") or not _window_exists(hwnd):
                with self._lock:
                    self._managed.pop(hwnd, None)
                    self._off_target_since.pop(hwnd, None)
                continue
            if window_monitor_device(hwnd).casefold() == rule["target_device"].casefold():
                with self._lock:
                    self._off_target_since.pop(hwnd, None)
                continue
            with self._lock:
                since = self._off_target_since.setdefault(hwnd, now)
            if not dragging and now - since >= REAPPLY_SETTLE_SECONDS:
                if apply_monitor_rule(hwnd, rule):
                    with self._lock:
                        self._off_target_since.pop(hwnd, None)

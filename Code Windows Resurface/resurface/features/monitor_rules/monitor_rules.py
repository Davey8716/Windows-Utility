from __future__ import annotations

import copy
import ctypes
import os
import threading
import time
import uuid
from ctypes import wintypes

import psutil
import win32api
import win32con
import win32gui
import win32process


POLL_INTERVAL_SECONDS = 0.5
MATCH_RETRY_SECONDS = 5.0
REAPPLY_SETTLE_SECONDS = 0.6
PLACEMENT_MODES = {"keep_size", "maximize", "saved_geometry"}
SYSTEM_EXECUTABLES = {
    "applicationframehost.exe",
    "dwm.exe",
    "explorer.exe",
    "searchhost.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "textinputhost.exe",
    "widgets.exe",
}


def _clean_text(value) -> str:
    return str(value or "").strip()


def _normalize_path(value) -> str:
    path = _clean_text(value)
    if not path:
        return ""
    return os.path.normcase(os.path.abspath(path))


def normalize_monitor_rule(raw: dict, *, create_id: bool = False) -> dict | None:
    if not isinstance(raw, dict):
        return None

    executable_name = os.path.basename(_clean_text(raw.get("executable_name"))).casefold()
    executable_path = _normalize_path(raw.get("executable_path"))
    target_device = _clean_text(raw.get("target_device"))
    placement_mode = _clean_text(raw.get("placement_mode")).casefold() or "keep_size"
    if not executable_name or not target_device or placement_mode not in PLACEMENT_MODES:
        return None

    geometry = raw.get("saved_geometry")
    normalized_geometry = None
    if isinstance(geometry, dict):
        try:
            normalized_geometry = {
                "x_offset": int(geometry["x_offset"]),
                "y_offset": int(geometry["y_offset"]),
                "width": max(1, int(geometry["width"])),
                "height": max(1, int(geometry["height"])),
            }
        except (KeyError, TypeError, ValueError):
            normalized_geometry = None
    if placement_mode == "saved_geometry" and normalized_geometry is None:
        return None

    rule_id = _clean_text(raw.get("id"))
    if not rule_id and create_id:
        rule_id = str(uuid.uuid4())
    if not rule_id:
        return None

    match_exact_path = bool(raw.get("match_exact_path", bool(executable_path)))
    if match_exact_path and not executable_path:
        match_exact_path = False

    return {
        "id": rule_id,
        "name": _clean_text(raw.get("name")) or executable_name,
        "enabled": bool(raw.get("enabled", True)),
        "reapply_if_moved": bool(raw.get("reapply_if_moved", False)),
        "executable_name": executable_name,
        "executable_path": executable_path,
        "match_exact_path": match_exact_path,
        "title_contains": _clean_text(raw.get("title_contains")),
        "class_name": _clean_text(raw.get("class_name")),
        "target_device": target_device,
        "target_label": _clean_text(raw.get("target_label")) or target_device,
        "placement_mode": placement_mode,
        "saved_geometry": normalized_geometry,
    }


def normalize_monitor_rules(rules) -> list[dict]:
    if not isinstance(rules, list):
        return []
    normalized = []
    seen_ids = set()
    for raw in rules:
        rule = normalize_monitor_rule(raw)
        if rule is None or rule["id"] in seen_ids:
            continue
        seen_ids.add(rule["id"])
        normalized.append(rule)
    return normalized


def enumerate_monitors() -> list[dict]:
    monitors = []
    for index, monitor_tuple in enumerate(win32api.EnumDisplayMonitors(), start=1):
        handle = monitor_tuple[0]
        info = win32api.GetMonitorInfo(handle)
        work = tuple(info["Work"])
        rect = tuple(info["Monitor"])
        device = _clean_text(info.get("Device")) or str(handle)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        primary = bool(info.get("Flags", 0) & 1)
        label = f"Monitor {index} - {width} x {height}"
        if primary:
            label += " (Primary)"
        monitors.append(
            {
                "handle": handle,
                "device": device,
                "label": label,
                "rect": rect,
                "work": work,
                "primary": primary,
            }
        )
    return monitors


def _monitor_by_device(device: str, monitors=None) -> dict | None:
    wanted = _clean_text(device).casefold()
    for monitor in monitors if monitors is not None else enumerate_monitors():
        if _clean_text(monitor.get("device")).casefold() == wanted:
            return monitor
    return None


def _process_details(hwnd) -> tuple[str, str, int, float]:
    try:
        _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        name = _clean_text(process.name()).casefold()
        try:
            path = _normalize_path(process.exe())
        except (psutil.Error, OSError):
            path = ""
        try:
            started_at = float(process.create_time())
        except (psutil.Error, OSError, TypeError, ValueError):
            started_at = 0.0
        return name, path, int(pid), started_at
    except (psutil.Error, OSError, win32gui.error):
        return "", "", 0, 0.0


def _is_cloaked(hwnd) -> bool:
    try:
        cloaked = wintypes.DWORD()
        result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd,
            14,  # DWMWA_CLOAKED
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )
        return result == 0 and bool(cloaked.value)
    except Exception:
        return False


def window_details(hwnd, *, app_hwnd=None) -> dict | None:
    """Return rule-matching details for an eligible top-level window.

    ``app_hwnd`` remains accepted for compatibility with existing callers, but the
    Windows Resurface window is deliberately eligible so the app can manage its
    own monitor placement.
    """
    try:
        if not hwnd or not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return None
        if win32gui.GetParent(hwnd):
            return None
        if win32gui.GetWindow(hwnd, getattr(win32con, "GW_OWNER", 4)):
            return None
        ex_style = int(win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE))
        if ex_style & win32con.WS_EX_TOOLWINDOW:
            return None
        if _is_cloaked(hwnd):
            return None
        title = _clean_text(win32gui.GetWindowText(hwnd))
        if not title:
            return None
        class_name = _clean_text(win32gui.GetClassName(hwnd))
    except (win32gui.error, OSError):
        return None

    executable_name, executable_path, process_id, process_started_at = _process_details(hwnd)
    if not executable_name:
        return None
    if executable_name in SYSTEM_EXECUTABLES:
        return None
    return {
        "hwnd": int(hwnd),
        "title": title,
        "class_name": class_name,
        "executable_name": executable_name,
        "executable_path": executable_path,
        "process_id": process_id,
        "process_started_at": process_started_at,
    }


def enumerate_eligible_windows(*, app_hwnd=None) -> list[dict]:
    windows = []

    def callback(hwnd, _extra):
        details = window_details(hwnd, app_hwnd=app_hwnd)
        if details is not None:
            windows.append(details)

    try:
        win32gui.EnumWindows(callback, None)
    except win32gui.error:
        return []
    windows.sort(key=lambda item: (item["executable_name"], item["title"].casefold()))
    return windows


def rule_matches_window(rule: dict, details: dict) -> bool:
    if not rule.get("enabled", True):
        return False
    if _clean_text(details.get("executable_name")).casefold() != rule["executable_name"]:
        return False
    if rule.get("match_exact_path"):
        actual_path = _normalize_path(details.get("executable_path"))
        if not actual_path or actual_path != rule.get("executable_path", ""):
            return False
    title_filter = _clean_text(rule.get("title_contains")).casefold()
    if title_filter and title_filter not in _clean_text(details.get("title")).casefold():
        return False
    class_filter = _clean_text(rule.get("class_name")).casefold()
    if class_filter and class_filter != _clean_text(details.get("class_name")).casefold():
        return False
    return True


def first_matching_rule(rules: list[dict], details: dict) -> dict | None:
    return next((rule for rule in rules if rule_matches_window(rule, details)), None)


def _normal_window_rect(hwnd) -> tuple[int, int, int, int]:
    placement = win32gui.GetWindowPlacement(hwnd)
    show_command = placement[1]
    if show_command in (win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED):
        rect = placement[4]
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        return tuple(rect)
    return tuple(win32gui.GetWindowRect(hwnd))


def capture_window_geometry(hwnd) -> dict | None:
    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] in (win32con.SW_SHOWMINIMIZED, win32con.SW_SHOWMAXIMIZED):
            rect = tuple(placement[4])
        else:
            rect = tuple(win32gui.GetWindowRect(hwnd))
        monitor_handle = win32api.MonitorFromWindow(
            hwnd, getattr(win32con, "MONITOR_DEFAULTTONEAREST", 2)
        )
        work = tuple(win32api.GetMonitorInfo(monitor_handle)["Work"])
    except (win32gui.error, OSError):
        return None
    left, top, right, bottom = rect
    return {
        "x_offset": left - work[0],
        "y_offset": top - work[1],
        "width": max(1, right - left),
        "height": max(1, bottom - top),
    }


def _clamped_position(work, x, y, width, height) -> tuple[int, int]:
    left, top, right, bottom = work
    width = min(max(1, width), max(1, right - left))
    height = min(max(1, height), max(1, bottom - top))
    return min(max(x, left), right - width), min(max(y, top), bottom - height)


def window_monitor_device(hwnd) -> str:
    try:
        handle = win32api.MonitorFromWindow(
            hwnd, getattr(win32con, "MONITOR_DEFAULTTONEAREST", 2)
        )
        return _clean_text(win32api.GetMonitorInfo(handle).get("Device"))
    except (win32gui.error, OSError):
        return ""


def apply_monitor_rule(hwnd, rule: dict, *, monitors=None) -> bool:
    normalized = normalize_monitor_rule(rule)
    if normalized is None:
        return False
    try:
        available = enumerate_monitors() if monitors is None else monitors
        target = _monitor_by_device(normalized["target_device"], available)
        if target is None or not win32gui.IsWindow(hwnd):
            return False

        rect = _normal_window_rect(hwnd)
        left, top, right, bottom = rect
        width, height = max(1, right - left), max(1, bottom - top)
        target_work = tuple(target["work"])
        mode = normalized["placement_mode"]

        if mode == "saved_geometry":
            geometry = normalized["saved_geometry"]
            width = min(geometry["width"], target_work[2] - target_work[0])
            height = min(geometry["height"], target_work[3] - target_work[1])
            x = target_work[0] + geometry["x_offset"]
            y = target_work[1] + geometry["y_offset"]
        else:
            source_handle = win32api.MonitorFromWindow(
                hwnd, getattr(win32con, "MONITOR_DEFAULTTONEAREST", 2)
            )
            source_work = tuple(win32api.GetMonitorInfo(source_handle)["Work"])
            x = target_work[0] + (left - source_work[0])
            y = target_work[1] + (top - source_work[1])

        x, y = _clamped_position(target_work, x, y, width, height)
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOP,
            x,
            y,
            width,
            height,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
        )
        if mode == "maximize":
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        return True
    except (win32gui.error, OSError, ValueError, KeyError) as exc:
        print(f"[MONITOR_RULES] Failed to place window {hwnd}: {exc}")
        return False


def _left_mouse_pressed() -> bool:
    try:
        return bool(win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000)
    except Exception:
        return False


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
            if rule is None or not rule.get("reapply_if_moved") or not win32gui.IsWindow(hwnd):
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

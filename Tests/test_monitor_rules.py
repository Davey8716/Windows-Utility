import copy

import pytest

from resurface.features.monitor_rules import monitor_rules


def make_rule(**overrides):
    rule = {
        "id": "rule-1",
        "name": "Discord",
        "enabled": True,
        "reapply_if_moved": False,
        "executable_name": "Discord.exe",
        "executable_path": r"C:\Apps\Discord.exe",
        "match_exact_path": True,
        "title_contains": "",
        "class_name": "",
        "target_device": r"\\.\DISPLAY2",
        "target_label": "Monitor 2",
        "placement_mode": "keep_size",
        "saved_geometry": None,
    }
    rule.update(overrides)
    return rule


def test_rule_normalization_rejects_invalid_records_and_normalizes_matching():
    assert monitor_rules.normalize_monitor_rule({}) is None
    assert monitor_rules.normalize_monitor_rules("not a list") == []

    normalized = monitor_rules.normalize_monitor_rule(make_rule())
    assert normalized["executable_name"] == "discord.exe"
    assert normalized["executable_path"] == monitor_rules._normalize_path(
        r"C:\Apps\Discord.exe"
    )
    assert normalized["match_exact_path"] is True

    invalid_geometry = make_rule(
        placement_mode="saved_geometry",
        saved_geometry={"width": 800},
    )
    assert monitor_rules.normalize_monitor_rule(invalid_geometry) is None


def test_duplicate_rule_ids_are_ignored_but_duplicate_executables_are_allowed():
    first = make_rule()
    second = make_rule(id="rule-2", title_contains="Work")
    duplicate_id = make_rule(name="Duplicate")
    rules = monitor_rules.normalize_monitor_rules([first, second, duplicate_id])
    assert [rule["id"] for rule in rules] == ["rule-1", "rule-2"]


def test_ordered_matching_honors_path_title_and_class_filters():
    details = {
        "executable_name": "discord.exe",
        "executable_path": r"C:\Apps\Discord.exe",
        "title": "Discord - Friends",
        "class_name": "Chrome_WidgetWin_1",
    }
    wrong_title = monitor_rules.normalize_monitor_rule(
        make_rule(id="first", title_contains="Calls")
    )
    matching = monitor_rules.normalize_monitor_rule(
        make_rule(id="second", title_contains="friends", class_name="chrome_widgetwin_1")
    )
    assert monitor_rules.first_matching_rule([wrong_title, matching], details)["id"] == "second"

    wrong_path = copy.deepcopy(details)
    wrong_path["executable_path"] = r"D:\Portable\Discord.exe"
    assert not monitor_rules.rule_matches_window(matching, wrong_path)
    name_only = copy.deepcopy(matching)
    name_only["match_exact_path"] = False
    assert monitor_rules.rule_matches_window(name_only, wrong_path)


def test_enumerate_monitors_keeps_device_identity_and_negative_coordinates(monkeypatch):
    monkeypatch.setattr(
        monitor_rules.win32api,
        "EnumDisplayMonitors",
        lambda: [(10, None, None), (20, None, None)],
    )
    infos = {
        10: {
            "Device": r"\\.\DISPLAY1",
            "Monitor": (-1920, 0, 0, 1080),
            "Work": (-1920, 0, 0, 1040),
            "Flags": 0,
        },
        20: {
            "Device": r"\\.\DISPLAY2",
            "Monitor": (0, 0, 2560, 1440),
            "Work": (0, 0, 2560, 1400),
            "Flags": 1,
        },
    }
    monkeypatch.setattr(monitor_rules.win32api, "GetMonitorInfo", infos.get)
    monitors = monitor_rules.enumerate_monitors()
    assert monitors[0]["device"] == r"\\.\DISPLAY1"
    assert monitors[0]["work"][0] == -1920
    assert monitors[1]["primary"] is True


def _patch_window_placement(monkeypatch, *, rect=(100, 100, 900, 700), show_cmd=1):
    calls = []
    monkeypatch.setattr(monitor_rules.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(
        monitor_rules.win32gui,
        "GetWindowPlacement",
        lambda _hwnd: (0, show_cmd, (0, 0), (0, 0), rect),
    )
    monkeypatch.setattr(monitor_rules.win32gui, "GetWindowRect", lambda _hwnd: rect)
    monkeypatch.setattr(
        monitor_rules.win32gui,
        "SetWindowPos",
        lambda *args: calls.append(("position", args)),
    )
    monkeypatch.setattr(
        monitor_rules.win32gui,
        "ShowWindow",
        lambda *args: calls.append(("show", args)),
    )
    monkeypatch.setattr(monitor_rules.win32api, "MonitorFromWindow", lambda *_args: 10)
    monkeypatch.setattr(
        monitor_rules.win32api,
        "GetMonitorInfo",
        lambda _handle: {"Device": r"\\.\DISPLAY1", "Work": (0, 0, 1920, 1040)},
    )
    return calls


def test_keep_size_placement_preserves_relative_position(monkeypatch):
    calls = _patch_window_placement(monkeypatch)
    target = {
        "device": r"\\.\DISPLAY2",
        "work": (1920, 0, 3840, 1040),
    }
    assert monitor_rules.apply_monitor_rule(100, make_rule(), monitors=[target])
    position = next(call[1] for call in calls if call[0] == "position")
    assert position[2:6] == (2020, 100, 800, 600)


def test_saved_geometry_is_clamped_and_maximize_is_applied_after_move(monkeypatch):
    calls = _patch_window_placement(monkeypatch)
    target = {
        "device": r"\\.\DISPLAY2",
        "work": (-1280, 0, 0, 984),
    }
    saved = make_rule(
        placement_mode="saved_geometry",
        saved_geometry={"x_offset": 1200, "y_offset": 900, "width": 900, "height": 700},
    )
    assert monitor_rules.apply_monitor_rule(100, saved, monitors=[target])
    position = next(call[1] for call in calls if call[0] == "position")
    assert position[2:6] == (-900, 284, 900, 700)

    calls.clear()
    assert monitor_rules.apply_monitor_rule(
        100,
        make_rule(placement_mode="maximize"),
        monitors=[target],
    )
    assert calls[-1] == ("show", (100, monitor_rules.win32con.SW_MAXIMIZE))


def test_missing_monitor_leaves_window_untouched(monkeypatch):
    calls = _patch_window_placement(monkeypatch)
    assert not monitor_rules.apply_monitor_rule(100, make_rule(), monitors=[])
    assert calls == []


def test_capture_uses_normal_rect_without_restoring_maximized_window(monkeypatch):
    calls = _patch_window_placement(
        monkeypatch,
        rect=(50, 60, 850, 660),
        show_cmd=monitor_rules.win32con.SW_SHOWMAXIMIZED,
    )
    geometry = monitor_rules.capture_window_geometry(100)
    assert geometry == {"x_offset": 50, "y_offset": 60, "width": 800, "height": 600}
    assert not any(call[0] == "show" for call in calls)


def test_watcher_baselines_existing_windows_then_places_a_new_match(monkeypatch):
    rule = monitor_rules.normalize_monitor_rule(make_rule(match_exact_path=False))
    watcher = monitor_rules.MonitorRuleWatcher()
    watcher._rules = [rule]
    watcher._app_hwnd = 999
    handles = {1}
    windows = [
        {
            "hwnd": 1,
            "title": "Existing",
            "class_name": "Main",
            "executable_name": "discord.exe",
            "executable_path": "",
            "process_id": 10,
            "process_started_at": 100.0,
        }
    ]
    placed = []
    monkeypatch.setattr(
        monitor_rules,
        "enumerate_eligible_windows",
        lambda **_kwargs: [
            copy.deepcopy(window) for window in windows if window["hwnd"] in handles
        ],
    )
    monkeypatch.setattr(
        monitor_rules,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher._scan_once()
    assert placed == []
    handles.add(2)
    windows.append({**windows[0], "hwnd": 2, "title": "New"})
    watcher._scan_once()
    assert placed == [2]


def test_watcher_reapplies_when_hidden_window_becomes_visible_again(monkeypatch):
    rule = monitor_rules.normalize_monitor_rule(make_rule(match_exact_path=False))
    watcher = monitor_rules.MonitorRuleWatcher()
    watcher._rules = [rule]
    visible = True
    details = {
        "hwnd": 1,
        "title": "Discord",
        "class_name": "Main",
        "executable_name": "discord.exe",
        "executable_path": "",
        "process_id": 10,
        "process_started_at": 100.0,
    }
    placed = []
    monkeypatch.setattr(
        monitor_rules,
        "enumerate_eligible_windows",
        lambda **_kwargs: [copy.deepcopy(details)] if visible else [],
    )
    monkeypatch.setattr(
        monitor_rules,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher._scan_once()
    assert placed == []
    visible = False
    watcher._managed[1] = rule["id"]
    watcher._off_target_since[1] = 1.0
    watcher._scan_once()
    assert watcher._seen == {}
    assert watcher._managed == {}
    assert watcher._off_target_since == {}

    visible = True
    watcher._scan_once()
    assert placed == [1]


def test_watcher_detects_fast_process_relaunch_reusing_same_hwnd(monkeypatch):
    rule = monitor_rules.normalize_monitor_rule(make_rule(match_exact_path=False))
    watcher = monitor_rules.MonitorRuleWatcher()
    watcher._rules = [rule]
    details = {
        "hwnd": 1,
        "title": "Discord",
        "class_name": "Main",
        "executable_name": "discord.exe",
        "executable_path": "",
        "process_id": 10,
        "process_started_at": 100.0,
    }
    placed = []
    monkeypatch.setattr(
        monitor_rules,
        "enumerate_eligible_windows",
        lambda **_kwargs: [copy.deepcopy(details)],
    )
    monkeypatch.setattr(
        monitor_rules,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher._scan_once()
    details["process_id"] = 20
    details["process_started_at"] = 200.0
    watcher._scan_once()
    assert placed == [1]


def test_watcher_does_not_retrigger_same_visible_window(monkeypatch):
    rule = monitor_rules.normalize_monitor_rule(make_rule(match_exact_path=False))
    watcher = monitor_rules.MonitorRuleWatcher()
    watcher._rules = [rule]
    details = {
        "hwnd": 1,
        "title": "Discord",
        "class_name": "Main",
        "executable_name": "discord.exe",
        "executable_path": "",
        "process_id": 10,
        "process_started_at": 100.0,
    }
    placed = []
    monkeypatch.setattr(
        monitor_rules,
        "enumerate_eligible_windows",
        lambda **_kwargs: [copy.deepcopy(details)],
    )
    monkeypatch.setattr(
        monitor_rules,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher._scan_once()
    watcher._scan_once()
    watcher._scan_once()
    assert placed == []


def test_watcher_starts_only_for_enabled_rules_and_stops_cleanly():
    watcher = monitor_rules.MonitorRuleWatcher()
    watcher.update_rules([make_rule(enabled=False)])
    assert not watcher.is_running
    watcher.update_rules([make_rule(enabled=True)])
    assert watcher.is_running
    watcher.stop()
    assert not watcher.is_running


def test_rule_changes_cancel_pending_matches_and_request_a_fresh_baseline():
    watcher = monitor_rules.MonitorRuleWatcher()
    original = monitor_rules.normalize_monitor_rule(make_rule(match_exact_path=False))
    watcher._rules = [original]
    watcher._thread = type("Thread", (), {"is_alive": lambda self: True})()
    watcher._pending = {123: 999.0}
    changed = make_rule(match_exact_path=False, title_contains="Main")

    watcher.update_rules([changed])

    assert watcher._pending == {}
    assert watcher._baseline_pending is True


def _matching_window_details(hwnd=1):
    return {
        "hwnd": hwnd,
        "title": "Discord",
        "class_name": "Main",
        "executable_name": "discord.exe",
        "executable_path": "",
        "process_id": 10,
        "process_started_at": 100.0,
    }


def _running_watcher_with_rule(rule):
    watcher = monitor_rules.MonitorRuleWatcher()
    normalized = monitor_rules.normalize_monitor_rule(rule)
    watcher._configured_rules = [normalized]
    watcher._rules = [normalized] if normalized["enabled"] else []
    watcher._thread = type("Thread", (), {"is_alive": lambda self: True})()
    return watcher


def test_enabling_reapply_enrolls_an_existing_correctly_placed_window(monkeypatch):
    watcher = _running_watcher_with_rule(
        make_rule(match_exact_path=False, reapply_if_moved=False)
    )
    enabled_rule = make_rule(match_exact_path=False, reapply_if_moved=True)
    details = _matching_window_details()
    placed = []
    monkeypatch.setattr(
        monitor_rules,
        "enumerate_eligible_windows",
        lambda **_kwargs: [copy.deepcopy(details)],
    )
    monkeypatch.setattr(monitor_rules.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(
        monitor_rules,
        "window_monitor_device",
        lambda _hwnd: enabled_rule["target_device"],
    )
    monkeypatch.setattr(
        monitor_rules,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher.update_rules([enabled_rule])
    watcher._scan_once()

    assert watcher._managed == {1: "rule-1"}
    assert watcher._enroll_rule_ids == set()
    assert placed == []


def test_enabling_reapply_moves_existing_off_target_window_after_settle(monkeypatch):
    watcher = _running_watcher_with_rule(
        make_rule(match_exact_path=False, reapply_if_moved=False)
    )
    enabled_rule = make_rule(match_exact_path=False, reapply_if_moved=True)
    details = _matching_window_details()
    placed = []
    current_time = [10.0]
    monkeypatch.setattr(
        monitor_rules,
        "enumerate_eligible_windows",
        lambda **_kwargs: [copy.deepcopy(details)],
    )
    monkeypatch.setattr(monitor_rules.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(
        monitor_rules,
        "window_monitor_device",
        lambda _hwnd: r"\\.\DISPLAY1",
    )
    monkeypatch.setattr(monitor_rules, "_left_mouse_pressed", lambda: False)
    monkeypatch.setattr(monitor_rules.time, "monotonic", lambda: current_time[0])
    monkeypatch.setattr(
        monitor_rules,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher.update_rules([enabled_rule])
    watcher._scan_once()
    assert placed == []
    current_time[0] += monitor_rules.REAPPLY_SETTLE_SECONDS + 0.1
    watcher._scan_once()
    assert placed == [1]


def test_reenabling_rule_immediately_moves_existing_off_target_window(monkeypatch):
    disabled_rule = make_rule(
        enabled=False,
        match_exact_path=False,
        reapply_if_moved=True,
    )
    enabled_rule = {**disabled_rule, "enabled": True}
    watcher = monitor_rules.MonitorRuleWatcher()
    details = _matching_window_details()
    placed = []
    monkeypatch.setattr(watcher, "start", lambda: None)
    monkeypatch.setattr(
        monitor_rules,
        "enumerate_eligible_windows",
        lambda **_kwargs: [copy.deepcopy(details)],
    )
    monkeypatch.setattr(monitor_rules.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(
        monitor_rules,
        "window_monitor_device",
        lambda _hwnd: r"\\.\DISPLAY1",
    )
    monkeypatch.setattr(
        monitor_rules,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher.update_rules([disabled_rule])
    watcher.update_rules([enabled_rule])
    watcher._scan_once()

    assert placed == [1]
    assert watcher._managed == {1: "rule-1"}
    assert watcher._enroll_rule_ids == set()
    assert watcher._immediate_rule_ids == set()


def test_reenabling_rule_enrolls_existing_window_already_on_target(monkeypatch):
    disabled_rule = make_rule(
        enabled=False,
        match_exact_path=False,
        reapply_if_moved=True,
    )
    enabled_rule = {**disabled_rule, "enabled": True}
    watcher = monitor_rules.MonitorRuleWatcher()
    placed = []
    monkeypatch.setattr(watcher, "start", lambda: None)
    monkeypatch.setattr(
        monitor_rules,
        "enumerate_eligible_windows",
        lambda **_kwargs: [_matching_window_details()],
    )
    monkeypatch.setattr(monitor_rules.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(
        monitor_rules,
        "window_monitor_device",
        lambda _hwnd: enabled_rule["target_device"],
    )
    monkeypatch.setattr(
        monitor_rules,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher.update_rules([disabled_rule])
    watcher.update_rules([enabled_rule])
    watcher._scan_once()

    assert placed == []
    assert watcher._managed == {1: "rule-1"}


def test_reenabling_rule_wakes_running_watcher_and_applies_immediately(monkeypatch):
    disabled_rule = make_rule(
        enabled=False,
        match_exact_path=False,
        reapply_if_moved=True,
    )
    other_rule = make_rule(
        id="other",
        executable_name="other.exe",
        enabled=True,
        match_exact_path=False,
    )
    enabled_rule = {**disabled_rule, "enabled": True}
    watcher = monitor_rules.MonitorRuleWatcher()
    watcher._configured_rules = [
        monitor_rules.normalize_monitor_rule(disabled_rule),
        monitor_rules.normalize_monitor_rule(other_rule),
    ]
    watcher._rules = [monitor_rules.normalize_monitor_rule(other_rule)]
    watcher._thread = type("Thread", (), {"is_alive": lambda self: True})()
    wake_calls = []
    placed = []
    monkeypatch.setattr(watcher._wake_event, "set", lambda: wake_calls.append(True))
    monkeypatch.setattr(
        monitor_rules,
        "enumerate_eligible_windows",
        lambda **_kwargs: [_matching_window_details()],
    )
    monkeypatch.setattr(monitor_rules.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(
        monitor_rules,
        "window_monitor_device",
        lambda _hwnd: r"\\.\DISPLAY1",
    )
    monkeypatch.setattr(
        monitor_rules,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher.update_rules([enabled_rule, other_rule])
    watcher._scan_once()

    assert wake_calls == [True]
    assert placed == [1]


def test_reenabling_rule_without_reapply_does_not_enroll_existing_window(monkeypatch):
    disabled_rule = make_rule(
        enabled=False,
        match_exact_path=False,
        reapply_if_moved=False,
    )
    watcher = monitor_rules.MonitorRuleWatcher()
    monkeypatch.setattr(watcher, "start", lambda: None)

    watcher.update_rules([disabled_rule])
    watcher.update_rules([{**disabled_rule, "enabled": True}])

    assert watcher._enroll_rule_ids == set()
    assert watcher._immediate_rule_ids == set()


def test_rapid_rule_transitions_clear_stale_immediate_requests(monkeypatch):
    disabled_rule = make_rule(enabled=False, reapply_if_moved=True)
    enabled_rule = {**disabled_rule, "enabled": True}
    watcher = monitor_rules.MonitorRuleWatcher()
    monkeypatch.setattr(watcher, "start", lambda: None)

    watcher.update_rules([disabled_rule])
    watcher.update_rules([enabled_rule])
    assert watcher._immediate_rule_ids == {"rule-1"}

    watcher.update_rules([disabled_rule])
    assert watcher._enroll_rule_ids == set()
    assert watcher._immediate_rule_ids == set()

    watcher.update_rules([enabled_rule])
    assert watcher._immediate_rule_ids == {"rule-1"}

    watcher.update_rules([])
    watcher.update_rules([enabled_rule])
    assert watcher._enroll_rule_ids == set()
    assert watcher._immediate_rule_ids == set()


def test_disabling_reapply_immediately_clears_management_and_enrollment():
    watcher = _running_watcher_with_rule(
        make_rule(match_exact_path=False, reapply_if_moved=True)
    )
    watcher._managed[1] = "rule-1"
    watcher._off_target_since[1] = 10.0
    watcher._enroll_rule_ids.add("rule-1")

    watcher.update_rules(
        [make_rule(match_exact_path=False, reapply_if_moved=False)]
    )

    assert watcher._managed == {}
    assert watcher._off_target_since == {}
    assert watcher._enroll_rule_ids == set()


def test_reapply_enrollment_respects_ordered_first_match(monkeypatch):
    first = monitor_rules.normalize_monitor_rule(
        make_rule(id="first", match_exact_path=False, reapply_if_moved=True)
    )
    second = monitor_rules.normalize_monitor_rule(
        make_rule(id="second", match_exact_path=False, reapply_if_moved=True)
    )
    watcher = monitor_rules.MonitorRuleWatcher()
    watcher._rules = [first, second]
    watcher._enroll_rule_ids = {"second"}

    watcher._enroll_existing_windows(
        {1: _matching_window_details()},
        {"second"},
    )

    assert watcher._managed == {}
    assert watcher._enroll_rule_ids == set()


def test_initial_reapply_rule_does_not_queue_existing_window_enrollment(monkeypatch):
    watcher = monitor_rules.MonitorRuleWatcher()
    monkeypatch.setattr(watcher, "start", lambda: None)

    watcher.update_rules(
        [make_rule(match_exact_path=False, reapply_if_moved=True)]
    )

    assert watcher._enroll_rule_ids == set()

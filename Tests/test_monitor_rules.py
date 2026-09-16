import copy

import pytest

from resurface.features.monitor_rules import rule_schema, watcher as watcher_module, win32_windows


@pytest.fixture(autouse=True)
def isolated_window_state(monkeypatch):
    # Every watcher test uses simulated windows, never the user's desktop.
    monkeypatch.setattr(watcher_module, "enumerate_eligible_windows", lambda **kwargs: [])
    monkeypatch.setattr(watcher_module, "apply_monitor_rule", lambda *args, **kwargs: False)
    monkeypatch.setattr(watcher_module, "_left_mouse_pressed", lambda: False)
    monkeypatch.setattr(
        watcher_module, "window_details",
        lambda hwnd, **kwargs: next((copy.deepcopy(d) for d in
            watcher_module.enumerate_eligible_windows(**kwargs)
            if d["hwnd"] == hwnd), None),
    )
    monkeypatch.setattr(watcher_module, "window_monitor_device", lambda hwnd: "")


def make_rule(**overrides):
    rule = {
        "id": "rule-1",
        "name": "Discord",
        "enabled": True,
        "reapply_if_moved": False,
        "executable_name": "Discord.exe",
        "executable_path": r"C:\Apps\Discord.exe",
        "match_exact_path": True,
        "target_device": r"\\.\DISPLAY2",
        "target_label": "Monitor 2",
        "placement_mode": "keep_size",
        "saved_geometry": None,
    }
    rule.update(overrides)
    return rule


def test_rule_normalization_rejects_invalid_records_and_normalizes_matching():
    assert rule_schema.normalize_monitor_rule({}) is None
    assert rule_schema.normalize_monitor_rules("not a list") == []

    normalized = rule_schema.normalize_monitor_rule(make_rule())
    assert normalized["executable_name"] == "discord.exe"
    assert normalized["executable_path"] == rule_schema._normalize_path(
        r"C:\Apps\Discord.exe"
    )
    assert normalized["match_exact_path"] is True

    invalid_geometry = make_rule(
        placement_mode="saved_geometry",
        saved_geometry={"width": 800},
    )
    assert rule_schema.normalize_monitor_rule(invalid_geometry) is None


def test_duplicate_rule_ids_are_ignored_but_duplicate_executables_are_allowed():
    first = make_rule()
    second = make_rule(id="rule-2", name="Discord Work")
    duplicate_id = make_rule(name="Duplicate")
    rules = rule_schema.normalize_monitor_rules([first, second, duplicate_id])
    assert [rule["id"] for rule in rules] == ["rule-1", "rule-2"]


def test_windows_resurface_group_is_normalized_and_wins_over_executable_rules():
    grouped = rule_schema.normalize_monitor_rule(
        {
            "id": "resurface",
            "app_group": "windows_resurface",
            "target_device": r"\\.\DISPLAY2",
            "target_label": "Monitor 2",
            "placement_mode": "maximize",
            "saved_geometry": {"width": 1},
        }
    )
    assert grouped["name"] == "Windows Resurface"
    assert grouped["placement_mode"] == "keep_size"
    assert grouped["saved_geometry"] is None

    generic = make_rule(id="generic", match_exact_path=False)
    details = {
        "executable_name": "windows resurface.exe",
        "executable_path": r"C:\Apps\Windows Resurface.exe",
        "app_group": "windows_resurface",
    }
    assert rule_schema.first_matching_rule([generic, grouped], details)["id"] == "resurface"
    assert rule_schema.first_matching_rule([generic], details) is None
    assert rule_schema.normalize_monitor_rule(
        make_rule(executable_name="Windows Resurface.exe")
    ) is None


def test_windows_resurface_group_recognizes_packaged_folder_creator(monkeypatch, tmp_path):
    from resurface.features.monitor_rules import application_groups

    target = tmp_path / "Code Folder Creator" / "Folder Creator.exe"

    class PackagedLauncher:
        def resolve_project_root(self):
            return tmp_path

        def resolve_launch_target(self, _project_dir):
            return target

        @staticmethod
        def process_references_target(process_id, candidate):
            return process_id == 42 and candidate == target

    monkeypatch.setattr(application_groups, "FolderCreatorLauncher", PackagedLauncher)
    assert application_groups.window_application_group({"hwnd": 2, "process_id": 42}) == (
        "windows_resurface"
    )


def test_prune_missing_exact_path_rules_keeps_name_rules_and_existing_files(monkeypatch):
    existing = make_rule(id="existing")
    missing = make_rule(id="missing", executable_path=r"C:\\Removed\\Discord.exe")
    name_only = make_rule(
        id="name-only",
        executable_path=r"C:\\Removed\\Discord.exe",
        match_exact_path=False,
    )
    monkeypatch.setattr(
        rule_schema.os.path,
        "isfile",
        lambda path: path == rule_schema._normalize_path(existing["executable_path"]),
    )

    retained = rule_schema.prune_missing_exact_path_rules(
        [existing, missing, name_only]
    )

    assert [rule["id"] for rule in retained] == ["existing", "name-only"]


def test_matching_ignores_retired_title_and_class_filters():
    details = {
        "executable_name": "discord.exe",
        "executable_path": r"C:\Apps\Discord.exe",
        "title": "Discord - Friends",
        "class_name": "Chrome_WidgetWin_1",
    }
    legacy_rule = rule_schema.normalize_monitor_rule(
        make_rule(id="second", title_contains="friends", class_name="chrome_widgetwin_1")
    )
    assert "title_contains" not in legacy_rule
    assert "class_name" not in legacy_rule
    assert rule_schema.first_matching_rule([legacy_rule], details)["id"] == "second"

    wrong_path = copy.deepcopy(details)
    wrong_path["executable_path"] = r"D:\Portable\Discord.exe"
    assert not rule_schema.rule_matches_window(legacy_rule, wrong_path)
    name_only = copy.deepcopy(legacy_rule)
    name_only["match_exact_path"] = False
    assert rule_schema.rule_matches_window(name_only, wrong_path)


def test_enumerate_monitors_keeps_device_identity_and_negative_coordinates(monkeypatch):
    monkeypatch.setattr(
        win32_windows.win32api,
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
    monkeypatch.setattr(win32_windows.win32api, "GetMonitorInfo", infos.get)
    monitors = win32_windows.enumerate_monitors()
    assert monitors[0]["device"] == r"\\.\DISPLAY1"
    assert monitors[0]["work"][0] == -1920
    assert monitors[1]["primary"] is True


def test_window_details_includes_windows_resurface_main_window(monkeypatch):
    app_hwnd = 999
    monkeypatch.setattr(win32_windows.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(
        win32_windows.win32gui, "IsWindowVisible", lambda _hwnd: True
    )
    monkeypatch.setattr(win32_windows.win32gui, "GetParent", lambda _hwnd: 0)
    monkeypatch.setattr(
        win32_windows.win32gui, "GetWindow", lambda _hwnd, _command: 0
    )
    monkeypatch.setattr(
        win32_windows.win32gui, "GetWindowLong", lambda _hwnd, _index: 0
    )
    monkeypatch.setattr(
        win32_windows.win32gui,
        "GetWindowText",
        lambda _hwnd: "Windows Resurface",
    )
    monkeypatch.setattr(
        win32_windows.win32gui, "GetClassName", lambda _hwnd: "QtWindowClass"
    )
    monkeypatch.setattr(win32_windows, "_is_cloaked", lambda _hwnd: False)
    monkeypatch.setattr(
        win32_windows,
        "_process_details",
        lambda _hwnd: (
            "windows resurface.exe",
            r"c:\apps\windows resurface.exe",
            123,
            456.0,
        ),
    )

    details = win32_windows.window_details(app_hwnd, app_hwnd=app_hwnd)

    assert details is not None
    assert details["hwnd"] == app_hwnd
    assert details["title"] == "Windows Resurface"
    assert details["executable_name"] == "windows resurface.exe"


def _patch_window_placement(monkeypatch, *, rect=(100, 100, 900, 700), show_cmd=1):
    calls = []
    monkeypatch.setattr(win32_windows.win32gui, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(
        win32_windows.win32gui,
        "GetWindowPlacement",
        lambda _hwnd: (0, show_cmd, (0, 0), (0, 0), rect),
    )
    monkeypatch.setattr(win32_windows.win32gui, "GetWindowRect", lambda _hwnd: rect)
    monkeypatch.setattr(
        win32_windows.win32gui,
        "SetWindowPos",
        lambda *args: calls.append(("position", args)),
    )
    monkeypatch.setattr(
        win32_windows.win32gui,
        "SetWindowPlacement",
        lambda *args: calls.append(("placement", args)),
    )
    monkeypatch.setattr(
        win32_windows.win32gui,
        "ShowWindow",
        lambda *args: calls.append(("show", args)),
    )
    monkeypatch.setattr(win32_windows.win32api, "MonitorFromWindow", lambda *_args: 10)
    monkeypatch.setattr(
        win32_windows.win32api,
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
    assert win32_windows.apply_monitor_rule(100, make_rule(), monitors=[target])
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
    assert win32_windows.apply_monitor_rule(100, saved, monitors=[target])
    position = next(call[1] for call in calls if call[0] == "position")
    assert position[2:6] == (-900, 284, 900, 700)

    calls.clear()
    assert win32_windows.apply_monitor_rule(
        100,
        make_rule(placement_mode="maximize"),
        monitors=[target],
    )
    assert [call[0] for call in calls] == ["position", "show"]
    assert calls[-1] == ("show", (100, win32_windows.win32con.SW_MAXIMIZE))


def test_already_maximized_rule_falls_back_when_single_placement_misses_target(monkeypatch):
    calls = _patch_window_placement(
        monkeypatch,
        show_cmd=win32_windows.win32con.SW_SHOWMAXIMIZED,
    )
    target = {
        "device": r"\\.\DISPLAY2",
        "work": (-1280, 0, 0, 984),
    }

    assert win32_windows.apply_monitor_rule(
        100,
        make_rule(placement_mode="maximize"),
        monitors=[target],
    )

    assert [call[0] for call in calls] == ["placement", "show", "position", "show"]
    assert calls[1] == ("show", (100, win32_windows.win32con.SW_RESTORE))
    assert calls[2][1][2:6] == (-1180, 100, 800, 600)
    assert calls[3] == ("show", (100, win32_windows.win32con.SW_MAXIMIZE))


def test_minimized_window_is_restored_moved_and_maximized(monkeypatch):
    calls = _patch_window_placement(
        monkeypatch,
        show_cmd=win32_windows.win32con.SW_SHOWMINIMIZED,
    )
    target = {
        "device": r"\\.\DISPLAY2",
        "work": (1920, 0, 3840, 1040),
    }

    assert win32_windows.apply_monitor_rule(
        100,
        make_rule(placement_mode="maximize"),
        monitors=[target],
    )

    assert [call[0] for call in calls] == ["placement", "show", "position", "show"]
    assert calls[1] == ("show", (100, win32_windows.win32con.SW_RESTORE))
    assert calls[-1] == ("show", (100, win32_windows.win32con.SW_MAXIMIZE))


@pytest.mark.parametrize("show_cmd", [2, 3])
def test_maximize_rule_reaches_target_without_restore_animation(monkeypatch, show_cmd):
    calls = _patch_window_placement(monkeypatch, show_cmd=show_cmd)
    target = {"device": r"\\.\DISPLAY2", "work": (-1280, 0, 0, 984)}
    monkeypatch.setattr(
        win32_windows, "window_monitor_device",
        lambda _hwnd: target["device"] if calls else r"\\.\DISPLAY1",
    )

    assert win32_windows.apply_monitor_rule(
        100, make_rule(placement_mode="maximize"), monitors=[target]
    )

    assert calls == [("placement", (100, (
        0, win32_windows.win32con.SW_SHOWMAXIMIZED,
        (0, 0), (-1280, 0), (-1180, 100, -380, 700),
    )))]


def test_maximized_window_already_on_target_is_not_maximized_again(monkeypatch):
    calls = _patch_window_placement(
        monkeypatch, show_cmd=win32_windows.win32con.SW_SHOWMAXIMIZED
    )
    target = {"device": r"\\.\DISPLAY2", "work": (0, 0, 1920, 1040)}
    monkeypatch.setattr(
        win32_windows, "window_monitor_device", lambda _hwnd: target["device"]
    )

    assert win32_windows.apply_monitor_rule(
        100, make_rule(placement_mode="maximize"), monitors=[target]
    )
    assert calls == []


def test_maximize_placement_error_preserves_existing_move_fallback(monkeypatch):
    calls = _patch_window_placement(
        monkeypatch, show_cmd=win32_windows.win32con.SW_SHOWMAXIMIZED
    )
    target = {"device": r"\\.\DISPLAY2", "work": (-1280, 0, 0, 984)}

    def fail_placement(*_args):
        raise OSError("Window rejected placement")

    monkeypatch.setattr(win32_windows.win32gui, "SetWindowPlacement", fail_placement)

    assert win32_windows.apply_monitor_rule(
        100, make_rule(placement_mode="maximize"), monitors=[target]
    )
    assert [call[0] for call in calls] == ["show", "position", "show"]
    assert calls[0] == ("show", (100, win32_windows.win32con.SW_RESTORE))
    assert calls[1][1][2:6] == (-1180, 100, 800, 600)
    assert calls[2] == ("show", (100, win32_windows.win32con.SW_MAXIMIZE))


def test_missing_monitor_leaves_window_untouched(monkeypatch):
    calls = _patch_window_placement(monkeypatch)
    assert not win32_windows.apply_monitor_rule(100, make_rule(), monitors=[])
    assert calls == []


def test_capture_uses_normal_rect_without_restoring_maximized_window(monkeypatch):
    calls = _patch_window_placement(
        monkeypatch,
        rect=(50, 60, 850, 660),
        show_cmd=win32_windows.win32con.SW_SHOWMAXIMIZED,
    )
    geometry = win32_windows.capture_window_geometry(100)
    assert geometry == {"x_offset": 50, "y_offset": 60, "width": 800, "height": 600}
    assert not any(call[0] == "show" for call in calls)


def test_watcher_baselines_existing_windows_then_places_a_new_match(monkeypatch):
    rule = rule_schema.normalize_monitor_rule(make_rule(match_exact_path=False))
    watcher = watcher_module.MonitorRuleWatcher()
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
        watcher_module,
        "enumerate_eligible_windows",
        lambda **_kwargs: [
            copy.deepcopy(window) for window in windows if window["hwnd"] in handles
        ],
    )
    monkeypatch.setattr(
        watcher_module,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher._scan_once()
    assert placed == []
    handles.add(2)
    windows.append({**windows[0], "hwnd": 2, "title": "New"})
    watcher._scan_once()
    assert placed == [2]


def test_startup_initialization_places_existing_matches_once(monkeypatch):
    rule = make_rule(match_exact_path=False, reapply_if_moved=False)
    watcher = watcher_module.MonitorRuleWatcher()
    placed = []
    device = [r"\\.\DISPLAY1"]
    monkeypatch.setattr(watcher, "start", lambda: None)
    monkeypatch.setattr(
        watcher_module,
        "enumerate_eligible_windows",
        lambda **_kwargs: [_matching_window_details()],
    )
    monkeypatch.setattr(
        watcher_module,
        "window_monitor_device",
        lambda _hwnd: device[0],
    )
    monkeypatch.setattr(
        watcher_module,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or device.__setitem__(0, _rule["target_device"]) or True,
    )

    watcher.update_rules([rule], app_hwnd=999, apply_existing=True)
    watcher._scan_once()
    watcher._scan_once()

    assert placed == [1]
    assert watcher._managed == {}


def test_startup_initialization_skips_match_already_on_target(monkeypatch):
    rule = make_rule(match_exact_path=False, reapply_if_moved=False)
    watcher = watcher_module.MonitorRuleWatcher()
    placed = []
    monkeypatch.setattr(watcher, "start", lambda: None)
    monkeypatch.setattr(
        watcher_module,
        "enumerate_eligible_windows",
        lambda **_kwargs: [_matching_window_details()],
    )
    monkeypatch.setattr(
        watcher_module,
        "window_monitor_device",
        lambda _hwnd: rule["target_device"],
    )
    monkeypatch.setattr(
        watcher_module,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher.update_rules([rule], app_hwnd=999, apply_existing=True)
    watcher._scan_once()

    assert placed == []


def test_startup_initialization_manages_successful_reapply_matches(monkeypatch):
    rule = make_rule(match_exact_path=False, reapply_if_moved=True)
    watcher = watcher_module.MonitorRuleWatcher()
    monkeypatch.setattr(watcher, "start", lambda: None)
    monkeypatch.setattr(
        watcher_module,
        "enumerate_eligible_windows",
        lambda **_kwargs: [_matching_window_details()],
    )
    monkeypatch.setattr(
        watcher_module,
        "window_monitor_device",
        lambda _hwnd: rule["target_device"],
    )
    monkeypatch.setattr(watcher_module, "apply_monitor_rule", lambda *_args: True)

    watcher.update_rules([rule], apply_existing=True)
    watcher._scan_once()

    assert watcher._managed == {1: "rule-1"}


def test_startup_initialization_uses_first_matching_rule(monkeypatch):
    first = make_rule(id="first", match_exact_path=False)
    second = make_rule(id="second", match_exact_path=False)
    watcher = watcher_module.MonitorRuleWatcher()
    applied_rule_ids = []
    monkeypatch.setattr(watcher, "start", lambda: None)
    monkeypatch.setattr(
        watcher_module,
        "enumerate_eligible_windows",
        lambda **_kwargs: [_matching_window_details()],
    )
    monkeypatch.setattr(
        watcher_module,
        "apply_monitor_rule",
        lambda _hwnd, rule: applied_rule_ids.append(rule["id"]) or True,
    )

    watcher.update_rules([first, second], apply_existing=True)
    watcher._scan_once()

    assert applied_rule_ids == ["first"]


def test_grouped_rule_places_main_and_folder_creator_on_the_same_monitor(monkeypatch):
    rule = rule_schema.normalize_monitor_rule(
        {
            "id": "resurface",
            "app_group": "windows_resurface",
            "target_device": r"\\.\DISPLAY2",
            "target_label": "Monitor 2",
        }
    )
    windows = [
        {**_matching_window_details(1), "title": "Windows Resurface"},
        {**_matching_window_details(2), "title": "Folder Creator", "process_id": 20},
    ]
    watcher = watcher_module.MonitorRuleWatcher()
    placed = []
    monkeypatch.setattr(watcher, "start", lambda: None)
    monkeypatch.setattr(watcher_module, "enumerate_eligible_windows", lambda **_kwargs: windows)
    monkeypatch.setattr(
        watcher_module, "window_application_group", lambda _details, **_kwargs: "windows_resurface"
    )
    monkeypatch.setattr(watcher_module, "window_monitor_device", lambda _hwnd: r"\\.\DISPLAY1")
    monkeypatch.setattr(
        watcher_module, "apply_monitor_rule", lambda hwnd, applied: placed.append((hwnd, applied["placement_mode"])) or True
    )

    watcher.update_rules([rule], app_hwnd=1, apply_existing=True)
    watcher._scan_once()

    assert placed == [(1, "keep_size"), (2, "keep_size")]


def test_watcher_reapplies_when_hidden_window_becomes_visible_again(monkeypatch):
    rule = rule_schema.normalize_monitor_rule(make_rule(match_exact_path=False))
    watcher = watcher_module.MonitorRuleWatcher()
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
        watcher_module,
        "enumerate_eligible_windows",
        lambda **_kwargs: [copy.deepcopy(details)] if visible else [],
    )
    monkeypatch.setattr(
        watcher_module,
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
    rule = rule_schema.normalize_monitor_rule(make_rule(match_exact_path=False))
    watcher = watcher_module.MonitorRuleWatcher()
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
        watcher_module,
        "enumerate_eligible_windows",
        lambda **_kwargs: [copy.deepcopy(details)],
    )
    monkeypatch.setattr(
        watcher_module,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher._scan_once()
    details["process_id"] = 20
    details["process_started_at"] = 200.0
    watcher._scan_once()
    assert placed == [1]


def test_watcher_does_not_retrigger_same_visible_window(monkeypatch):
    rule = rule_schema.normalize_monitor_rule(make_rule(match_exact_path=False))
    watcher = watcher_module.MonitorRuleWatcher()
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
        watcher_module,
        "enumerate_eligible_windows",
        lambda **_kwargs: [copy.deepcopy(details)],
    )
    monkeypatch.setattr(
        watcher_module,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher._scan_once()
    watcher._scan_once()
    watcher._scan_once()
    assert placed == []


def test_watcher_starts_only_for_enabled_rules_and_stops_cleanly():
    watcher = watcher_module.MonitorRuleWatcher()
    watcher.update_rules([make_rule(enabled=False)])
    assert not watcher.is_running
    watcher.update_rules([make_rule(enabled=True)])
    assert watcher.is_running
    watcher.stop()
    assert not watcher.is_running



def _matching_window_details(hwnd=1):
    return {
        "hwnd": hwnd, "title": "Discord", "class_name": "Main",
        "executable_name": "discord.exe", "executable_path": "",
        "process_id": 10, "process_started_at": 100.0,
    }


@pytest.fixture
def simulation(monkeypatch):
    class Desktop:
        now = 10.0
        dragging = False
        succeeds = True
        reset_after_move = False

        def __init__(self):
            self.windows = [_matching_window_details()]
            self.devices = {1: r"\\.\DISPLAY1"}
            self.moves = []
            self.watcher = watcher_module.MonitorRuleWatcher()
            monkeypatch.setattr(self.watcher, "start", lambda: None)
            monkeypatch.setattr(self.watcher, "stop", lambda: None)

        def move(self, hwnd, rule):
            self.moves.append((hwnd, rule["id"], rule["placement_mode"]))
            if self.succeeds and not self.reset_after_move:
                self.devices[hwnd] = rule["target_device"]
            return self.succeeds

        def scan(self, seconds=0.5):
            self.now += seconds
            self.watcher._scan_once()

        def configure(self, rules=None, **kwargs):
            self.watcher.update_rules(
                [make_rule(match_exact_path=False)] if rules is None else rules,
                **kwargs)

    desktop = Desktop()
    monkeypatch.setattr(watcher_module.time, "monotonic", lambda: desktop.now)
    monkeypatch.setattr(watcher_module, "enumerate_eligible_windows",
                        lambda **kwargs: copy.deepcopy(desktop.windows))
    monkeypatch.setattr(watcher_module, "window_monitor_device",
                        lambda hwnd: desktop.devices.get(hwnd, ""))
    monkeypatch.setattr(watcher_module, "apply_monitor_rule", desktop.move)
    monkeypatch.setattr(watcher_module, "_left_mouse_pressed", lambda: desktop.dragging)
    return desktop


@pytest.mark.parametrize("existing", [True, False])
def test_failed_placement_recovers(simulation, existing):
    d = simulation
    rule = make_rule(match_exact_path=False)
    window = d.windows[0]
    d.windows = [window] if existing else []
    d.succeeds = False
    d.configure([rule], apply_existing=True)
    d.scan()
    if not existing:
        d.windows = [window]
        d.scan()
    assert len(d.moves) == 1
    assert 1 in d.watcher._pending
    d.succeeds = True
    d.scan()
    assert len(d.moves) == 2
    assert d.devices[1] == rule["target_device"]


@pytest.mark.parametrize("existing", [True, False])
def test_app_position_reset_is_corrected_only_during_recovery(simulation, existing):
    d = simulation
    window = d.windows[0]
    d.windows = [window] if existing else []
    d.configure(apply_existing=True)
    d.scan()
    if not existing:
        d.windows = [window]
        d.scan()
    d.devices[1] = r"\\.\DISPLAY1"
    d.scan(5)
    assert len(d.moves) == 2
    d.scan(15)
    d.devices[1] = r"\\.\DISPLAY1"
    d.scan()
    assert len(d.moves) == 2
    assert d.watcher._pending == {}


@pytest.mark.parametrize("mode", ["keep_size", "maximize", "saved_geometry"])
def test_new_window_applies_mode_even_on_target_but_startup_skips(simulation, mode):
    d = simulation
    rule = make_rule(match_exact_path=False, placement_mode=mode,
                     saved_geometry={"x_offset": 0, "y_offset": 0, "width": 800, "height": 600})
    d.devices[1] = rule["target_device"]
    d.configure([rule], apply_existing=True)
    d.scan()
    assert d.moves == []
    d.windows.append(_matching_window_details(2))
    d.devices[2] = rule["target_device"]
    d.scan()
    d.scan()
    assert d.moves == [(2, "rule-1", mode)]


@pytest.mark.parametrize("reapply", [False, True])
def test_missing_display_expires_unless_reapply_enabled(simulation, reapply):
    d = simulation
    d.succeeds = False
    d.configure([make_rule(match_exact_path=False, reapply_if_moved=reapply)],
                apply_existing=True)
    d.scan()
    d.scan(14)
    assert len(d.moves) == 2
    d.scan(1)
    count = len(d.moves)
    d.succeeds = True
    d.scan(1)
    assert len(d.moves) == count + int(reapply)


def test_dragging_pauses_moves_without_extending_deadline(simulation):
    d = simulation
    d.dragging = True
    d.configure(apply_existing=True)
    d.scan()
    deadline = d.watcher._pending[1].deadline
    d.scan(5)
    assert d.moves == []
    d.dragging = False
    d.scan()
    assert len(d.moves) == 1
    assert d.watcher._pending[1].deadline == deadline
    d.devices[1] = r"\\.\DISPLAY1"
    d.dragging = True
    d.scan(15)
    d.dragging = False
    d.scan()
    assert len(d.moves) == 1


def test_manual_drag_ends_successful_recovery_when_reapply_is_disabled(simulation):
    d = simulation
    d.configure(apply_existing=True)
    d.scan()
    assert len(d.moves) == 1
    assert d.watcher._pending[1].placed is True

    d.devices[1] = r"\\.\DISPLAY1"
    d.dragging = True
    d.scan()
    assert len(d.moves) == 1
    assert d.watcher._pending == {}

    d.dragging = False
    d.scan()
    assert len(d.moves) == 1


def test_manual_drag_only_pauses_recovery_when_reapply_is_enabled(simulation):
    d = simulation
    d.configure([make_rule(match_exact_path=False, reapply_if_moved=True)],
                apply_existing=True)
    d.scan()
    d.devices[1] = r"\\.\DISPLAY1"
    d.dragging = True
    d.scan()
    assert len(d.moves) == 1
    assert 1 in d.watcher._pending

    d.dragging = False
    d.scan()
    assert len(d.moves) == 2


def test_shortcut_move_ends_recovery_when_reapply_is_disabled(monkeypatch):
    rule = rule_schema.normalize_monitor_rule(
        make_rule(match_exact_path=False, reapply_if_moved=False)
    )
    watcher = watcher_module.MonitorRuleWatcher()
    watcher._rules = [rule]
    details = _matching_window_details()
    watcher._seen[1] = watcher_module._identity(details)
    watcher._pending[1] = watcher_module._Recovery(
        watcher_module._identity(details),
        100.0,
        True,
        placed=True,
    )
    watcher._managed[1] = rule["id"]
    watcher._off_target_since[1] = 5.0
    monkeypatch.setattr(
        watcher_module,
        "window_details",
        lambda _hwnd, **_kwargs: copy.deepcopy(details),
    )

    watcher.note_manual_move(1)

    assert watcher._pending == {}
    assert watcher._managed == {}
    assert watcher._off_target_since == {}


def test_shortcut_move_keeps_enforcement_and_uses_settle_delay(monkeypatch):
    rule = rule_schema.normalize_monitor_rule(
        make_rule(match_exact_path=False, reapply_if_moved=True)
    )
    watcher = watcher_module.MonitorRuleWatcher()
    watcher._rules = [rule]
    details = _matching_window_details()
    placed = []
    monkeypatch.setattr(watcher_module.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(
        watcher_module,
        "window_details",
        lambda _hwnd, **_kwargs: copy.deepcopy(details),
    )
    monkeypatch.setattr(
        watcher_module,
        "window_monitor_device",
        lambda _hwnd: r"\\.\DISPLAY1",
    )
    monkeypatch.setattr(
        watcher_module,
        "apply_monitor_rule",
        lambda hwnd, _rule: placed.append(hwnd) or True,
    )

    watcher.note_manual_move(1)

    assert watcher._pending == {}
    assert watcher._managed == {1: rule["id"]}
    assert watcher._off_target_since == {1: 10.0}
    watcher._place_window(1, watcher._revision, 10.5)
    assert placed == []
    watcher._place_window(1, watcher._revision, 10.7)
    assert placed == [1]


def test_shortcut_move_without_matching_rule_does_not_change_tracking(monkeypatch):
    watcher = watcher_module.MonitorRuleWatcher()
    watcher._managed[1] = "existing"
    monkeypatch.setattr(
        watcher_module,
        "window_details",
        lambda _hwnd, **_kwargs: _matching_window_details(),
    )

    watcher.note_manual_move(1)

    assert watcher._managed == {1: "existing"}


@pytest.mark.parametrize("change", ["add", "edit", "enable", "delete", "reorder"])
def test_rule_changes_place_affected_open_windows(simulation, change):
    d = simulation
    first = make_rule(id="first", match_exact_path=False)
    second = make_rule(id="second", match_exact_path=False, target_device=r"\\.\DISPLAY3")
    before = {"add": [], "edit": [first], "enable": [{**second, "enabled": False}],
              "delete": [first, second], "reorder": [first, second]}[change]
    after = {"add": [second], "edit": [{**second, "id": "first"}],
             "enable": [second], "delete": [second], "reorder": [second, first]}[change]
    d.configure(before, apply_existing=True)
    d.scan()
    d.scan(16)
    d.moves.clear()
    d.configure(after)
    d.scan()
    assert len(d.moves) == 1
    assert d.devices[1] == second["target_device"]


def test_cosmetic_and_unrelated_edits_preserve_pending_deadline(simulation):
    d = simulation
    rule = make_rule(match_exact_path=False)
    d.configure([rule], apply_existing=True)
    d.scan()
    recovery = d.watcher._pending[1]
    d.configure([{**rule, "name": "Renamed", "target_label": "My screen"},
                 make_rule(id="other", executable_name="other.exe", match_exact_path=False)])
    d.scan()
    assert d.watcher._pending[1] is recovery
    d.scan()
    assert len(d.moves) == 1
    assert d.watcher._pending[1].deadline == recovery.deadline


def test_unrelated_windows_and_cosmetic_edits_do_not_restart_recovery(simulation):
    d = simulation
    rule = make_rule(match_exact_path=False)
    d.configure([rule], apply_existing=True)
    d.scan()
    d.scan(16)
    d.devices[1] = r"\\.\DISPLAY1"
    d.moves.clear()
    d.configure([{**rule, "name": "New name"},
                 make_rule(id="other", executable_name="other.exe", match_exact_path=False)])
    d.scan()
    assert d.moves == []
    assert d.watcher._pending == {}


def test_disabling_and_rapid_edits_do_not_leave_stale_work(simulation):
    d = simulation
    d.configure(apply_existing=True)
    d.scan()
    d.moves.clear()
    d.configure([make_rule(match_exact_path=False, target_device=r"\\.\DISPLAY3")])
    d.configure([])
    d.scan()
    assert d.moves == []
    assert d.watcher._pending == {}
    assert d.watcher._managed == {}


def test_reapply_toggle_enrolls_then_stops_enforcement(simulation):
    d = simulation
    rule = make_rule(match_exact_path=False)
    d.configure([rule], apply_existing=True)
    d.scan()
    d.configure([{**rule, "reapply_if_moved": True}])
    d.scan()
    assert d.watcher._managed == {1: "rule-1"}
    assert len(d.moves) == 1
    d.scan(16)
    d.devices[1] = r"\\.\DISPLAY1"
    d.dragging = True
    d.scan()
    assert len(d.moves) == 1
    d.dragging = False
    d.scan()
    d.scan(1)
    assert len(d.moves) == 2
    d.configure([rule])
    assert d.watcher._managed == {}


def test_hidden_window_and_reused_handle_get_fresh_recovery(simulation):
    d = simulation
    d.configure(apply_existing=True)
    d.scan()
    first = d.watcher._pending[1]
    window = d.windows.pop()
    d.scan()
    assert d.watcher._pending == {}
    d.windows.append(window)
    d.scan()
    assert d.watcher._pending[1] is not first
    second = d.watcher._pending[1]
    window["process_started_at"] += 1
    d.scan()
    assert d.watcher._pending[1].identity != second.identity
    assert len(d.moves) == 3


def test_edit_during_enumeration_uses_latest_rules(simulation, monkeypatch):
    d = simulation
    d.configure(apply_existing=True)
    def enumerate_and_edit(**kwargs):
        d.configure([make_rule(match_exact_path=False, target_device=r"\\.\DISPLAY3")])
        return copy.deepcopy(d.windows)
    monkeypatch.setattr(watcher_module, "enumerate_eligible_windows", enumerate_and_edit)
    d.scan()
    assert d.devices[1] == r"\\.\DISPLAY3"


def test_edit_during_placement_does_not_commit_stale_success(simulation, monkeypatch):
    d = simulation
    d.configure(apply_existing=True)
    def move_and_edit(hwnd, rule):
        d.configure([])
        return True
    monkeypatch.setattr(watcher_module, "apply_monitor_rule", move_and_edit)
    d.scan()
    assert d.watcher._pending == {}
    assert d.watcher._managed == {}


def test_identity_change_before_placement_does_not_move_replacement(simulation, monkeypatch):
    d = simulation
    d.configure(apply_existing=True)
    monkeypatch.setattr(watcher_module, "window_details",
                        lambda *args, **kwargs: {**d.windows[0], "process_id": 999})
    d.scan()
    assert d.moves == []
    assert d.watcher._pending == {}


@pytest.mark.parametrize("reapply", [False, True])
def test_reenable_after_stopping_all_rules_places_existing_window(simulation, reapply):
    d = simulation
    rule = make_rule(match_exact_path=False, reapply_if_moved=reapply)
    d.configure([rule], apply_existing=True)
    d.scan()
    d.devices[1] = r"\\.\DISPLAY1"
    d.configure([{**rule, "enabled": False}])
    # No scan runs while all rules are disabled.
    d.configure([rule])
    d.scan()
    assert len(d.moves) == 2


def test_failed_move_cannot_succeed_after_exact_deadline(simulation):
    d = simulation
    d.succeeds = False
    d.configure(apply_existing=True)
    d.scan()
    d.succeeds = True
    d.scan(15)
    assert len(d.moves) == 1
    assert d.watcher._pending == {}


def test_placement_mode_edit_applies_on_same_monitor(simulation):
    d = simulation
    d.configure(apply_existing=True)
    d.scan()
    d.configure([make_rule(match_exact_path=False, placement_mode="maximize")])
    d.scan()
    assert d.moves[-1] == (1, "rule-1", "maximize")
    assert len(d.moves) == 2


def test_edit_wakes_running_watcher_without_clearing_pending(simulation, monkeypatch):
    d = simulation
    d.configure(apply_existing=True)
    d.scan()
    recovery = d.watcher._pending[1]
    d.watcher._thread = type("Thread", (), {"is_alive": lambda self: True})()
    wakes = []
    monkeypatch.setattr(d.watcher._wake_event, "set", lambda: wakes.append(True))
    d.configure([make_rule(match_exact_path=False, name="Renamed")])
    assert wakes == [True]
    assert d.watcher._pending[1] is recovery
    assert not d.watcher._baseline_pending


@pytest.mark.parametrize("change", ["delete", "reorder"])
def test_equivalent_winning_rule_preserves_reapply_management(simulation, change):
    d = simulation
    first = make_rule(id="first", match_exact_path=False, reapply_if_moved=True)
    second = {**first, "id": "second"}
    d.configure([first, second], apply_existing=True)
    d.scan()
    d.scan(16)
    d.configure([second] if change == "delete" else [second, first])
    d.scan()
    assert d.watcher._managed == {1: "second"}
    assert d.watcher._pending == {}
    d.devices[1] = r"\\.\DISPLAY1"
    d.scan()
    d.scan(1)
    assert d.moves[-1][1] == "second"


def test_temporarily_unavailable_window_details_are_seen_again(simulation, monkeypatch):
    d = simulation
    d.configure(apply_existing=True)
    original = watcher_module.window_details
    monkeypatch.setattr(watcher_module, "window_details", lambda *args, **kwargs: None)
    d.scan()
    assert d.moves == []
    monkeypatch.setattr(watcher_module, "window_details", original)
    d.scan()
    assert len(d.moves) == 1


@pytest.mark.parametrize("edit", ["unchanged", "name", "monitor", "mode", "geometry"])
def test_explicit_save_forces_full_placement_and_wakes_watcher(simulation, monkeypatch, edit):
    d = simulation
    rule = make_rule(match_exact_path=False, placement_mode="saved_geometry",
                     saved_geometry={"x_offset": 0, "y_offset": 0, "width": 800, "height": 600})
    d.configure([rule], apply_existing=True)
    d.scan()
    d.scan(16)
    d.moves.clear()
    changed = copy.deepcopy(rule)
    if edit == "name":
        changed["name"] = "New name"
    elif edit == "monitor":
        changed["target_device"] = r"\\.\DISPLAY3"
    elif edit == "mode":
        changed["placement_mode"] = "maximize"
    elif edit == "geometry":
        changed["saved_geometry"]["width"] = 1000
    captured = []
    original_move = d.move
    def move(hwnd, applied):
        captured.append(copy.deepcopy(applied))
        return original_move(hwnd, applied)
    monkeypatch.setattr(watcher_module, "apply_monitor_rule", move)
    d.watcher._thread = type("Thread", (), {"is_alive": lambda self: True})()
    wakes = []
    monkeypatch.setattr(d.watcher._wake_event, "set", lambda: wakes.append(True))
    d.configure([changed], apply_rule_ids={rule["id"]})
    assert wakes == [True]
    d.scan(0)
    d.scan()
    assert len(d.moves) == 1
    assert captured == [rule_schema.normalize_monitor_rule(changed)]
    assert d.watcher._pending[1].force_initial
    assert d.watcher._pending[1].placed
    assert d.watcher._apply_rule_ids == set()


@pytest.mark.parametrize("blocked", ["disabled", "earlier_match", "missing_id"])
def test_explicit_save_honors_matching_and_rule_priority(simulation, blocked):
    d = simulation
    first = make_rule(id="first", match_exact_path=False)
    second = make_rule(id="second", match_exact_path=False)
    if blocked == "disabled":
        first["enabled"] = False
    rules = [second, first] if blocked == "earlier_match" else [first, second]
    d.configure(rules, apply_existing=True)
    d.scan()
    d.scan(16)
    d.moves.clear()
    d.configure(rules, apply_rule_ids={"missing" if blocked == "missing_id" else "first"})
    d.scan()
    assert d.moves == []
    assert d.watcher._pending == {}


def test_explicit_save_affects_only_requested_rule_windows(simulation):
    d = simulation
    d.windows.append({**_matching_window_details(2), "executable_name": "other.exe"})
    rules = [make_rule(match_exact_path=False),
             make_rule(id="other", executable_name="other.exe", match_exact_path=False)]
    d.configure(rules, apply_existing=True)
    d.scan()
    d.scan(16)
    d.moves.clear()
    d.devices[2] = r"\\.\DISPLAY1"
    d.configure(rules, apply_rule_ids={"rule-1"})
    d.scan()
    assert d.moves == [(1, "rule-1", "keep_size")]
    assert d.devices[2] == r"\\.\DISPLAY1"


def test_saved_rule_waits_for_drag_and_retries_failure_and_reset(simulation):
    d = simulation
    d.configure(apply_existing=True)
    d.scan()
    d.scan(16)
    d.moves.clear()
    d.dragging = True
    d.configure(apply_rule_ids={"rule-1"})
    d.scan()
    deadline = d.watcher._pending[1].deadline
    assert d.moves == []
    d.dragging = False
    d.succeeds = False
    d.scan()
    assert not d.watcher._pending[1].placed
    d.succeeds = True
    d.scan()
    d.devices[1] = r"\\.\DISPLAY1"
    d.scan()
    assert len(d.moves) == 3
    assert d.watcher._pending[1].deadline == deadline
    d.scan(16)
    d.devices[1] = r"\\.\DISPLAY1"
    d.scan()
    assert len(d.moves) == 3


def test_rapid_saves_use_latest_rule_and_disabled_requests_are_removed(simulation):
    d = simulation
    rule = make_rule(match_exact_path=False)
    d.configure([rule], apply_existing=True)
    d.scan()
    d.moves.clear()
    d.configure([{**rule, "placement_mode": "maximize"}], apply_rule_ids={"rule-1"})
    d.configure([rule], apply_rule_ids={"rule-1"})
    d.scan()
    assert d.moves == [(1, "rule-1", "keep_size")]
    d.configure([rule], apply_rule_ids={"rule-1"})
    d.configure([{**rule, "enabled": False}])
    assert d.watcher._apply_rule_ids == set()
    assert d.watcher._pending == {}


def test_save_during_placement_retains_new_request(simulation, monkeypatch):
    d = simulation
    d.configure(apply_existing=True)
    d.scan()
    d.scan(16)
    d.moves.clear()
    def save_during_move(hwnd, rule):
        d.configure(apply_rule_ids={"rule-1"})
        return d.move(hwnd, rule)
    monkeypatch.setattr(watcher_module, "apply_monitor_rule", save_during_move)
    d.configure(apply_rule_ids={"rule-1"})
    d.scan()
    assert d.watcher._apply_rule_ids == {"rule-1"}
    assert not d.watcher._pending[1].placed
    monkeypatch.setattr(watcher_module, "apply_monitor_rule", d.move)
    d.scan()
    assert len(d.moves) == 2
    assert d.watcher._pending[1].placed

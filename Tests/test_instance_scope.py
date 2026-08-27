from pathlib import Path

import main as resurface_main


class FakeProcess:
    def __init__(self, *, exe=None, cmdline=None, cwd=None):
        self._exe = exe
        self._cmdline = cmdline or []
        self._cwd = cwd

    def exe(self):
        return self._exe

    def cmdline(self):
        return self._cmdline

    def cwd(self):
        return self._cwd


def test_source_and_local_exe_use_different_mutex_names(tmp_path):
    source_root = tmp_path / "Projects" / "Win-11-Resurface"
    local_exe = (
        tmp_path
        / "Local EXES"
        / "Win-11-Resurface"
        / "main_Code Windows Resurface_UK_2.exe"
    )

    source_mutex = resurface_main.instance_mutex_name(("source", source_root))
    exe_mutex = resurface_main.instance_mutex_name(("exe", local_exe))

    assert source_mutex != exe_mutex
    assert source_mutex.startswith("Windows Resurface:source:")
    assert exe_mutex.startswith("Windows Resurface:exe:")


def test_source_instance_scope_rejects_local_exe_window(monkeypatch, tmp_path):
    source_root = tmp_path / "Projects" / "Win-11-Resurface"
    local_exe = (
        tmp_path
        / "Local EXES"
        / "Win-11-Resurface"
        / "main_Code Windows Resurface_UK_2.exe"
    )

    monkeypatch.setattr(
        resurface_main.win32process,
        "GetWindowThreadProcessId",
        lambda hwnd: (10, 20),
    )
    monkeypatch.setattr(
        resurface_main.psutil,
        "Process",
        lambda pid: FakeProcess(
            exe=str(local_exe),
            cmdline=[str(local_exe)],
            cwd=str(local_exe.parent),
        ),
    )

    matches = resurface_main._window_matches_instance_scope(
        100,
        ("source", source_root),
    )

    assert matches is False


def test_source_instance_scope_matches_source_main_window(monkeypatch, tmp_path):
    source_root = tmp_path / "Projects" / "Win-11-Resurface"
    app_dir = source_root / "Code Windows Resurface"

    monkeypatch.setattr(
        resurface_main.win32process,
        "GetWindowThreadProcessId",
        lambda hwnd: (10, 20),
    )
    monkeypatch.setattr(
        resurface_main.psutil,
        "Process",
        lambda pid: FakeProcess(
            exe="C:/Python310/python.exe",
            cmdline=["C:/Python310/python.exe", "main.py"],
            cwd=str(app_dir),
        ),
    )

    matches = resurface_main._window_matches_instance_scope(
        100,
        ("source", source_root),
    )

    assert matches is True


def test_exe_instance_scope_matches_only_same_exe(monkeypatch, tmp_path):
    target_exe = tmp_path / "Local EXES" / "Win-11-Resurface" / "Windows Resurface.exe"
    other_exe = tmp_path / "Local EXES" / "Other" / "Windows Resurface.exe"
    returned_process = {"exe": str(target_exe)}

    monkeypatch.setattr(
        resurface_main.win32process,
        "GetWindowThreadProcessId",
        lambda hwnd: (10, 20),
    )
    monkeypatch.setattr(
        resurface_main.psutil,
        "Process",
        lambda pid: FakeProcess(exe=returned_process["exe"]),
    )

    assert resurface_main._window_matches_instance_scope(
        100,
        ("exe", target_exe),
    )

    returned_process["exe"] = str(other_exe)

    assert not resurface_main._window_matches_instance_scope(
        100,
        ("exe", target_exe),
    )


def test_restore_retries_until_starting_instance_creates_its_window(monkeypatch):
    enum_calls = 0
    posted_messages = []

    def enum_windows(callback, _):
        nonlocal enum_calls
        enum_calls += 1
        if enum_calls == 2:
            callback(100, None)

    monkeypatch.setattr(resurface_main.win32gui, "EnumWindows", enum_windows)
    monkeypatch.setattr(resurface_main.win32gui, "GetWindowText", lambda hwnd: "Windows Resurface")
    monkeypatch.setattr(resurface_main, "_window_matches_instance_scope", lambda hwnd, scope: True)
    monkeypatch.setattr(
        resurface_main.win32gui,
        "PostMessage",
        lambda hwnd, message, wparam, lparam: posted_messages.append(
            (hwnd, message, wparam, lparam)
        ),
    )
    monkeypatch.setattr(resurface_main.time, "sleep", lambda seconds: None)

    assert resurface_main.bring_existing_instance_to_front(
        attempts=3,
        retry_delay_seconds=0,
    )
    assert enum_calls == 2
    assert posted_messages == [(100, resurface_main.WM_APP_RESTORE_INSTANCE, 0, 0)]

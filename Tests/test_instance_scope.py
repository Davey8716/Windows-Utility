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

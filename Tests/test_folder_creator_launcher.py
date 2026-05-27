import subprocess
import sys
from pathlib import Path

import pytest

from desktop_operations import DesktopOperationsMixin, PROJECT_ROOT_ENV_VAR


class FakeActions:
    def __init__(self, window_state: str = "closed"):
        self.window_state = window_state
        self.folder_path_calls = []
        self.window_title_calls = []
        self.closed_title_calls = []

    def get_window_titles_state(self, title_candidates):
        return self.window_state

    def close_window_titles(self, title_candidates):
        self.closed_title_calls.append(tuple(title_candidates))
        return False

    def open_or_focus_window_titles(self, title_candidates, launch):
        self.window_title_calls.append(tuple(title_candidates))
        launch()
        return True

    def open_or_focus_folder_path(self, *args, **kwargs):
        self.folder_path_calls.append((args, kwargs))
        return True


class FolderCreatorHarness(DesktopOperationsMixin):
    def __init__(self, launch_target=None):
        self.actions = FakeActions()
        self.launch_target = launch_target
        self.warning_messages = []
        self.restored_topmost = False
        self.focused_titles = []
        self.handoff_titles = []

    def _should_minimize_after_use(self):
        return False

    def _resolve_folder_creator_launch_target(self, project_dir: Path):
        if self.launch_target == "real":
            return super()._resolve_folder_creator_launch_target(project_dir)
        return self.launch_target

    def _begin_folder_creator_z_order_handoff(self, title_candidates):
        self.handoff_titles.append(tuple(title_candidates))

    def _focus_folder_creator_window(self, title_candidates=None):
        self.focused_titles.append(tuple(title_candidates or ()))

    def _monitor_folder_creator_window(self):
        pass

    def _restore_folder_creator_parent_topmost(self):
        self.restored_topmost = True

    def _message_box_icon(self, icon_name):
        return icon_name

    def _show_organizing_timed_message(self, icon, title, message, **kwargs):
        self.warning_messages.append((icon, title, message, kwargs))


def test_resolve_folder_creator_launch_target_returns_absolute_main(tmp_path):
    project_dir = tmp_path / "Code Folder Creator"
    project_dir.mkdir()
    main_path = project_dir / "main.py"
    main_path.write_text("print('folder creator')", encoding="utf-8")

    resolved = DesktopOperationsMixin()._resolve_folder_creator_launch_target(
        project_dir
    )

    assert resolved == main_path.resolve()


def test_resolve_folder_creator_launch_target_ignores_other_candidates(tmp_path):
    project_dir = tmp_path / "Code Folder Creator"
    project_dir.mkdir()
    (project_dir / "main.pyw").write_text("", encoding="utf-8")
    (project_dir / "Folder Creator.exe").write_text("", encoding="utf-8")
    (project_dir / "launch.bat").write_text("", encoding="utf-8")

    resolved = DesktopOperationsMixin()._resolve_folder_creator_launch_target(
        project_dir
    )

    assert resolved is None


def test_resolve_project_root_prefers_valid_source_checkout(monkeypatch, tmp_path):
    project_root = tmp_path / "Win-11-Resurface"
    app_dir = project_root / "Code Windows Resurface"
    app_dir.mkdir(parents=True)
    (app_dir / "main.py").write_text("", encoding="utf-8")
    monkeypatch.setenv(PROJECT_ROOT_ENV_VAR, str(project_root))

    resolved = DesktopOperationsMixin()._resolve_windows_resurface_project_root()

    assert resolved == project_root.resolve()


def test_python_script_command_uses_python_when_packaged_exe_is_current_process(
    monkeypatch,
    tmp_path,
):
    packaged_exe = (
        tmp_path
        / "Local EXES"
        / "Win-11-Resurface"
        / "main_Code Windows Resurface_UK_2.exe"
    )
    python_exe = tmp_path / "Python310" / "python.exe"
    script_path = tmp_path / "Win-11-Resurface" / "Code Folder Creator" / "main.py"
    monkeypatch.setattr(sys, "executable", str(packaged_exe))
    monkeypatch.setattr(
        "desktop_operations.shutil.which",
        lambda command: str(python_exe) if command == "python" else None,
    )

    command = DesktopOperationsMixin()._python_script_command(script_path)

    assert command == [str(python_exe), str(script_path)]


def test_open_folder_creator_launches_main_py_without_folder_fallback(monkeypatch):
    launch_target = Path(__file__).resolve()
    harness = FolderCreatorHarness(launch_target=launch_target)
    popen_calls = []

    def fake_popen(args, **kwargs):
        popen_calls.append((args, kwargs))

        class FakeProcess:
            pass

        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    harness.open_folder_creator()

    assert harness.actions.window_title_calls == []
    assert harness.actions.folder_path_calls == []
    assert popen_calls
    assert popen_calls[0][0] == [sys.executable, str(launch_target)]
    assert popen_calls[0][1]["stdout"] == subprocess.DEVNULL
    assert popen_calls[0][1]["stderr"] == subprocess.DEVNULL


def test_open_folder_creator_missing_main_py_does_not_open_folder(monkeypatch):
    harness = FolderCreatorHarness(launch_target=None)

    def fail_startfile(path):
        pytest.fail(f"folder fallback should not open: {path}")

    monkeypatch.setattr("desktop_operations.os.startfile", fail_startfile)

    harness.open_folder_creator()

    assert harness.actions.window_title_calls == []
    assert harness.actions.folder_path_calls == []
    assert harness.warning_messages
    assert harness.warning_messages[0][1] == "Folder Creator"

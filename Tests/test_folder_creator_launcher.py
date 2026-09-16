import subprocess
import sys
from pathlib import Path

from resurface.features.folder_creator import launcher as launcher_module
from resurface.features.folder_creator.launcher import (
    PROJECT_ROOT_ENV_VAR,
    FolderCreatorLaunchStatus,
    FolderCreatorLauncher,
)
from resurface.ui.controllers import folder_actions
from resurface.ui.controllers.folder_actions import FolderActionsController


def test_resolve_folder_creator_launch_target_returns_absolute_main(tmp_path):
    project_dir = tmp_path / "Code Folder Creator"
    project_dir.mkdir()
    main_path = project_dir / "main.py"
    main_path.write_text("", encoding="utf-8")
    assert FolderCreatorLauncher().resolve_launch_target(project_dir) == main_path.resolve()


def test_resolve_folder_creator_launch_target_prefers_packaged_companion(tmp_path):
    project_dir = tmp_path / "Code Folder Creator"
    project_dir.mkdir()
    for name in ("main.py", "Folder Creator.exe", "launch.bat"):
        (project_dir / name).write_text("", encoding="utf-8")
    assert FolderCreatorLauncher().resolve_launch_target(project_dir) == (
        project_dir / "Folder Creator.exe"
    ).resolve()


def test_resolve_project_root_prefers_environment_checkout(monkeypatch, tmp_path):
    root = tmp_path / "Win-11-Resurface"
    app_dir = root / "Code Windows Resurface"
    app_dir.mkdir(parents=True)
    (app_dir / "main.py").write_text("", encoding="utf-8")
    monkeypatch.setenv(PROJECT_ROOT_ENV_VAR, str(root))
    assert FolderCreatorLauncher().resolve_project_root() == root.resolve()


def test_python_script_command_uses_python_when_packaged(monkeypatch, tmp_path):
    packaged = tmp_path / "WindowsResurface.exe"
    python_exe = tmp_path / "python.exe"
    script = tmp_path / "main.py"
    monkeypatch.setattr(sys, "executable", str(packaged))
    monkeypatch.setattr(launcher_module.shutil, "which", lambda command: str(python_exe) if command == "python" else None)
    assert FolderCreatorLauncher.python_script_command(script) == [str(python_exe), str(script)]


def test_packaged_companion_launches_directly_without_python(monkeypatch, tmp_path):
    companion = tmp_path / "Folder Creator.exe"
    companion.write_text("", encoding="utf-8")
    assert FolderCreatorLauncher.launch_command(companion) == [str(companion)]


def test_launcher_focuses_existing_without_relaunch(monkeypatch, tmp_path):
    root, target = make_checkout(tmp_path)
    launcher = FolderCreatorLauncher()
    monkeypatch.setattr(launcher, "focus_existing", lambda *_: True)
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("relaunch")))
    assert launcher.launch_or_focus(root).status is FolderCreatorLaunchStatus.FOCUSED


def test_launcher_launches_main_with_suppressed_streams(monkeypatch, tmp_path):
    root, target = make_checkout(tmp_path)
    launcher = FolderCreatorLauncher()
    monkeypatch.setattr(launcher, "focus_existing", lambda *_: False)
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs)))
    result = launcher.launch_or_focus(root)
    assert result.status is FolderCreatorLaunchStatus.LAUNCHED and result.target == target
    assert calls[0][0][-1] == str(target)
    assert Path(calls[0][0][0]).name.casefold() in {"python.exe", "pythonw.exe"}
    assert calls[0][1]["stdout"] == subprocess.DEVNULL
    assert calls[0][1]["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


def test_packaging_spec_defines_windowed_companion_release_contract():
    spec = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "Code Folder Creator" / "folder_creator.spec"
    ).read_text(encoding="utf-8")
    assert 'name="Folder Creator"' in spec
    assert "console=False" in spec


def make_checkout(tmp_path):
    root = tmp_path / "Win-11-Resurface"
    project = root / "Code Folder Creator"
    project.mkdir(parents=True)
    target = project / "main.py"
    target.write_text("", encoding="utf-8")
    return root, target.resolve()


class App:
    def __init__(self):
        self.minimized = self.restored = 0
    def showMinimized(self): self.minimized += 1
    def showNormal(self): self.restored += 1
    def raise_(self): pass
    def activateWindow(self): pass
    @staticmethod
    def _message_box_icon(name): return name


class Organising:
    def __init__(self): self.messages = []
    def show_timed_message(self, *args, **kwargs): self.messages.append((args, kwargs))


class LauncherStub:
    def __init__(self, root, status): self.root, self.status = root, status
    def resolve_project_root(self): return self.root
    def resolve_launch_target(self, project):
        target = project / "main.py"
        return target if target.exists() else None
    def launch_or_focus(self, *_):
        target = self.root / "Code Folder Creator" / "main.py"
        return type("Result", (), {"status": self.status, "target": target})()
    def focus_existing(self, *_): return True


def test_controller_schedules_focus_retry_after_launch(monkeypatch, tmp_path):
    root, _ = make_checkout(tmp_path)
    app, organising = App(), Organising()
    scheduled = []
    monkeypatch.setattr(folder_actions.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    controller = FolderActionsController(app, None, LauncherStub(root, FolderCreatorLaunchStatus.LAUNCHED), organising)
    controller.open_folder_creator()
    assert app.minimized == 1 and scheduled[0][0] == 100


def test_controller_missing_target_does_not_minimize(tmp_path):
    root = tmp_path / "Win-11-Resurface"
    (root / "Code Folder Creator").mkdir(parents=True)
    app, organising = App(), Organising()
    controller = FolderActionsController(app, None, LauncherStub(root, FolderCreatorLaunchStatus.MISSING), organising)
    controller.open_folder_creator()
    assert app.minimized == 0 and organising.messages


def test_controller_restores_parent_after_launch_failure(tmp_path):
    root, _ = make_checkout(tmp_path)
    app, organising = App(), Organising()
    controller = FolderActionsController(app, None, LauncherStub(root, FolderCreatorLaunchStatus.FAILED), organising)
    controller.open_folder_creator()
    assert app.minimized == 1 and app.restored == 1 and organising.messages

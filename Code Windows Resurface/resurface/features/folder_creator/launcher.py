from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import psutil
import win32gui
import win32process

from resurface.features.windows.window_management import focus_window_handles


PROJECT_ROOT_ENV_VAR = "WIN11_RESURFACE_PROJECT_ROOT"
DEFAULT_WINDOW_TITLES = ("Folder Generator", "Folder Creator", "Code Folder Creator")


class FolderCreatorLaunchStatus(str, Enum):
    FOCUSED = "focused"
    LAUNCHED = "launched"
    MISSING = "missing"
    FAILED = "failed"


@dataclass(frozen=True)
class FolderCreatorLaunchResult:
    status: FolderCreatorLaunchStatus
    project_dir: Path
    target: Path | None = None
    error: str | None = None


class FolderCreatorLauncher:
    def launch_or_focus(
        self,
        project_root: str | Path | None = None,
        title_candidates: tuple[str, ...] = DEFAULT_WINDOW_TITLES,
    ) -> FolderCreatorLaunchResult:
        root = Path(project_root).resolve() if project_root else self.resolve_project_root()
        project_dir = root / "Code Folder Creator"
        target = self.resolve_launch_target(project_dir)
        if target is None:
            return FolderCreatorLaunchResult(FolderCreatorLaunchStatus.MISSING, project_dir)
        if self.focus_existing(title_candidates, target):
            return FolderCreatorLaunchResult(FolderCreatorLaunchStatus.FOCUSED, project_dir, target)
        try:
            subprocess.Popen(
                self.python_script_command(target),
                cwd=str(project_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            print(f"[DEBUG] Folder Creator launch failed for {target}: {exc}")
            return FolderCreatorLaunchResult(
                FolderCreatorLaunchStatus.FAILED, project_dir, target, str(exc)
            )
        return FolderCreatorLaunchResult(FolderCreatorLaunchStatus.LAUNCHED, project_dir, target)

    def focus_existing(self, title_candidates, launch_target: Path) -> bool:
        return focus_window_handles(self.window_handles(title_candidates, launch_target))

    def window_handles(self, title_candidates, launch_target: Path) -> list[int]:
        normalized = [candidate.strip().casefold() for candidate in title_candidates if candidate.strip()]
        handles: list[int] = []

        def enum_handler(hwnd, _):
            try:
                title = win32gui.GetWindowText(hwnd).strip()
            except Exception:
                return True
            folded = title.casefold()
            title_matches = title and any(
                folded == candidate
                or folded.endswith(f" - {candidate}")
                or candidate in folded
                for candidate in normalized
            )
            if title_matches and self.window_process_references_script(hwnd, launch_target):
                handles.append(hwnd)
            return True

        try:
            win32gui.EnumWindows(enum_handler, None)
        except Exception as exc:
            print(f"[DEBUG] Folder Creator window enumeration failed: {exc}")
        return handles

    def window_process_references_script(self, hwnd: int, script_path: Path) -> bool:
        try:
            _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            cmdline = process.cmdline()
            cwd = process.cwd()
        except Exception:
            return False
        normalized_script = str(script_path.resolve()).casefold()
        cwd_path = Path(cwd) if cwd else None
        for arg in cmdline:
            if not arg:
                continue
            arg_path = Path(arg.strip('"'))
            candidates = [arg_path]
            if not arg_path.is_absolute() and cwd_path is not None:
                candidates.append(cwd_path / arg_path)
            for candidate in candidates:
                try:
                    if str(candidate.resolve()).casefold() == normalized_script:
                        return True
                except OSError:
                    continue
        return False

    def resolve_launch_target(self, project_dir: Path) -> Path | None:
        target = project_dir.resolve() / "main.py"
        return target if target.is_file() else None

    def resolve_project_root(self) -> Path:
        for candidate in self.project_root_candidates():
            root = candidate.resolve()
            if self.is_project_root(root):
                return root
        return Path(__file__).resolve().parents[4]

    def project_root_candidates(self) -> tuple[Path, ...]:
        candidates: list[Path] = []
        env_path = os.environ.get(PROJECT_ROOT_ENV_VAR)
        if env_path:
            candidates.append(Path(env_path))
        candidates.append(Path(__file__).resolve().parents[4])
        cwd = Path.cwd().resolve()
        candidates.extend((cwd, *cwd.parents))
        candidates.append(Path.home() / "Desktop" / "Projects" / "Win-11-Resurface")
        return tuple(dict.fromkeys(candidates))

    @staticmethod
    def is_project_root(path: Path) -> bool:
        return (path / "Code Windows Resurface" / "main.py").is_file()

    @staticmethod
    def python_script_command(script_path: Path) -> list[str]:
        executable = Path(sys.executable)
        if executable.name.lower().startswith("python"):
            return [str(executable), str(script_path)]
        python_path = shutil.which("python")
        if python_path:
            return [python_path, str(script_path)]
        py_launcher = shutil.which("py")
        if py_launcher:
            return [py_launcher, "-3", str(script_path)]
        return ["python", str(script_path)]

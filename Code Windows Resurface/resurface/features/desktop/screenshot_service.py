from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageGrab
import win32api
import win32con
import win32gui

from resurface.features.windows.window_management import should_skip_window


@dataclass(frozen=True)
class MonitorCapture:
    index: int
    rect: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class ScreenshotCapturePlan:
    monitors: tuple[MonitorCapture, ...]
    save_dir: Path
    target_paths: tuple[Path, ...]
    stale_paths: tuple[Path, ...]
    existing_paths: tuple[Path, ...]


@dataclass(frozen=True)
class ScreenshotCaptureResult:
    saved_paths: tuple[Path, ...]
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and bool(self.saved_paths)


class ScreenshotService:
    def enumerate_monitors(self) -> tuple[MonitorCapture, ...]:
        monitors = []
        for index, monitor in enumerate(win32api.EnumDisplayMonitors(), start=1):
            info = win32api.GetMonitorInfo(monitor[0])
            monitors.append(MonitorCapture(index, tuple(info["Monitor"])))
        return tuple(monitors)

    def build_capture_plan(self, output_path: str | Path) -> ScreenshotCapturePlan:
        save_dir = Path(output_path).parent
        save_dir.mkdir(parents=True, exist_ok=True)
        monitors = self.enumerate_monitors() or (MonitorCapture(1, None),)
        target_paths = tuple(
            save_dir / f"DesktopScreenshot_Monitor{monitor.index}.png"
            for monitor in monitors
        )
        pattern_paths = tuple(sorted(save_dir.glob("DesktopScreenshot_Monitor*.png")))
        stale_paths = tuple(path for path in pattern_paths if path not in target_paths)
        existing_paths = tuple(
            path for path in (*target_paths, *stale_paths) if path.exists()
        )
        return ScreenshotCapturePlan(
            monitors=monitors,
            save_dir=save_dir,
            target_paths=target_paths,
            stale_paths=stale_paths,
            existing_paths=existing_paths,
        )

    def capture(self, plan: ScreenshotCapturePlan) -> ScreenshotCaptureResult:
        saved_paths: list[Path] = []
        try:
            image = ImageGrab.grab(all_screens=True)
            monitors = plan.monitors
            target_paths = plan.target_paths
            if monitors and monitors[0].rect is None:
                width, height = image.size
                monitors = (MonitorCapture(1, (0, 0, width, height)),)
                target_paths = (plan.save_dir / "DesktopScreenshot_Monitor1.png",)

            rects = [monitor.rect for monitor in monitors if monitor.rect is not None]
            virtual_left = min(rect[0] for rect in rects)
            virtual_top = min(rect[1] for rect in rects)
            for monitor, save_path in zip(monitors, target_paths):
                left, top, right, bottom = monitor.rect
                cropped = image.crop(
                    (
                        left - virtual_left,
                        top - virtual_top,
                        right - virtual_left,
                        bottom - virtual_top,
                    )
                )
                cropped.save(save_path)
                saved_paths.append(save_path)

            for stale_path in plan.stale_paths:
                stale_path.unlink(missing_ok=True)
            return ScreenshotCaptureResult(tuple(saved_paths))
        except Exception as exc:
            for save_path in saved_paths:
                try:
                    save_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return ScreenshotCaptureResult((), str(exc))

    def collect_windows_to_minimize(self, skip_hwnd: int) -> tuple[int, ...]:
        handles: list[int] = []

        def enum_handler(hwnd, _):
            if should_skip_window(hwnd, skip_hwnd):
                return
            try:
                placement = win32gui.GetWindowPlacement(hwnd)
            except Exception:
                return
            if placement[1] != win32con.SW_SHOWMINIMIZED:
                handles.append(hwnd)

        try:
            win32gui.EnumWindows(enum_handler, None)
        except Exception as exc:
            print(f"[SCREENSHOT] Window enumeration failed: {exc}")
        return tuple(handles)

    def minimize_windows(self, handles: tuple[int, ...] | list[int]) -> None:
        for hwnd in handles:
            try:
                if win32gui.IsWindow(hwnd) and not win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            except Exception as exc:
                print(f"[SCREENSHOT] Window minimize failed for {hwnd}: {exc}")

    def restore_windows(self, handles: tuple[int, ...] | list[int]) -> None:
        for hwnd in handles:
            try:
                if win32gui.IsWindow(hwnd) and win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            except Exception as exc:
                print(f"[SCREENSHOT] Window restore failed for {hwnd}: {exc}")

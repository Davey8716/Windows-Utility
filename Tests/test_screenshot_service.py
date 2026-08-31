from pathlib import Path

from resurface.features.desktop import screenshot_service
from resurface.features.desktop.screenshot_service import MonitorCapture, ScreenshotService


class FakeCrop:
    def __init__(self, owner, box): self.owner, self.box = owner, box
    def save(self, path):
        self.owner.saved.append((Path(path), self.box))
        Path(path).write_text("image", encoding="utf-8")


class FakeImage:
    size = (300, 100)
    def __init__(self): self.saved = []
    def crop(self, box): return FakeCrop(self, box)


def test_plan_detects_targets_stale_and_existing(monkeypatch, tmp_path):
    service = ScreenshotService()
    monkeypatch.setattr(service, "enumerate_monitors", lambda: (MonitorCapture(1, (0, 0, 100, 100)), MonitorCapture(2, (100, 0, 200, 100))))
    output_dir = tmp_path / "shots"
    output_dir.mkdir()
    (output_dir / "DesktopScreenshot_Monitor1.png").write_text("old", encoding="utf-8")
    stale = output_dir / "DesktopScreenshot_Monitor3.png"
    stale.write_text("old", encoding="utf-8")
    plan = service.build_capture_plan(output_dir / "desktop_screenshot.png")
    assert len(plan.target_paths) == 2 and plan.stale_paths == (stale,)
    assert set(plan.existing_paths) == {plan.target_paths[0], stale}


def test_capture_crops_negative_monitor_coordinates_and_removes_stale(monkeypatch, tmp_path):
    service = ScreenshotService()
    monkeypatch.setattr(service, "enumerate_monitors", lambda: (MonitorCapture(1, (-100, 0, 0, 100)), MonitorCapture(2, (0, 0, 200, 100))))
    plan = service.build_capture_plan(tmp_path / "shots" / "desktop_screenshot.png")
    stale = plan.save_dir / "DesktopScreenshot_Monitor9.png"
    stale.write_text("old", encoding="utf-8")
    plan = type(plan)(plan.monitors, plan.save_dir, plan.target_paths, (stale,), (stale,))
    image = FakeImage()
    monkeypatch.setattr(screenshot_service.ImageGrab, "grab", lambda **_: image)
    result = service.capture(plan)
    assert result.succeeded and not stale.exists()
    assert [box for _, box in image.saved] == [(0, 0, 100, 100), (100, 0, 300, 100)]


def test_capture_cleans_partial_outputs_after_failure(monkeypatch, tmp_path):
    service = ScreenshotService()
    monkeypatch.setattr(service, "enumerate_monitors", lambda: (MonitorCapture(1, (0, 0, 100, 100)), MonitorCapture(2, (100, 0, 200, 100))))
    plan = service.build_capture_plan(tmp_path / "shots" / "desktop_screenshot.png")

    class FailingImage(FakeImage):
        def crop(self, box):
            if box[0] == 100:
                raise OSError("crop failed")
            return super().crop(box)

    monkeypatch.setattr(screenshot_service.ImageGrab, "grab", lambda **_: FailingImage())
    result = service.capture(plan)
    assert not result.succeeded and "crop failed" in result.error
    assert not plan.target_paths[0].exists()


def test_minimize_and_restore_only_change_valid_window_state(monkeypatch):
    calls = []
    monkeypatch.setattr(screenshot_service.win32gui, "IsWindow", lambda hwnd: hwnd != 3)
    monkeypatch.setattr(screenshot_service.win32gui, "IsIconic", lambda hwnd: hwnd == 2)
    monkeypatch.setattr(
        screenshot_service.win32gui,
        "ShowWindow",
        lambda hwnd, command: calls.append((hwnd, command)),
    )
    service = ScreenshotService()
    service.minimize_windows((1, 2, 3))
    service.restore_windows((1, 2, 3))
    assert calls == [
        (1, screenshot_service.win32con.SW_MINIMIZE),
        (2, screenshot_service.win32con.SW_RESTORE),
    ]

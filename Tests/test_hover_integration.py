import json
from types import SimpleNamespace

from resurface.features.hover_window_controls import service as service_module
from resurface.features.hover_window_controls.migration import import_standalone_data
from resurface.features.hover_window_controls.service import (
    HoverWindowControlsService,
    normalized_dwell_ms,
)


class FakeController:
    def __init__(self, *_args, **_kwargs):
        self.calls = []

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")

    def suspend(self):
        self.calls.append("suspend")

    def resume(self):
        self.calls.append("resume")

    def set_dwell_ms(self, dwell_ms):
        self.calls.append(("dwell", dwell_ms))


class FakeWindowApi:
    def __init__(self, *args, **kwargs):
        self.cleared = False

    def clear_vision_cache(self):
        self.cleared = True


def _service(monkeypatch, tmp_path, state):
    monkeypatch.setattr(service_module, "VisionCache", lambda **_kwargs: object())
    monkeypatch.setattr(service_module, "CaptionVisionDetector", lambda _cache: object())
    monkeypatch.setattr(service_module, "Win32WindowApi", FakeWindowApi)
    monkeypatch.setattr(service_module, "TaskbarRestoreMonitor", lambda **_kwargs: object())
    monkeypatch.setattr(service_module, "HoverController", FakeController)
    monkeypatch.setattr(
        service_module,
        "InstalledAutoHotkeyRunner",
        lambda: SimpleNamespace(available=lambda: False),
    )
    saves = []
    service = HoverWindowControlsService(
        state, lambda value: saves.append(dict(value)), data_root=tmp_path
    )
    return service, saves


def test_dwell_normalization_clamps_and_steps():
    assert normalized_dwell_ms("bad") == 750
    assert normalized_dwell_ms(200) == 500
    assert normalized_dwell_ms(1126) == 1250
    assert normalized_dwell_ms(5000) == 2000


def test_service_owns_start_settings_and_idempotent_shutdown(monkeypatch, tmp_path):
    state = {
        "hover_window_controls_enabled": False,
        "hover_window_controls_dwell_ms": 750,
    }
    service, saves = _service(monkeypatch, tmp_path, state)
    emitted = []
    service.settings_changed.connect(lambda enabled, dwell: emitted.append((enabled, dwell)))

    service.start()
    service.start()
    assert service.controller.calls == ["start", "suspend"]

    service.set_enabled(True)
    service.set_dwell_ms(1126)
    assert service.controller.calls[-2:] == ["resume", ("dwell", 1250)]
    assert state["hover_window_controls_enabled"] is True
    assert state["hover_window_controls_dwell_ms"] == 1250
    assert emitted[-1] == (True, 1250)
    assert len(saves) == 2

    service.stop()
    service.stop()
    assert service.controller.calls.count("stop") == 1


def test_calibration_suspends_and_resumes_enabled_service(monkeypatch, tmp_path):
    state = {
        "hover_window_controls_enabled": True,
        "hover_window_controls_dwell_ms": 750,
    }
    service, _saves = _service(monkeypatch, tmp_path, state)
    dialogs = []

    class FakeDialog:
        def __init__(self, *_args, **_kwargs):
            dialogs.append(self)

        def exec(self):
            return 0

    monkeypatch.setattr(service_module, "CalibrationDialog", FakeDialog)
    for name in (
        "list_tracked_calibration_apps",
        "list_tracked_calibration_assets",
        "update_tracked_calibration",
        "delete_tracked_calibration_application",
    ):
        setattr(service.window_api, name, lambda *_args: [])

    service.start()
    service.calibrate()

    assert len(dialogs) == 1
    assert service.controller.calls[-2:] == ["suspend", "resume"]


def test_migration_imports_preferences_and_copies_valid_profiles(tmp_path):
    standalone = tmp_path / "Hover Window Controls"
    legacy = tmp_path / "No Click Min Max Restore"
    integrated = tmp_path / "Windows Resurface" / "hover-window-controls"
    standalone.mkdir()
    (standalone / "settings.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "hover": {"paused": True, "dwell_ms": 1126},
            }
        ),
        encoding="utf-8",
    )
    valid = standalone / "vision-cache" / "sample"
    valid.mkdir(parents=True)
    (valid / "manifest_abc.json").write_text(
        json.dumps(
            {
                "schema_version": 5,
                "application": {"friendly_name": "Sample"},
                "contexts": [],
            }
        ),
        encoding="utf-8",
    )
    (valid / "caption.jpg").write_bytes(b"jpeg")
    invalid = standalone / "vision-cache" / "broken"
    invalid.mkdir()
    (invalid / "manifest_bad.json").write_text("not json", encoding="utf-8")

    state = {}
    assert import_standalone_data(
        state,
        standalone_root=standalone,
        legacy_root=legacy,
        integrated_root=integrated,
    )

    assert state == {
        "hover_window_controls_enabled": False,
        "hover_window_controls_dwell_ms": 1250,
        "hover_window_controls_migration_completed": True,
    }
    assert (integrated / "vision-cache" / "sample" / "manifest_abc.json").is_file()
    assert not (integrated / "vision-cache" / "broken").exists()
    assert (valid / "manifest_abc.json").is_file()
    assert not import_standalone_data(
        state,
        standalone_root=standalone,
        legacy_root=legacy,
        integrated_root=integrated,
    )

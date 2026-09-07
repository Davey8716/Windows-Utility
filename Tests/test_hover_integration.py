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

    def set_caption_controls_enabled(self, enabled):
        self.calls.append(("caption", enabled))


class FakeWindowApi:
    def __init__(self, *args, **kwargs):
        self.init_kwargs = kwargs
        self.cleared = False
        self.exported_to = None
        self.imported_from = None

    def clear_vision_cache(self):
        self.cleared = True

    def export_all_data(self, destination, settings=None):
        self.exported_to = destination
        self.exported_settings = settings
        return SimpleNamespace(directory=destination / "Hover Export")

    def has_export_changes(self, _destination, _settings):
        return True

    def import_all_data(self, source):
        self.imported_from = source
        return SimpleNamespace(
            source_directory=source,
            settings={
                "schema_version": 1,
                "hover": {
                    "enabled": False,
                    "taskbar_restore_enabled": False,
                    "dwell_ms": 1250,
                },
            },
        )


def _service(monkeypatch, tmp_path, state):
    monkeypatch.setattr(service_module, "VisionCache", lambda **_kwargs: object())
    monkeypatch.setattr(
        service_module, "CaptionVisionDetector", lambda _cache: object()
    )
    monkeypatch.setattr(service_module, "Win32WindowApi", FakeWindowApi)
    monkeypatch.setattr(
        service_module,
        "TaskbarRestoreMonitor",
        lambda **_kwargs: SimpleNamespace(
            resume=lambda: None,
            suspend=lambda: None,
        ),
    )
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


def test_self_window_provider_is_packaged_only(monkeypatch):
    parent = SimpleNamespace(winId=lambda: 321)
    owner = SimpleNamespace(parent=lambda: parent)

    monkeypatch.setattr(
        service_module, "current_instance_scope", lambda: ("source", object())
    )
    assert HoverWindowControlsService._allowed_self_window_handle(owner) is None

    monkeypatch.setattr(
        service_module, "current_instance_scope", lambda: ("exe", object())
    )
    assert HoverWindowControlsService._allowed_self_window_handle(owner) == 321


def test_service_supplies_lazy_self_window_provider(monkeypatch, tmp_path):
    service, _saves = _service(monkeypatch, tmp_path, {})

    provider = service.window_api.init_kwargs["allowed_self_hwnd_provider"]
    assert callable(provider)
    assert provider() is None


def test_service_owns_start_settings_and_idempotent_shutdown(monkeypatch, tmp_path):
    state = {
        "hover_window_controls_enabled": False,
        "hover_window_controls_dwell_ms": 750,
    }
    service, saves = _service(monkeypatch, tmp_path, state)
    emitted = []
    service.settings_changed.connect(
        lambda enabled, taskbar, dwell: emitted.append(
            (enabled, taskbar, dwell)
        )
    )

    service.start()
    service.start()
    assert service.controller.calls == ["start", ("caption", False)]

    service.set_enabled(True)
    service.set_dwell_ms(1126)
    assert service.controller.calls[-2:] == [("caption", True), ("dwell", 1250)]
    assert state["hover_window_controls_enabled"] is True
    assert state["hover_window_controls_dwell_ms"] == 1250
    assert emitted[-1] == (True, True, 1250)
    assert len(saves) == 2

    service.stop()
    service.stop()
    assert service.controller.calls.count("stop") == 1


def test_calibration_uses_live_capture_and_resumes(monkeypatch, tmp_path):
    state = {
        "hover_window_controls_enabled": True,
        "hover_window_controls_dwell_ms": 750,
    }
    service, _saves = _service(monkeypatch, tmp_path, state)
    dialogs = []

    class FakeDialog:
        def __init__(self, *_args, **kwargs):
            dialogs.append(kwargs)

        def exec(self):
            return 0

    monkeypatch.setattr(service_module, "CalibrationDialog", FakeDialog)
    for name in (
        "list_tracked_calibration_apps",
        "list_tracked_calibration_assets",
        "update_tracked_calibration",
        "list_calibration_targets",
        "capture_vision_calibration",
        "save_vision_calibration",
    ):
        setattr(service.window_api, name, lambda *_args: [])

    service.start()
    service.calibrate()

    assert len(dialogs) == 1
    assert set(dialogs[0]) >= {
        "target_provider",
        "capture_provider",
        "save_provider",
        "clear_provider",
    }
    assert service.controller.calls[-3:] == [
        "suspend",
        "resume",
        ("caption", True),
    ]


def test_export_writes_integrated_settings_and_resumes(monkeypatch, tmp_path):
    data_root = tmp_path / "integrated"
    state = {
        "hover_window_controls_enabled": True,
        "hover_window_controls_dwell_ms": 1000,
    }
    service, _saves = _service(monkeypatch, data_root, state)
    destination = tmp_path / "exports"

    service.start()
    result = service.export_all_data(destination)

    assert result.directory == destination / "Hover Export"
    assert service.window_api.exported_to == destination
    assert service.controller.calls[-3:] == [
        "suspend",
        "resume",
        ("caption", True),
    ]
    assert json.loads((data_root / "settings.json").read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "hover": {
            "enabled": True,
            "taskbar_restore_enabled": True,
            "dwell_ms": 1000,
        },
    }


def test_import_applies_settings_persists_and_resumes(monkeypatch, tmp_path):
    state = {
        "hover_window_controls_enabled": True,
        "hover_taskbar_restore_enabled": True,
        "hover_window_controls_dwell_ms": 750,
    }
    service, saves = _service(monkeypatch, tmp_path / "active", state)
    source = tmp_path / "backup"
    service.start()

    result = service.import_all_data(source)

    assert result.source_directory == source
    assert service.window_api.imported_from == source
    assert state["hover_window_controls_enabled"] is False
    assert state["hover_taskbar_restore_enabled"] is False
    assert state["hover_window_controls_dwell_ms"] == 1250
    assert saves[-1] == state
    assert service.controller.calls[-4:] == [
        "suspend",
        ("dwell", 1250),
        "resume",
        ("caption", False),
    ]


def test_service_runs_taskbar_restoration_independently(monkeypatch, tmp_path):
    state = {
        "hover_window_controls_enabled": True,
        "hover_taskbar_restore_enabled": True,
    }
    service, _saves = _service(monkeypatch, tmp_path, state)
    monitor_calls = []
    service.taskbar_monitor = SimpleNamespace(
        resume=lambda: monitor_calls.append("resume"),
        suspend=lambda: monitor_calls.append("suspend"),
    )
    service.taskbar_restore_available = True

    service.start()
    service.set_enabled(False)
    service.set_taskbar_restore_enabled(False)
    service.set_taskbar_restore_enabled(True)

    assert state["hover_window_controls_enabled"] is False
    assert state["hover_taskbar_restore_enabled"] is True
    assert service.controller.calls[-1] == ("caption", False)
    assert monitor_calls == ["resume", "suspend", "resume"]


def test_clear_learned_buttons_is_forwarded(monkeypatch, tmp_path):
    service, _saves = _service(monkeypatch, tmp_path, {})

    service.clear_learned_buttons()

    assert service.window_api.cleared is True
    assert service.taskbar_restore_available is False


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

    state = {"theme_dark": True}
    assert import_standalone_data(
        state,
        standalone_root=standalone,
        legacy_root=legacy,
        integrated_root=integrated,
    )

    assert state == {
        "theme_dark": True,
        "hover_window_controls_enabled": False,
        "hover_window_controls_dwell_ms": 1250,
        "hover_window_controls_migration_completed": True,
    }
    assert (integrated / "vision-cache" / "sample" / "caption.jpg").is_file()
    assert not (integrated / "vision-cache" / "broken").exists()
    assert (valid / "manifest_abc.json").is_file()
    assert not import_standalone_data(
        state,
        standalone_root=standalone,
        legacy_root=legacy,
        integrated_root=integrated,
    )


def test_migration_ignores_corrupt_settings_and_preserves_defaults(tmp_path):
    standalone = tmp_path / "Hover Window Controls"
    standalone.mkdir()
    (standalone / "settings.json").write_text("not json", encoding="utf-8")
    state = {
        "hover_window_controls_enabled": True,
        "hover_window_controls_dwell_ms": 750,
    }

    assert import_standalone_data(
        state,
        standalone_root=standalone,
        legacy_root=tmp_path / "legacy",
        integrated_root=tmp_path / "integrated",
    )
    assert state["hover_window_controls_enabled"] is True
    assert state["hover_window_controls_dwell_ms"] == 750
    assert state["hover_window_controls_migration_completed"] is True

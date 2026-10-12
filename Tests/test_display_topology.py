import ctypes
from types import SimpleNamespace

from resurface.features.system import display_topology


def test_windows_display_structures_match_sdk_sizes():
    assert ctypes.sizeof(display_topology.PathInfo) == 72
    assert ctypes.sizeof(display_topology.ModeInfo) == 64
    assert ctypes.sizeof(display_topology.SourceDeviceName) == 84


def test_disconnect_and_wake_restore_original_paths(tmp_path):
    paths = (display_topology.PathInfo * 3)()
    for path in paths:
        path.flags = display_topology.DISPLAYCONFIG_PATH_ACTIVE
    modes = (display_topology.ModeInfo * 1)()
    calls = []

    def set_config(path_count, submitted_paths, mode_count, _modes, flags):
        calls.append((path_count, [p.flags for p in submitted_paths] if submitted_paths else None, mode_count, flags))
        return 0

    controller = display_topology.DisplayTopology.__new__(
        display_topology.DisplayTopology
    )
    controller._user32 = SimpleNamespace(SetDisplayConfig=set_config)
    controller._saved = None
    controller._marker_path = tmp_path / "display_recovery.txt"
    controller._active_configuration = lambda: (paths, modes)
    for index, path in enumerate(paths):
        path.source.id = index
    controller._source_name = lambda path: rf"\\.\DISPLAY{path.source.id + 1}"

    device = r"\\.\DISPLAY3"
    controller.disconnect(device)
    assert controller.is_disconnected(device)
    assert controller._marker_path.read_text(encoding="utf-8") == device
    controller.wake(device)
    assert not controller.is_disconnected(device)
    assert not controller._marker_path.exists()
    assert calls == [
        (3, [1, 1, 0], 1, display_topology.SDC_VALIDATE | display_topology.SDC_USE_SUPPLIED_DISPLAY_CONFIG),
        (3, [1, 1, 0], 1, display_topology.SDC_APPLY | display_topology.SDC_USE_SUPPLIED_DISPLAY_CONFIG),
        (3, [1, 1, 1], 1, display_topology.SDC_APPLY | display_topology.SDC_USE_SUPPLIED_DISPLAY_CONFIG),
    ]


def test_restart_recovery_restores_saved_windows_layout(tmp_path, monkeypatch):
    class Function:
        def __init__(self, callback=None):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args) if self.callback else 0

    calls = []
    api = SimpleNamespace(
        GetDisplayConfigBufferSizes=Function(),
        QueryDisplayConfig=Function(),
        DisplayConfigGetDeviceInfo=Function(),
        SetDisplayConfig=Function(
            lambda count, paths, mode_count, modes, flags: calls.append(
                (count, paths, mode_count, modes, flags)
            ) or 0
        ),
    )
    marker = tmp_path / "display_recovery.txt"
    marker.write_text(r"\\.\DISPLAY3", encoding="utf-8")
    monkeypatch.setattr(display_topology.ctypes, "WinDLL", lambda *_args: api)
    monkeypatch.setattr(
        display_topology, "get_config_path", lambda: tmp_path / "app_state.json"
    )

    controller = display_topology.DisplayTopology()
    assert controller.disconnected_device() is None
    assert not marker.exists()
    assert calls == [
        (
            0, None, 0, None,
            display_topology.SDC_APPLY | display_topology.SDC_USE_DATABASE_CURRENT,
        )
    ]

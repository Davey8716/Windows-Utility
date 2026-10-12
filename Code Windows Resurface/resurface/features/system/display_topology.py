"""Temporary Windows display disconnection for monitors without DDC power control."""

from __future__ import annotations

import atexit
import ctypes
from ctypes import wintypes
from resurface.core.state_manager import get_config_path


QDC_ONLY_ACTIVE_PATHS = 0x00000002
SDC_USE_SUPPLIED_DISPLAY_CONFIG = 0x00000020
SDC_VALIDATE = 0x00000040
SDC_APPLY = 0x00000080
SDC_USE_DATABASE_CURRENT = 0x0000000F
DISPLAYCONFIG_PATH_ACTIVE = 0x00000001
DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME = 1
ERROR_INSUFFICIENT_BUFFER = 122


class Luid(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.LONG)]


class Rational(ctypes.Structure):
    _fields_ = [("numerator", wintypes.UINT), ("denominator", wintypes.UINT)]


class PathSource(ctypes.Structure):
    _fields_ = [
        ("adapter_id", Luid),
        ("id", wintypes.UINT),
        ("mode_index", wintypes.UINT),
        ("status_flags", wintypes.UINT),
    ]


class PathTarget(ctypes.Structure):
    _fields_ = [
        ("adapter_id", Luid),
        ("id", wintypes.UINT),
        ("mode_index", wintypes.UINT),
        ("output_technology", wintypes.UINT),
        ("rotation", wintypes.UINT),
        ("scaling", wintypes.UINT),
        ("refresh_rate", Rational),
        ("scanline_ordering", wintypes.UINT),
        ("target_available", wintypes.BOOL),
        ("status_flags", wintypes.UINT),
    ]


class PathInfo(ctypes.Structure):
    _fields_ = [
        ("source", PathSource),
        ("target", PathTarget),
        ("flags", wintypes.UINT),
    ]


class ModeInfo(ctypes.Structure):
    # The largest union member, DISPLAYCONFIG_TARGET_MODE, is 48 bytes.
    _fields_ = [
        ("type", wintypes.UINT),
        ("id", wintypes.UINT),
        ("adapter_id", Luid),
        ("mode", ctypes.c_byte * 48),
    ]


class DeviceInfoHeader(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.UINT),
        ("size", wintypes.UINT),
        ("adapter_id", Luid),
        ("id", wintypes.UINT),
    ]


class SourceDeviceName(ctypes.Structure):
    _fields_ = [("header", DeviceInfoHeader), ("view_name", wintypes.WCHAR * 32)]


class DisplayTopology:
    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32.dll")
        self._configure_api()
        self._saved: tuple[str, object, object] | None = None
        self._marker_path = get_config_path().with_name("display_recovery.txt")
        if self._marker_path.exists():
            result = self._restore_database()
            if result == 0:
                self._clear_marker()
        atexit.register(self.restore_on_exit)

    def _write_marker(self, device: str) -> None:
        self._marker_path.parent.mkdir(parents=True, exist_ok=True)
        self._marker_path.write_text(device, encoding="utf-8")

    def _clear_marker(self) -> None:
        self._marker_path.unlink(missing_ok=True)

    def _restore_database(self) -> int:
        return self._user32.SetDisplayConfig(
            0, None, 0, None, SDC_APPLY | SDC_USE_DATABASE_CURRENT
        )

    def _configure_api(self) -> None:
        api = self._user32
        api.GetDisplayConfigBufferSizes.argtypes = [
            wintypes.UINT, ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT)
        ]
        api.GetDisplayConfigBufferSizes.restype = wintypes.LONG
        api.QueryDisplayConfig.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(PathInfo),
            ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(ModeInfo),
            ctypes.c_void_p,
        ]
        api.QueryDisplayConfig.restype = wintypes.LONG
        api.DisplayConfigGetDeviceInfo.argtypes = [ctypes.POINTER(DeviceInfoHeader)]
        api.DisplayConfigGetDeviceInfo.restype = wintypes.LONG
        api.SetDisplayConfig.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(PathInfo),
            wintypes.UINT,
            ctypes.POINTER(ModeInfo),
            wintypes.UINT,
        ]
        api.SetDisplayConfig.restype = wintypes.LONG

    def _active_configuration(self) -> tuple[object, object]:
        for _ in range(3):
            path_count = wintypes.UINT()
            mode_count = wintypes.UINT()
            result = self._user32.GetDisplayConfigBufferSizes(
                QDC_ONLY_ACTIVE_PATHS,
                ctypes.byref(path_count),
                ctypes.byref(mode_count),
            )
            if result:
                raise OSError(result, "Could not inspect Windows display layout")
            paths = (PathInfo * path_count.value)()
            modes = (ModeInfo * mode_count.value)()
            result = self._user32.QueryDisplayConfig(
                QDC_ONLY_ACTIVE_PATHS,
                ctypes.byref(path_count),
                paths,
                ctypes.byref(mode_count),
                modes,
                None,
            )
            if result == ERROR_INSUFFICIENT_BUFFER:
                continue
            if result:
                raise OSError(result, "Could not inspect Windows display layout")
            active_paths = (PathInfo * path_count.value)()
            active_modes = (ModeInfo * mode_count.value)()
            ctypes.memmove(active_paths, paths, ctypes.sizeof(active_paths))
            ctypes.memmove(active_modes, modes, ctypes.sizeof(active_modes))
            return active_paths, active_modes
        raise RuntimeError("The Windows display layout changed while reading it")

    def _source_name(self, path: PathInfo) -> str:
        name = SourceDeviceName()
        name.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME
        name.header.size = ctypes.sizeof(name)
        name.header.adapter_id = path.source.adapter_id
        name.header.id = path.source.id
        result = self._user32.DisplayConfigGetDeviceInfo(ctypes.byref(name.header))
        if result:
            raise OSError(result, "Could not identify a Windows display path")
        return name.view_name

    def validate_disconnect(self, device: str) -> int:
        paths, modes = self._active_configuration()
        changed = self._without_device(paths, device)
        return self._user32.SetDisplayConfig(
            len(changed), changed, len(modes), modes,
            SDC_VALIDATE | SDC_USE_SUPPLIED_DISPLAY_CONFIG,
        )

    def _without_device(self, paths, device: str):
        changed = (PathInfo * len(paths))()
        ctypes.memmove(changed, paths, ctypes.sizeof(changed))
        matches = 0
        for index, path in enumerate(paths):
            if self._source_name(path).casefold() == device.casefold():
                changed[index].flags &= ~DISPLAYCONFIG_PATH_ACTIVE
                matches += 1
        if matches != 1:
            raise RuntimeError("Expected one active path for this monitor")
        if len(paths) <= 1:
            raise RuntimeError("Cannot disconnect the only active display")
        return changed

    def disconnect(self, device: str) -> None:
        if self._saved is not None:
            if self._saved[0].casefold() == device.casefold():
                return
            raise RuntimeError("Wake the disconnected monitor first")
        paths, modes = self._active_configuration()
        changed = self._without_device(paths, device)
        validation = self._user32.SetDisplayConfig(
            len(changed), changed, len(modes), modes,
            SDC_VALIDATE | SDC_USE_SUPPLIED_DISPLAY_CONFIG,
        )
        if validation:
            raise OSError(validation, "Windows cannot temporarily disconnect this monitor")
        self._write_marker(device)
        result = self._user32.SetDisplayConfig(
            len(changed), changed, len(modes), modes,
            SDC_APPLY | SDC_USE_SUPPLIED_DISPLAY_CONFIG,
        )
        if result:
            self._clear_marker()
            raise OSError(result, "Windows could not disconnect this monitor")
        self._saved = (device, paths, modes)

    def is_disconnected(self, device: str) -> bool:
        return self._saved is not None and self._saved[0].casefold() == device.casefold()

    def disconnected_device(self) -> str | None:
        if self._saved:
            return self._saved[0]
        if self._marker_path.exists():
            return self._marker_path.read_text(encoding="utf-8")
        return None

    def wake(self, device: str) -> None:
        if self._saved is None:
            result = self._restore_database()
            if result:
                raise OSError(result, "Windows could not restore its saved display layout")
            self._clear_marker()
            return
        if not self.is_disconnected(device):
            return
        _, paths, modes = self._saved
        result = self._user32.SetDisplayConfig(
            len(paths), paths, len(modes), modes,
            SDC_APPLY | SDC_USE_SUPPLIED_DISPLAY_CONFIG,
        )
        if result:
            raise OSError(result, "Windows could not restore this monitor")
        self._saved = None
        self._clear_marker()

    def restore_on_exit(self) -> None:
        if self._saved is None:
            return
        try:
            self.wake(self._saved[0])
        except OSError:
            # The last saved Windows topology is a recovery path after a driver reset.
            if self._restore_database() == 0:
                self._clear_marker()


_topology: DisplayTopology | None = None


def topology() -> DisplayTopology:
    global _topology
    if _topology is None:
        _topology = DisplayTopology()
    return _topology

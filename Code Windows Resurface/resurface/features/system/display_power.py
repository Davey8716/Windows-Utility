"""Windows display power controls used by the Displays page."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

import win32api
import win32con
import win32gui

from resurface.features.system.display_topology import topology


POWER_VCP_CODE = 0xD6
POWER_ON = 0x01
POWER_STANDBY = 0x02
POWER_OFF = 0x04
OFF_MODE_HARDWARE_IDS = frozenset({"ACR0424"})
WINDOWS_DISCONNECT_HARDWARE_IDS = frozenset({"IVM61A1"})


class PhysicalMonitor(ctypes.Structure):
    _fields_ = [
        ("handle", wintypes.HANDLE),
        ("description", wintypes.WCHAR * 128),
    ]


@dataclass(frozen=True)
class Display:
    device: str
    label: str


def _hardware_id(device: str) -> str:
    try:
        device_id = win32api.EnumDisplayDevices(device, 0).DeviceID
    except Exception as error:
        raise RuntimeError("Could not identify this monitor") from error
    parts = str(device_id).upper().split("\\")
    return parts[1] if len(parts) > 1 and parts[0] == "MONITOR" else ""


def _standby_value(device: str) -> int:
    """Choose the observed working mode by physical monitor identity."""
    return POWER_OFF if _hardware_id(device) in OFF_MODE_HARDWARE_IDS else POWER_STANDBY


def connected_displays() -> list[Display]:
    """List active logical displays, using the same numbering as Monitor Rules."""
    displays = []
    for index, (handle, *_rest) in enumerate(win32api.EnumDisplayMonitors(), 1):
        info = win32api.GetMonitorInfo(handle)
        left, top, right, bottom = info["Monitor"]
        label = f"Monitor {index} - {right - left} x {bottom - top}"
        if info.get("Flags", 0) & 1:
            label += " (Primary)"
        displays.append(Display(str(info["Device"]), label))
    device = topology().disconnected_device()
    if device and device.casefold() not in {item.device.casefold() for item in displays}:
        number = device.rsplit("DISPLAY", 1)[-1]
        displays.append(Display(device, f"Monitor {number} - disconnected (iiyama)"))
    return displays


def set_display_power(device: str, *, awake: bool) -> None:
    """Control one display through DDC/CI or a temporary Windows disconnect."""
    if _hardware_id(device) in WINDOWS_DISCONNECT_HARDWARE_IDS:
        if awake:
            if topology().is_disconnected(device) or not any(
                win32api.GetMonitorInfo(handle).get("Device", "").casefold()
                == device.casefold()
                for handle, *_ in win32api.EnumDisplayMonitors()
            ):
                topology().wake(device)
        else:
            topology().disconnect(device)
        return

    dxva2 = ctypes.WinDLL("Dxva2.dll", use_last_error=True)
    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)
    ]
    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
    dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(PhysicalMonitor)
    ]
    dxva2.GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
    dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, wintypes.BYTE, wintypes.DWORD]
    dxva2.SetVCPFeature.restype = wintypes.BOOL
    dxva2.DestroyPhysicalMonitors.argtypes = [
        wintypes.DWORD, ctypes.POINTER(PhysicalMonitor)
    ]
    dxva2.DestroyPhysicalMonitors.restype = wintypes.BOOL

    for handle, *_rest in win32api.EnumDisplayMonitors():
        info = win32api.GetMonitorInfo(handle)
        if str(info.get("Device", "")).casefold() != device.casefold():
            continue
        count = wintypes.DWORD()
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(int(handle), ctypes.byref(count)):
            raise OSError(ctypes.get_last_error(), "Could not inspect this monitor")
        if not count.value:
            raise RuntimeError("No physical monitor is available for this display")
        monitors = (PhysicalMonitor * count.value)()
        if not dxva2.GetPhysicalMonitorsFromHMONITOR(
            int(handle), count.value, monitors
        ):
            raise OSError(ctypes.get_last_error(), "Could not open this monitor")
        try:
            value = POWER_ON if awake else _standby_value(device)
            for monitor in monitors:
                if not dxva2.SetVCPFeature(monitor.handle, POWER_VCP_CODE, value):
                    raise OSError(
                        ctypes.get_last_error(),
                        "This monitor did not accept the DDC/CI power command",
                    )
        finally:
            dxva2.DestroyPhysicalMonitors(count.value, monitors)
        return
    raise RuntimeError("This display is no longer connected")


def turn_off_all_displays() -> None:
    """Ask Windows to blank the display output without sleeping the PC."""
    win32gui.SendMessageTimeout(
        win32con.HWND_BROADCAST,
        win32con.WM_SYSCOMMAND,
        win32con.SC_MONITORPOWER,
        2,
        win32con.SMTO_ABORTIFHUNG,
        1_000,
    )

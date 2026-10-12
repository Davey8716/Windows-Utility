import ctypes
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from resurface.features.system import display_power
from resurface.ui.pages.display_power_page import DisplayPowerPage


def test_displays_page_lists_each_monitor_and_dispatches_its_device(monkeypatch):
    app = QApplication.instance() or QApplication([])
    displays = [
        display_power.Display(r"\\.\DISPLAY1", "Monitor 1 (Primary)"),
        display_power.Display(r"\\.\DISPLAY2", "Monitor 2"),
    ]
    calls = []
    monkeypatch.setattr(display_power, "connected_displays", lambda: displays)
    monkeypatch.setattr(
        display_power,
        "set_display_power",
        lambda device, *, awake: calls.append((device, awake)),
    )
    page = DisplayPowerPage(lambda *_args: None)
    try:
        assert page.monitor_layout.count() == 4
        first_row = page.monitor_layout.itemAt(1).widget()
        second_row = page.monitor_layout.itemAt(3).widget()
        first_row.layout().itemAt(0).widget().click()
        second_row.layout().itemAt(1).widget().click()
        assert calls == [
            (r"\\.\DISPLAY1", False),
            (r"\\.\DISPLAY2", True),
        ]
    finally:
        page.deleteLater()
        app.processEvents()


def test_connected_displays_uses_active_windows_monitors(monkeypatch):
    monkeypatch.setattr(
        display_power.win32api,
        "EnumDisplayMonitors",
        lambda: [(100, None, None), (200, None, None)],
    )
    info = {
        100: {"Monitor": (0, 0, 1920, 1080), "Flags": 1, "Device": "A"},
        200: {"Monitor": (1920, 0, 4480, 1440), "Flags": 0, "Device": "B"},
    }
    monkeypatch.setattr(display_power.win32api, "GetMonitorInfo", info.__getitem__)
    monkeypatch.setattr(
        display_power.win32api,
        "EnumDisplayDevices",
        lambda _device, _index: (_ for _ in ()).throw(OSError("end")),
    )
    monkeypatch.setattr(
        display_power,
        "topology",
        lambda: SimpleNamespace(disconnected_device=lambda: None),
    )
    assert display_power.connected_displays() == [
        display_power.Display("A", "Monitor 1 - 1920 x 1080 (Primary)"),
        display_power.Display("B", "Monitor 2 - 2560 x 1440"),
    ]


@pytest.mark.parametrize(
    ("awake", "expected"),
    [(False, display_power.POWER_STANDBY), (True, display_power.POWER_ON)],
)
def test_individual_power_command_closes_physical_monitor_handles(
    monkeypatch, awake, expected
):
    calls = []

    class Function:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    def count_monitors(_handle, count):
        ctypes.cast(count, ctypes.POINTER(ctypes.c_ulong))[0] = 1
        return True

    def get_monitors(_handle, _count, monitors):
        monitors[0].handle = 123
        return True

    fake_dxva2 = type("FakeDxva2", (), {})()
    fake_dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR = Function(count_monitors)
    fake_dxva2.GetPhysicalMonitorsFromHMONITOR = Function(get_monitors)
    fake_dxva2.SetVCPFeature = Function(
        lambda handle, code, value: calls.append(("set", handle, code, value)) or True
    )
    fake_dxva2.DestroyPhysicalMonitors = Function(
        lambda count, _monitors: calls.append(("close", count)) or True
    )
    monkeypatch.setattr(display_power.ctypes, "WinDLL", lambda *_args, **_kwargs: fake_dxva2)
    monkeypatch.setattr(display_power.win32api, "EnumDisplayMonitors", lambda: [(100, None, None)])
    monkeypatch.setattr(
        display_power.win32api,
        "GetMonitorInfo",
        lambda _handle: {"Device": "DISPLAY1"},
    )
    monkeypatch.setattr(
        display_power.win32api,
        "EnumDisplayDevices",
        lambda _device, _index: SimpleNamespace(DeviceID=r"MONITOR\ACR0975\instance"),
    )

    display_power.set_display_power("display1", awake=awake)
    assert calls == [
        ("set", 123, display_power.POWER_VCP_CODE, expected),
        ("close", 1),
    ]


@pytest.mark.parametrize(
    ("hardware_id", "expected"),
    [
        ("ACR0975", display_power.POWER_STANDBY),
        ("ACR0424", display_power.POWER_OFF),
        ("NEW1234", display_power.POWER_STANDBY),
    ],
)
def test_standby_mode_follows_hardware_id_not_screen_number(
    monkeypatch, hardware_id, expected
):
    monkeypatch.setattr(
        display_power.win32api,
        "EnumDisplayDevices",
        lambda _device, _index: SimpleNamespace(
            DeviceID=rf"MONITOR\{hardware_id}\instance"
        ),
    )
    assert display_power._standby_value(r"\\.\DISPLAY3") == expected


def test_displays_page_reports_failed_wake_and_all_screens_action(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        display_power,
        "connected_displays",
        lambda: [display_power.Display("DISPLAY1", "Monitor 1")],
    )
    calls = []

    def fail_wake(_device, *, awake):
        assert awake
        raise OSError("DDC/CI unavailable")

    monkeypatch.setattr(display_power, "set_display_power", fail_wake)
    monkeypatch.setattr(
        display_power,
        "turn_off_all_displays",
        lambda: calls.append("all off"),
    )
    page = DisplayPowerPage(lambda *_args: None)
    try:
        wake = page.monitor_layout.itemAt(1).widget().layout().itemAt(1).widget()
        wake.click()
        assert "Individual control failed" in page.status.text()
        assert "physical power button" in page.status.text()
        page._send_all_off()
        assert calls == ["all off"]
    finally:
        page.deleteLater()


def test_iiyama_uses_windows_disconnect_and_wake(monkeypatch):
    events = []

    class FakeTopology:
        def is_disconnected(self, _device):
            return True

        def disconnect(self, device):
            events.append(("disconnect", device))

        def wake(self, device):
            events.append(("wake", device))

    monkeypatch.setattr(display_power, "topology", lambda: FakeTopology())
    monkeypatch.setattr(
        display_power.win32api,
        "EnumDisplayDevices",
        lambda _device, _index: SimpleNamespace(DeviceID=r"MONITOR\IVM61A1\instance"),
    )
    device = r"\\.\DISPLAY3"
    display_power.set_display_power(device, awake=False)
    display_power.set_display_power(device, awake=True)
    assert events == [("disconnect", device), ("wake", device)]


def test_disconnected_iiyama_keeps_one_wake_row(monkeypatch):
    device = r"\\.\DISPLAY3"
    monkeypatch.setattr(
        display_power.win32api,
        "EnumDisplayMonitors",
        lambda: [(1, None, None), (2, None, None)],
    )
    monkeypatch.setattr(
        display_power.win32api,
        "GetMonitorInfo",
        lambda handle: {
            "Device": rf"\\.\DISPLAY{handle}",
            "Monitor": (0, 0, 1920, 1080),
        },
    )
    monkeypatch.setattr(
        display_power,
        "topology",
        lambda: SimpleNamespace(disconnected_device=lambda: device),
    )
    displays = display_power.connected_displays()
    assert len(displays) == 3
    assert displays[-1] == display_power.Display(
        device, "Monitor 3 - disconnected (iiyama)"
    )

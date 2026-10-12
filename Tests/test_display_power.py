import ctypes
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from resurface.features.system import display_power
from resurface.ui import styles
from resurface.ui.navigation_shell import NavigationShell
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


@pytest.mark.parametrize("styled", [False, True])
def test_monitor_buttons_keep_full_height_after_font_and_monitor_refresh(
    monkeypatch, styled
):
    app = QApplication.instance() or QApplication([])
    original_font = QFont(app.font())
    displays = [
        display_power.Display(
            f"DISPLAY{number}", f"Monitor {number} - 1920 x 1080"
        )
        for number in range(1, 4)
    ]
    monkeypatch.setattr(display_power, "connected_displays", lambda: list(displays))
    shell = NavigationShell(
        app_version="test", sidebar_width=220, page_title_top_inset=40
    )
    if styled:
        shell.setStyleSheet(styles.window_style())
    page = DisplayPowerPage(lambda *_args: None, shell.content_parent("display_power"))
    shell.mount_content("display_power", page)
    shell.finish_page_layouts()
    shell.resize(821, 533)
    shell.show()
    shell.navigate_to("display_power")
    try:
        app.processEvents()
        scroll = shell.page_scroll_areas["display_power"]
        last_row = page.monitor_layout.itemAt(5).widget()
        assert last_row.mapTo(page, QPoint(0, last_row.height())).y() <= page.height()
        assert last_row.mapTo(scroll.viewport(), QPoint(0, last_row.height())).y() <= (
            scroll.viewport().height()
        )
        shell.resize(821, 320)
        font = QFont(original_font)
        font.setPointSize(max(14, original_font.pointSize() + 5))
        app.setFont(font)
        app.processEvents()
        app.processEvents()

        def assert_full_rows():
            for index in range(1, page.monitor_layout.count(), 2):
                row = page.monitor_layout.itemAt(index).widget()
                for button_index in range(2):
                    button = row.layout().itemAt(button_index).widget()
                    assert row.height() >= button.height() == 34
                    assert button.geometry().bottom() < row.height()
                assert row.mapTo(
                    page.monitor_container, QPoint(0, row.height())
                ).y() <= page.monitor_container.height()
                assert row.mapTo(page, QPoint(0, row.height())).y() <= page.height()
            assert page.monitor_container.height() >= page.monitor_container.sizeHint().height()
            assert page.height() >= page.sizeHint().height()

        scrollbar = scroll.verticalScrollBar()

        def assert_last_row_scrolls_into_view():
            assert scrollbar.maximum() > 0
            scrollbar.setValue(scrollbar.maximum())
            app.processEvents()
            last_row = page.monitor_layout.itemAt(page.monitor_layout.count() - 1).widget()
            assert last_row.mapTo(scroll.viewport(), QPoint(0, last_row.height())).y() <= (
                scroll.viewport().height()
            )

        assert_full_rows()
        assert_last_row_scrolls_into_view()

        page.refresh()
        app.processEvents()
        assert_full_rows()

        displays[:] = displays[:1]
        page.refresh()
        app.processEvents()
        assert page.monitor_layout.count() == 2
        assert_full_rows()

        displays[:] = [
            display_power.Display(f"DISPLAY{number}", f"Monitor {number}")
            for number in range(1, 5)
        ]
        page.refresh()
        app.processEvents()
        assert page.monitor_layout.count() == 8
        assert_full_rows()
        assert_last_row_scrolls_into_view()

        page.refresh()
        app.processEvents()
        assert page.monitor_layout.count() == 8
        assert_full_rows()

        displays.clear()
        page.refresh()
        app.processEvents()
        assert page.monitor_layout.count() == 0
        assert page.monitor_container.minimumHeight() == 0
        assert "No active monitors" in page.status.text()

        def fail_to_list():
            raise OSError("Display enumeration failed")

        monkeypatch.setattr(display_power, "connected_displays", fail_to_list)
        page.refresh()
        app.processEvents()
        assert page.monitor_layout.count() == 0
        assert page.monitor_container.minimumHeight() == 0
        assert "Display enumeration failed" in page.status.text()
    finally:
        app.setFont(original_font)
        shell.deleteLater()
        app.processEvents()

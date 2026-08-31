from resurface.features.drives.drive_reminder_logic import (
    DriveChanges,
    DriveReminderPolicy,
)
from resurface.features.drives.drive_service import DriveInfo
from resurface.ui.controllers.external_drives import ExternalDriveController


class FakeSignal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback


class FakeMonitor:
    def __init__(self):
        self.snapshot_changed = FakeSignal()
        self.is_running = False
        self.started = False
        self.stopped = False
        self.scan_requests = 0

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def request_scan(self):
        self.scan_requests += 1


class FakePage:
    def __init__(self):
        self.drive_open_requested = FakeSignal()
        self.context_menu_requested = FakeSignal()
        self.drives = ()

    def set_connected_drives(self, drives):
        self.drives = tuple(drives)


class FakeWindow:
    def __init__(self):
        self._overview_connected_drives = set()
        self.messages = []
        self.warnings = []

    def _message_box_icon(self, name):
        return name

    def _show_timed_message(self, icon, title, text, **options):
        self.messages.append((icon, title, text, options))

    def _show_acknowledged_message(self, icon, title, text, **options):
        self.warnings.append((icon, title, text, options))


class FakeDriveService:
    def __init__(self, paths=()):
        self.paths = tuple(paths)

    def list_drives(self):
        return [DriveInfo(path, 100, 40, 60, True) for path in self.paths]


def make_controller(paths=()):
    window = FakeWindow()
    page = FakePage()
    monitor = FakeMonitor()
    overview_refreshes = []
    controller = ExternalDriveController(
        window=window,
        state={"usb_idle_enabled": True, "usb_plug_notify_mode": "on"},
        drive_service=FakeDriveService(paths),
        monitor=monitor,
        policy=DriveReminderPolicy(),
        page=lambda: page,
        drive_space_page=lambda: None,
        refresh_overview=lambda: overview_refreshes.append(True),
        run_with_optional_minimize=lambda callback: callback(),
    )
    return controller, window, page, monitor, overview_refreshes


def test_snapshot_updates_page_overview_and_connection_notification():
    controller, window, page, _monitor, overview_refreshes = make_controller()

    controller._handle_snapshot(
        DriveChanges(current=("E:\\",), added=("E:\\",))
    )

    assert page.drives == ("E:\\",)
    assert window._overview_connected_drives == {"E:\\"}
    assert overview_refreshes == [True]
    assert window.messages[0][1:3] == (
        "Drive Connected",
        "External drive connected:\nE:\\",
    )


def test_confirmation_without_connected_drives_runs_action_immediately():
    controller, _window, _page, _monitor, _refreshes = make_controller()
    actions = []

    controller.confirm_power_action("Shutdown", lambda: actions.append(True))

    assert actions == [True]


def test_end_session_uses_fresh_synchronous_snapshot_and_blocks(monkeypatch):
    controller, window, _page, _monitor, _refreshes = make_controller(["E:\\"])
    monkeypatch.setattr(
        "resurface.ui.controllers.external_drives.QTimer.singleShot",
        lambda _delay, callback: callback(),
    )

    blocked = controller.block_end_session("Log Out")

    assert blocked
    assert window.warnings[0][1] == "Log Out Blocked"
    assert "E:\\" in window.warnings[0][2]

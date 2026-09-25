from resurface.features.drives.drive_reminder_logic import (
    DriveChanges,
    DriveReminderPolicy,
)
from resurface.features.drives.drive_service import DriveInfo, DriveServiceError
from resurface.ui.controllers.external_drives import ExternalDriveController
from resurface.ui.external_drive_popups import status_popup_options, usb_popup_icon_path
from resurface.ui import styles


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
    def __init__(self, paths=(), eject_error=None):
        self.paths = tuple(paths)
        self.eject_error = eject_error
        self.ejected_paths = []

    def list_drives(self):
        return [DriveInfo(path, 100, 40, 60, True) for path in self.paths]

    def eject(self, path):
        if self.eject_error is not None:
            raise self.eject_error
        self.ejected_paths.append(path)


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
    assert window.messages[0][3] == status_popup_options() | {
        "merge_group": "external_drive_changes",
        "merge_title": "External Drives",
        "replace_grouped_entries": True,
        "text_color": styles.TEXT_LIGHT,
    }


def test_removed_drive_notification_uses_the_shared_status_options():
    controller, window, _page, _monitor, _refreshes = make_controller()

    controller._handle_snapshot(
        DriveChanges(current=(), removed=("E:\\",))
    )

    assert window.messages[0][1:3] == (
        "Drive Removed",
        "External drive removed:\nE:\\",
    )
    assert window.messages[0][3] == status_popup_options() | {
        "merge_group": "external_drive_changes",
        "merge_title": "External Drives",
        "replace_grouped_entries": True,
        "text_color": styles.TEXT_LIGHT,
    }


def test_usb_popup_icon_resolves_the_moved_historical_asset():
    path = usb_popup_icon_path()

    assert path.is_file()
    assert path.name == "Usb Icon.png"
    assert path.parent.name == "Light Theme"


def test_status_popup_uses_standard_rounding_in_both_themes():
    try:
        for is_dark in (False, True):
            styles.set_theme(is_dark)
            options = status_popup_options()
            assert options["popup_corner_radius"] == styles.BUTTON_CORNER_RADIUS
            assert options["accessory_icon_path"].is_file()
    finally:
        styles.set_theme(True)


def test_safe_removal_status_popup_uses_the_shared_options(monkeypatch):
    controller, window, _page, _monitor, _refreshes = make_controller()
    monkeypatch.setattr(
        "resurface.ui.controllers.external_drives.QTimer.singleShot",
        lambda *_args: None,
    )

    controller.safely_remove("E:\\")

    assert window.messages[-1][1:3] == (
        "Drive Removal",
        "Requested safe removal for E:.",
    )
    assert window.messages[-1][3] == status_popup_options()


def test_safe_removal_error_popup_uses_the_shared_options(monkeypatch):
    controller, window, _page, _monitor, _refreshes = make_controller()
    controller.drive_service.eject_error = DriveServiceError("device busy")
    monkeypatch.setattr(
        "resurface.ui.controllers.external_drives.QTimer.singleShot",
        lambda *_args: None,
    )

    controller.safely_remove("E:\\")

    assert window.messages[-1][1] == "Drive Removal"
    assert window.messages[-1][3] == status_popup_options()


def test_safe_removal_menu_uses_the_rounded_theme_aware_style(monkeypatch):
    controller, _window, page, _monitor, _refreshes = make_controller(["E:\\"])
    controller._current_drives = ("E:\\",)
    applied_radii = []

    class Menu:
        def __init__(self, _parent):
            pass

        def addAction(self, _label):
            return object()

        def exec(self, _position):
            return None

    monkeypatch.setattr("resurface.ui.controllers.external_drives.QMenu", Menu)
    monkeypatch.setattr(
        "resurface.ui.controllers.external_drives.styles.apply_popup_menu_style",
        lambda _menu, *, radius: applied_radii.append(radius),
    )
    page.drive_combo = lambda: type(
        "Combo", (), {"mapToGlobal": lambda _self, pos: pos}
    )()

    controller.show_context_menu(object())

    assert applied_radii == [styles.BUTTON_CORNER_RADIUS]


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
    options = window.warnings[0][3]
    assert options["popup_corner_radius"] == styles.BUTTON_CORNER_RADIUS
    assert options["accessory_icon_path"] == usb_popup_icon_path()
    assert "timeout_ms" not in options

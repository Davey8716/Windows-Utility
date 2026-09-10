from resurface.features.system import maintenance_actions
from resurface.features.system.maintenance_actions import MaintenanceActions


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append(("run", command, kwargs))

    def run_elevated(self, command, **kwargs):
        self.calls.append(("elevated", command, kwargs))

    def set_output(self, text):
        self.calls.append(("output", text, {}))


class FakeWindowActions:
    pass


def test_network_and_integrity_actions_delegate_to_runner(monkeypatch):
    runner = FakeRunner()
    actions = MaintenanceActions(runner, FakeWindowActions(), FakeWindowActions())
    actions.flush_dns()
    actions.restart_explorer()
    monkeypatch.setattr(actions, "is_admin", lambda: False)
    requests = []
    actions.admin_access_required.connect(
        lambda title, command, finished: requests.append((title, command, finished))
    )
    actions.run_sfc_scannow()

    assert runner.calls[0] == ("run", "ipconfig /flushdns", {})
    assert runner.calls[1] == (
        "run",
        "taskkill /f /im explorer.exe && start explorer",
        {"shell": True},
    )
    assert requests == [("System File Checker (SFC)", ["sfc", "/scannow"], None)]


def test_integrity_actions_request_admin_access_when_not_elevated(monkeypatch):
    runner = FakeRunner()
    actions = MaintenanceActions(runner, FakeWindowActions(), FakeWindowActions())
    monkeypatch.setattr(actions, "is_admin", lambda: False)
    requests = []
    actions.admin_access_required.connect(
        lambda title, command, finished: requests.append((title, command, finished))
    )
    monkeypatch.setattr(actions, "is_service_running", lambda _name: False)

    actions.run_dism_restorehealth()
    actions.run_sfc_scannow()
    actions.run_chkdsk()

    assert requests[:2] == [
        ("DISM Repair", ["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"], None),
        ("System File Checker (SFC)", ["sfc", "/scannow"], None),
    ]
    assert requests[2][:2] == (
        "Check Disk (CHKDSK)",
        ["chkdsk", "C:", "/scan"],
    )
    assert callable(requests[2][2])
    assert runner.calls == []


def test_integrity_actions_run_directly_when_already_elevated(monkeypatch):
    runner = FakeRunner()
    actions = MaintenanceActions(runner, FakeWindowActions(), FakeWindowActions())
    monkeypatch.setattr(actions, "is_admin", lambda: True)
    monkeypatch.setattr(actions, "is_service_running", lambda _name: False)

    actions.run_chkdsk()

    assert runner.calls[0][:2] == ("run", ["chkdsk", "C:", "/scan"])
    assert callable(runner.calls[0][2]["finished"])


def test_chkdsk_is_blocked_when_vanguard_driver_is_running(monkeypatch):
    runner = FakeRunner()
    actions = MaintenanceActions(runner, FakeWindowActions(), FakeWindowActions())
    monkeypatch.setattr(actions, "is_service_running", lambda name: name == "vgk")
    blocked = []
    actions.chkdsk_blocked_by_vanguard.connect(lambda: blocked.append(True))

    actions.run_chkdsk()

    assert blocked == [True]
    assert runner.calls == []


def test_service_status_check_allows_stopped_missing_and_unqueryable_services(monkeypatch):
    class FakeService:
        def __init__(self, status):
            self._status = status

        def status(self):
            return self._status

    monkeypatch.setattr(
        maintenance_actions.psutil,
        "win_service_get",
        lambda _name: FakeService("stopped"),
    )
    assert not MaintenanceActions.is_service_running("vgk")

    monkeypatch.setattr(
        maintenance_actions.psutil,
        "win_service_get",
        lambda _name: (_ for _ in ()).throw(OSError("unavailable")),
    )
    assert not MaintenanceActions.is_service_running("missing")


def test_chkdsk_access_denied_signal_only_matches_failed_access_denial():
    runner = FakeRunner()
    actions = MaintenanceActions(runner, FakeWindowActions(), FakeWindowActions())
    blocked = []
    actions.chkdsk_access_denied.connect(lambda: blocked.append(True))

    actions._handle_chkdsk_finished(1, "Access is denied.")
    actions._handle_chkdsk_finished(0, "Access is denied was mentioned in a successful report.")
    actions._handle_chkdsk_finished(3, "The disk could not be checked.")

    assert blocked == [True]


def test_admin_confirmation_routes_to_captured_elevated_runner():
    runner = FakeRunner()
    actions = MaintenanceActions(runner, FakeWindowActions(), FakeWindowActions())
    finished = lambda *_args: None

    actions.run_admin_command_elevated(["chkdsk", "C:", "/scan"], finished=finished)

    assert runner.calls == [
        ("elevated", ["chkdsk", "C:", "/scan"], {"finished": finished})
    ]


def test_temp_cleanup_requests_elevation_only_for_access_denied(monkeypatch):
    runner = FakeRunner()
    actions = MaintenanceActions(runner, FakeWindowActions(), FakeWindowActions())
    monkeypatch.setattr(actions, "is_admin", lambda: False)
    requested = []
    actions.temp_cleanup_admin_required.connect(lambda: requested.append(True))
    actions.clear_temp()
    finished = runner.calls[-1][2]["finished"]
    finished(1, "An item failed: Access is denied")
    assert requested == [True]
    actions.retry_temp_cleanup_elevated()
    assert runner.calls[-1][0] == "elevated"


def test_power_actions_use_expected_windows_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(maintenance_actions.subprocess, "Popen", lambda command: calls.append(command))
    MaintenanceActions.run_sleep()
    MaintenanceActions.run_restart()
    MaintenanceActions.run_logout()
    MaintenanceActions.run_shutdown()
    assert calls == [
        ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
        ["shutdown", "/r", "/t", "0"],
        ["shutdown", "/l"],
        ["shutdown", "/s", "/t", "0"],
    ]

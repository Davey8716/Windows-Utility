from resurface.features.system import maintenance_actions
from resurface.features.system.maintenance_actions import MaintenanceActions


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append(("run", command, kwargs))

    def run_elevated(self, command):
        self.calls.append(("elevated", command, {}))

    def run_elevated_visible(self, command):
        self.calls.append(("elevated_visible", command, {}))

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
    actions.admin_access_required.connect(lambda title, command: requests.append((title, command)))
    actions.run_sfc_scannow()

    assert runner.calls[0] == ("run", "ipconfig /flushdns", {})
    assert runner.calls[1] == (
        "run",
        "taskkill /f /im explorer.exe && start explorer",
        {"shell": True},
    )
    assert requests == [("System File Checker (SFC)", ["sfc", "/scannow"])]


def test_integrity_actions_request_admin_access_when_not_elevated(monkeypatch):
    runner = FakeRunner()
    actions = MaintenanceActions(runner, FakeWindowActions(), FakeWindowActions())
    monkeypatch.setattr(actions, "is_admin", lambda: False)
    requests = []
    actions.admin_access_required.connect(lambda title, command: requests.append((title, command)))

    actions.run_dism_restorehealth()
    actions.run_sfc_scannow()
    actions.run_chkdsk()

    assert requests == [
        ("DISM Repair", ["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"]),
        ("System File Checker (SFC)", ["sfc", "/scannow"]),
        ("Check Disk (CHKDSK)", ["chkdsk", "C:", "/scan"]),
    ]
    assert runner.calls == []


def test_integrity_actions_run_directly_when_already_elevated(monkeypatch):
    runner = FakeRunner()
    actions = MaintenanceActions(runner, FakeWindowActions(), FakeWindowActions())
    monkeypatch.setattr(actions, "is_admin", lambda: True)

    actions.run_chkdsk()

    assert runner.calls == [("run", ["chkdsk", "C:", "/scan"], {})]


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

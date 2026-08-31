import threading
import time

from resurface.features.drives.drive_monitor import DriveMonitor
from resurface.features.drives.drive_service import DriveInfo


def drive(path, *, ejectable=True):
    return DriveInfo(path, 100, 40, 60, ejectable)


class SequencedDriveService:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.calls = 0

    def list_drives(self):
        index = min(self.calls, len(self.snapshots) - 1)
        self.calls += 1
        value = self.snapshots[index]
        if isinstance(value, Exception):
            raise value
        return value


def test_initial_scan_sets_baseline_without_addition_notification():
    monitor = DriveMonitor(SequencedDriveService([[drive("E:\\")]]))

    changes = monitor._scan_once()

    assert changes.current == ("E:\\",)
    assert changes.added == ()
    assert changes.removed == ()


def test_scan_reports_normalized_additions_and_removals():
    service = SequencedDriveService(
        [
            [drive("F:\\"), drive("E:\\"), drive("C:\\", ejectable=False)],
            [drive("F:\\"), drive("G:\\")],
        ]
    )
    monitor = DriveMonitor(service)
    monitor._scan_once()

    changes = monitor._scan_once()

    assert changes.current == ("F:\\", "G:\\")
    assert changes.added == ("G:\\",)
    assert changes.removed == ("E:\\",)


def test_failed_scan_retains_previous_snapshot_without_false_removal():
    monitor = DriveMonitor(
        SequencedDriveService([[drive("E:\\")], OSError("scan failed")])
    )
    monitor._scan_once()

    changes = monitor._scan_once()

    assert changes.current == ("E:\\",)
    assert changes.added == ()
    assert changes.removed == ()


def test_requested_scan_wakes_worker_and_stop_joins_it():
    scanned_twice = threading.Event()

    class Service:
        calls = 0

        def list_drives(self):
            self.calls += 1
            if self.calls >= 2:
                scanned_twice.set()
            return []

    service = Service()
    monitor = DriveMonitor(service, interval_seconds=60)
    monitor.start()
    deadline = time.monotonic() + 1
    while service.calls < 1 and time.monotonic() < deadline:
        time.sleep(0.01)

    monitor.request_scan()

    assert scanned_twice.wait(1)
    monitor.stop()
    assert not monitor.is_running

"""Background discovery of connected external drives."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from resurface.features.drives.drive_reminder_logic import DriveChanges


def external_drive_signature(drive_service) -> tuple[str, ...]:
    """Read and normalize the ejectable drives reported by a drive service."""

    return tuple(
        sorted({drive.path for drive in drive_service.list_drives() if drive.ejectable})
    )


class DriveMonitor(QObject):
    """Poll external drives without running blocking discovery on the UI thread."""

    snapshot_changed = Signal(object)

    def __init__(
        self,
        drive_service,
        *,
        interval_seconds: float = 3.0,
        name: str = "ExternalDriveMonitor",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.drive_service = drive_service
        self.interval_seconds = float(interval_seconds)
        self.name = name
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._known: tuple[str, ...] | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive())

    @property
    def current(self) -> tuple[str, ...]:
        with self._lock:
            return self._known or ()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event = threading.Event()
            self._wake_event = threading.Event()
            self._known = None
            self._thread = threading.Thread(
                target=self._run,
                name=self.name,
                daemon=True,
            )
            thread = self._thread
        thread.start()

    def request_scan(self) -> None:
        """Wake the worker so a new snapshot is produced as soon as possible."""

        self._wake_event.set()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            if not thread or not thread.is_alive():
                self._thread = None
                return
            self._stop_event.set()
            self._wake_event.set()
        if thread is not threading.current_thread():
            thread.join(timeout=1.5)
        with self._lock:
            if not thread.is_alive():
                self._thread = None

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                self._wake_event.clear()
                self._scan_once()
                self._wake_event.wait(self.interval_seconds)
        finally:
            with self._lock:
                if threading.current_thread() is self._thread:
                    self._thread = None

    def _scan_once(self) -> DriveChanges:
        """Perform one scan; unexpected failures retain the previous snapshot."""

        try:
            current = external_drive_signature(self.drive_service)
        except Exception:
            with self._lock:
                current = self._known or ()
            changes = DriveChanges(current=current)
            self.snapshot_changed.emit(changes)
            return changes

        with self._lock:
            previous = self._known
            self._known = current

        if previous is None:
            changes = DriveChanges(current=current)
        else:
            previous_set = set(previous)
            current_set = set(current)
            changes = DriveChanges(
                current=current,
                added=tuple(sorted(current_set - previous_set)),
                removed=tuple(sorted(previous_set - current_set)),
            )
        self.snapshot_changed.emit(changes)
        return changes

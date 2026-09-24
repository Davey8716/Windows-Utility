"""Low-frequency Windows refresh work kept off the Qt GUI thread."""

from __future__ import annotations

import pythoncom

from PySide6.QtCore import QObject, QThread, Signal, Slot


class _RefreshWorker(QObject):
    drives_ready = Signal(object)
    recycle_ready = Signal(bool, object)
    folder_open_ready = Signal(str, bool)
    title_states_ready = Signal(object)

    def __init__(self, drives, recycle_bin, explorer, windows):
        super().__init__()
        self._drives = drives
        self._recycle_bin = recycle_bin
        self._explorer = explorer
        self._windows = windows

    @Slot()
    def scan_drives(self):
        try:
            records = [
                {"path": drive.path, "total_bytes": drive.total_bytes,
                 "used_bytes": drive.used_bytes, "free_bytes": drive.free_bytes,
                 "ejectable": drive.ejectable}
                for drive in self._drives.list_drives()
            ]
        except Exception:
            records = []
        self.drives_ready.emit(records)

    @Slot()
    def scan_recycle_bin(self):
        try:
            has_items = bool(self._recycle_bin.has_items())
            ages = self._recycle_bin.cleanup_age_rule_availability()
        except Exception:
            has_items, ages = False, {}
        self.recycle_ready.emit(has_items, ages)

    @Slot(str)
    def check_folder_open(self, path):
        initialized = False
        try:
            pythoncom.CoInitialize()
            initialized = True
            is_open = bool(self._explorer.is_folder_open(path)) if path else False
        except Exception:
            is_open = False
        finally:
            if initialized:
                pythoncom.CoUninitialize()
        self.folder_open_ready.emit(path, is_open)

    @Slot(object)
    def check_title_states(self, candidates_by_key):
        states = {}
        for key, candidates in dict(candidates_by_key).items():
            try:
                states[key] = self._windows.get_titles_state(tuple(candidates))
            except Exception:
                states[key] = "closed"
        self.title_states_ready.emit(states)


class BackgroundRefreshService(QObject):
    """Coalesce timer requests and publish worker results on the GUI thread."""

    _scan_drives = Signal()
    _scan_recycle = Signal()
    _check_folder = Signal(str)
    _check_titles = Signal(object)

    drives_ready = Signal(object)
    recycle_ready = Signal(bool, object)
    folder_open_ready = Signal(str, bool)
    title_states_ready = Signal(object)

    def __init__(self, drives, recycle_bin, explorer, windows, parent=None):
        super().__init__(parent)
        self._pending = {"drives": False, "recycle": False, "folder": False, "titles": False}
        self._thread = QThread(self)
        self._worker = _RefreshWorker(drives, recycle_bin, explorer, windows)
        self._worker.moveToThread(self._thread)
        self._scan_drives.connect(self._worker.scan_drives)
        self._scan_recycle.connect(self._worker.scan_recycle_bin)
        self._check_folder.connect(self._worker.check_folder_open)
        self._check_titles.connect(self._worker.check_title_states)
        self._worker.drives_ready.connect(self._on_drives_ready)
        self._worker.recycle_ready.connect(self._on_recycle_ready)
        self._worker.folder_open_ready.connect(self._on_folder_open_ready)
        self._worker.title_states_ready.connect(self._on_title_states_ready)

    def start(self):
        if not self._thread.isRunning():
            self._thread.start()

    def stop(self):
        self._thread.quit()
        self._thread.wait(1500)

    def request_drive_scan(self):
        if not self._pending["drives"]:
            self._pending["drives"] = True
            self._scan_drives.emit()

    def request_recycle_scan(self):
        if not self._pending["recycle"]:
            self._pending["recycle"] = True
            self._scan_recycle.emit()

    def request_folder_open_check(self, path):
        if not self._pending["folder"]:
            self._pending["folder"] = True
            self._check_folder.emit(path)

    def request_title_state_check(self, candidates_by_key):
        if not self._pending["titles"]:
            self._pending["titles"] = True
            self._check_titles.emit(dict(candidates_by_key))

    def _on_drives_ready(self, records):
        self._pending["drives"] = False
        self.drives_ready.emit(records)

    def _on_recycle_ready(self, has_items, ages):
        self._pending["recycle"] = False
        self.recycle_ready.emit(has_items, ages)

    def _on_folder_open_ready(self, path, is_open):
        self._pending["folder"] = False
        self.folder_open_ready.emit(path, is_open)

    def _on_title_states_ready(self, states):
        self._pending["titles"] = False
        self.title_states_ready.emit(states)

from datetime import datetime, timezone

from resurface.features.recycle_bin import service as recycle_module
from resurface.features.recycle_bin.service import RecycleBinService, delete_recycle_bin_entry, read_recycle_bin_deleted_at


class FakeWindows:
    def __init__(self):
        self.closed = None

    def close_handles(self, handles):
        self.closed = list(handles)
        return bool(handles)


def _filetime(value: datetime) -> int:
    return int(value.timestamp() * 10_000_000) + 116444736000000000


def test_metadata_timestamp_and_paired_entry_deletion(tmp_path):
    deleted_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    metadata = tmp_path / "$IABC"
    metadata.write_bytes(b"\0" * 16 + _filetime(deleted_at).to_bytes(8, "little"))
    resource = tmp_path / "$RABC"
    resource.mkdir()
    (resource / "file.txt").write_text("x")
    assert read_recycle_bin_deleted_at(metadata) == deleted_at
    assert delete_recycle_bin_entry(metadata) is True
    assert not metadata.exists() and not resource.exists()


def test_invalid_metadata_and_recycle_window_close(tmp_path, monkeypatch):
    malformed = tmp_path / "$IBAD"
    malformed.write_bytes(b"short")
    assert read_recycle_bin_deleted_at(malformed) is None
    windows = FakeWindows()
    monkeypatch.setattr(recycle_module, "find_recycle_bin_explorer_windows", lambda: [{"hwnd": 4, "pid": 9}])
    assert RecycleBinService(windows).close() is True
    assert windows.closed == [4]


def test_has_items_uses_the_windows_recycle_bin_count(monkeypatch):
    class Shell32:
        @staticmethod
        def SHQueryRecycleBinW(_root, info):
            info._obj.i64NumItems = 2
            return 0

    class Windll:
        shell32 = Shell32()

    monkeypatch.setattr(recycle_module.ctypes, "windll", Windll(), raising=False)
    assert RecycleBinService(FakeWindows()).has_items() is True

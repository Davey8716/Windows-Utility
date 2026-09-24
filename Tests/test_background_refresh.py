import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from resurface.ui.background_refresh import _RefreshWorker


class _Drives:
    def list_drives(self):
        return [type("Drive", (), {
            "path": "D:\\", "total_bytes": 100, "used_bytes": 40,
            "free_bytes": 60, "ejectable": True,
        })()]


class _Recycle:
    def has_items(self):
        return True

    def cleanup_age_rule_availability(self):
        return {7: True, 14: False, 30: False}


class _Explorer:
    def is_folder_open(self, _path):
        return True


class _Windows:
    def get_titles_state(self, candidates):
        return "open" if candidates else "closed"


def test_refresh_worker_returns_plain_drive_and_availability_snapshots():
    worker = _RefreshWorker(_Drives(), _Recycle(), _Explorer(), _Windows())
    drives = []
    recycle = []
    titles = []
    worker.drives_ready.connect(drives.append)
    worker.recycle_ready.connect(lambda has_items, ages: recycle.append((has_items, ages)))
    worker.title_states_ready.connect(titles.append)

    worker.scan_drives()
    worker.scan_recycle_bin()
    worker.check_title_states({"this_pc": ("This PC",)})

    assert drives == [[{
        "path": "D:\\", "total_bytes": 100, "used_bytes": 40,
        "free_bytes": 60, "ejectable": True,
    }]]
    assert recycle == [(True, {7: True, 14: False, 30: False})]
    assert titles == [{"this_pc": "open"}]

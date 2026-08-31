from resurface.features.system.utility_toggles import UtilityActionsManager


class FakeWindows:
    def __init__(self):
        self.restored = []

    def restore_all_except(self, hwnd):
        self.restored.append(hwnd)


class FakeApp:
    def __init__(self):
        self.saved = 0

    def winId(self):
        return 42

    def save_all_settings(self):
        self.saved += 1

    def get_default_taskbar_backup_dir(self):
        return "backup-path"


class FakeBackup:
    def __init__(self):
        self.path = None

    def backup_pinned_shortcuts(self, path):
        self.path = path
        return 3


def test_facade_resolves_paths_delegates_and_persists():
    app = FakeApp()
    windows = FakeWindows()
    backup = FakeBackup()
    actions = UtilityActionsManager(app, windows=windows, taskbar_backup=backup)
    assert actions.maximize_all_toggle(True) is True
    assert windows.restored == [42]
    assert actions.backup_pinned_shortcuts() == 3
    assert backup.path == "backup-path"
    assert app.saved == 2

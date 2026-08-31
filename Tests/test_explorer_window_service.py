from types import SimpleNamespace

from resurface.features.explorer import window_service
from resurface.features.explorer.window_service import ExplorerWindowService


class FakeWindows:
    def __init__(self, focused=False):
        self.focused = focused
        self.handles = None

    def focus_handles(self, handles):
        self.handles = list(handles)
        return self.focused

    def close_handles(self, handles):
        self.handles = list(handles)
        return bool(handles)


def _shell_window(hwnd, path):
    folder_self = SimpleNamespace(Path=path)
    return SimpleNamespace(HWND=hwnd, Document=SimpleNamespace(Folder=SimpleNamespace(Self=folder_self)))


def test_find_for_folder_prefers_exact_com_path(monkeypatch, tmp_path):
    target = tmp_path / "Folder"
    target.mkdir()
    shell = SimpleNamespace(Windows=lambda: [_shell_window(17, str(target))])
    monkeypatch.setattr(window_service.win32com.client, "Dispatch", lambda _name: shell)
    windows = FakeWindows()
    service = ExplorerWindowService(windows)
    assert service.find_for_folder(str(target)) == [17]


def test_open_or_focus_folder_focuses_existing_or_launches(monkeypatch, tmp_path):
    target = str(tmp_path)
    windows = FakeWindows(focused=True)
    service = ExplorerWindowService(windows)
    monkeypatch.setattr(service, "find_for_folder", lambda _path: [8])
    launched = []
    assert service.open_or_focus_folder(target, lambda: launched.append(True)) is True
    assert launched == [] and windows.handles == [8]

    windows.focused = False
    assert service.open_or_focus_folder(target, lambda: launched.append(True)) is True
    assert launched == [True]


def test_open_or_focus_folder_reports_launch_failure(monkeypatch, tmp_path):
    service = ExplorerWindowService(FakeWindows())
    monkeypatch.setattr(service, "find_for_folder", lambda _path: [])
    assert service.open_or_focus_folder(str(tmp_path), lambda: (_ for _ in ()).throw(OSError("failed"))) is False

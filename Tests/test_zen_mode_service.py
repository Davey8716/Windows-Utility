from resurface.features.desktop import zen_mode
from resurface.features.desktop.zen_mode import ZenModeService


def test_zen_mode_inverts_desktop_icon_visibility(monkeypatch):
    calls = []
    monkeypatch.setattr(zen_mode, "set_desktop_icons_visible", lambda visible: calls.append(visible) or True)
    service = ZenModeService()
    assert service.set_enabled(True) is True
    assert calls == [False]


def test_zen_mode_reports_missing_list_view_and_read_failure(monkeypatch):
    monkeypatch.setattr(zen_mode, "set_desktop_icons_visible", lambda _visible: False)
    monkeypatch.setattr(zen_mode, "desktop_icons_visible", lambda: (_ for _ in ()).throw(OSError("failed")))
    service = ZenModeService()
    assert service.set_enabled(False) is None
    assert service.icons_visible() is None

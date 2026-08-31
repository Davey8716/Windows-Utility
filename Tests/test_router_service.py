from resurface.features.system import router_service
from resurface.features.system.router_service import RouterService


def test_parse_default_gateway_ignores_empty_and_zero_values():
    output = "Default Gateway . . . . . . . . . :\nDefault Gateway . . . . . . . . . : fe80::1234\nDefault Gateway . . . . . . . . . : 0.0.0.0\nDefault Gateway . . . . . . . . . : 192.168.1.1"
    assert RouterService.parse_default_gateway(output) == "192.168.1.1"
    assert RouterService.parse_default_gateway("Default Gateway . . . :") is None


def test_open_router_page_opens_detected_gateway(monkeypatch):
    service = RouterService()
    monkeypatch.setattr(service, "detect_default_gateway", lambda: "10.0.0.1")
    opened = []
    monkeypatch.setattr(router_service.webbrowser, "open", opened.append)
    assert service.open_router_page() == "10.0.0.1"
    assert opened == ["http://10.0.0.1"]


def test_open_router_page_handles_detection_failure(monkeypatch):
    service = RouterService()
    monkeypatch.setattr(service, "detect_default_gateway", lambda: (_ for _ in ()).throw(OSError("no ipconfig")))
    assert service.open_router_page() is None

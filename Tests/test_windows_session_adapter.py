from resurface.features.drives.windows_session_adapter import (
    ENDSESSION_LOGOFF,
    WM_QUERYENDSESSION,
    WM_WTSSESSION_CHANGE,
    WTS_SESSION_LOCK,
    WindowsSessionEventAdapter,
)


class FakeSessionApi:
    def __init__(self):
        self.registered = []
        self.unregistered = []

    def WTSRegisterSessionNotification(self, hwnd, scope):
        self.registered.append((hwnd, scope))
        return True

    def WTSUnRegisterSessionNotification(self, hwnd):
        self.unregistered.append(hwnd)
        return True


def make_adapter(*, blocked=False):
    locks = []
    endings = []
    api = FakeSessionApi()
    adapter = WindowsSessionEventAdapter(
        window_handle=lambda: 42,
        on_session_lock=lambda: locks.append(True),
        on_end_session=lambda action: endings.append(action) or blocked,
        schedule=lambda _delay, callback: callback(),
        wts_api=api,
    )
    return adapter, api, locks, endings


def test_session_lock_is_scheduled_without_claiming_native_message():
    adapter, _api, locks, _endings = make_adapter()

    result = adapter.handle_message(WM_WTSSESSION_CHANGE, WTS_SESSION_LOCK, 0)

    assert result == (False, 0)
    assert locks == [True]


def test_end_session_translates_reason_and_returns_blocking_result():
    adapter, _api, _locks, endings = make_adapter(blocked=True)

    assert adapter.handle_message(WM_QUERYENDSESSION, 0, 0) == (True, 0)
    assert adapter.handle_message(
        WM_QUERYENDSESSION,
        0,
        ENDSESSION_LOGOFF,
    ) == (True, 0)
    assert endings == ["Shutdown or Restart", "Log Out"]


def test_registration_and_unregistration_are_idempotent():
    adapter, api, _locks, _endings = make_adapter()

    adapter.register()
    adapter.register()
    adapter.unregister()
    adapter.unregister()

    assert api.registered == [(42, 0)]
    assert api.unregistered == [42]
    assert not adapter.is_registered

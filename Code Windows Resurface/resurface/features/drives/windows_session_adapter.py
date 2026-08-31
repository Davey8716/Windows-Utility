"""Windows native-session message integration for external-drive reminders."""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QTimer


WM_QUERYENDSESSION = 0x0011
ENDSESSION_LOGOFF = 0x80000000
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
NOTIFY_FOR_THIS_SESSION = 0


class WindowsSessionEventAdapter:
    """Translate Windows session messages into feature-level callbacks."""

    def __init__(
        self,
        *,
        window_handle: Callable[[], int],
        on_session_lock: Callable[[], None],
        on_end_session: Callable[[str], bool],
        schedule: Callable[[int, Callable[[], None]], None] = QTimer.singleShot,
        wts_api=None,
    ) -> None:
        self._window_handle = window_handle
        self._on_session_lock = on_session_lock
        self._on_end_session = on_end_session
        self._schedule = schedule
        self._wts_api = wts_api
        self._registered = False

    def _session_api(self):
        return self._wts_api or ctypes.windll.wtsapi32

    @property
    def is_registered(self) -> bool:
        return self._registered

    def register(self) -> None:
        if self._registered:
            return
        hwnd = int(self._window_handle())
        if not hwnd:
            return
        try:
            registered = bool(
                self._session_api().WTSRegisterSessionNotification(
                    hwnd,
                    NOTIFY_FOR_THIS_SESSION,
                )
            )
        except Exception as exc:
            print(f"[SESSION] Failed to register session notifications: {exc}")
            return
        if registered:
            self._registered = True

    def unregister(self) -> None:
        if not self._registered:
            return
        hwnd = int(self._window_handle())
        if not hwnd:
            return
        try:
            self._session_api().WTSUnRegisterSessionNotification(hwnd)
        except Exception as exc:
            print(f"[SESSION] Failed to unregister session notifications: {exc}")
        finally:
            self._registered = False

    def handle_native_event(self, event_type, message) -> tuple[bool, int]:
        try:
            event_name = bytes(event_type).decode(errors="ignore")
        except Exception:
            event_name = str(event_type)
        if event_name != "windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        return self.handle_message(msg.message, msg.wParam, msg.lParam)

    def handle_message(
        self,
        message: int,
        w_param: int,
        l_param: int,
    ) -> tuple[bool, int]:
        if message == WM_WTSSESSION_CHANGE and w_param == WTS_SESSION_LOCK:
            self._schedule(0, self._on_session_lock)
            return False, 0
        if message == WM_QUERYENDSESSION:
            action = (
                "Log Out"
                if (l_param & ENDSESSION_LOGOFF)
                else "Shutdown or Restart"
            )
            if self._on_end_session(action):
                return True, 0
        return False, 0

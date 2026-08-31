from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DriveChanges:
    """A normalized snapshot of external-drive changes."""

    current: tuple[str, ...]
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


class DriveReminderPolicy:
    """Track external drives and make reminder decisions without UI dependencies."""

    def __init__(self, known_drives: Iterable[str] = ()) -> None:
        self._known_drives = set(known_drives)

    @staticmethod
    def signature(drives: Iterable[str]) -> tuple[str, ...]:
        return tuple(sorted(set(drives)))

    @staticmethod
    def format_connected_drives(drives: Iterable[str]) -> tuple[str, str]:
        signature = DriveReminderPolicy.signature(drives)
        drive_label = "drive is" if len(signature) == 1 else "drives are"
        return drive_label, "\n".join(signature)

    @staticmethod
    def should_remind(enabled: bool, drives: Iterable[str]) -> bool:
        return enabled and bool(DriveReminderPolicy.signature(drives))

    def reset(self, drives: Iterable[str]) -> None:
        self._known_drives = set(drives)

    def observe(
        self,
        drives: Iterable[str],
        *,
        notifications_enabled: bool = True,
        suppressed_removals: Iterable[str] = (),
    ) -> DriveChanges:
        current_drives = set(drives)
        current_signature = self.signature(current_drives)

        if not notifications_enabled:
            self._known_drives = current_drives
            return DriveChanges(current=current_signature)

        added = self.signature(current_drives - self._known_drives)
        removed = self.signature(self._known_drives - current_drives)
        self._known_drives = current_drives

        suppressed = set(suppressed_removals)
        if removed and set(removed).issubset(suppressed):
            removed = ()

        return DriveChanges(
            current=current_signature,
            added=added,
            removed=removed,
        )

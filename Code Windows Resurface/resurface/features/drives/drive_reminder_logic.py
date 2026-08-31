from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class DriveChanges:
    """A normalized external-drive snapshot and its changes."""

    current: tuple[str, ...]
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


class DriveReminderPolicy:
    """Make external-drive reminder decisions without UI dependencies."""

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

    @staticmethod
    def notification_changes(
        changes: DriveChanges,
        *,
        notifications_enabled: bool = True,
        suppressed_removals: Iterable[str] = (),
    ) -> DriveChanges:
        if not notifications_enabled:
            return DriveChanges(current=changes.current)

        suppressed = set(suppressed_removals)
        removed = changes.removed
        if removed and set(removed).issubset(suppressed):
            removed = ()

        return DriveChanges(
            current=changes.current,
            added=changes.added,
            removed=removed,
        )

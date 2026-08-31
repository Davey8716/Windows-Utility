from resurface.features.drives.drive_reminder_logic import (
    DriveChanges,
    DriveReminderPolicy,
)


def test_signature_normalizes_duplicate_unsorted_drives():
    assert DriveReminderPolicy.signature(["F:\\", "E:\\", "F:\\"]) == (
        "E:\\",
        "F:\\",
    )


def test_format_connected_drives_uses_singular_and_plural_grammar():
    assert DriveReminderPolicy.format_connected_drives(["E:\\"]) == (
        "drive is",
        "E:\\",
    )
    assert DriveReminderPolicy.format_connected_drives(["F:\\", "E:\\"]) == (
        "drives are",
        "E:\\\nF:\\",
    )


def test_should_remind_requires_enabled_policy_and_connected_drive():
    assert DriveReminderPolicy.should_remind(True, ["E:\\"])
    assert not DriveReminderPolicy.should_remind(False, ["E:\\"])
    assert not DriveReminderPolicy.should_remind(True, [])


def test_notification_changes_hides_disabled_notifications():
    changes = DriveReminderPolicy.notification_changes(
        DriveChanges(
            current=("F:\\",),
            added=("F:\\",),
            removed=("E:\\",),
        ),
        notifications_enabled=False,
    )

    assert changes.added == ()
    assert changes.removed == ()


def test_notification_changes_suppresses_expected_removal_from_confirmation_dialog():
    changes = DriveReminderPolicy.notification_changes(
        DriveChanges(current=(), removed=("E:\\",)),
        suppressed_removals=["E:\\"],
    )

    assert changes.removed == ()


def test_notification_changes_keeps_partial_unexpected_removal():
    changes = DriveReminderPolicy.notification_changes(
        DriveChanges(current=(), removed=("E:\\", "F:\\")),
        suppressed_removals=["E:\\"],
    )

    assert changes.removed == ("E:\\", "F:\\")

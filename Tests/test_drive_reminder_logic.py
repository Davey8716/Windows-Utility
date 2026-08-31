from resurface.features.drives.drive_reminder_logic import DriveReminderPolicy


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


def test_observe_reports_added_and_removed_drives_and_advances_state():
    policy = DriveReminderPolicy(["E:\\", "F:\\"])

    changes = policy.observe(["F:\\", "G:\\"])

    assert changes.current == ("F:\\", "G:\\")
    assert changes.added == ("G:\\",)
    assert changes.removed == ("E:\\",)
    assert policy.observe(["F:\\", "G:\\"]).added == ()


def test_observe_tracks_state_without_reporting_disabled_notifications():
    policy = DriveReminderPolicy(["E:\\"])

    changes = policy.observe(["F:\\"], notifications_enabled=False)

    assert changes.added == ()
    assert changes.removed == ()
    assert policy.observe(["F:\\"]).removed == ()


def test_observe_suppresses_expected_removal_from_confirmation_dialog():
    policy = DriveReminderPolicy(["E:\\"])

    changes = policy.observe([], suppressed_removals=["E:\\"])

    assert changes.removed == ()

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from resurface.features.hover_window_controls.app.data_export import (
    DataExportError,
    export_application_data,
)
from resurface.features.hover_window_controls.app.identity import (
    DISPLAY_NAME,
    LEGACY_DATA_DIRECTORY,
)


class ApplicationDataExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.current = self.root / "source" / DISPLAY_NAME
        self.legacy = self.root / "source" / LEGACY_DATA_DIRECTORY
        self.destination = self.root / "backups"
        self.current.mkdir(parents=True)
        self.legacy.mkdir(parents=True)
        self.destination.mkdir()
        (self.current / "settings.json").write_text(
            '{"schema_version": 1}',
            "utf-8",
        )
        cache = self.current / "vision-cache" / "example"
        cache.mkdir(parents=True)
        (cache / "manifest_abc.json").write_text(
            '{"schema_version": 3}',
            "utf-8",
        )
        (cache / "caption.jpg").write_bytes(b"jpeg-data")
        legacy_cache = self.legacy / "vision-cache" / "old-example"
        legacy_cache.mkdir(parents=True)
        (legacy_cache / "manifest_old.json").write_text(
            '{"schema_version": 3}',
            "utf-8",
        )
        self.now = datetime(2026, 7, 30, 20, 15, 30, tzinfo=timezone.utc)

    def tearDown(self):
        self.temporary.cleanup()

    def export(self, **changes):
        arguments = {
            "current_root": self.current,
            "legacy_root": self.legacy,
            "now": self.now,
        }
        arguments.update(changes)
        return export_application_data(self.destination, **arguments)

    def test_exports_current_and_legacy_trees_with_manifest(self):
        source_image = (
            self.current / "vision-cache" / "example" / "caption.jpg"
        )
        os.utime(source_image, (1_700_000_000, 1_700_000_000))

        result = self.export()

        legacy_copy = result.directory / LEGACY_DATA_DIRECTORY
        copied_image = (
            result.directory / "vision-cache" / "example" / "caption.jpg"
        )
        self.assertEqual(copied_image.read_bytes(), b"jpeg-data")
        self.assertEqual(
            copied_image.stat().st_mtime_ns,
            source_image.stat().st_mtime_ns,
        )
        self.assertTrue(
            (
                legacy_copy
                / "vision-cache"
                / "old-example"
                / "manifest_old.json"
            ).is_file()
        )
        manifest = json.loads(
            (result.directory / "export_manifest.json").read_text("utf-8")
        )
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["application"], DISPLAY_NAME)
        self.assertEqual(manifest["layout"], "direct")
        self.assertEqual(
            manifest["managed_entries"],
            [LEGACY_DATA_DIRECTORY, "settings.json", "vision-cache"],
        )
        self.assertEqual(
            manifest["included_roots"],
            [DISPLAY_NAME, LEGACY_DATA_DIRECTORY],
        )
        self.assertNotIn(str(self.current), json.dumps(manifest))
        self.assertEqual(result.directory, self.destination)
        self.assertFalse((self.destination / DISPLAY_NAME).exists())

    def test_succeeds_without_cache_or_legacy_root(self):
        for child in (self.current / "vision-cache").iterdir():
            for item in child.iterdir():
                item.unlink()
            child.rmdir()
        (self.current / "vision-cache").rmdir()
        for child in (self.legacy / "vision-cache").iterdir():
            for item in child.iterdir():
                item.unlink()
            child.rmdir()
        (self.legacy / "vision-cache").rmdir()
        self.legacy.rmdir()

        result = self.export()

        self.assertTrue(
            (result.directory / "settings.json").is_file()
        )
        self.assertFalse(
            (result.directory / LEGACY_DATA_DIRECTORY).exists()
        )
        self.assertEqual(result.included_roots, (DISPLAY_NAME,))

    def test_changed_export_updates_the_direct_copy(self):
        self.export()
        (self.current / "settings.json").write_text(
            '{"schema_version": 2}',
            "utf-8",
        )
        result = self.export()

        self.assertEqual(result.directory, self.destination)
        self.assertEqual(
            (self.destination / "settings.json").read_text("utf-8"),
            '{"schema_version": 2}',
        )

    def test_unchanged_export_is_skipped(self):
        first = self.export()

        second = self.export()

        self.assertIsNone(second)
        self.assertEqual(first.directory, self.destination)

    def test_json_change_creates_a_new_export(self):
        first = self.export()
        (self.current / "settings.json").write_text(
            '{"schema_version": 2}',
            "utf-8",
        )

        second = self.export()

        self.assertIsNotNone(second)
        self.assertEqual(second.directory, first.directory)

    def test_removed_source_entry_is_removed_from_direct_export(self):
        self.export()
        (self.current / "settings.json").unlink()

        self.export()

        self.assertFalse((self.destination / "settings.json").exists())
        manifest = json.loads(
            (self.destination / "export_manifest.json").read_text("utf-8")
        )
        self.assertNotIn("settings.json", manifest["managed_entries"])

    def test_existing_timestamped_exports_are_left_untouched(self):
        historical = self.destination / (
            f"{DISPLAY_NAME} Export - 2026-07-29_10-00-00"
        )
        historical.mkdir()
        marker = historical / "old.json"
        marker.write_text("old", "utf-8")

        self.export()

        self.assertEqual(marker.read_text("utf-8"), "old")

    def test_unmanaged_destination_entry_is_not_overwritten(self):
        existing = self.destination / "settings.json"
        existing.write_text("user data", "utf-8")

        with self.assertRaisesRegex(DataExportError, "unmanaged data"):
            self.export()

        self.assertEqual(existing.read_text("utf-8"), "user data")

    def test_temporary_file_change_does_not_create_a_new_export(self):
        self.export()
        (self.current / ".settings.json.tmp").write_text("partial", "utf-8")

        self.assertIsNone(self.export())

    def test_excludes_incomplete_atomic_temporary_files(self):
        (self.current / ".settings.json.tmp").write_text("partial", "utf-8")
        cache = self.current / "vision-cache" / "example"
        (cache / ".manifest_abc.json.tmp").write_text("partial", "utf-8")

        result = self.export()

        exported = result.directory
        self.assertFalse((exported / ".settings.json.tmp").exists())
        self.assertFalse(
            (
                exported
                / "vision-cache"
                / "example"
                / ".manifest_abc.json.tmp"
            ).exists()
        )

    def test_rejects_destination_inside_source_root(self):
        destination = self.current / "exports"
        destination.mkdir()

        with self.assertRaisesRegex(
            DataExportError,
            "outside the application-data",
        ):
            export_application_data(
                destination,
                current_root=self.current,
                legacy_root=self.legacy,
                now=self.now,
            )

        self.assertFalse(any(destination.iterdir()))

    def test_rejects_symlink_without_completed_export(self):
        linked = self.current / "linked"
        linked.write_text("not followed", "utf-8")
        original_is_symlink = Path.is_symlink

        def pretend_symlink(path):
            return path == linked or original_is_symlink(path)

        with patch.object(
            Path,
            "is_symlink",
            autospec=True,
            side_effect=pretend_symlink,
        ):
            with self.assertRaisesRegex(DataExportError, "symbolic link"):
                self.export()

        self.assertFalse(any(self.destination.iterdir()))

    def test_copy_failure_cleans_staging_and_preserves_source(self):
        source_before = (self.current / "settings.json").read_bytes()
        with patch(
            "resurface.features.hover_window_controls.app.data_export.shutil.copy2",
            side_effect=PermissionError("protected"),
        ):
            with self.assertRaisesRegex(DataExportError, "Cannot copy"):
                self.export()

        self.assertEqual(
            (self.current / "settings.json").read_bytes(),
            source_before,
        )
        self.assertFalse(any(self.destination.iterdir()))

    def test_final_rename_failure_leaves_no_partial_export(self):
        def fail_rename(_source, _destination):
            raise OSError("rename failed")

        with self.assertRaisesRegex(
            DataExportError,
            "could not be completed",
        ):
            self.export(rename=fail_rename)

        self.assertFalse(any(self.destination.iterdir()))

    def test_update_failure_restores_previous_direct_export(self):
        self.export()
        original_settings = (self.destination / "settings.json").read_bytes()
        (self.current / "settings.json").write_text(
            '{"schema_version": 2}', "utf-8"
        )
        calls = 0

        def fail_during_install(source, destination):
            nonlocal calls
            calls += 1
            if calls == 5:
                raise OSError("rename failed")
            return source.rename(destination)

        with self.assertRaisesRegex(DataExportError, "could not be completed"):
            self.export(rename=fail_during_install)

        self.assertEqual(
            (self.destination / "settings.json").read_bytes(),
            original_settings,
        )
        self.assertFalse(
            any("rollback" in path.name for path in self.destination.iterdir())
        )


if __name__ == "__main__":
    unittest.main()

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

        current_copy = result.directory / DISPLAY_NAME
        legacy_copy = result.directory / LEGACY_DATA_DIRECTORY
        copied_image = (
            current_copy / "vision-cache" / "example" / "caption.jpg"
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
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["application"], DISPLAY_NAME)
        self.assertEqual(
            manifest["included_roots"],
            [DISPLAY_NAME, LEGACY_DATA_DIRECTORY],
        )
        self.assertNotIn(str(self.current), json.dumps(manifest))

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
            (result.directory / DISPLAY_NAME / "settings.json").is_file()
        )
        self.assertFalse(
            (result.directory / LEGACY_DATA_DIRECTORY).exists()
        )
        self.assertEqual(result.included_roots, (DISPLAY_NAME,))

    def test_timestamp_collision_adds_numeric_suffix(self):
        first = self.export()
        second = self.export()

        self.assertNotEqual(first.directory, second.directory)
        self.assertEqual(
            second.directory.name,
            f"{first.directory.name} (2)",
        )

    def test_excludes_incomplete_atomic_temporary_files(self):
        (self.current / ".settings.json.tmp").write_text("partial", "utf-8")
        cache = self.current / "vision-cache" / "example"
        (cache / ".manifest_abc.json.tmp").write_text("partial", "utf-8")

        result = self.export()

        exported = result.directory / DISPLAY_NAME
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

        self.assertFalse(
            any(
                path.name.startswith(f"{DISPLAY_NAME} Export")
                for path in destination.iterdir()
            )
        )

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


if __name__ == "__main__":
    unittest.main()

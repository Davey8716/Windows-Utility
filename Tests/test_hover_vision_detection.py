import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
from PySide6.QtGui import QColor, QImage

from resurface.features.hover_window_controls.app.data_export import DataExportError
from resurface.features.hover_window_controls.core.hover_controller import CaptionAction
from resurface.features.hover_window_controls.vision.detection import (
    AUTOMATIC_SCORE,
    LEGACY_SCHEMA_VERSION,
    ApplicationIdentity,
    CaptionVisionDetector,
    VisionCache,
    VisionContext,
    VisionMatch,
    VisionMatcher,
    VisionSnapshot,
    denormalized_rect,
    encode_jpeg,
    encode_png,
    fixed_caption_strip_rect,
    generated_template,
    is_informative_crop,
    normalized_rect,
    rects_overlap,
    safe_name,
)


def identity(**changes):
    values = {
        "executable_path": r"c:\apps\Example App\example.exe",
        "executable_version": "1.2.3.4",
        "friendly_name": "Example App",
        "window_class": "ExampleWindow",
        "dpi": 96,
        "theme": "dark",
        "caption_side": "right",
        "window_state": "normal",
    }
    values.update(changes)
    return ApplicationIdentity(**values)


def synthetic_titlebar(dpi=96, background=0):
    height = round(64 * dpi / 96)
    width = round(320 * dpi / 96)
    image = np.full((height, width, 3), background, dtype=np.uint8)
    size = round(16 * dpi / 96)
    foreground = 255 - background
    positions = {}
    actions = (
        CaptionAction.MINIMIZE,
        CaptionAction.MAXIMIZE_RESTORE,
        CaptionAction.CLOSE,
    )
    for index, action in enumerate(actions):
        glyph = generated_template(action, size)
        if foreground == 0:
            glyph = 255 - glyph
        glyph = cv2.cvtColor(glyph, cv2.COLOR_GRAY2BGR)
        x = width - round((3 - index) * 45 * dpi / 96) + round(
            10 * dpi / 96
        )
        y = round(10 * dpi / 96)
        image[y : y + size, x : x + size] = glyph
        positions[action] = (x, y, x + size, y + size)
    return image, positions


class VisionMatcherTests(unittest.TestCase):
    def test_recognizes_generated_glyphs_across_dpi_and_themes(self):
        matcher = VisionMatcher()
        for dpi in (96, 120, 144, 192):
            for background in (0, 255):
                with self.subTest(dpi=dpi, background=background):
                    image, _positions = synthetic_titlebar(dpi, background)
                    matches = matcher.propose(
                        image,
                        dpi=dpi,
                        caption_side="right",
                    )
                    by_action = {match.action: match for match in matches}
                    self.assertEqual(set(by_action), set(CaptionAction))
                    for match in by_action.values():
                        self.assertGreaterEqual(match.score, AUTOMATIC_SCORE)

    def test_requires_clear_winner_under_pointer(self):
        matcher = VisionMatcher()
        matches = [
            VisionMatch(
                CaptionAction.CLOSE,
                (0, 0, 40, 40),
                0.95,
                "a",
            ),
            VisionMatch(
                CaptionAction.MINIMIZE,
                (0, 0, 40, 40),
                0.90,
                "b",
            ),
        ]
        self.assertIsNone(
            matcher.choose_at_point(matches, (20, 20), final=False)
        )

    def test_rejects_point_outside_detected_rectangle(self):
        matcher = VisionMatcher()
        match = VisionMatch(
            CaptionAction.CLOSE,
            (0, 0, 40, 40),
            0.99,
            "a",
        )
        self.assertIsNone(
            matcher.choose_at_point([match], (50, 20), final=True)
        )

    def test_final_match_uses_higher_threshold(self):
        matcher = VisionMatcher()
        match = VisionMatch(
            CaptionAction.CLOSE,
            (0, 0, 40, 40),
            0.89,
            "a",
        )
        self.assertIsNotNone(
            matcher.choose_at_point([match], (20, 20), final=False)
        )
        self.assertIsNone(
            matcher.choose_at_point([match], (20, 20), final=True)
        )


class VisionCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.cache = VisionCache(self.base)
        self.identity = identity()
        self.image = np.zeros((60, 200, 3), dtype=np.uint8)
        cv2.line(self.image, (150, 20), (170, 20), (255, 255, 255), 2)

    def tearDown(self):
        self.temporary.cleanup()

    def test_default_roots_use_branded_and_legacy_local_appdata_paths(self):
        with patch.dict(
            "resurface.features.hover_window_controls.app.identity.os.environ",
            {"LOCALAPPDATA": self.temporary.name},
            clear=False,
        ):
            cache = VisionCache()

        self.assertEqual(
            cache.base_dir,
            self.base / "Hover Window Controls" / "vision-cache",
        )
        self.assertEqual(
            cache.legacy_base_dir,
            self.base / "No Click Min Max Restore" / "vision-cache",
        )

    def test_saves_named_manifest_and_jpeg_button_crops(self):
        profile = self.cache.save(
            identity=self.identity,
            origin="user",
            image=self.image,
            assignments={CaptionAction.MINIMIZE: (140, 0, 180, 40)},
        )
        files = {path.name for path in profile.directory.iterdir()}
        manifest_name = f"manifest_{self.identity.executable_hash}.json"
        self.assertIn(manifest_name, files)
        self.assertEqual(
            len([name for name in files if name.endswith(".jpg")]),
            1,
        )
        self.assertFalse(any(name.endswith(".png") for name in files))
        manifest = json.loads(
            (profile.directory / manifest_name).read_text("utf-8")
        )
        self.assertEqual(
            manifest["application"]["friendly_name"],
            "Example App",
        )
        statuses = {
            item["action"]: item["status"]
            for item in manifest["contexts"][0]["buttons"]
        }
        self.assertEqual(statuses["MINIMIZE"], "available")
        self.assertEqual(statuses["CLOSE"], "unresolved")

    def test_lists_tracked_applications_and_available_assets(self):
        self.cache.save(
            identity=self.identity,
            origin="automatic",
            image=self.image,
            assignments={CaptionAction.MINIMIZE: (140, 0, 180, 40)},
        )

        applications = self.cache.list_tracked_applications()
        self.assertEqual(
            [application.friendly_name for application in applications],
            ["Example App"],
        )
        assets = self.cache.list_tracked_assets(applications[0])
        self.assertEqual(len(assets), 1)
        self.assertIs(assets[0].action, CaptionAction.MINIMIZE)
        self.assertIn("Minimize — normal", assets[0].label)
        self.assertEqual(assets[0].rect, (140, 0, 180, 40))

    def test_updates_only_tracked_rectangle_and_preserves_jpeg(self):
        self.cache.save(
            identity=self.identity,
            origin="user",
            image=self.image,
            assignments={CaptionAction.MINIMIZE: (140, 0, 180, 40)},
        )
        application = self.cache.list_tracked_applications()[0]
        asset = self.cache.list_tracked_assets(application)[0]
        jpeg_before = asset.image_path.read_bytes()
        old_profile_id = asset.profile_id

        updated = self.cache.update_tracked_rect(
            asset,
            (130, 5, 175, 45),
        )

        self.assertNotEqual(updated.profile_id, old_profile_id)
        self.assertEqual(updated.rect, (130, 5, 175, 45))
        self.assertEqual(updated.image_path.read_bytes(), jpeg_before)
        reloaded = self.cache.list_tracked_assets(application)
        self.assertEqual(reloaded[0].rect, (130, 5, 175, 45))
        self.assertEqual(
            len(list(application.manifest_path.parent.glob("*.jpg"))),
            1,
        )

    def test_editing_automatic_asset_creates_single_action_user_profile(self):
        assignments = {
            CaptionAction.MINIMIZE: (20, 0, 60, 40),
            CaptionAction.MAXIMIZE_RESTORE: (80, 0, 120, 40),
            CaptionAction.CLOSE: (140, 0, 180, 40),
        }
        image = np.zeros((60, 200, 3), dtype=np.uint8)
        for left in (20, 80, 140):
            cv2.line(
                image,
                (left + 5, 20),
                (left + 35, 20),
                (255, 255, 255),
                2,
            )
        self.cache.save(
            identity=self.identity,
            origin="automatic",
            image=image,
            assignments=assignments,
        )
        application = self.cache.list_tracked_applications()[0]
        automatic = next(
            asset
            for asset in self.cache.list_tracked_assets(application)
            if asset.action is CaptionAction.MINIMIZE
        )

        updated = self.cache.update_tracked_rect(
            automatic,
            (25, 5, 65, 45),
        )

        self.assertEqual(updated.origin, "user")
        manifest = json.loads(
            application.manifest_path.read_text("utf-8")
        )
        automatic_context = next(
            item for item in manifest["contexts"]
            if item["origin"] == "automatic"
        )
        user_context = next(
            item for item in manifest["contexts"]
            if item["origin"] == "user"
        )
        self.assertEqual(len(user_context["buttons"]), 1)
        self.assertEqual(
            user_context["buttons"][0]["action"],
            "MINIMIZE",
        )
        self.assertEqual(
            denormalized_rect(
                tuple(user_context["buttons"][0]["rect"]),
                (200, 60),
            ),
            (25, 5, 65, 45),
        )
        self.assertEqual(
            denormalized_rect(
                tuple(automatic_context["buttons"][0]["rect"]),
                (200, 60),
            ),
            assignments[CaptionAction.MINIMIZE],
        )

    def test_manual_edits_merge_and_are_listed_before_automatic_variants(self):
        assignments = {
            CaptionAction.MINIMIZE: (20, 0, 60, 40),
            CaptionAction.MAXIMIZE_RESTORE: (80, 0, 120, 40),
            CaptionAction.CLOSE: (140, 0, 180, 40),
        }
        image = np.zeros((60, 200, 3), dtype=np.uint8)
        for left in (20, 80, 140):
            cv2.line(
                image,
                (left + 5, 20),
                (left + 35, 20),
                (255, 255, 255),
                2,
            )
        self.cache.save(
            identity=self.identity,
            origin="automatic",
            image=image,
            assignments=assignments,
        )
        application = self.cache.list_tracked_applications()[0]
        assets = self.cache.list_tracked_assets(application)
        for action, rect in (
            (CaptionAction.MINIMIZE, (25, 5, 65, 45)),
            (CaptionAction.CLOSE, (135, 5, 185, 45)),
        ):
            automatic = next(
                asset
                for asset in assets
                if asset.action is action and asset.origin == "automatic"
            )
            self.cache.update_tracked_rect(automatic, rect)
            assets = self.cache.list_tracked_assets(application)

        manual = [asset for asset in assets if asset.origin == "user"]
        self.assertEqual(
            {asset.action for asset in manual},
            {CaptionAction.MINIMIZE, CaptionAction.CLOSE},
        )
        minimize_variants = [
            asset for asset in assets
            if asset.action is CaptionAction.MINIMIZE
        ]
        self.assertEqual(
            [asset.origin for asset in minimize_variants],
            ["user", "automatic"],
        )

    def test_automatic_recapture_preserves_manual_rectangle(self):
        self.cache.save(
            identity=self.identity,
            origin="automatic",
            image=self.image,
            assignments={CaptionAction.MINIMIZE: (140, 0, 180, 40)},
        )
        application = self.cache.list_tracked_applications()[0]
        automatic = self.cache.list_tracked_assets(application)[0]
        self.cache.update_tracked_rect(
            automatic,
            (130, 5, 175, 45),
        )

        recaptured = self.image.copy()
        cv2.line(
            recaptured,
            (145, 25),
            (175, 25),
            (255, 255, 255),
            2,
        )
        self.cache.save(
            identity=self.identity,
            origin="automatic",
            image=recaptured,
            assignments={CaptionAction.MINIMIZE: (135, 0, 180, 40)},
        )

        assets = self.cache.list_tracked_assets(application)
        manual = next(asset for asset in assets if asset.origin == "user")
        self.assertEqual(manual.rect, (130, 5, 175, 45))

    def test_tracked_discovery_skips_missing_assets_and_corrupt_manifests(self):
        profile = self.cache.save(
            identity=self.identity,
            origin="automatic",
            image=self.image,
            assignments={CaptionAction.MINIMIZE: (140, 0, 180, 40)},
        )
        next(profile.directory.glob("*.jpg")).unlink()
        self.assertEqual(self.cache.list_tracked_applications(), [])

        self.cache.manifest_path(self.identity).write_text(
            "{broken",
            encoding="utf-8",
        )
        self.assertEqual(self.cache.list_tracked_applications(), [])

    def test_tracked_discovery_skips_undecodable_jpeg(self):
        profile = self.cache.save(
            identity=self.identity,
            origin="automatic",
            image=self.image,
            assignments={CaptionAction.MINIMIZE: (140, 0, 180, 40)},
        )
        jpeg = next(profile.directory.glob("*.jpg"))
        jpeg.write_bytes(b"not a jpeg")

        self.assertEqual(self.cache.list_tracked_applications(), [])

    def test_round_trips_profile_and_normalized_rectangle(self):
        self.cache.save(
            identity=self.identity,
            origin="user",
            image=self.image,
            assignments={CaptionAction.CLOSE: (160, 0, 200, 40)},
        )
        profiles = self.cache.load(self.identity)
        self.assertEqual(len(profiles), 1)
        button = profiles[0].buttons[0]
        self.assertIs(button.action, CaptionAction.CLOSE)
        self.assertEqual(
            denormalized_rect(button.rect, (200, 60)),
            (160, 0, 200, 40),
        )

    def test_identity_change_invalidates_profile(self):
        self.cache.save(
            identity=self.identity,
            origin="user",
            image=self.image,
            assignments={CaptionAction.CLOSE: (160, 0, 200, 40)},
        )
        self.assertEqual(self.cache.load(identity(dpi=144)), [])

    def test_corrupt_manifest_is_ignored(self):
        directory = self.cache.app_directory(self.identity)
        directory.mkdir(parents=True)
        self.cache.manifest_path(self.identity).write_text(
            "{broken",
            "utf-8",
        )
        self.assertEqual(self.cache.load(self.identity), [])

    def test_merges_states_and_deduplicates_unchanged_buttons(self):
        assignments = {
            CaptionAction.MINIMIZE: (20, 0, 60, 40),
            CaptionAction.MAXIMIZE_RESTORE: (80, 0, 120, 40),
            CaptionAction.CLOSE: (140, 0, 180, 40),
        }
        normal = np.zeros((60, 200, 3), dtype=np.uint8)
        cv2.line(normal, (30, 20), (50, 20), (255, 255, 255), 2)
        cv2.rectangle(normal, (90, 10), (110, 30), (255, 255, 255), 2)
        cv2.line(normal, (148, 8), (172, 32), (255, 255, 255), 2)
        cv2.line(normal, (172, 8), (148, 32), (255, 255, 255), 2)
        maximized = normal.copy()
        maximized[0:40, 80:120] = 0
        cv2.rectangle(
            maximized,
            (88, 13),
            (106, 31),
            (255, 255, 255),
            2,
        )
        cv2.rectangle(
            maximized,
            (94, 8),
            (112, 26),
            (255, 255, 255),
            2,
        )

        self.cache.save(
            identity=self.identity,
            origin="automatic",
            image=normal,
            assignments=assignments,
        )
        maximized_identity = identity(window_state="maximized")
        self.cache.save(
            identity=maximized_identity,
            origin="automatic",
            image=maximized,
            assignments=assignments,
        )

        directory = self.cache.app_directory(self.identity)
        self.assertFalse(any(path.is_dir() for path in directory.iterdir()))
        manifests = list(directory.glob("manifest_*.json"))
        self.assertEqual(len(manifests), 1)
        data = json.loads(manifests[0].read_text("utf-8"))
        self.assertEqual(len(data["contexts"]), 2)
        self.assertEqual(len(data["assets"]), 2)
        self.assertTrue(
            all(
                "_caption_" in context["caption_asset"]["image_file"]
                for context in data["contexts"]
            )
        )
        self.assertTrue(
            all(
                denormalized_rect(
                    tuple(context["caption_asset"]["rect"]),
                    tuple(context["crop_size"]),
                )
                == (8, 0, 200, 60)
                for context in data["contexts"]
            )
        )
        self.assertTrue(
            all(
                "image_file" not in button
                for context in data["contexts"]
                for button in context["buttons"]
            )
        )
        visuals = {
            button["visual"]
            for context in data["contexts"]
            for button in context["buttons"]
            if button["status"] == "available"
        }
        self.assertIn("maximize", visuals)
        self.assertIn("restore", visuals)

    def test_stores_one_grouped_visual_per_layout_and_state(self):
        assignments = {
            CaptionAction.MINIMIZE: (20, 0, 60, 40),
            CaptionAction.MAXIMIZE_RESTORE: (80, 0, 120, 40),
            CaptionAction.CLOSE: (140, 0, 180, 40),
        }
        normal = np.zeros((60, 200, 3), dtype=np.uint8)
        cv2.line(normal, (30, 20), (50, 20), (255, 255, 255), 2)
        cv2.rectangle(normal, (90, 10), (110, 30), (255, 255, 255), 2)
        cv2.line(normal, (148, 8), (172, 32), (255, 255, 255), 2)
        cv2.line(normal, (172, 8), (148, 32), (255, 255, 255), 2)
        maximized = normal.copy()
        maximized[0:40, 20:60] = 32
        maximized[0:40, 80:120] = 0
        maximized[0:40, 140:180] = 64
        cv2.line(
            maximized, (30, 20), (50, 20), (255, 255, 255), 2
        )
        cv2.rectangle(
            maximized, (88, 13), (106, 31), (255, 255, 255), 2
        )
        cv2.rectangle(
            maximized, (94, 8), (112, 26), (255, 255, 255), 2
        )
        cv2.line(
            maximized, (148, 8), (172, 32), (255, 255, 255), 2
        )
        cv2.line(
            maximized, (172, 8), (148, 32), (255, 255, 255), 2
        )

        self.cache.save(
            identity=self.identity,
            origin="automatic",
            image=normal,
            assignments=assignments,
        )
        self.cache.save(
            identity=identity(window_state="maximized"),
            origin="automatic",
            image=maximized,
            assignments=assignments,
        )

        manifest = json.loads(
            self.cache.manifest_path(self.identity).read_text("utf-8")
        )
        grouped_files = {
            context["caption_asset"]["image_file"]
            for context in manifest["contexts"]
        }
        self.assertEqual(len(grouped_files), 2)
        self.assertEqual(len(list(
            self.cache.app_directory(self.identity).glob("*.jpg")
        )), 2)

    def test_schema_two_assets_remain_until_grouped_recapture(self):
        assignments = {
            CaptionAction.MINIMIZE: (20, 0, 60, 40),
            CaptionAction.MAXIMIZE_RESTORE: (80, 0, 120, 40),
            CaptionAction.CLOSE: (140, 0, 180, 40),
        }
        image = np.zeros((60, 200, 3), dtype=np.uint8)
        cv2.line(image, (30, 20), (50, 20), (255, 255, 255), 2)
        cv2.rectangle(image, (90, 10), (110, 30), (255, 255, 255), 2)
        cv2.line(image, (148, 8), (172, 32), (255, 255, 255), 2)
        cv2.line(image, (172, 8), (148, 32), (255, 255, 255), 2)
        directory = self.cache.app_directory(self.identity)
        directory.mkdir(parents=True)
        assets = []
        buttons = []
        for action, rect in assignments.items():
            visual = (
                "maximize"
                if action is CaptionAction.MAXIMIZE_RESTORE
                else action.name.lower()
            )
            filename = f"example-app_{visual}_legacy.jpg"
            crop = image[rect[1] : rect[3], rect[0] : rect[2]]
            (directory / filename).write_bytes(encode_jpeg(crop))
            assets.append(
                {"pixel_hash": visual, "image_file": filename}
            )
            buttons.append(
                {
                    "action": action.name,
                    "visual": visual,
                    "status": "available",
                    "rect": list(normalized_rect(rect, (200, 60))),
                    "image_file": filename,
                }
            )
        manifest_path = self.cache.manifest_path(self.identity)
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "application": {
                        "executable_path": self.identity.executable_path,
                        "executable_hash": self.identity.executable_hash,
                        "friendly_name": self.identity.friendly_name,
                    },
                    "assets": assets,
                    "contexts": [
                        {
                            "profile_id": "legacy",
                            "origin": "automatic",
                            "identity": self.identity.__dict__,
                            "crop_size": [200, 60],
                            "buttons": buttons,
                        }
                    ],
                }
            ),
            "utf-8",
        )

        self.cache.migrate_legacy()
        migrated = json.loads(manifest_path.read_text("utf-8"))
        self.assertEqual(migrated["schema_version"], 3)
        self.assertEqual(len(list(directory.glob("*.jpg"))), 3)
        self.assertTrue(
            migrated["contexts"][0]["legacy_individual_assets"]
        )

        self.cache.save_observation(
            identity=self.identity,
            image=image,
            assignments=assignments,
        )

        repaired = json.loads(manifest_path.read_text("utf-8"))
        self.assertEqual(len(list(directory.glob("*.jpg"))), 1)
        self.assertIn("caption_asset", repaired["contexts"][0])
        self.assertTrue(
            all(
                "image_file" not in button
                for button in repaired["contexts"][0]["buttons"]
            )
        )

    def test_old_automatic_layout_is_retried_on_next_encounter(self):
        self.cache.save(
            identity=self.identity,
            origin="automatic",
            image=self.image,
            assignments={CaptionAction.MINIMIZE: (140, 0, 180, 40)},
            statuses={
                CaptionAction.MAXIMIZE_RESTORE: "unresolved",
                CaptionAction.CLOSE: "unavailable",
            },
        )
        manifest_path = self.cache.manifest_path(self.identity)
        manifest = json.loads(manifest_path.read_text("utf-8"))
        manifest["contexts"][0].pop("capture_layout_version")
        manifest_path.write_text(json.dumps(manifest), "utf-8")

        statuses = self.cache.observation_statuses(self.identity)

        self.assertEqual(
            statuses[(CaptionAction.MINIMIZE, "minimize")],
            "unresolved",
        )
        self.assertEqual(
            statuses[(CaptionAction.MAXIMIZE_RESTORE, "maximize")],
            "unresolved",
        )
        self.assertEqual(
            statuses[(CaptionAction.CLOSE, "close")],
            "unavailable",
        )

    def test_repeated_save_is_idempotent_and_preserves_manual_profile(self):
        assignments = {CaptionAction.MINIMIZE: (140, 0, 180, 40)}
        for _index in range(2):
            self.cache.save(
                identity=self.identity,
                origin="automatic",
                image=self.image,
                assignments=assignments,
            )
        self.cache.save(
            identity=self.identity,
            origin="user",
            image=self.image,
            assignments=assignments,
        )
        profiles = self.cache.load(self.identity)
        self.assertEqual(
            {profile.origin for profile in profiles},
            {"automatic", "user"},
        )
        directory = self.cache.app_directory(self.identity)
        self.assertEqual(len(list(directory.glob("*.jpg"))), 1)

    def test_records_unavailable_without_fabricating_an_image(self):
        self.cache.save(
            identity=self.identity,
            origin="automatic",
            image=self.image,
            assignments={CaptionAction.MINIMIZE: (140, 0, 180, 40)},
            statuses={
                CaptionAction.MAXIMIZE_RESTORE: "unavailable",
                CaptionAction.CLOSE: "unavailable",
            },
        )
        manifest = json.loads(
            self.cache.manifest_path(self.identity).read_text("utf-8")
        )
        buttons = {
            item["action"]: item
            for item in manifest["contexts"][0]["buttons"]
        }
        self.assertNotIn("image_file", buttons["CLOSE"])
        self.assertEqual(buttons["CLOSE"]["status"], "unavailable")

    def test_automatic_observation_saves_valid_crops_independently(self):
        image = np.zeros((60, 200, 3), dtype=np.uint8)
        cv2.line(image, (20, 20), (50, 20), (255, 255, 255), 2)
        cv2.line(image, (150, 10), (170, 30), (255, 255, 255), 2)
        cv2.line(image, (170, 10), (150, 30), (255, 255, 255), 2)
        assignments = {
            CaptionAction.MINIMIZE: (10, 0, 60, 40),
            CaptionAction.MAXIMIZE_RESTORE: (75, 0, 125, 40),
            CaptionAction.CLOSE: (140, 0, 190, 40),
        }

        result = self.cache.save_observation(
            identity=self.identity,
            image=image,
            assignments=assignments,
            statuses={
                action: "available" for action in CaptionAction
            },
        )

        self.assertEqual(
            result.saved,
            {
                (CaptionAction.MINIMIZE, "minimize"),
                (CaptionAction.CLOSE, "close"),
            },
        )
        self.assertEqual(
            result.unresolved,
            {(CaptionAction.MAXIMIZE_RESTORE, "maximize")},
        )
        self.assertEqual(len(list(result.profile.directory.glob("*.jpg"))), 1)

    def test_later_observation_retries_only_missing_asset(self):
        image = np.zeros((60, 200, 3), dtype=np.uint8)
        cv2.line(image, (20, 20), (50, 20), (255, 255, 255), 2)
        cv2.line(image, (150, 10), (170, 30), (255, 255, 255), 2)
        cv2.line(image, (170, 10), (150, 30), (255, 255, 255), 2)
        assignments = {
            CaptionAction.MINIMIZE: (10, 0, 60, 40),
            CaptionAction.MAXIMIZE_RESTORE: (75, 0, 125, 40),
            CaptionAction.CLOSE: (140, 0, 190, 40),
        }
        self.cache.save_observation(
            identity=self.identity,
            image=image,
            assignments=assignments,
        )
        cv2.rectangle(image, (88, 10), (112, 30), (255, 255, 255), 2)

        result = self.cache.save_observation(
            identity=self.identity,
            image=image,
            assignments={
                CaptionAction.MAXIMIZE_RESTORE: assignments[
                    CaptionAction.MAXIMIZE_RESTORE
                ]
            },
        )

        self.assertEqual(
            result.saved,
            {(CaptionAction.MAXIMIZE_RESTORE, "maximize")},
        )
        self.assertEqual(
            result.existing,
            {
                (CaptionAction.MINIMIZE, "minimize"),
                (CaptionAction.CLOSE, "close"),
            },
        )
        self.assertFalse(result.unresolved)
        self.assertEqual(len(list(result.profile.directory.glob("*.jpg"))), 1)

    def test_migrates_legacy_png_and_removes_profile_directory(self):
        legacy_directory = (
            self.cache.app_directory(self.identity)
            / self.identity.fingerprint
        )
        legacy_directory.mkdir(parents=True)
        crop = self.image[0:40, 140:180]
        (legacy_directory / "minimize-old.png").write_bytes(
            encode_png(crop)
        )
        legacy_manifest = {
            "schema_version": LEGACY_SCHEMA_VERSION,
            "profile_id": "legacy",
            "origin": "user",
            "identity": {
                key: value
                for key, value in self.identity.__dict__.items()
            },
            "crop_size": [200, 60],
            "buttons": [
                {
                    "action": "MINIMIZE",
                    "rect": [0.7, 0.0, 0.9, 2 / 3],
                    "image_file": "minimize-old.png",
                }
            ],
        }
        (legacy_directory / "manifest.json").write_text(
            json.dumps(legacy_manifest),
            "utf-8",
        )

        self.cache.migrate_legacy()

        self.assertFalse(legacy_directory.exists())
        self.assertTrue(self.cache.manifest_path(self.identity).exists())
        self.assertEqual(
            len(list(self.cache.app_directory(self.identity).glob("*.jpg"))),
            1,
        )
        self.assertEqual(len(self.cache.load(self.identity)), 1)

    def test_keeps_legacy_folder_when_migration_write_fails(self):
        legacy_directory = (
            self.cache.app_directory(self.identity)
            / self.identity.fingerprint
        )
        legacy_directory.mkdir(parents=True)
        crop = self.image[0:40, 140:180]
        (legacy_directory / "minimize-old.png").write_bytes(
            encode_png(crop)
        )
        (legacy_directory / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": LEGACY_SCHEMA_VERSION,
                    "profile_id": "legacy",
                    "origin": "automatic",
                    "identity": self.identity.__dict__,
                    "crop_size": [200, 60],
                    "buttons": [
                        {
                            "action": "MINIMIZE",
                            "rect": [0.7, 0.0, 0.9, 2 / 3],
                            "image_file": "minimize-old.png",
                        }
                    ],
                }
            ),
            "utf-8",
        )

        with patch.object(
            self.cache,
            "save",
            side_effect=OSError("disk unavailable"),
        ):
            self.cache.migrate_legacy()

        self.assertTrue(legacy_directory.exists())

    def test_uses_hash_free_friendly_folder_and_hashed_manifests(self):
        other = identity(
            executable_path=r"c:\other\example.exe",
            executable_version="9.0",
        )
        self.cache.save(
            identity=self.identity,
            origin="user",
            image=self.image,
            assignments={CaptionAction.MINIMIZE: (140, 0, 180, 40)},
        )
        self.cache.save(
            identity=other,
            origin="user",
            image=self.image,
            assignments={CaptionAction.CLOSE: (140, 0, 180, 40)},
        )

        directory = self.cache.app_directory(self.identity)
        self.assertEqual(directory.name, "example-app")
        self.assertEqual(directory, self.cache.app_directory(other))
        self.assertEqual(
            {path.name for path in directory.glob("manifest_*.json")},
            {
                f"manifest_{self.identity.executable_hash}.json",
                f"manifest_{other.executable_hash}.json",
            },
        )

    def test_shared_folder_cleanup_preserves_other_manifest_assets(self):
        other = identity(
            executable_path=r"c:\other\example.exe",
            executable_version="9.0",
        )
        close_image = self.image.copy()
        cv2.line(
            close_image,
            (145, 5),
            (175, 35),
            (255, 255, 255),
            2,
        )
        self.cache.save(
            identity=self.identity,
            origin="user",
            image=self.image,
            assignments={CaptionAction.MINIMIZE: (140, 0, 180, 40)},
        )
        other_profile = self.cache.save(
            identity=other,
            origin="user",
            image=close_image,
            assignments={CaptionAction.CLOSE: (140, 0, 180, 40)},
        )
        other_asset = (
            other_profile.directory / other_profile.image_file
        )

        self.cache.save(
            identity=self.identity,
            origin="user",
            image=self.image,
            assignments={CaptionAction.MINIMIZE: (130, 0, 180, 40)},
        )

        self.assertTrue(other_asset.is_file())
        self.assertEqual(len(self.cache.load(other)), 1)

    def test_migrates_legacy_hashed_folder_to_branded_layout(self):
        with tempfile.TemporaryDirectory() as target_name:
            target_root = Path(target_name) / "vision-cache"
            legacy_root = Path(target_name) / "legacy" / "vision-cache"
            legacy_cache = VisionCache(legacy_root)
            legacy_cache.save(
                identity=self.identity,
                origin="user",
                image=self.image,
                assignments={
                    CaptionAction.MINIMIZE: (140, 0, 180, 40)
                },
            )
            original = legacy_cache.app_directory(self.identity)
            legacy_directory = legacy_root / (
                f"example-app-{self.identity.executable_hash}"
            )
            original.rename(legacy_directory)
            cache = VisionCache(
                target_root,
                legacy_base_dir=legacy_root,
            )

            cache.migrate_legacy()

            self.assertFalse(legacy_directory.exists())
            self.assertTrue(cache.manifest_path(self.identity).exists())
            self.assertEqual(len(cache.load(self.identity)), 1)

    def test_migration_merges_without_discarding_manual_context(self):
        with tempfile.TemporaryDirectory() as target_name:
            root = Path(target_name)
            target_root = root / "new" / "vision-cache"
            legacy_root = root / "old" / "vision-cache"
            cache = VisionCache(
                target_root,
                legacy_base_dir=legacy_root,
            )
            cache.save(
                identity=self.identity,
                origin="user",
                image=self.image,
                assignments={
                    CaptionAction.MINIMIZE: (140, 0, 180, 40)
                },
            )
            legacy_cache = VisionCache(legacy_root)
            legacy_cache.save(
                identity=self.identity,
                origin="automatic",
                image=self.image,
                assignments={CaptionAction.CLOSE: (140, 0, 180, 40)},
            )
            source = legacy_cache.app_directory(self.identity)
            source.rename(
                legacy_root
                / f"example-app-{self.identity.executable_hash}"
            )

            cache.migrate_legacy()

            profiles = cache.load(self.identity)
            self.assertEqual(
                {profile.origin for profile in profiles},
                {"user", "automatic"},
            )
            self.assertEqual(
                {
                    button.action
                    for profile in profiles
                    for button in profile.buttons
                },
                {CaptionAction.MINIMIZE, CaptionAction.CLOSE},
            )

    def test_migration_renames_different_same_named_assets(self):
        with tempfile.TemporaryDirectory() as target_name:
            root = Path(target_name)
            target_root = root / "new" / "vision-cache"
            legacy_root = root / "old" / "vision-cache"
            cache = VisionCache(
                target_root,
                legacy_base_dir=legacy_root,
            )
            cache.save(
                identity=self.identity,
                origin="user",
                image=self.image,
                assignments={
                    CaptionAction.MINIMIZE: (140, 0, 180, 40)
                },
            )
            target_manifest = cache.manifest_path(self.identity)
            target_data = json.loads(target_manifest.read_text("utf-8"))
            target_filename = next(
                iter(cache._referenced_files(target_data))
            )
            (target_manifest.parent / target_filename).rename(
                target_manifest.parent / "shared.jpg"
            )
            cache._replace_image_references(
                target_data,
                {target_filename: "shared.jpg"},
            )
            target_manifest.write_text(json.dumps(target_data), "utf-8")

            other = identity(
                executable_path=r"c:\other\example.exe",
                executable_version="9.0",
            )
            other_image = np.zeros_like(self.image)
            cv2.line(
                other_image,
                (145, 5),
                (175, 35),
                (255, 255, 255),
                2,
            )
            legacy_cache = VisionCache(legacy_root)
            legacy_cache.save(
                identity=other,
                origin="user",
                image=other_image,
                assignments={CaptionAction.CLOSE: (140, 0, 180, 40)},
            )
            source_manifest = legacy_cache.manifest_path(other)
            source_data = json.loads(source_manifest.read_text("utf-8"))
            source_filename = next(
                iter(legacy_cache._referenced_files(source_data))
            )
            (source_manifest.parent / source_filename).rename(
                source_manifest.parent / "shared.jpg"
            )
            legacy_cache._replace_image_references(
                source_data,
                {source_filename: "shared.jpg"},
            )
            source_manifest.write_text(json.dumps(source_data), "utf-8")
            source_directory = source_manifest.parent
            legacy_directory = (
                legacy_root / f"example-app-{other.executable_hash}"
            )
            source_directory.rename(legacy_directory)

            cache.migrate_legacy()

            migrated = json.loads(
                cache.manifest_path(other).read_text("utf-8")
            )
            migrated_filename = next(
                iter(cache._referenced_files(migrated))
            )
            self.assertEqual(
                migrated_filename,
                f"shared_{other.executable_hash}.jpg",
            )
            self.assertTrue(
                (cache.app_directory(other) / migrated_filename).is_file()
            )
            self.assertTrue(
                (cache.app_directory(self.identity) / "shared.jpg").is_file()
            )

    def test_interrupted_storage_migration_keeps_legacy_directory(self):
        with tempfile.TemporaryDirectory() as target_name:
            root = Path(target_name)
            target_root = root / "new" / "vision-cache"
            legacy_root = root / "old" / "vision-cache"
            legacy_cache = VisionCache(legacy_root)
            legacy_cache.save(
                identity=self.identity,
                origin="user",
                image=self.image,
                assignments={
                    CaptionAction.MINIMIZE: (140, 0, 180, 40)
                },
            )
            source = legacy_cache.app_directory(self.identity)
            legacy_directory = legacy_root / (
                f"example-app-{self.identity.executable_hash}"
            )
            source.rename(legacy_directory)
            cache = VisionCache(
                target_root,
                legacy_base_dir=legacy_root,
            )
            real_replace = os.replace

            def fail_manifest(source_path, destination_path):
                if str(destination_path).endswith(".json"):
                    raise OSError("interrupted")
                return real_replace(source_path, destination_path)

            with patch(
                "resurface.features.hover_window_controls.vision.detection.os.replace",
                side_effect=fail_manifest,
            ):
                cache.migrate_legacy()

            self.assertTrue(legacy_directory.exists())
            self.assertFalse(cache.manifest_path(self.identity).exists())

    def test_clear_removes_new_and_remaining_legacy_caches_only(self):
        with tempfile.TemporaryDirectory() as target_name:
            root = Path(target_name)
            cache = VisionCache(
                root / "new" / "vision-cache",
                legacy_base_dir=root / "old" / "vision-cache",
            )
            cache.base_dir.mkdir(parents=True)
            cache.legacy_base_dir.mkdir(parents=True)
            (cache.base_dir / "new.txt").write_text("new", "utf-8")
            (cache.legacy_base_dir / "old.txt").write_text(
                "old",
                "utf-8",
            )
            settings = root / "new" / "settings.json"
            settings.write_text("settings", "utf-8")

            cache.clear()

            self.assertFalse(cache.base_dir.exists())
            self.assertFalse(cache.legacy_base_dir.exists())
            self.assertTrue(settings.is_file())

    def test_jpeg_asset_remains_usable_for_matching(self):
        profile = self.cache.save(
            identity=self.identity,
            origin="user",
            image=self.image,
            assignments={CaptionAction.MINIMIZE: (140, 0, 180, 40)},
        )
        button = profile.buttons[0]
        reloaded = cv2.imread(str(profile.directory / button.image_file))
        original = self.image[0:60, 8:200]
        self.assertIsNotNone(reloaded)
        self.assertGreater(
            VisionMatcher().compare_crop(original, reloaded),
            0.90,
        )

    def test_clear_removes_only_configured_cache_root(self):
        sibling = self.base.parent / "unrelated-test-file"
        sibling.write_text("keep", "utf-8")
        try:
            self.cache.save(
                identity=self.identity,
                origin="user",
                image=self.image,
                assignments={CaptionAction.CLOSE: (160, 0, 200, 40)},
            )
            self.cache.clear()
            self.assertFalse(self.base.exists())
            self.assertTrue(sibling.exists())
        finally:
            sibling.unlink(missing_ok=True)

    def test_helpers_sanitize_and_scale_rectangles(self):
        self.assertEqual(safe_name("Bad:/ App?"), "Bad-App")
        rect = (20, 10, 60, 30)
        normalized = normalized_rect(rect, (100, 50))
        self.assertEqual(denormalized_rect(normalized, (200, 100)), (40, 20, 120, 60))
        self.assertTrue(rects_overlap((0, 0, 10, 10), (5, 5, 15, 15)))
        self.assertFalse(rects_overlap((0, 0, 10, 10), (10, 0, 20, 10)))
        self.assertEqual(
            fixed_caption_strip_rect((320, 96), 96, "right"),
            (128, 0, 320, 64),
        )
        self.assertEqual(
            fixed_caption_strip_rect((640, 192), 192, "left"),
            (0, 0, 384, 128),
        )

    def test_rejects_blank_or_protected_button_crops(self):
        with self.assertRaises(ValueError):
            self.cache.save(
                identity=self.identity,
                origin="user",
                image=np.zeros((60, 200, 3), dtype=np.uint8),
                assignments={CaptionAction.CLOSE: (160, 0, 200, 40)},
            )
        self.assertFalse(
            is_informative_crop(np.zeros((20, 20, 3), dtype=np.uint8))
        )


class VisionCapturePolicyTests(unittest.TestCase):
    def test_export_waits_for_pending_work_then_uses_cache(self):
        cache = MagicMock()
        expected = MagicMock()
        cache.export_all_data.return_value = expected
        detector = CaptionVisionDetector(cache=cache)
        detector._busy = True

        def release_worker():
            with detector._lock:
                detector._busy = False

        timer = threading.Timer(0.03, release_worker)
        timer.start()
        try:
            result = detector.export_all_data(
                Path("backups"),
                idle_timeout_s=0.5,
            )
        finally:
            timer.join()

        self.assertIs(result, expected)
        cache.export_all_data.assert_called_once_with(Path("backups"))
        self.assertFalse(detector._busy)

    def test_export_times_out_when_worker_never_becomes_idle(self):
        cache = MagicMock()
        detector = CaptionVisionDetector(cache=cache)
        detector._busy = True

        with self.assertRaisesRegex(DataExportError, "still being updated"):
            detector.export_all_data(
                Path("backups"),
                idle_timeout_s=0,
            )

        cache.export_all_data.assert_not_called()
        self.assertTrue(detector._busy)

    def test_capture_is_limited_to_scaled_corner(self):
        context = VisionContext(
            1,
            (100, 200, 1100, 1000),
            192,
            identity(dpi=192),
        )
        self.assertEqual(
            CaptionVisionDetector.capture_rect(context),
            (650, 200, 1100, 360),
        )

    def test_left_caption_side_uses_left_corner(self):
        context = VisionContext(
            1,
            (100, 200, 1100, 1000),
            96,
            identity(caption_side="left"),
        )
        self.assertEqual(
            CaptionVisionDetector.capture_rect(context),
            (100, 200, 420, 296),
        )

    def test_grouped_profile_match_resolves_individual_action_rect(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = VisionCache(Path(directory))
            current_identity = identity()
            image = np.zeros((60, 200, 3), dtype=np.uint8)
            cv2.line(image, (30, 20), (50, 20), (255, 255, 255), 2)
            cv2.rectangle(
                image, (90, 10), (110, 30), (255, 255, 255), 2
            )
            cv2.line(
                image, (148, 8), (172, 32), (255, 255, 255), 2
            )
            cv2.line(
                image, (172, 8), (148, 32), (255, 255, 255), 2
            )
            assignments = {
                CaptionAction.MINIMIZE: (20, 0, 60, 40),
                CaptionAction.MAXIMIZE_RESTORE: (80, 0, 120, 40),
                CaptionAction.CLOSE: (140, 0, 180, 40),
            }
            cache.save(
                identity=current_identity,
                origin="automatic",
                image=image,
                assignments=assignments,
            )
            context = VisionContext(
                1,
                (0, 0, 444, 300),
                96,
                current_identity,
            )
            detector = CaptionVisionDetector(cache=cache)
            detector.capture = lambda _context: QImage.fromData(
                encode_png(image)
            )
            detector._run = (
                lambda function, *args, **kwargs: function(
                    *args, **kwargs
                )
            )

            result = detector._probe_profiles(
                cache.load(current_identity),
                context,
                (244 + 160, 20),
                final=True,
            )

            self.assertIsNotNone(result)
            self.assertIs(result.action, CaptionAction.CLOSE)
            self.assertEqual(result.rect, assignments[CaptionAction.CLOSE])

    def test_manual_update_invalidates_loaded_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = VisionCache(Path(directory))
            current_identity = identity()
            image = np.zeros((60, 200, 3), dtype=np.uint8)
            cv2.line(
                image,
                (145, 20),
                (175, 20),
                (255, 255, 255),
                2,
            )
            cache.save(
                identity=current_identity,
                origin="automatic",
                image=image,
                assignments={
                    CaptionAction.MINIMIZE: (140, 0, 180, 40)
                },
            )
            detector = CaptionVisionDetector(cache=cache)
            detector._load_profiles(current_identity)
            self.assertIn(
                current_identity.fingerprint,
                detector._profiles,
            )
            application = cache.list_tracked_applications()[0]
            automatic = cache.list_tracked_assets(application)[0]

            updated = detector.update_tracked_rect(
                automatic,
                (130, 5, 175, 45),
            )

            self.assertEqual(updated.origin, "user")
            self.assertNotIn(
                current_identity.fingerprint,
                detector._profiles,
            )
            context = VisionContext(
                1,
                (0, 0, 444, 300),
                96,
                current_identity,
            )
            detector.capture = lambda _context: QImage.fromData(
                encode_png(image)
            )
            detector._run = (
                lambda function, *args, **kwargs: function(
                    *args, **kwargs
                )
            )

            final_match = detector.probe_calibrated(
                context,
                (244 + 150, 20),
                final=True,
            )

            self.assertIsNotNone(final_match)
            self.assertIs(
                final_match.action,
                CaptionAction.MINIMIZE,
            )
            self.assertEqual(final_match.rect, (130, 5, 175, 45))

    def test_live_calibration_persists_only_included_actions_and_merges(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = VisionCache(Path(directory))
            detector = CaptionVisionDetector(cache=cache)
            current_identity = identity()
            context = VisionContext(
                1,
                (0, 0, 444, 300),
                96,
                current_identity,
            )
            image = np.zeros((60, 200, 3), dtype=np.uint8)
            cv2.line(
                image,
                (25, 20),
                (55, 20),
                (255, 255, 255),
                2,
            )
            cv2.line(
                image,
                (148, 8),
                (172, 32),
                (255, 255, 255),
                2,
            )
            cv2.line(
                image,
                (172, 8),
                (148, 32),
                (255, 255, 255),
                2,
            )
            snapshot = VisionSnapshot(
                context,
                QImage.fromData(encode_png(image)),
                {},
            )

            first = detector.save_calibration(
                snapshot,
                {CaptionAction.CLOSE: (140, 0, 180, 40)},
            )
            self.assertEqual(
                [button.action for button in first.buttons],
                [CaptionAction.CLOSE],
            )

            second = detector.save_calibration(
                snapshot,
                {CaptionAction.MINIMIZE: (20, 0, 60, 40)},
            )

            self.assertEqual(
                {button.action for button in second.buttons},
                {CaptionAction.MINIMIZE, CaptionAction.CLOSE},
            )
            self.assertEqual(
                len(
                    [
                        profile
                        for profile in cache.load(current_identity)
                        if profile.origin == "user"
                    ]
                ),
                1,
            )
            directory_path = cache.app_directory(current_identity)
            persisted_images = list(directory_path.glob("*.jpg"))
            self.assertEqual(len(persisted_images), 1)
            persisted = QImage(str(persisted_images[0]))
            self.assertEqual(persisted.width(), 192)
            self.assertEqual(persisted.height(), 60)
            self.assertEqual(list(directory_path.glob("*.png")), [])

    def test_worker_shutdown_is_bounded_when_matcher_is_busy(self):
        entered = threading.Event()
        release = threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            detector = CaptionVisionDetector(
                cache=VisionCache(Path(directory)),
                worker_timeout_ms=1000,
                shutdown_timeout_s=0.01,
            )
            detector.start()

            def blocking_work():
                entered.set()
                release.wait(1)
                return True

            caller = threading.Thread(
                target=lambda: detector._run(blocking_work),
                daemon=True,
            )
            caller.start()
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            detector.stop()
            self.assertLess(time.monotonic() - started, 0.5)
            release.set()
            caller.join(1)
            detector.stop()

    def test_observation_worker_submits_only_unresolved_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = VisionCache(Path(directory))
            detector = CaptionVisionDetector(cache=cache)
            detector.matcher.propose = lambda *_args, **_kwargs: []
            current_identity = identity()
            context = VisionContext(
                1,
                (0, 0, 600, 400),
                96,
                current_identity,
            )
            image = np.zeros((60, 200, 3), dtype=np.uint8)
            cv2.line(
                image, (20, 20), (50, 20), (255, 255, 255), 2
            )
            cv2.line(
                image, (150, 10), (170, 30), (255, 255, 255), 2
            )
            cv2.line(
                image, (170, 10), (150, 30), (255, 255, 255), 2
            )
            assignments = {
                CaptionAction.MINIMIZE: (10, 0, 60, 40),
                CaptionAction.MAXIMIZE_RESTORE: (75, 0, 125, 40),
                CaptionAction.CLOSE: (140, 0, 190, 40),
            }
            cache.save_observation(
                identity=current_identity,
                image=image,
                assignments=assignments,
            )
            cv2.rectangle(
                image, (88, 10), (112, 30), (255, 255, 255), 2
            )

            with patch.object(
                cache,
                "save_observation",
                wraps=cache.save_observation,
            ) as save:
                result = detector._save_observation(
                    context,
                    image,
                    assignments,
                    {
                        action: "available"
                        for action in CaptionAction
                    },
                    {
                        CaptionAction.MINIMIZE: "minimize",
                        CaptionAction.MAXIMIZE_RESTORE: "maximize",
                        CaptionAction.CLOSE: "close",
                    },
                )

            self.assertIsNotNone(result)
            self.assertEqual(
                set(save.call_args.kwargs["assignments"]),
                set(CaptionAction),
            )

    def test_first_observation_is_non_blocking_and_deduplicated(self):
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        class BlockingCache:
            calls = 0

            def migrate_legacy(self):
                return None

            def observation_statuses(self, _identity):
                return {}

            def save_observation(self, **_kwargs):
                self.calls += 1
                entered.set()
                release.wait(1)
                finished.set()

        cache = BlockingCache()
        detector = CaptionVisionDetector(cache=cache)
        detector.matcher.propose = lambda *_args, **_kwargs: []
        image = QImage(200, 60, QImage.Format.Format_RGB32)
        image.fill(QColor("#202020"))
        detector.capture = lambda _context: image
        context = VisionContext(
            1,
            (0, 0, 600, 400),
            96,
            identity(),
        )
        detector.start()
        try:
            started = time.monotonic()
            detector.observe_caption_assets(
                context,
                {},
                {
                    action: "unresolved"
                    for action in CaptionAction
                },
                {
                    action: action.name.lower()
                    for action in CaptionAction
                },
            )
            detector.observe_caption_assets(
                context,
                {},
                {
                    action: "unresolved"
                    for action in CaptionAction
                },
                {
                    action: action.name.lower()
                    for action in CaptionAction
                },
            )
            self.assertLess(time.monotonic() - started, 0.1)
            self.assertTrue(entered.wait(1))
            self.assertEqual(cache.calls, 1)
            release.set()
            self.assertTrue(finished.wait(1))
        finally:
            release.set()
            detector.stop()


if __name__ == "__main__":
    unittest.main()

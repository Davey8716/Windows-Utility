import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock

from resurface.features.hover_window_controls.platform.accessibility import AccessibleCaptionTarget
from resurface.features.hover_window_controls.core.hover_controller import CaptionAction
from resurface.features.hover_window_controls.core.hover_controller import (
    DetectionSource,
    HoverProbe,
    HoverTarget,
    ProbeStatus,
)
from resurface.features.hover_window_controls.platform.win32 import (
    ERROR_ACCESS_DENIED,
    ERROR_TIMEOUT,
    HTCLOSE,
    HTMAXBUTTON,
    HTMINBUTTON,
    SC_CLOSE,
    SC_MAXIMIZE,
    SC_MINIMIZE,
    SC_RESTORE,
    WS_EX_LAYOUTRTL,
    WS_MAXIMIZEBOX,
    WS_MINIMIZEBOX,
    WS_SYSMENU,
    SingleInstanceMutex,
    Win32WindowApi,
    action_for_hit_test,
    caption_button_region,
    caption_asset_layout,
    geometry_action_at_point,
    is_caption_point_allowed,
    is_fullscreen_layout,
    is_point_within_caption_buttons,
    is_within_caption_buttons,
    probe_for_hit_test_result,
    resolve_caption_probe,
    system_command_for,
)
from resurface.features.hover_window_controls.vision.detection import (
    ApplicationIdentity,
    VisionContext,
    VisionMatch,
)


class Win32MappingTests(unittest.TestCase):
    def test_export_is_forwarded_to_vision_detector(self):
        api = Win32WindowApi.__new__(Win32WindowApi)
        api._vision = MagicMock()
        expected = MagicMock()
        api._vision.export_all_data.return_value = expected

        result = api.export_all_data(Path("backups"))

        self.assertIs(result, expected)
        api._vision.export_all_data.assert_called_once_with(
            Path("backups")
        )

    def test_open_application_discovery_observes_standard_caption_layout(self):
        api = Win32WindowApi.__new__(Win32WindowApi)
        api._window_bounds = MagicMock(return_value=(0, 0, 800, 600))
        api._window_class = MagicMock(return_value="DiscordWindow")
        api._window_process_id = MagicMock(return_value=42)
        api._get_window_long = MagicMock(
            return_value=WS_SYSMENU | WS_MAXIMIZEBOX | WS_MINIMIZEBOX
        )
        api._window_dpi = MagicMock(return_value=96)
        context = VisionContext(
            100,
            (0, 0, 800, 600),
            96,
            ApplicationIdentity(
                executable_path=r"c:\\apps\\discord.exe",
                executable_version="1",
                friendly_name="Discord",
                window_class="DiscordWindow",
                dpi=96,
                theme="dark",
                caption_side="right",
                window_state="normal",
            ),
        )
        api._vision_context = MagicMock(return_value=context)
        api._caption_metrics = MagicMock(return_value=(45, 30))
        api._is_fullscreen = MagicMock(return_value=False)
        api._caption_button_bounds = MagicMock(return_value=None)
        api._close_is_available = MagicMock(return_value=True)
        api._vision = MagicMock()

        self.assertTrue(api._observe_application_window(100))

        api._vision.observe_caption_assets.assert_called_once()

    def test_hit_tests_map_to_caption_actions(self) -> None:
        self.assertIs(action_for_hit_test(HTMINBUTTON), CaptionAction.MINIMIZE)
        self.assertIs(
            action_for_hit_test(HTMAXBUTTON), CaptionAction.MAXIMIZE_RESTORE
        )
        self.assertIs(action_for_hit_test(HTCLOSE), CaptionAction.CLOSE)
        self.assertIsNone(action_for_hit_test(1))

    def test_actions_map_to_system_commands(self) -> None:
        self.assertEqual(system_command_for(CaptionAction.MINIMIZE), SC_MINIMIZE)
        self.assertEqual(system_command_for(CaptionAction.CLOSE), SC_CLOSE)
        self.assertEqual(
            system_command_for(CaptionAction.MAXIMIZE_RESTORE, False),
            SC_MAXIMIZE,
        )
        self.assertEqual(
            system_command_for(CaptionAction.MAXIMIZE_RESTORE, True),
            SC_RESTORE,
        )

    def test_successful_hit_test_returns_confirmed_target(self) -> None:
        self.assertEqual(
            probe_for_hit_test_result(
                hwnd=100,
                sent=True,
                hit_test=HTCLOSE,
            ),
            HoverProbe.confirmed(
                HoverTarget(100, CaptionAction.CLOSE)
            ),
        )

    def test_timeout_is_transient_for_the_same_window(self) -> None:
        probe = probe_for_hit_test_result(
            hwnd=100,
            sent=False,
            error=ERROR_TIMEOUT,
        )
        self.assertIs(probe.status, ProbeStatus.TRANSIENT_FAILURE)
        self.assertEqual(probe.hwnd, 100)

    def test_unknown_send_failure_is_transient(self) -> None:
        probe = probe_for_hit_test_result(
            hwnd=100,
            sent=False,
            error=0,
        )
        self.assertIs(probe.status, ProbeStatus.TRANSIENT_FAILURE)

    def test_access_denied_is_a_definitive_unsupported_target(self) -> None:
        probe = probe_for_hit_test_result(
            hwnd=100,
            sent=False,
            error=ERROR_ACCESS_DENIED,
        )
        self.assertIs(probe.status, ProbeStatus.NO_TARGET)

    def test_non_caption_hit_is_a_definitive_non_target(self) -> None:
        probe = probe_for_hit_test_result(
            hwnd=100,
            sent=True,
            hit_test=1,
        )
        self.assertIs(probe.status, ProbeStatus.NO_TARGET)

    def test_accessibility_target_overrides_conflicting_native_target(self):
        native = HoverProbe.confirmed(
            HoverTarget(100, CaptionAction.MINIMIZE)
        )
        result = resolve_caption_probe(
            hwnd=100,
            accessible=AccessibleCaptionTarget(
                CaptionAction.CLOSE,
                (9,),
            ),
            vision=VisionMatch(
                CaptionAction.MAXIMIZE_RESTORE,
                (0, 0, 10, 10),
                0.99,
                "vision",
            ),
            native_probe=native,
            geometry_action=CaptionAction.MAXIMIZE_RESTORE,
        )
        self.assertEqual(
            result.target,
            HoverTarget(
                100,
                CaptionAction.CLOSE,
                DetectionSource.ACCESSIBILITY,
                (9,),
            ),
        )

    def test_authoritative_manual_vision_overrides_accessibility(self):
        result = resolve_caption_probe(
            hwnd=100,
            accessible=AccessibleCaptionTarget(
                CaptionAction.CLOSE,
                (9,),
            ),
            vision=VisionMatch(
                CaptionAction.MINIMIZE,
                (0, 0, 40, 40),
                0.99,
                "manual-profile",
            ),
            native_probe=HoverProbe.confirmed(
                HoverTarget(100, CaptionAction.MAXIMIZE_RESTORE)
            ),
            geometry_action=CaptionAction.CLOSE,
            vision_overrides_accessibility=True,
        )
        self.assertEqual(
            result.target,
            HoverTarget(
                100,
                CaptionAction.MINIMIZE,
                DetectionSource.VISION,
                vision_id="manual-profile",
            ),
        )

    def test_native_target_precedes_geometry_fallback(self):
        native = HoverProbe.confirmed(
            HoverTarget(100, CaptionAction.MINIMIZE)
        )
        result = resolve_caption_probe(
            hwnd=100,
            accessible=None,
            vision=None,
            native_probe=native,
            geometry_action=CaptionAction.CLOSE,
        )
        self.assertEqual(result, native)

    def test_calibrated_vision_target_overrides_native_target(self):
        native = HoverProbe.confirmed(
            HoverTarget(100, CaptionAction.MINIMIZE)
        )
        result = resolve_caption_probe(
            hwnd=100,
            accessible=None,
            vision=VisionMatch(
                CaptionAction.CLOSE,
                (0, 0, 40, 40),
                0.99,
                "calibrated-profile",
            ),
            native_probe=native,
            geometry_action=CaptionAction.MAXIMIZE_RESTORE,
        )
        self.assertEqual(
            result.target,
            HoverTarget(
                100,
                CaptionAction.CLOSE,
                DetectionSource.VISION,
                vision_id="calibrated-profile",
            ),
        )


class GeometryFallbackTests(unittest.TestCase):
    BOUNDS = (0, 0, 600, 400)
    STYLE = WS_SYSMENU | WS_MAXIMIZEBOX | WS_MINIMIZEBOX

    def action(self, point, *, dpi=96, style=None, ex_style=0, **kwargs):
        return geometry_action_at_point(
            point=point,
            bounds=self.BOUNDS,
            button_width=30 * dpi // 96,
            button_height=30 * dpi // 96,
            style=self.STYLE if style is None else style,
            ex_style=ex_style,
            close_enabled=kwargs.get("close_enabled", True),
            fullscreen=kwargs.get("fullscreen", False),
        )

    def test_maps_right_anchored_caption_slots(self):
        self.assertIs(self.action((590, 10)), CaptionAction.CLOSE)
        self.assertIs(
            self.action((560, 10)),
            CaptionAction.MAXIMIZE_RESTORE,
        )
        self.assertIs(self.action((530, 10)), CaptionAction.MINIMIZE)

    def test_scales_caption_slots_for_common_dpis(self):
        for dpi in (96, 120, 144, 192):
            slot_width = 30 * dpi // 96
            with self.subTest(dpi=dpi):
                self.assertIs(
                    self.action((600 - slot_width // 2, 5), dpi=dpi),
                    CaptionAction.CLOSE,
                )

    def test_omits_unavailable_maximize_slot(self):
        style = WS_SYSMENU | WS_MINIMIZEBOX
        self.assertIs(self.action((590, 10), style=style), CaptionAction.CLOSE)
        self.assertIs(
            self.action((560, 10), style=style),
            CaptionAction.MINIMIZE,
        )

    def test_supports_right_to_left_layout(self):
        self.assertIs(
            self.action((10, 10), ex_style=WS_EX_LAYOUTRTL),
            CaptionAction.CLOSE,
        )
        self.assertIs(
            self.action((40, 10), ex_style=WS_EX_LAYOUTRTL),
            CaptionAction.MAXIMIZE_RESTORE,
        )

    def test_rejects_points_outside_slots_and_unsafe_windows(self):
        self.assertIsNone(self.action((500, 10)))
        self.assertIsNone(self.action((590, 100)))
        self.assertIsNone(self.action((590, 10), fullscreen=True))
        self.assertIsNone(
            self.action((590, 10), close_enabled=False)
        )
        self.assertIsNone(self.action((590, 10), style=0))

    def test_caption_asset_layout_captures_all_native_buttons(self):
        identity = ApplicationIdentity(
            executable_path=r"c:\windows\explorer.exe",
            executable_version="1",
            friendly_name="explorer",
            window_class="CabinetWClass",
            dpi=96,
            theme="light",
            caption_side="right",
            window_state="normal",
        )
        context = VisionContext(100, self.BOUNDS, 96, identity)
        assignments, statuses, visuals = caption_asset_layout(
            context=context,
            button_width=30,
            button_height=30,
            style=self.STYLE,
            ex_style=0,
            close_enabled=True,
            fullscreen=False,
        )
        self.assertEqual(set(assignments), set(CaptionAction))
        self.assertTrue(
            all(status == "available" for status in statuses.values())
        )
        self.assertEqual(
            visuals[CaptionAction.MAXIMIZE_RESTORE],
            "maximize",
        )

    def test_caption_asset_layout_uses_actual_dwm_button_bounds(self):
        current_identity = ApplicationIdentity(
            executable_path=r"c:\program files\7-zip\7zfm.exe",
            executable_version="1",
            friendly_name="7zfm",
            window_class="7-Zip::FM",
            dpi=96,
            theme="light",
            caption_side="right",
            window_state="normal",
        )
        context = VisionContext(100, self.BOUNDS, 96, current_identity)

        assignments, _statuses, _visuals = caption_asset_layout(
            context=context,
            button_width=30,
            button_height=22,
            style=self.STYLE,
            ex_style=0,
            close_enabled=True,
            fullscreen=False,
            caption_bounds=(462, 0, 600, 32),
        )

        self.assertEqual(
            assignments[CaptionAction.CLOSE],
            (224, 0, 270, 32),
        )
        self.assertEqual(
            assignments[CaptionAction.MAXIMIZE_RESTORE],
            (178, 0, 224, 32),
        )
        self.assertEqual(
            assignments[CaptionAction.MINIMIZE],
            (132, 0, 178, 32),
        )

    def test_caption_asset_layout_marks_missing_controls_unavailable(self):
        identity = ApplicationIdentity(
            executable_path=r"c:\apps\dialog.exe",
            executable_version="1",
            friendly_name="dialog",
            window_class="Dialog",
            dpi=96,
            theme="light",
            caption_side="right",
            window_state="maximized",
        )
        context = VisionContext(100, self.BOUNDS, 96, identity)
        assignments, statuses, visuals = caption_asset_layout(
            context=context,
            button_width=30,
            button_height=30,
            style=WS_SYSMENU,
            ex_style=0,
            close_enabled=True,
            fullscreen=False,
        )
        self.assertEqual(set(assignments), {CaptionAction.CLOSE})
        self.assertEqual(
            statuses[CaptionAction.MAXIMIZE_RESTORE],
            "unavailable",
        )
        self.assertEqual(
            visuals[CaptionAction.MAXIMIZE_RESTORE],
            "restore",
        )

    def test_browser_tab_button_is_outside_native_caption_bounds(self):
        caption_bounds = (462, 0, 600, 32)
        self.assertTrue(
            is_within_caption_buttons(
                (554, 0, 600, 32),
                caption_bounds,
            )
        )
        self.assertTrue(
            is_point_within_caption_buttons(
                (575, 16),
                caption_bounds,
            )
        )
        self.assertFalse(
            is_point_within_caption_buttons(
                (260, 14),
                caption_bounds,
            )
        )
        self.assertFalse(
            is_within_caption_buttons(
                (250, 4, 270, 24),
                caption_bounds,
            )
        )

    def test_missing_native_caption_bounds_is_not_itself_active(self):
        self.assertFalse(
            is_point_within_caption_buttons(
                (260, 14),
                None,
            )
        )

    def test_missing_native_bounds_uses_strict_top_corner_region(self):
        region = caption_button_region(
            bounds=self.BOUNDS,
            button_width=30,
            button_height=30,
            style=self.STYLE,
            ex_style=0,
            close_enabled=True,
            fullscreen=False,
            native_bounds=None,
        )
        self.assertEqual(region, (510, 0, 600, 30))
        self.assertTrue(is_point_within_caption_buttons((590, 10), region))
        self.assertFalse(is_point_within_caption_buttons((500, 10), region))
        self.assertFalse(is_point_within_caption_buttons((590, 40), region))

    def test_native_caption_region_takes_precedence(self):
        native_bounds = (462, 0, 600, 32)
        self.assertEqual(
            caption_button_region(
                bounds=self.BOUNDS,
                button_width=30,
                button_height=30,
                style=self.STYLE,
                ex_style=0,
                close_enabled=True,
                fullscreen=False,
                native_bounds=native_bounds,
            ),
            native_bounds,
        )

    def test_native_hit_is_allowed_outside_estimated_region(self):
        native = HoverProbe.confirmed(
            HoverTarget(100, CaptionAction.CLOSE)
        )
        self.assertTrue(
            is_caption_point_allowed(
                (250, 14),
                (510, 0, 600, 30),
                native,
            )
        )

    def test_non_native_hit_is_rejected_outside_corner_region(self):
        self.assertFalse(
            is_caption_point_allowed(
                (250, 14),
                (510, 0, 600, 30),
                HoverProbe.no_target(100),
            )
        )

    def test_maximized_layout_is_not_treated_as_fullscreen(self):
        monitor_bounds = (0, 0, 1920, 1080)
        self.assertFalse(
            is_fullscreen_layout(
                bounds=monitor_bounds,
                monitor_bounds=monitor_bounds,
                is_zoomed=True,
            )
        )

    def test_borderless_monitor_sized_layout_is_fullscreen(self):
        monitor_bounds = (0, 0, 1920, 1080)
        self.assertTrue(
            is_fullscreen_layout(
                bounds=monitor_bounds,
                monitor_bounds=monitor_bounds,
                is_zoomed=False,
            )
        )

    def test_restored_layout_is_not_fullscreen(self):
        self.assertFalse(
            is_fullscreen_layout(
                bounds=(100, 100, 1200, 800),
                monitor_bounds=(0, 0, 1920, 1080),
                is_zoomed=False,
            )
        )


@unittest.skipUnless(os.name == "nt", "Windows mutex integration test")
class SingleInstanceMutexTests(unittest.TestCase):
    def test_only_one_mutex_owner_at_a_time(self) -> None:
        name = rf"Local\NoClickMinMaxRestore.Test.{uuid.uuid4()}"
        first = SingleInstanceMutex(name)
        second = SingleInstanceMutex(name)
        third = SingleInstanceMutex(name)
        try:
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.close()
            self.assertTrue(third.acquire())
        finally:
            first.close()
            second.close()
            third.close()


if __name__ == "__main__":
    unittest.main()

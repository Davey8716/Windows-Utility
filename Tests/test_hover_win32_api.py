import os
import ctypes
import unittest
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
    CalibrationCaptureResult,
    CalibrationTarget,
    Win32WindowApi,
    action_for_hit_test,
    caption_button_region,
    caption_asset_layout,
    geometry_action_at_point,
    is_caption_point_allowed,
    is_fullscreen_layout,
    is_point_within_caption_buttons,
    is_within_caption_buttons,
    hwnd_value,
    probe_for_hit_test_result,
    resolve_caption_probe,
    sort_calibration_targets,
    system_command_for,
)
from resurface.features.hover_window_controls.vision.detection import (
    ApplicationIdentity,
    VisionContext,
    VisionMatch,
)


class Win32MappingTests(unittest.TestCase):
    def test_hwnd_value_accepts_ctypes_pointer_handles(self):
        self.assertEqual(hwnd_value(ctypes.c_void_p(0x170)), 0x170)
        self.assertEqual(hwnd_value(ctypes.c_void_p()), 0)
        self.assertEqual(hwnd_value(0x170), 0x170)

    def test_same_process_window_requires_explicit_matching_handle(self):
        api = Win32WindowApi.__new__(Win32WindowApi)
        api._allowed_self_hwnd_provider = None

        self.assertTrue(api._is_window_eligible(100, os.getpid() + 1))
        self.assertFalse(api._is_window_eligible(100, os.getpid()))

        api._allowed_self_hwnd_provider = lambda: 100
        self.assertTrue(api._is_window_eligible(100, os.getpid()))
        self.assertFalse(api._is_window_eligible(101, os.getpid()))

    def test_same_process_provider_failure_is_safely_rejected(self):
        api = Win32WindowApi.__new__(Win32WindowApi)
        api._allowed_self_hwnd_provider = lambda: (_ for _ in ()).throw(
            RuntimeError("window destroyed")
        )

        self.assertFalse(api._is_window_eligible(100, os.getpid()))

    def test_calibration_targets_include_only_approved_self_window(self):
        api = Win32WindowApi.__new__(Win32WindowApi)
        api._user32 = MagicMock()
        api._user32.IsWindowVisible.return_value = True
        api._user32.IsIconic.return_value = False
        api._user32.EnumWindows.side_effect = lambda callback, _data: [
            callback(hwnd, 0) for hwnd in (100, 101, 200)
        ]
        api._enum_windows_callback_type = lambda callback: callback
        api._get_window_long = MagicMock(return_value=0)
        api._window_class = MagicMock(return_value="QtWindow")
        api._window_title = MagicMock(side_effect=lambda hwnd: f"Window {hwnd}")
        api._window_bounds = MagicMock(return_value=(0, 0, 600, 400))
        api._window_process_id = MagicMock(
            side_effect=lambda hwnd: (
                os.getpid() if int(hwnd) < 200 else os.getpid() + 1
            )
        )
        api._process_metadata = MagicMock(
            return_value=(r"c:\apps\example.exe", "1", "Example")
        )
        api._allowed_self_hwnd_provider = lambda: 100

        targets = api.list_calibration_targets()

        self.assertEqual([target.hwnd for target in targets], [100, 200])

    def test_discovery_lists_only_eligible_visible_top_level_windows(self):
        api = Win32WindowApi.__new__(Win32WindowApi)
        api._user32 = MagicMock()
        api._user32.IsWindowVisible.return_value = True
        api._user32.IsIconic.return_value = False
        api._user32.EnumWindows.side_effect = lambda callback, _data: [
            callback(hwnd, 0) for hwnd in (100, 200, 300)
        ]
        api._enum_windows_callback_type = lambda callback: callback
        api._get_window_long = MagicMock(return_value=0)
        api._window_class = MagicMock(
            side_effect=lambda hwnd: "Shell_TrayWnd" if hwnd == 200 else "App"
        )
        api._window_title = MagicMock(
            side_effect=lambda hwnd: "" if hwnd == 300 else f"Window {hwnd}"
        )
        api._window_process_id = MagicMock(return_value=900)
        api._is_window_eligible = MagicMock(return_value=True)
        api._process_metadata = MagicMock(
            return_value=(r"c:\\apps\\example.exe", "1", "Example")
        )
        api._window_bounds = MagicMock(return_value=(0, 0, 600, 400))

        assert api.list_open_discovery_windows() == [100]

    def test_live_probe_rejects_unapproved_same_process_window_early(self):
        api = Win32WindowApi.__new__(Win32WindowApi)
        api._user32 = MagicMock()

        def set_cursor(point):
            point._obj.x = 10
            point._obj.y = 10
            return True

        api._user32.GetCursorPos.side_effect = set_cursor
        api._user32.WindowFromPoint.return_value = 101
        api._user32.GetAncestor.return_value = 101
        api._window_class = MagicMock(return_value="QtDialog")
        api._window_process_id = MagicMock(return_value=os.getpid())
        api._window_bounds = MagicMock()
        api._allowed_self_hwnd_provider = lambda: 100

        result = api.probe_at_cursor()

        self.assertIs(result.status, ProbeStatus.NO_TARGET)
        self.assertEqual(result.hwnd, 101)
        api._window_bounds.assert_not_called()

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

    def test_calibration_targets_are_sorted_without_deduplication(self):
        targets = [
            CalibrationTarget(30, "Example", "Second"),
            CalibrationTarget(20, "example", "First"),
            CalibrationTarget(10, "Example", "First"),
        ]
        self.assertEqual(
            [target.hwnd for target in sort_calibration_targets(targets)],
            [10, 20, 30],
        )
        self.assertEqual(targets[0].label, "Example — Second")

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

    def test_live_capture_reports_stale_and_identity_failures(self):
        api = Win32WindowApi.__new__(Win32WindowApi)
        api._user32 = MagicMock()
        api._user32.IsWindow.return_value = False

        stale = api.capture_vision_calibration(100)

        self.assertFalse(stale.succeeded)
        self.assertIn("no longer available", stale.error)

        api._user32.IsWindow.return_value = True
        api._user32.IsWindowVisible.return_value = True
        api._user32.IsIconic.return_value = False
        api._window_class = MagicMock(return_value="ExampleWindow")
        api._window_bounds = MagicMock(return_value=(0, 0, 600, 400))
        api._window_process_id = MagicMock(return_value=123)
        api._get_window_long = MagicMock(return_value=0)
        api._window_dpi = MagicMock(return_value=96)
        api._vision_context = MagicMock(return_value=None)

        missing_identity = api.capture_vision_calibration(100)

        self.assertFalse(missing_identity.succeeded)
        self.assertIn("identity", missing_identity.error)

    def test_live_capture_rejects_unapproved_same_process_window(self):
        api = Win32WindowApi.__new__(Win32WindowApi)
        api._user32 = MagicMock()
        api._user32.IsWindow.return_value = True
        api._user32.IsWindowVisible.return_value = True
        api._user32.IsIconic.return_value = False
        api._window_class = MagicMock(return_value="QtDialog")
        api._window_bounds = MagicMock(return_value=(0, 0, 600, 400))
        api._window_process_id = MagicMock(return_value=os.getpid())
        api._allowed_self_hwnd_provider = lambda: 200

        result = api.capture_vision_calibration(100)

        self.assertFalse(result.succeeded)
        self.assertIn("cannot be calibrated", result.error)

    def test_live_capture_reports_protected_capture_and_success(self):
        api = Win32WindowApi.__new__(Win32WindowApi)
        api._user32 = MagicMock()
        api._user32.IsWindow.return_value = True
        api._user32.IsWindowVisible.return_value = True
        api._user32.IsIconic.return_value = False
        api._window_class = MagicMock(return_value="ExampleWindow")
        api._window_bounds = MagicMock(return_value=(0, 0, 600, 400))
        api._window_process_id = MagicMock(return_value=123)
        api._get_window_long = MagicMock(return_value=0)
        api._window_dpi = MagicMock(return_value=96)
        context = VisionContext(
            100,
            (0, 0, 600, 400),
            96,
            ApplicationIdentity(
                executable_path=r"c:\apps\example.exe",
                executable_version="1",
                friendly_name="Example",
                window_class="ExampleWindow",
                dpi=96,
                theme="light",
                caption_side="right",
                window_state="normal",
            ),
        )
        api._vision_context = MagicMock(return_value=context)
        api._vision = MagicMock()
        api._vision.snapshot.return_value = None

        protected = api.capture_vision_calibration(100)

        self.assertFalse(protected.succeeded)
        self.assertIn("Protected", protected.error)

        snapshot = MagicMock()
        api._vision.snapshot.return_value = snapshot
        success = api.capture_vision_calibration(100)
        self.assertEqual(
            success,
            CalibrationCaptureResult(snapshot=snapshot),
        )
        self.assertTrue(success.succeeded)

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
if __name__ == "__main__":
    unittest.main()

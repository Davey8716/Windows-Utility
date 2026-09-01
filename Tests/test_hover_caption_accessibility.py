import threading
import time
import unittest

from resurface.features.hover_window_controls.platform.accessibility import (
    AccessibilityProbe,
    CaptionAccessibilityDetector,
    _ProbeRequest,
    action_from_accessible_metadata,
)
from resurface.features.hover_window_controls.ui.calibration import validate_assignments
from resurface.features.hover_window_controls.core.hover_controller import CaptionAction


class FakeBounds:
    def __init__(self, left=400, top=0, right=450, bottom=32):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class FakeControl:
    def __init__(
        self,
        *,
        name="",
        automation_id="",
        class_name="",
        help_text="",
        runtime_id=(1,),
        process_id=100,
        control_type=50000,
        enabled=True,
        offscreen=False,
        bounds=None,
        native_hwnd=0,
        parent=None,
    ):
        self.Name = name
        self.AutomationId = automation_id
        self.ClassName = class_name
        self.HelpText = help_text
        self.ProcessId = process_id
        self.ControlType = control_type
        self.IsEnabled = enabled
        self.IsOffscreen = offscreen
        self.BoundingRectangle = bounds or FakeBounds()
        self.NativeWindowHandle = native_hwnd
        self._runtime_id = runtime_id
        self._parent = parent

    def GetRuntimeId(self):
        return self._runtime_id

    def GetParentControl(self):
        return self._parent


class FakeAutomation:
    def __init__(self, control):
        self.control = control

    def ControlFromPoint(self, *_point):
        return self.control


def request_for(control):
    return FakeAutomation(control), _ProbeRequest(
        point=(425, 16),
        root_hwnd=500,
        process_id=100,
        root_bounds=(0, 0, 500, 300),
        caption_band_height=64,
        completed=threading.Event(),
    )


class AccessibilityMetadataTests(unittest.TestCase):
    def test_maps_exact_caption_metadata(self):
        cases = {
            "Minimize": CaptionAction.MINIMIZE,
            "PART_MaximizeButton": CaptionAction.MAXIMIZE_RESTORE,
            "Restore button": CaptionAction.MAXIMIZE_RESTORE,
            "WindowCloseButton": CaptionAction.CLOSE,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertIs(
                    action_from_accessible_metadata([value]),
                    expected,
                )

    def test_rejects_partial_and_ambiguous_metadata(self):
        self.assertIsNone(
            action_from_accessible_metadata(["Close document"])
        )
        self.assertIsNone(
            action_from_accessible_metadata(["Close", "Minimize"])
        )

    def test_detects_parent_button_with_exact_runtime_id(self):
        root = FakeControl(control_type=50032, native_hwnd=500)
        button = FakeControl(
            automation_id="btnClose",
            runtime_id=(4, 5),
            parent=root,
        )
        leaf = FakeControl(
            control_type=50020,
            bounds=FakeBounds(410, 8, 440, 24),
            parent=button,
        )
        automation, request = request_for(leaf)
        result = CaptionAccessibilityDetector._probe_current(
            automation,
            request,
        )
        self.assertEqual(result.target.action, CaptionAction.CLOSE)
        self.assertEqual(result.target.runtime_id, (4, 5))
        self.assertEqual(result.target.rect, (400, 0, 450, 32))

    def test_rejects_wrong_root_process_and_non_caption_bounds(self):
        cases = [
            FakeControl(name="Close", process_id=999, native_hwnd=500),
            FakeControl(name="Close", native_hwnd=999),
            FakeControl(
                name="Close",
                bounds=FakeBounds(400, 100, 450, 132),
                native_hwnd=500,
            ),
        ]
        for control in cases:
            with self.subTest(control=control):
                automation, request = request_for(control)
                result = CaptionAccessibilityDetector._probe_current(
                    automation,
                    request,
                )
                self.assertIsNone(result.target)
                self.assertFalse(result.transient)

    def test_rejects_disabled_offscreen_and_missing_runtime_id(self):
        cases = [
            FakeControl(name="Close", enabled=False, native_hwnd=500),
            FakeControl(name="Close", offscreen=True, native_hwnd=500),
            FakeControl(name="Close", runtime_id=(), native_hwnd=500),
        ]
        for control in cases:
            with self.subTest(control=control):
                automation, request = request_for(control)
                result = CaptionAccessibilityDetector._probe_current(
                    automation,
                    request,
                )
                self.assertIsNone(result.target)


class BlockingDetector(CaptionAccessibilityDetector):
    def __init__(self):
        super().__init__(shutdown_timeout_s=0.01)
        self.entered = threading.Event()
        self.release = threading.Event()

    def _run(self):
        self.entered.set()
        self.release.wait(1)


class AccessibilityWorkerTests(unittest.TestCase):
    def test_shutdown_is_bounded_when_provider_is_busy(self):
        detector = BlockingDetector()
        detector.start()
        self.assertTrue(detector.entered.wait(1))
        started = time.monotonic()
        detector.stop()
        self.assertLess(time.monotonic() - started, 0.5)
        detector.release.set()
        detector.stop()

    def test_unavailable_probe_is_explicitly_transient(self):
        self.assertTrue(AccessibilityProbe.unavailable().transient)


class CalibrationValidationTests(unittest.TestCase):
    def test_accepts_non_overlapping_labelled_buttons(self):
        self.assertIsNone(
            validate_assignments(
                {
                    CaptionAction.MINIMIZE: (0, 0, 30, 30),
                    CaptionAction.CLOSE: (60, 0, 90, 30),
                },
                (100, 40),
            )
        )

    def test_rejects_empty_out_of_bounds_and_overlapping_boxes(self):
        self.assertIsNotNone(validate_assignments({}, (100, 40)))
        self.assertIsNotNone(
            validate_assignments(
                {CaptionAction.CLOSE: (80, 0, 110, 30)},
                (100, 40),
            )
        )
        self.assertIsNotNone(
            validate_assignments(
                {
                    CaptionAction.CLOSE: (40, 0, 80, 30),
                    CaptionAction.MINIMIZE: (60, 0, 90, 30),
                },
                (100, 40),
            )
        )


if __name__ == "__main__":
    unittest.main()

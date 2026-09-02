import unittest
from unittest.mock import patch

from resurface.features.hover_window_controls.core.hover_controller import (
    CaptionAction,
    DetectionSource,
    HoverController,
    HoverDecisionEngine,
    HoverProbe,
    HoverTarget,
)


class HoverDecisionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = HoverDecisionEngine(dwell_ms=750)
        self.close = HoverTarget(100, CaptionAction.CLOSE)
        self.minimize = HoverTarget(100, CaptionAction.MINIMIZE)

    @staticmethod
    def probe(target):
        return HoverProbe.confirmed(target)

    def test_fires_after_continuous_dwell(self) -> None:
        self.assertIsNone(self.engine.observe(self.probe(self.close), 0))
        self.assertIsNone(self.engine.observe(self.probe(self.close), 749))
        self.assertEqual(
            self.engine.observe(self.probe(self.close), 750),
            self.close,
        )

    def test_moving_away_cancels_dwell(self) -> None:
        self.engine.observe(self.probe(self.close), 0)
        self.engine.observe(HoverProbe.no_target(100), 700)
        self.assertIsNone(self.engine.observe(self.probe(self.close), 800))
        self.assertIsNone(self.engine.observe(self.probe(self.close), 1549))
        self.assertEqual(
            self.engine.observe(self.probe(self.close), 1550),
            self.close,
        )

    def test_changing_button_restarts_dwell(self) -> None:
        self.engine.observe(self.probe(self.close), 0)
        self.assertIsNone(
            self.engine.observe(self.probe(self.minimize), 700)
        )
        self.assertIsNone(
            self.engine.observe(self.probe(self.minimize), 1449)
        )
        self.assertEqual(
            self.engine.observe(self.probe(self.minimize), 1450),
            self.minimize,
        )

    def test_fires_only_once_until_pointer_leaves_button(self) -> None:
        self.engine.observe(self.probe(self.close), 0)
        self.assertEqual(
            self.engine.observe(self.probe(self.close), 750),
            self.close,
        )
        self.engine.commit(self.close)
        self.assertIsNone(
            self.engine.observe(self.probe(self.close), 1500)
        )
        self.assertIsNone(
            self.engine.observe(self.probe(self.close), 3000)
        )

        self.engine.observe(HoverProbe.no_target(100), 3001)
        self.engine.observe(self.probe(self.close), 3002)
        self.assertEqual(
            self.engine.observe(self.probe(self.close), 3752),
            self.close,
        )

    def test_moving_to_another_button_rearms_previous_button(self) -> None:
        self.engine.observe(self.probe(self.close), 0)
        self.engine.observe(self.probe(self.close), 750)
        self.engine.commit(self.close)
        self.engine.observe(self.probe(self.minimize), 800)
        self.engine.observe(self.probe(self.close), 900)
        self.assertEqual(
            self.engine.observe(self.probe(self.close), 1650),
            self.close,
        )

    def test_reset_clears_candidate_and_latch(self) -> None:
        self.engine.observe(self.probe(self.close), 0)
        self.engine.observe(self.probe(self.close), 750)
        self.engine.commit(self.close)
        self.engine.reset()
        self.assertIsNone(
            self.engine.observe(self.probe(self.close), 800)
        )

    def test_changing_dwell_resets_progress_and_uses_new_delay(self) -> None:
        self.assertIsNone(self.engine.observe(self.probe(self.close), 0))
        self.engine.set_dwell_ms(500)
        self.assertIsNone(self.engine.observe(self.probe(self.close), 400))
        self.assertIsNone(self.engine.observe(self.probe(self.close), 899))
        self.assertEqual(
            self.engine.observe(self.probe(self.close), 900),
            self.close,
        )

    def test_brief_transient_failure_preserves_dwell(self) -> None:
        self.engine.observe(self.probe(self.close), 0)
        self.engine.observe(HoverProbe.transient(100), 700)
        self.assertEqual(
            self.engine.observe(self.probe(self.close), 750),
            self.close,
        )

    def test_extended_transient_failure_resets_dwell(self) -> None:
        self.engine.observe(self.probe(self.close), 0)
        self.engine.observe(HoverProbe.transient(100), 600)
        self.engine.observe(HoverProbe.transient(100), 801)
        self.assertIsNone(
            self.engine.observe(self.probe(self.close), 802)
        )
        self.assertEqual(
            self.engine.observe(self.probe(self.close), 1552),
            self.close,
        )

    def test_transient_failure_on_different_window_resets_immediately(self):
        self.engine.observe(self.probe(self.close), 0)
        self.engine.observe(HoverProbe.transient(200), 700)
        self.assertIsNone(
            self.engine.observe(self.probe(self.close), 750)
        )

    def test_transient_failures_cannot_begin_a_dwell(self) -> None:
        self.engine.observe(HoverProbe.transient(100), 0)
        self.engine.observe(HoverProbe.transient(100), 750)
        self.assertIsNone(
            self.engine.observe(self.probe(self.close), 800)
        )

    def test_decision_repeats_until_committed(self) -> None:
        self.engine.observe(self.probe(self.close), 0)
        self.assertEqual(
            self.engine.observe(self.probe(self.close), 750),
            self.close,
        )
        self.assertEqual(
            self.engine.observe(self.probe(self.close), 800),
            self.close,
        )
        self.engine.commit(self.close)
        self.assertIsNone(
            self.engine.observe(self.probe(self.close), 850)
        )

    def test_transient_failure_does_not_rearm_latched_target(self) -> None:
        self.engine.observe(self.probe(self.close), 0)
        self.engine.observe(self.probe(self.close), 750)
        self.engine.commit(self.close)
        self.engine.observe(HoverProbe.transient(100), 1000)
        self.assertIsNone(
            self.engine.observe(self.probe(self.close), 1100)
        )

    def test_accessibility_runtime_id_change_restarts_dwell(self) -> None:
        first = HoverTarget(
            100,
            CaptionAction.CLOSE,
            DetectionSource.ACCESSIBILITY,
            (1,),
        )
        second = HoverTarget(
            100,
            CaptionAction.CLOSE,
            DetectionSource.ACCESSIBILITY,
            (2,),
        )
        self.engine.observe(self.probe(first), 0)
        self.engine.observe(self.probe(second), 700)
        self.assertIsNone(self.engine.observe(self.probe(second), 1449))
        self.assertEqual(
            self.engine.observe(self.probe(second), 1450),
            second,
        )

    def test_vision_profile_change_restarts_dwell(self) -> None:
        first = HoverTarget(
            100,
            CaptionAction.CLOSE,
            DetectionSource.VISION,
            vision_id="profile-a",
        )
        second = HoverTarget(
            100,
            CaptionAction.CLOSE,
            DetectionSource.VISION,
            vision_id="profile-b",
        )
        self.engine.observe(self.probe(first), 0)
        self.engine.observe(self.probe(second), 700)
        self.assertIsNone(self.engine.observe(self.probe(second), 1449))
        self.assertEqual(
            self.engine.observe(self.probe(second), 1450),
            second,
        )


class FakeWindowApi:
    def __init__(self, samples, available=True, execute_result=True):
        self.samples = iter(samples)
        self.available = available
        self.execute_result = execute_result
        self.executed = []
        self.timeouts = []

    def probe_at_cursor(self, timeout_ms=None):
        self.timeouts.append(timeout_ms)
        sample = next(self.samples)
        if isinstance(sample, BaseException):
            raise sample
        return sample

    def is_action_available(self, target):
        return self.available

    def execute(self, target):
        self.executed.append(target)
        return self.execute_result


class FakeAuxiliaryMonitor:
    def __init__(self):
        self.controlled = False
        self.calls = []

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")

    def suspend(self):
        self.calls.append("suspend")

    def resume(self):
        self.calls.append("resume")

    def set_dwell_ms(self, dwell_ms):
        self.calls.append(("dwell", dwell_ms))

    def pointer_is_controlled(self):
        return self.controlled


class HoverControllerFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.close = HoverTarget(100, CaptionAction.CLOSE)
        self.close_probe = HoverProbe.confirmed(self.close)

    def test_unavailable_action_is_not_executed(self) -> None:
        api = FakeWindowApi(
            [self.close_probe, self.close_probe, self.close_probe],
            available=False,
        )
        controller = HoverController(api, dwell_ms=0)
        with patch(
            "resurface.features.hover_window_controls.core.hover_controller.time.monotonic",
            return_value=1,
        ):
            controller._poll()
            controller._poll()
        self.assertEqual(api.executed, [])

    def test_target_is_rechecked_before_execution(self) -> None:
        api = FakeWindowApi(
            [
                self.close_probe,
                self.close_probe,
                HoverProbe.no_target(100),
            ]
        )
        controller = HoverController(api, dwell_ms=0)
        with patch(
            "resurface.features.hover_window_controls.core.hover_controller.time.monotonic",
            return_value=1,
        ):
            controller._poll()
            controller._poll()
        self.assertEqual(api.executed, [])

    def test_native_sampling_error_is_ignored(self) -> None:
        api = FakeWindowApi([OSError("timed out")])
        controller = HoverController(api, dwell_ms=0)
        controller._poll()
        self.assertEqual(api.executed, [])

    def test_transient_final_probe_retries_without_pointer_exit(self) -> None:
        api = FakeWindowApi(
            [
                self.close_probe,
                self.close_probe,
                HoverProbe.transient(100),
                self.close_probe,
                self.close_probe,
            ]
        )
        controller = HoverController(api, dwell_ms=0)
        with patch(
            "resurface.features.hover_window_controls.core.hover_controller.time.monotonic",
            return_value=1,
        ):
            controller._poll()
            controller._poll()
            controller._poll()
        self.assertEqual(api.executed, [self.close])
        self.assertEqual(api.timeouts, [None, None, 250, None, 250])

    def test_failed_post_does_not_latch_target(self) -> None:
        api = FakeWindowApi(
            [
                self.close_probe,
                self.close_probe,
                self.close_probe,
                self.close_probe,
                self.close_probe,
            ],
            execute_result=False,
        )
        controller = HoverController(api, dwell_ms=0)
        with patch(
            "resurface.features.hover_window_controls.core.hover_controller.time.monotonic",
            return_value=1,
        ):
            controller._poll()
            controller._poll()
            controller._poll()
        self.assertEqual(api.executed, [self.close, self.close])

    def test_auxiliary_monitor_receives_lifecycle_and_dwell_updates(self):
        api = FakeWindowApi([])
        api.start = lambda: None
        api.stop = lambda: None
        auxiliary = FakeAuxiliaryMonitor()
        controller = HoverController(api, auxiliary_monitor=auxiliary)

        controller.start()
        controller.suspend()
        controller.resume()
        controller.set_dwell_ms(1000)
        controller.stop()

        self.assertEqual(
            auxiliary.calls,
            ["start", "suspend", "resume", ("dwell", 1000), "stop"],
        )

    def test_caption_poll_is_suppressed_during_pointer_control(self):
        api = FakeWindowApi([self.close_probe])
        auxiliary = FakeAuxiliaryMonitor()
        auxiliary.controlled = True
        controller = HoverController(api, auxiliary_monitor=auxiliary)

        controller._poll()

        self.assertEqual(api.timeouts, [])
        self.assertEqual(api.executed, [])

    def test_caption_poll_can_pause_without_stopping_auxiliary_monitor(self):
        api = FakeWindowApi([])
        api.start = lambda: None
        auxiliary = FakeAuxiliaryMonitor()
        controller = HoverController(api, auxiliary_monitor=auxiliary)

        controller.start()
        controller.set_caption_controls_enabled(False)

        self.assertEqual(auxiliary.calls, ["start"])
        self.assertFalse(controller._timer.isActive())


if __name__ == "__main__":
    unittest.main()

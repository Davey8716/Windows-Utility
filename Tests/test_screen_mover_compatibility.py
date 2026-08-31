from resurface.features.screen_mover import (
    dock_overlay,
    screen_mover,
    service,
    window_actions,
)


def test_legacy_module_reexports_canonical_screen_mover_objects():
    assert screen_mover.ScreenMover is service.ScreenMover
    assert screen_mover.ScreenMoverWorker is service.ScreenMoverWorker
    assert screen_mover.DockOverlayButton is dock_overlay.DockOverlayButton
    assert screen_mover.perform_window_action is window_actions.perform_window_action
    assert screen_mover.SCREEN_MOVER is service.SCREEN_MOVER

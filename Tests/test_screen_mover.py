import threading
import time

import screen_mover


def wait_until(predicate, timeout=1.5, interval=0.01):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class FakeListener:
    instances = []

    def __init__(self, on_click):
        self.on_click = on_click
        self.started = False
        self.stopped = False
        type(self).instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FakeOverlay:
    def __init__(self, target_hwnd=None, direction=None):
        self.target_hwnd = target_hwnd
        self.rect = (0, 0, 10, 10)
        self.visible = True
        self.direction = direction
        self.hit_test_threads = []
        self.hide_threads = []
        self.destroy_threads = []

    def hit_test(self, x, y):
        self.hit_test_threads.append(threading.current_thread().name)
        return self.direction

    def hide(self):
        self.hide_threads.append(threading.current_thread().name)
        self.target_hwnd = None
        self.rect = None
        self.visible = False

    def destroy(self):
        self.destroy_threads.append(threading.current_thread().name)


def test_screen_mover_clicks_are_processed_on_worker_thread(monkeypatch):
    FakeListener.instances = []
    monkeypatch.setattr(
        screen_mover,
        "load_state",
        lambda: {
            "title_bar_dock_enabled": True,
            "screen_mover_activation_button": "middle",
        },
    )
    monkeypatch.setattr(screen_mover.mouse, "Listener", FakeListener)

    external_actions = []
    monkeypatch.setattr(
        screen_mover,
        "perform_window_action",
        lambda hwnd, action: external_actions.append((hwnd, action)),
    )

    dispatch_calls = []
    dispatch_event = threading.Event()

    worker = screen_mover.ScreenMoverWorker()
    worker.dock_overlay = FakeOverlay(target_hwnd=101, direction="MAXIMIZE")
    worker._pump_messages = lambda: None
    worker._update_title_bar_dock = lambda: None
    worker.configure(
        app_hwnd=101,
        self_action_dispatch=lambda action: (
            dispatch_calls.append((action, threading.current_thread().name)),
            dispatch_event.set(),
        ),
    )

    worker.start()
    assert FakeListener.instances and FakeListener.instances[0].started

    worker.on_mouse_click(5, 5, screen_mover.mouse.Button.middle, True)

    assert dispatch_event.wait(1.0)
    assert dispatch_calls == [("MAXIMIZE", "ScreenMoverWorker")]
    assert worker.dock_overlay.hide_threads
    assert worker.dock_overlay.hide_threads[0] == "ScreenMoverWorker"
    assert external_actions == []

    worker.stop()
    assert wait_until(lambda: worker.thread is None)
    assert worker.dock_overlay.destroy_threads == ["ScreenMoverWorker"]


def test_screen_mover_stop_keeps_thread_reference_until_worker_exits(monkeypatch):
    FakeListener.instances = []
    monkeypatch.setattr(
        screen_mover,
        "load_state",
        lambda: {
            "title_bar_dock_enabled": True,
            "screen_mover_activation_button": "middle",
        },
    )
    monkeypatch.setattr(screen_mover.mouse, "Listener", FakeListener)

    entered_pump = threading.Event()
    allow_exit = threading.Event()

    worker = screen_mover.ScreenMoverWorker()
    worker.dock_overlay = FakeOverlay()

    def blocking_pump():
        entered_pump.set()
        allow_exit.wait(5.0)

    worker._pump_messages = blocking_pump
    worker._update_title_bar_dock = lambda: None
    worker.configure(app_hwnd=101, self_action_dispatch=lambda action: None)

    worker.start()
    assert entered_pump.wait(1.0)
    assert FakeListener.instances and FakeListener.instances[0].started

    thread_obj = worker.thread
    original_join = thread_obj.join
    thread_obj.join = lambda timeout=None: None

    worker.stop()

    assert FakeListener.instances[0].stopped
    assert worker.mouse_listener is None
    assert worker.thread is thread_obj
    assert worker.dock_overlay.destroy_threads == []

    thread_obj.join = original_join
    allow_exit.set()
    original_join(1.0)

    assert wait_until(lambda: worker.thread is None)
    assert worker.dock_overlay.destroy_threads == ["ScreenMoverWorker"]

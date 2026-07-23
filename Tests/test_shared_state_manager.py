import json
import threading

import state_manager
from Shared.shared_state_manager import JsonStateManager


def test_json_state_manager_handles_concurrent_load_and_save(tmp_path):
    config_path = tmp_path / "app_state.json"
    defaults = {
        "counter": 0,
        "nested": {"enabled": False},
    }
    manager = JsonStateManager(
        app_dir_name="Windows Resurface Test",
        config_filename="app_state.json",
        defaults=defaults,
        config_path_resolver=lambda: config_path,
    )

    barrier = threading.Barrier(6)
    errors = []

    def writer(seed):
        barrier.wait()
        for offset in range(60):
            manager.save_state(
                {
                    "counter": (seed * 1000) + offset,
                    "nested": {"enabled": bool(offset % 2)},
                }
            )

    def reader():
        barrier.wait()
        for _ in range(120):
            state = manager.load_state()
            if not isinstance(state.get("counter"), int):
                errors.append(("counter", state))
            nested = state.get("nested")
            if not isinstance(nested, dict):
                errors.append(("nested", state))
                continue
            if not isinstance(nested.get("enabled"), bool):
                errors.append(("enabled", state))

    threads = [
        threading.Thread(target=writer, args=(index,), daemon=True)
        for index in range(3)
    ] + [
        threading.Thread(target=reader, daemon=True)
        for _ in range(3)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []

    with open(config_path, "r", encoding="utf-8") as file_obj:
        persisted = json.load(file_obj)

    assert isinstance(persisted, dict)
    assert isinstance(persisted["counter"], int)
    assert isinstance(persisted["nested"]["enabled"], bool)
    assert list(tmp_path.glob("*.tmp")) == []


def test_windows_resurface_state_fills_missing_screen_mover_hotkeys(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "app_state.json"
    config_path.write_text(
        json.dumps(
            {
                "screen_mover_keyboard_hotkeys": {
                    "LEFT": "<ctrl>+<left>",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(state_manager, "get_config_path", lambda: config_path)
    monkeypatch.setattr(
        state_manager,
        "LEGACY_CONFIG_PATH",
        tmp_path / "missing-legacy.json",
    )

    loaded = state_manager.load_state()

    assert loaded["screen_mover_keyboard_hotkeys"] == {
        "FAR_LEFT": "",
        "LEFT": "<ctrl>+<left>",
        "RIGHT": "",
        "FAR_RIGHT": "",
        "MINIMIZE": "",
        "MAXIMIZE": "",
    }

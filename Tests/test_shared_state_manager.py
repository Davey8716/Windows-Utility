import json
import threading

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

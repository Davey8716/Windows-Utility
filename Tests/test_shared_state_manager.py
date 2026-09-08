import json
import multiprocessing
import threading
import time
from pathlib import Path

from resurface.core import state_manager
from Shared.shared_state_manager import JsonStateManager, _interprocess_file_lock


def _write_owned_state(config_path, owned_key, value, barrier, iterations):
    manager = JsonStateManager(
        app_dir_name="Cross Process Test",
        config_filename="app_state.json",
        defaults={"resurface": 0, "folder_creator": 0},
        preserve_unknown_keys=True,
        owned_keys={owned_key},
        config_path_resolver=lambda: Path(config_path),
    )
    stale_state = {"resurface": 0, "folder_creator": 0}
    stale_state[owned_key] = value

    for _ in range(iterations):
        barrier.wait()
        manager.save_state(stale_state)
        barrier.wait()


def _hold_state_lock(lock_path, acquired, release):
    with _interprocess_file_lock(Path(lock_path), 5.0):
        acquired.set()
        release.wait(5.0)


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


def test_owned_keys_prevent_stale_cross_application_updates(tmp_path):
    config_path = tmp_path / "app_state.json"
    defaults = {"resurface": 0, "folder_creator": 0}
    resurface_manager = JsonStateManager(
        app_dir_name="Ownership Test",
        config_filename="app_state.json",
        defaults=defaults,
        preserve_unknown_keys=True,
        owned_keys={"resurface"},
        config_path_resolver=lambda: config_path,
    )
    folder_manager = JsonStateManager(
        app_dir_name="Ownership Test",
        config_filename="app_state.json",
        defaults=defaults,
        preserve_unknown_keys=True,
        owned_keys={"folder_creator"},
        config_path_resolver=lambda: config_path,
    )

    resurface_manager.save_state({"resurface": 10, "folder_creator": 0})
    folder_manager.save_state({"resurface": 0, "folder_creator": 20})
    assert resurface_manager.load_state() == {
        "resurface": 10,
        "folder_creator": 20,
    }

    config_path.write_text(
        json.dumps({"resurface": 1, "folder_creator": 2}),
        encoding="utf-8",
    )
    folder_manager.save_state({"resurface": 1, "folder_creator": 40})
    resurface_manager.save_state({"resurface": 30, "folder_creator": 2})
    assert resurface_manager.load_state() == {
        "resurface": 30,
        "folder_creator": 40,
    }


def test_owned_save_preserves_unknown_disk_keys_and_ignores_unowned_input(tmp_path):
    config_path = tmp_path / "app_state.json"
    config_path.write_text(
        json.dumps({"owned": 3, "other": 4, "future_key": "preserve"}),
        encoding="utf-8",
    )
    manager = JsonStateManager(
        app_dir_name="Ownership Test",
        config_filename="app_state.json",
        defaults={"owned": 0, "other": 0},
        preserve_unknown_keys=True,
        owned_keys={"owned", "optional_owned"},
        config_path_resolver=lambda: config_path,
    )

    manager.save_state(
        {
            "other": 999,
            "new_unowned": "ignore",
            "optional_owned": "persist",
        }
    )

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted == {
        "owned": 3,
        "other": 4,
        "future_key": "preserve",
        "optional_owned": "persist",
    }


def test_deprecated_keys_are_not_loaded_or_preserved(tmp_path):
    config_path = tmp_path / "app_state.json"
    config_path.write_text(
        json.dumps(
            {
                "owned": 3,
                "retired": "remove",
                "future_key": "preserve",
            }
        ),
        encoding="utf-8",
    )
    manager = JsonStateManager(
        app_dir_name="Ownership Test",
        config_filename="app_state.json",
        defaults={"owned": 0},
        preserve_unknown_keys=True,
        deprecated_keys={"retired"},
        config_path_resolver=lambda: config_path,
    )

    assert manager.load_state() == {
        "owned": 3,
        "future_key": "preserve",
    }
    manager.save_state(manager.load_state())
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "owned": 3,
        "future_key": "preserve",
    }


def test_owned_optional_key_does_not_require_unknown_key_preservation(tmp_path):
    config_path = tmp_path / "app_state.json"
    manager = JsonStateManager(
        app_dir_name="Ownership Test",
        config_filename="app_state.json",
        defaults={"owned": 0},
        owned_keys={"owned", "optional_owned"},
        config_path_resolver=lambda: config_path,
    )

    manager.save_state({"optional_owned": "persist"})

    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "owned": 0,
        "optional_owned": "persist",
    }


def test_update_rejects_unowned_key(tmp_path):
    manager = JsonStateManager(
        app_dir_name="Ownership Test",
        config_filename="app_state.json",
        defaults={"owned": 0, "other": 0},
        owned_keys={"owned"},
        config_path_resolver=lambda: tmp_path / "app_state.json",
    )

    try:
        manager.update("other", 1)
    except ValueError as exc:
        assert "other" in str(exc)
    else:
        raise AssertionError("Updating an unowned key should fail")


def test_cross_process_writers_preserve_disjoint_owned_values(tmp_path):
    config_path = tmp_path / "app_state.json"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    processes = [
        context.Process(
            target=_write_owned_state,
            args=(str(config_path), "resurface", 10, barrier, 30),
        ),
        context.Process(
            target=_write_owned_state,
            args=(str(config_path), "folder_creator", 20, barrier, 30),
        ),
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(20.0)

    assert [process.exitcode for process in processes] == [0, 0]
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "resurface": 10,
        "folder_creator": 20,
    }
    assert list(tmp_path.glob("*.tmp")) == []
    lock_path = config_path.with_name("app_state.json.lock")
    assert lock_path.exists()
    assert lock_path.stat().st_size == 0


def test_cross_process_lock_blocks_state_transaction_until_release(
    tmp_path,
    capsys,
):
    config_path = tmp_path / "app_state.json"
    config_path.write_text(json.dumps({"value": 0}), encoding="utf-8")
    lock_path = config_path.with_name("app_state.json.lock")
    lock_path.touch()
    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_state_lock,
        args=(str(lock_path), acquired, release),
    )
    process.start()
    assert acquired.wait(5.0)

    manager = JsonStateManager(
        app_dir_name="Lock Test",
        config_filename="app_state.json",
        defaults={"value": 0},
        lock_timeout_seconds=0.1,
        config_path_resolver=lambda: config_path,
    )
    started = time.monotonic()
    manager.save_state({"value": 1})
    elapsed = time.monotonic() - started

    assert elapsed >= 0.09
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"value": 0}
    assert "Timed out waiting for state lock" in capsys.readouterr().out

    release.set()
    process.join(10.0)
    assert process.exitcode == 0
    manager.save_state({"value": 2})
    assert manager.load_state()["value"] == 2


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


def test_windows_resurface_state_removes_retired_screen_mover_dock_settings(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "app_state.json"
    config_path.write_text(
        json.dumps(
            {
                "title_bar_dock_enabled": True,
                "screen_mover_activation_button": "middle",
                "mmb_activation_enabled": True,
                "screen_mover_keyboard_hotkeys": {"LEFT": "<ctrl>+<left>"},
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

    assert "title_bar_dock_enabled" not in loaded
    assert "screen_mover_activation_button" not in loaded
    assert "mmb_activation_enabled" not in loaded
    assert loaded["screen_mover_keyboard_hotkeys"]["LEFT"] == "<ctrl>+<left>"

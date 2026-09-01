from pathlib import Path

from resurface.core.retired_features import (
    RETIRED_FEATURES_CLEANUP_VERSION,
    cleanup_retired_features,
    retired_hover_data_directories,
)


def _create_retired_data(root: Path) -> tuple[Path, ...]:
    directories = retired_hover_data_directories(root)
    for index, directory in enumerate(directories):
        directory.mkdir(parents=True)
        (directory / f"data-{index}.jpg").write_bytes(b"retired")
    return directories


def test_cleanup_removes_all_retired_hover_data_and_state(tmp_path):
    directories = _create_retired_data(tmp_path)
    unrelated = tmp_path / "Windows Resurface" / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")
    state = {
        "hover_window_controls_enabled": True,
        "hover_window_controls_dwell_ms": 750,
        "hover_window_controls_migration_completed": True,
        "retired_features_cleanup_version": 0,
        "theme_dark": True,
    }

    assert cleanup_retired_features(state, local_app_data=tmp_path)

    assert all(not directory.exists() for directory in directories)
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert state == {
        "retired_features_cleanup_version": RETIRED_FEATURES_CLEANUP_VERSION,
        "theme_dark": True,
    }


def test_cleanup_tolerates_missing_directories(tmp_path):
    state = {"retired_features_cleanup_version": 0}

    assert cleanup_retired_features(state, local_app_data=tmp_path)
    assert state["retired_features_cleanup_version"] == 1
    assert not cleanup_retired_features(state, local_app_data=tmp_path)


def test_cleanup_failure_is_not_marked_complete_and_retries(tmp_path):
    directories = _create_retired_data(tmp_path)
    failed = directories[1]
    attempts = []

    def fail_one(directory: Path) -> None:
        attempts.append(directory)
        if directory == failed:
            raise OSError("in use")
        import shutil

        shutil.rmtree(directory)

    state = {"retired_features_cleanup_version": 0}
    assert not cleanup_retired_features(
        state,
        local_app_data=tmp_path,
        remove_tree=fail_one,
    )
    assert failed.exists()
    assert state["retired_features_cleanup_version"] == 0

    assert cleanup_retired_features(state, local_app_data=tmp_path)
    assert not failed.exists()
    assert state["retired_features_cleanup_version"] == 1
    assert set(attempts) == set(directories)

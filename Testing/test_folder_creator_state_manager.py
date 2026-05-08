import importlib.util
import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch


def load_folder_creator_state_manager_module():
    module_path = (
        Path(__file__).resolve().parent.parent
        / "Code Folder Creator"
        / "state_manager.py"
    )
    spec = importlib.util.spec_from_file_location(
        "folder_creator_state_manager",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


state_manager = load_folder_creator_state_manager_module()


class FolderCreatorStateManagerTests(unittest.TestCase):
    def make_temp_dir(self, name: str) -> Path:
        temp_dir = Path(__file__).resolve().parent / ".tmp" / name
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        return temp_dir

    def test_load_state_persists_defaults_when_missing(self):
        config_root = self.make_temp_dir("folder-creator-missing")

        with patch.dict(
            "os.environ",
            {"LOCALAPPDATA": str(config_root)},
            clear=False,
        ):
            manager = state_manager.StateManager()
            state = manager.load_state()

        expected_path = (
            config_root / "FolderCreator" / "folder_creator_user_state.json"
        )
        self.assertEqual(state, state_manager.DEFAULT_STATE)
        self.assertTrue(expected_path.exists())

    def test_load_state_merges_missing_keys(self):
        config_root = self.make_temp_dir("folder-creator-merge")
        config_path = config_root / "FolderCreator" / "folder_creator_user_state.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"last_base_dir": "C:\\Code"}),
            encoding="utf-8",
        )

        with patch.dict(
            "os.environ",
            {"LOCALAPPDATA": str(config_root)},
            clear=False,
        ):
            manager = state_manager.StateManager()
            state = manager.load_state()

        self.assertEqual(state["last_base_dir"], "C:\\Code")
        self.assertIn("nested_date_stamp_enabled", state)
        self.assertIn("close_after_build", state)

    def test_update_writes_single_key_change(self):
        config_root = self.make_temp_dir("folder-creator-update")

        with patch.dict(
            "os.environ",
            {"LOCALAPPDATA": str(config_root)},
            clear=False,
        ):
            manager = state_manager.StateManager()
            manager.update("open_folder_after_build", True)
            state = manager.load_state()

        self.assertTrue(state["open_folder_after_build"])


if __name__ == "__main__":
    unittest.main()

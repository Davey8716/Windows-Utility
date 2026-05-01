import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import state_manager


class StateManagerTests(unittest.TestCase):
    def make_temp_dir(self, name: str) -> Path:
        temp_dir = Path(__file__).resolve().parent / ".tmp" / name
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        return temp_dir

    def test_load_state_returns_defaults_when_file_missing(self):
        config_path = self.make_temp_dir("state-missing") / "missing.json"
        with patch.object(state_manager, "CONFIG_PATH", str(config_path)):
            state = state_manager.load_state()

        self.assertTrue(state["theme_dark"])
        self.assertTrue(state["main_always_on_top_enabled"])
        self.assertIn("left_section_states", state)

    def test_load_state_merges_defaults_into_existing_file(self):
        config_path = self.make_temp_dir("state-merge") / "state.json"
        config_path.write_text(json.dumps({"theme_dark": False}), encoding="utf-8")

        with patch.object(state_manager, "CONFIG_PATH", str(config_path)):
            state = state_manager.load_state()

        self.assertFalse(state["theme_dark"])
        self.assertIn("tooltips_enabled", state)
        self.assertIn("right_section_states", state)

    def test_save_state_writes_json_file(self):
        config_path = self.make_temp_dir("state-save") / "state.json"
        payload = {"feature": True, "count": 2}

        with patch.object(state_manager, "CONFIG_PATH", str(config_path)):
            state_manager.save_state(payload)

        saved = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(saved, payload)


if __name__ == "__main__":
    unittest.main()

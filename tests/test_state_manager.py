import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import state_manager

EXPECTED_PERSISTED_KEYS = {
    "theme_dark",
    "main_always_on_top_enabled",
    "tooltips_enabled",
    "minimize_all_enabled",
    "power_options_enabled",
    "power_sleep_enabled",
    "power_lock_enabled",
    "power_restart_enabled",
    "power_logout_enabled",
    "power_shutdown_enabled",
    "mmb_activation_enabled",
    "title_bar_dock_enabled",
    "usb_idle_enabled",
    "usb_download_enabled",
    "usb_plug_enabled",
    "master_backup_output_path",
    "advanced_panel_open",
    "master_toggle_left",
    "master_toggle_right",
    "left_section_states",
    "right_section_states",
}


class StateManagerTests(unittest.TestCase):
    def make_temp_dir(self, name: str) -> Path:
        temp_dir = Path(__file__).resolve().parent / ".tmp" / name
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        return temp_dir

    def test_load_state_returns_defaults_when_file_missing(self):
        config_path = self.make_temp_dir("state-missing") / "missing.json"
        with patch.object(state_manager, "get_config_path", return_value=config_path):
            state = state_manager.load_state()

        self.assertTrue(state["theme_dark"])
        self.assertTrue(state["main_always_on_top_enabled"])
        self.assertIn("left_section_states", state)

    def test_load_state_merges_defaults_into_existing_file(self):
        config_path = self.make_temp_dir("state-merge") / "state.json"
        config_path.write_text(json.dumps({"theme_dark": False}), encoding="utf-8")

        with patch.object(state_manager, "get_config_path", return_value=config_path):
            state = state_manager.load_state()

        self.assertFalse(state["theme_dark"])
        self.assertIn("tooltips_enabled", state)
        self.assertIn("right_section_states", state)

    def test_save_state_writes_json_file(self):
        config_path = self.make_temp_dir("state-save") / "state.json"
        payload = {
            "feature": True,
            "theme_dark": False,
            "usb_idle_enabled": False,
            "usb_download_enabled": False,
            "usb_plug_enabled": False,
            "master_backup_output_path": "C:\\Backups",
            "left_section_states": {"screen_mover": False},
        }

        with patch.object(state_manager, "get_config_path", return_value=config_path):
            state_manager.save_state(payload)

        saved = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(set(saved), EXPECTED_PERSISTED_KEYS)
        self.assertFalse(saved["theme_dark"])
        self.assertFalse(saved["usb_idle_enabled"])
        self.assertFalse(saved["usb_download_enabled"])
        self.assertFalse(saved["usb_plug_enabled"])
        self.assertEqual(saved["master_backup_output_path"], "C:\\Backups")
        self.assertFalse(saved["left_section_states"]["screen_mover"])
        self.assertNotIn("feature", saved)

    def test_get_config_path_uses_local_app_data(self):
        with patch.dict("os.environ", {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}, clear=False):
            config_path = state_manager.get_config_path()

        self.assertEqual(
            config_path,
            Path(r"C:\Users\Test\AppData\Local") / "Windows Resurface" / "app_state.json",
        )


if __name__ == "__main__":
    unittest.main()

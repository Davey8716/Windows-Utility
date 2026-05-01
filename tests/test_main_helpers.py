import shutil
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from _stubs import install_dependency_stubs

install_dependency_stubs()

import main


class MainHelperTests(unittest.TestCase):
    def make_temp_dir(self, name: str) -> Path:
        temp_dir = Path(__file__).resolve().parent / ".tmp" / name
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        return temp_dir

    def _build_app(self):
        app = main.UtilityControlApp.__new__(main.UtilityControlApp)
        app.state = {}
        return app

    def test_get_master_backup_dir_prefers_master_path(self):
        app = self._build_app()
        app.state = {
            "master_backup_output_path": "C:\\master",
            "backup_output_path": "C:\\backup",
        }

        self.assertEqual(app._get_master_backup_dir(), "C:\\master")

    def test_build_master_output_path_joins_filename(self):
        app = self._build_app()
        app.state = {"master_backup_output_path": "C:\\base"}

        output = app._build_master_output_path("desktop.png")

        self.assertEqual(output, str(Path("C:\\base") / "desktop.png"))

    def test_set_master_backup_dir_updates_state_and_persists(self):
        app = self._build_app()
        app.backup_path_input = Mock()
        app.backup_path_input.text.return_value = ""

        with patch.object(main, "save_state") as save_state_mock:
            app._set_master_backup_dir("C:\\archives")

        self.assertEqual(app.backup_path, "C:\\archives")
        self.assertEqual(app.state["master_backup_output_path"], "C:\\archives")
        app.backup_path_input.setText.assert_called_once_with("C:\\archives")
        save_state_mock.assert_called_once_with(app.state)

    def test_create_desktop_folder_clears_input_and_saves_state(self):
        temp_dir = self.make_temp_dir("desktop-home")
        app = self._build_app()
        app.state = {"folder_to_desktop_name": "Reports"}
        folder_input = Mock()
        folder_input.text.return_value = "Reports"

        with patch.object(main.Path, "home", return_value=temp_dir), \
             patch.object(main, "save_state") as save_state_mock:
            app._create_desktop_folder(folder_input)

        self.assertTrue((temp_dir / "Desktop" / "Reports").exists())
        folder_input.clear.assert_called_once()
        self.assertEqual(app.state["folder_to_desktop_name"], "")
        save_state_mock.assert_called_once_with(app.state)

    def test_save_section_states_collects_left_and_right_panels(self):
        app = self._build_app()
        app.left_sections = [
            type("Section", (), {"section_id": "left-a", "content": type("Content", (), {"isVisible": lambda self: True})()})(),
            type("Section", (), {"section_id": "left-b", "content": type("Content", (), {"isVisible": lambda self: False})()})(),
        ]
        app.collapsible_sections = [
            type("Section", (), {"section_id": "right-a", "is_open": True})(),
            type("Section", (), {"section_id": "right-b", "is_open": False})(),
        ]

        app.save_section_states()

        self.assertEqual(app.state["left_section_states"], {"left-a": True, "left-b": False})
        self.assertEqual(app.state["right_section_states"], {"right-a": True, "right-b": False})
        self.assertFalse(app.state["master_toggle_left"])
        self.assertFalse(app.state["master_toggle_right"])


if __name__ == "__main__":
    unittest.main()

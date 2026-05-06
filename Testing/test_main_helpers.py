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
        app.master_collapse_btn_left = Mock()
        app.right_tools_panel = type(
            "RightToolsPanel",
            (),
            {"master_collapse_btn_right": Mock()},
        )()
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

    def test_sync_left_section_spacing_uses_collapsed_profile_when_hidden(self):
        app = self._build_app()
        app.MAIN_SECTION_SIDE_PADDING = 14
        app.LEFT_SECTION_TOP_MARGIN = 5
        app.LEFT_SECTION_BOTTOM_MARGIN = 12
        app.LEFT_SECTION_COLLAPSED_TOP_MARGIN = 10
        app.LEFT_SECTION_COLLAPSED_BOTTOM_MARGIN = 0
        app.LEFT_SECTION_COLLAPSED_SPACER = 6
        app.main_layout = Mock()

        top_spacer = Mock()
        section_layout = Mock()
        section = type(
            "Section",
            (),
            {
                "content": type("Content", (), {"isVisible": lambda self: False})(),
                "top_spacer": top_spacer,
                "expanded_spacer_height": 38,
                "section_layout": section_layout,
            },
        )()

        app._sync_left_section_spacing(section)

        top_spacer.changeSize.assert_called_once_with(
            0,
            6,
            main.QSizePolicy.Policy.Fixed,
            main.QSizePolicy.Policy.Fixed,
        )
        section_layout.setContentsMargins.assert_called_once_with(14, 10, 14, 0)
        app.main_layout.invalidate.assert_called_once_with()

    def test_sync_left_section_spacing_restores_original_profile_when_visible(self):
        app = self._build_app()
        app.MAIN_SECTION_SIDE_PADDING = 14
        app.LEFT_SECTION_TOP_MARGIN = 5
        app.LEFT_SECTION_BOTTOM_MARGIN = 12
        app.LEFT_SECTION_COLLAPSED_TOP_MARGIN = 10
        app.LEFT_SECTION_COLLAPSED_BOTTOM_MARGIN = 0
        app.LEFT_SECTION_COLLAPSED_SPACER = 6
        app.main_layout = Mock()

        top_spacer = Mock()
        section_layout = Mock()
        section = type(
            "Section",
            (),
            {
                "content": type("Content", (), {"isVisible": lambda self: True})(),
                "top_spacer": top_spacer,
                "expanded_spacer_height": 38,
                "section_layout": section_layout,
            },
        )()

        app._sync_left_section_spacing(section)

        top_spacer.changeSize.assert_called_once_with(
            0,
            38,
            main.QSizePolicy.Policy.Fixed,
            main.QSizePolicy.Policy.Fixed,
        )
        section_layout.setContentsMargins.assert_called_once_with(14, 5, 14, 12)
        app.main_layout.invalidate.assert_called_once_with()

    def test_sync_left_section_spacing_uses_logical_open_state_during_startup(self):
        app = self._build_app()
        app.MAIN_SECTION_SIDE_PADDING = 14
        app.LEFT_SECTION_TOP_MARGIN = 5
        app.LEFT_SECTION_BOTTOM_MARGIN = 12
        app.LEFT_SECTION_COLLAPSED_TOP_MARGIN = 10
        app.LEFT_SECTION_COLLAPSED_BOTTOM_MARGIN = 0
        app.LEFT_SECTION_COLLAPSED_SPACER = 6
        app.main_layout = Mock()

        top_spacer = Mock()
        section_layout = Mock()
        section = type(
            "Section",
            (),
            {
                "is_open": True,
                "content": type("Content", (), {"isVisible": lambda self: False})(),
                "top_spacer": top_spacer,
                "expanded_spacer_height": 38,
                "section_layout": section_layout,
            },
        )()

        app._sync_left_section_spacing(section)

        top_spacer.changeSize.assert_called_once_with(
            0,
            38,
            main.QSizePolicy.Policy.Fixed,
            main.QSizePolicy.Policy.Fixed,
        )
        section_layout.setContentsMargins.assert_called_once_with(14, 5, 14, 12)
        app.main_layout.invalidate.assert_called_once_with()

    def test_set_left_section_open_updates_visibility_arrow_and_spacing(self):
        app = self._build_app()
        app._sync_left_section_spacing = Mock()
        section = type(
            "Section",
            (),
            {
                "content": Mock(),
                "frame": Mock(),
                "toggle_btn": Mock(),
            },
        )()

        app._set_left_section_open(section, True)

        section.content.setVisible.assert_called_once_with(True)
        section.frame.setVisible.assert_called_once_with(True)
        section.toggle_btn.setArrowType.assert_called_once_with(main.Qt.ArrowType.DownArrow)
        app._sync_left_section_spacing.assert_called_once_with(section)

    def test_bring_existing_instance_posts_restore_message(self):
        with patch.object(main.win32gui, "EnumWindows") as enum_windows, \
             patch.object(main.win32gui, "GetWindowText", return_value="Windows Resurface"), \
             patch.object(main.win32gui, "PostMessage") as post_message:
            enum_windows.side_effect = lambda callback, extra: callback(321, extra)

            main.bring_existing_instance_to_front()

        post_message.assert_called_once_with(321, main.WM_APP_RESTORE_INSTANCE, 0, 0)


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
)

from resurface.features.hover_window_controls.ui.calibration import (
    CALIBRATION_DIALOG_SIZE,
    CalibrationDialog,
    HOVER_CONTROLS_PROMPT_CORNER_RADIUS,
    _apply_frameless_window_style,
    action_glyph_geometry,
)
from resurface.features.hover_window_controls.core.hover_controller import CaptionAction
from resurface.features.hover_window_controls.vision.detection import (
    ApplicationIdentity,
    TrackedApplication,
    TrackedAsset,
)
from resurface.ui import styles


def identity(
    name: str,
    *,
    version: str = "1.0",
    state: str = "normal",
    dpi: int = 96,
    theme: str = "dark",
    caption_side: str = "right",
    window_class: str | None = None,
) -> ApplicationIdentity:
    return ApplicationIdentity(
        executable_path=rf"c:\apps\{name}.exe",
        executable_version=version,
        friendly_name=name,
        window_class=window_class or f"{name}Window",
        dpi=dpi,
        theme=theme,
        caption_side=caption_side,
        window_state=state,
    )


class CalibrationDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.example = TrackedApplication(
            "example-hash",
            "Example",
            root / "manifest_example.json",
        )
        self.other = TrackedApplication(
            "other-hash",
            "Other",
            root / "manifest_other.json",
        )
        first_jpeg = root / "example_minimize.jpg"
        maximize_jpeg = root / "example_maximize.jpg"
        restore_jpeg = root / "example_restore.jpg"
        other_jpeg = root / "other_close.jpg"
        for path, color in (
            (first_jpeg, "#3388cc"),
            (maximize_jpeg, "#55aa44"),
            (restore_jpeg, "#ddaa22"),
            (other_jpeg, "#cc3344"),
        ):
            image = QImage(30, 30, QImage.Format.Format_RGB32)
            image.fill(QColor(color))
            self.assertTrue(image.save(str(path), "JPG", 95))
        self.assets = {
            self.example.key: [
                TrackedAsset(
                    self.example,
                    identity("Example"),
                    "automatic",
                    "profile-normal",
                    CaptionAction.MINIMIZE,
                    "minimize",
                    (160, 60),
                    (100, 5, 130, 35),
                    first_jpeg,
                ),
                TrackedAsset(
                    self.example,
                    identity("Example"),
                    "automatic",
                    "profile-maximize",
                    CaptionAction.MAXIMIZE_RESTORE,
                    "maximize",
                    (160, 60),
                    (70, 5, 100, 35),
                    maximize_jpeg,
                ),
                TrackedAsset(
                    self.example,
                    identity("Example", state="maximized"),
                    "automatic",
                    "profile-maximized",
                    CaptionAction.MAXIMIZE_RESTORE,
                    "restore",
                    (160, 60),
                    (70, 5, 100, 35),
                    restore_jpeg,
                ),
            ],
            self.other.key: [
                TrackedAsset(
                    self.other,
                    identity("Other"),
                    "user",
                    "profile-other",
                    CaptionAction.CLOSE,
                    "close",
                    (200, 70),
                    (160, 5, 195, 40),
                    other_jpeg,
                )
            ],
        }
        self.updates = []

    def make_dialog(self) -> CalibrationDialog:
        def update(asset, rect):
            self.updates.append((asset, rect))
            return replace(asset, rect=rect, profile_id="updated-profile")

        dialog = CalibrationDialog(
            lambda: [self.example, self.other],
            lambda application: self.assets[application.key],
            update,
        )
        def close_dialog():
            with patch.object(
                dialog,
                "_show_modal_message",
                return_value=QMessageBox.StandardButton.Discard,
            ):
                dialog.close()

        self.addCleanup(close_dialog)
        return dialog

    def test_loads_tracked_jpeg_and_switches_action_variant(self):
        dialog = self.make_dialog()
        self.assertIsNone(dialog.findChild(QLabel, "liveCalibrationStatus"))
        self.assertIsNone(
            dialog.findChild(QPushButton, "captureLiveApplicationButton")
        )
        self.assertEqual(dialog.application_selector.count(), 2)
        self.assertEqual(dialog.profile_selector.count(), 2)
        self.assertIn(
            "v1.0 · Normal · 96 DPI · Dark",
            dialog.profile_selector.itemText(0),
        )
        self.assertEqual(
            dialog.profile_path_label.text(),
            "Executable: c:\\apps\\Example.exe",
        )
        self.assertEqual(
            dialog.profile_selector.toolTip(),
            r"c:\apps\Example.exe",
        )
        self.assertEqual(dialog.action_selector.count(), 3)
        self.assertEqual(dialog.action_selector.itemText(0), "Minimize")
        self.assertEqual(
            dialog.action_selector.itemText(1),
            "Maximize / Restore",
        )
        self.assertEqual(
            dialog.action_selector.itemText(2),
            "Close (No JPEG)",
        )
        self.assertFalse(dialog.action_selector.model().item(2).isEnabled())
        self.assertEqual(dialog.variant_selector.count(), 1)
        self.assertIn(
            "Minimize — normal",
            dialog.variant_selector.itemText(0),
        )
        self.assertEqual(
            dialog.current_rect(),
            (100, 5, 130, 35),
        )
        self.assertEqual(dialog.canvas.reference_rect, (100, 5, 130, 35))

        dialog.action_selector.setCurrentIndex(1)

        self.assertEqual(dialog.variant_selector.count(), 1)
        self.assertIn(
            "Maximize — normal",
            dialog.variant_selector.itemText(0),
        )

        dialog.profile_selector.setCurrentIndex(1)

        self.assertIn("Maximized", dialog.profile_selector.currentText())
        self.assertIn("(No JPEG)", dialog.action_selector.itemText(0))
        self.assertEqual(dialog.action_selector.itemText(1), "Maximize / Restore")
        self.assertIn(
            "Restore — maximized",
            dialog.variant_selector.itemText(0),
        )
        self.assertEqual(dialog.current_rect(), (70, 5, 100, 35))
        self.assertEqual(dialog.canvas.reference_rect, (70, 5, 100, 35))
        self.assertEqual(
            dialog.canvas._action,
            CaptionAction.MAXIMIZE_RESTORE,
        )

    def test_build_profiles_identify_versions_contexts_and_paths(self):
        newer_identity = identity(
            "Example",
            version="2.4.1",
            dpi=144,
            theme="light",
            caption_side="left",
            window_class="ExampleNewWindow",
        )
        newer_asset = replace(
            self.assets[self.example.key][0],
            identity=newer_identity,
            profile_id="profile-new-build",
            action=CaptionAction.CLOSE,
            visual="close",
        )
        self.assets[self.example.key].append(newer_asset)
        dialog = self.make_dialog()

        profile_index = dialog._find_profile(
            dialog.profile_selector,
            newer_identity.fingerprint,
        )
        self.assertGreaterEqual(profile_index, 0)
        self.assertEqual(
            dialog.profile_selector.itemText(profile_index),
            "v2.4.1 · Normal · 144 DPI · Light · Left captions · "
            "ExampleNewWindow",
        )

        dialog.profile_selector.setCurrentIndex(profile_index)

        self.assertEqual(
            dialog.profile_path_label.text(),
            "Executable: c:\\apps\\Example.exe",
        )
        self.assertEqual(
            dialog.profile_selector.toolTip(),
            r"c:\apps\Example.exe",
        )
        self.assertIn("(No JPEG)", dialog.action_selector.itemText(0))
        self.assertIn("(No JPEG)", dialog.action_selector.itemText(1))
        self.assertEqual(dialog.action_selector.itemText(2), "Close")
        self.assertEqual(dialog.variant_selector.count(), 1)
        self.assertEqual(
            dialog.variant_selector.currentData().identity,
            newer_identity,
        )
        dialog.canvas.rectChanged.emit((90, 5, 120, 35))
        dialog.save_button.click()
        self.assertEqual(self.updates[-1][0].identity, newer_identity)

        self.assertTrue(
            dialog._profile_label(identity("Unknown", version="")).startswith(
                "Version unavailable"
            )
        )

    def test_refresh_preserves_selected_build_profile(self):
        dialog = self.make_dialog()
        dialog.profile_selector.setCurrentIndex(1)
        selected_identity = dialog.profile_selector.currentData()

        dialog.refresh_applications(prompt=False)

        self.assertEqual(
            dialog.profile_selector.currentData().fingerprint,
            selected_identity.fingerprint,
        )

    def test_refresh_scans_then_reloads_tracked_applications(self):
        applications = [self.example]
        completed = []

        def refresh(callback):
            completed.append(callback)
            return True

        dialog = CalibrationDialog(
            lambda: list(applications),
            lambda application: self.assets[application.key],
            lambda asset, rect: asset,
            refresh_provider=refresh,
        )
        self.addCleanup(dialog.close)

        dialog.refresh_button.click()

        self.assertEqual(len(completed), 1)
        self.assertFalse(dialog.refresh_button.isEnabled())
        applications.append(self.other)
        completed[0](2, list(applications), 2, "")

        self.assertTrue(dialog.refresh_button.isEnabled())
        self.assertEqual(dialog.application_selector.count(), 2)
        self.assertEqual(
            dialog.application_selector.currentData().key,
            self.example.key,
        )
        self.assertIn("Scanned 2", dialog.status_label.text())

    def test_clear_availability_can_be_controlled_externally(self):
        dialog = CalibrationDialog(
            lambda: [self.example],
            lambda application: self.assets[application.key],
            MagicMock(),
            clear_provider=MagicMock(),
            clear_available=False,
        )
        self.addCleanup(dialog.close)

        self.assertFalse(dialog.clear_button.isEnabled())
        dialog.set_clear_available(True)
        self.assertTrue(dialog.clear_button.isEnabled())

    def test_successful_refresh_restores_clear_availability(self):
        dialog = CalibrationDialog(
            lambda: [self.example],
            lambda application: self.assets[application.key],
            MagicMock(),
            clear_provider=MagicMock(),
            clear_available=False,
        )
        self.addCleanup(dialog.close)

        dialog._tracked_refresh_completed(0, [self.example], 1, "")

        self.assertTrue(dialog.clear_button.isEnabled())

    def test_refresh_shows_untracked_scanned_application(self):
        untracked = TrackedApplication("new-hash", "New App")
        dialog = CalibrationDialog(
            lambda: [self.example],
            lambda application: self.assets.get(application.key, []),
            lambda asset, rect: asset,
        )
        self.addCleanup(dialog.close)

        dialog._tracked_refresh_completed(1, [self.example, untracked], 1, "")
        dialog.application_selector.setCurrentIndex(1)

        self.assertEqual(
            dialog.application_selector.currentData(),
            untracked,
        )
        self.assertIn("not yet learned", dialog.application_selector.currentText())
        self.assertFalse(dialog.profile_selector.isEnabled())
        self.assertFalse(dialog.action_selector.isEnabled())
        self.assertFalse(dialog.variant_selector.isEnabled())
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertIn("No tracked JPEGs yet", dialog.status_label.text())

    def test_selects_first_enabled_action_for_application(self):
        dialog = self.make_dialog()
        dialog.application_selector.setCurrentIndex(1)
        self.assertEqual(dialog.action_selector.currentIndex(), 2)
        self.assertIn("(No JPEG)", dialog.action_selector.itemText(0))
        self.assertIn("(No JPEG)", dialog.action_selector.itemText(1))
        self.assertEqual(dialog.action_selector.itemText(2), "Close")

    def test_red_drag_updates_the_selected_position_without_coordinate_editor(self):
        dialog = self.make_dialog()
        self.assertEqual(len(dialog.findChildren(QSpinBox)), 0)
        dialog.canvas.rectChanged.emit((80, 10, 120, 45))
        self.assertEqual(dialog.current_rect(), (80, 10, 120, 45))
        self.assertEqual(dialog.canvas.working_rect, (80, 10, 120, 45))
        self.assertTrue(dialog._dirty)

    def test_save_updates_position_and_keeps_dialog_open(self):
        dialog = self.make_dialog()
        dialog.canvas.rectChanged.emit((90, 5, 120, 35))

        dialog.save_button.click()

        self.assertEqual(len(self.updates), 1)
        self.assertEqual(self.updates[0][1], (90, 5, 120, 35))
        self.assertEqual(dialog.canvas.reference_rect, (90, 5, 120, 35))
        self.assertEqual(dialog.result(), 0)
        self.assertIn("Saved", dialog.status_label.text())

    def test_grouped_jpeg_stays_fixed_when_action_position_is_saved(self):
        grouped_rect = (60, 0, 150, 40)
        self.assets[self.example.key][0] = replace(
            self.assets[self.example.key][0],
            image_rect=grouped_rect,
        )
        dialog = self.make_dialog()
        self.assertEqual(dialog.canvas.reference_rect, grouped_rect)

        dialog.canvas.rectChanged.emit((90, 5, 120, 35))
        dialog.save_button.click()

        self.assertEqual(dialog.canvas.reference_rect, grouped_rect)
        self.assertEqual(dialog.canvas.working_rect, (90, 5, 120, 35))

    def test_dirty_profile_switch_can_cancel_or_discard(self):
        dialog = self.make_dialog()
        dialog.canvas.rectChanged.emit((90, 5, 120, 35))
        with patch.object(
            dialog,
            "_show_modal_message",
            return_value=QMessageBox.StandardButton.Cancel,
        ) as show_modal:
            dialog.profile_selector.setCurrentIndex(1)
        self.assertEqual(dialog.profile_selector.currentIndex(), 0)
        self.assertEqual(dialog.current_rect(), (90, 5, 120, 35))
        show_modal.assert_called_once_with(
            QMessageBox.Icon.NoIcon,
            "Save position changes?",
            "Save the current action position before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
            popup_corner_radius=HOVER_CONTROLS_PROMPT_CORNER_RADIUS,
        )

        with patch.object(
            dialog,
            "_show_modal_message",
            return_value=QMessageBox.StandardButton.Discard,
        ):
            dialog.profile_selector.setCurrentIndex(1)
        self.assertEqual(dialog.profile_selector.currentIndex(), 1)
        self.assertEqual(dialog.action_selector.currentIndex(), 1)
        self.assertEqual(dialog.current_rect(), (70, 5, 100, 35))

    def test_dirty_variant_switch_can_cancel_then_discard(self):
        self.assets[self.example.key].append(
            replace(
                self.assets[self.example.key][1],
                profile_id="profile-maximize-alternate",
                visual="restore",
            )
        )
        dialog = self.make_dialog()
        dialog.action_selector.setCurrentIndex(1)
        dialog.canvas.rectChanged.emit((80, 5, 110, 35))
        with patch.object(
            dialog,
            "_show_modal_message",
            return_value=QMessageBox.StandardButton.Cancel,
        ):
            dialog.variant_selector.setCurrentIndex(1)
        self.assertEqual(dialog.variant_selector.currentIndex(), 0)
        self.assertEqual(dialog.current_rect(), (80, 5, 110, 35))

        with patch.object(
            dialog,
            "_show_modal_message",
            return_value=QMessageBox.StandardButton.Discard,
        ):
            dialog.variant_selector.setCurrentIndex(1)
        self.assertEqual(dialog.variant_selector.currentIndex(), 1)
        self.assertEqual(dialog.current_rect(), (70, 5, 100, 35))

    def test_dirty_close_can_cancel_then_save(self):
        dialog = self.make_dialog()
        dialog.show()
        self.app.processEvents()
        dialog.canvas.rectChanged.emit((90, 5, 120, 35))
        with patch.object(
            dialog,
            "_show_modal_message",
            return_value=QMessageBox.StandardButton.Cancel,
        ):
            self.assertFalse(dialog.close())
        self.assertTrue(dialog.isVisible())

        with patch.object(
            dialog,
            "_show_modal_message",
            return_value=QMessageBox.StandardButton.Save,
        ):
            self.assertTrue(dialog.close())
        self.assertEqual(len(self.updates), 1)

    def test_missing_jpeg_is_recoverable(self):
        missing = replace(
            self.assets[self.example.key][0],
            image_path=Path(self.temporary.name) / "missing.jpg",
        )
        self.assets[self.example.key] = [missing]
        dialog = self.make_dialog()
        self.assertIsNone(dialog.current_rect())
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertIn("missing", dialog.status_label.text())

    def test_uses_host_theme_without_coordinate_editor(self):
        styles.set_theme(False)
        self.addCleanup(styles.set_theme, True)
        dialog = self.make_dialog()
        self.assertIn("#dde3ea", dialog.styleSheet())
        self.assertIn("#111820", dialog.styleSheet())
        self.assertEqual(len(dialog.findChildren(QSpinBox)), 0)
        self.assertNotIn(
            "Selected action position",
            [label.text() for label in dialog.findChildren(QLabel)],
        )

    def test_has_fixed_size_and_no_native_chrome(self):
        dialog = self.make_dialog()
        self.assertEqual(
            (dialog.width(), dialog.height()),
            CALIBRATION_DIALOG_SIZE,
        )
        flags = dialog.windowFlags()
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
        self.assertFalse(flags & Qt.WindowType.WindowMaximizeButtonHint)

        dialog.show()
        self.app.processEvents()
        button_box = dialog.findChild(QDialogButtonBox)
        button_box.button(QDialogButtonBox.StandardButton.Close).click()
        self.app.processEvents()
        self.assertFalse(dialog.isVisible())

    def test_native_window_style_removes_caption_and_frame(self):
        dialog = MagicMock()
        dialog.winId.return_value = 123
        user32 = MagicMock()
        original_style = 0x00CF0000
        user32.GetWindowLongW.return_value = original_style

        with patch(
            "resurface.features.hover_window_controls.ui.calibration.ctypes.windll.user32",
            user32,
        ), patch(
            "resurface.features.hover_window_controls.ui.calibration._apply_native_window_appearance"
        ) as apply_appearance:
            _apply_frameless_window_style(dialog)

        removed_styles = (
            0x00C00000
            | 0x00080000
            | 0x00020000
            | 0x00010000
            | 0x00040000
        )
        user32.GetWindowLongW.assert_called_once_with(123, -16)
        user32.SetWindowLongW.assert_called_once_with(
            123,
            -16,
            original_style & ~removed_styles,
        )
        user32.SetWindowPos.assert_called_once_with(
            123,
            0,
            0,
            0,
            0,
            0,
            0x0002 | 0x0001 | 0x0004 | 0x0020,
        )
        apply_appearance.assert_called_once_with(dialog)

    def test_clear_learned_buttons_confirms_then_requires_refresh(self):
        applications = [self.example]
        clear = MagicMock(side_effect=applications.clear)
        application_provider = MagicMock(side_effect=lambda: list(applications))
        dialog = CalibrationDialog(
            application_provider,
            lambda application: self.assets[application.key],
            MagicMock(),
            clear_provider=clear,
        )
        self.addCleanup(dialog.close)

        with patch.object(
            dialog,
            "_show_modal_message",
            return_value=QMessageBox.StandardButton.Cancel,
        ) as show_modal:
            dialog.clear_button.click()
        clear.assert_not_called()
        show_modal.assert_called_once_with(
            QMessageBox.Icon.NoIcon,
            "Clear all learned buttons?",
            "This permanently removes all learned caption-button images and "
            "calibration data.\nHover preferences are kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
            fixed_popup_width=360,
            center_text_block=True,
            popup_corner_radius=HOVER_CONTROLS_PROMPT_CORNER_RADIUS,
        )

        with patch.object(
            dialog,
            "_show_modal_message",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            dialog.clear_button.click()

        clear.assert_called_once_with()
        self.assertEqual(application_provider.call_count, 1)
        self.assertEqual(dialog.application_selector.count(), 1)
        self.assertFalse(dialog.clear_button.isEnabled())
        self.assertEqual(
            dialog.status_label.text(),
            "All learned buttons were cleared. Click Refresh to scan open "
            "applications.",
        )

    def test_dialog_has_visible_calibration_explorer_title(self):
        dialog = self.make_dialog()

        title = dialog.findChild(QLabel, "calibrationTitle")
        self.assertIsNotNone(title)
        self.assertEqual(title.text(), "Calibration Explorer")

    def test_semantic_glyph_geometry_has_no_generic_plus(self):
        target = QRect(10, 10, 30, 30)
        minimize_lines, minimize_square = action_glyph_geometry(
            CaptionAction.MINIMIZE,
            target,
        )
        self.assertIsNone(minimize_square)
        self.assertEqual(len(minimize_lines), 1)
        self.assertEqual(minimize_lines[0][1], minimize_lines[0][3])

        maximize_lines, maximize_square = action_glyph_geometry(
            CaptionAction.MAXIMIZE_RESTORE,
            target,
        )
        self.assertEqual(maximize_lines, ())
        self.assertIsNotNone(maximize_square)
        self.assertGreater(maximize_square.width(), 0)

        close_lines, close_square = action_glyph_geometry(
            CaptionAction.CLOSE,
            target,
        )
        self.assertIsNone(close_square)
        self.assertEqual(len(close_lines), 2)
        self.assertNotEqual(close_lines[0][1], close_lines[0][3])
        self.assertNotEqual(close_lines[1][1], close_lines[1][3])


if __name__ == "__main__":
    unittest.main()

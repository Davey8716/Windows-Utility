import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QSpinBox

from resurface.features.hover_window_controls.core.hover_controller import CaptionAction
from resurface.features.hover_window_controls.ui.calibration import CalibrationDialog
from resurface.features.hover_window_controls.vision.detection import (
    ApplicationIdentity,
    TrackedApplication,
    TrackedAsset,
)


def identity(name: str) -> ApplicationIdentity:
    return ApplicationIdentity(
        executable_path=rf"c:\\apps\\{name}.exe", executable_version="1.0",
        friendly_name=name, window_class=f"{name}Window", dpi=96,
        theme="dark", caption_side="right", window_state="normal",
    )


class CalibrationDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.application = TrackedApplication("example", "Example", root / "manifest_example.json")
        image_path = root / "example.jpg"
        image = QImage(30, 30, QImage.Format.Format_RGB32)
        image.fill(QColor("#3388cc"))
        self.assertTrue(image.save(str(image_path), "JPG", 95))
        self.asset = TrackedAsset(
            self.application, identity("Example"), "automatic", "profile",
            CaptionAction.MINIMIZE, "minimize", (160, 60),
            (100, 5, 130, 35), image_path,
        )

    def make_dialog(self, *, applications=None, delete_provider=None):
        applications = applications if applications is not None else [self.application]
        dialog = CalibrationDialog(
            lambda: list(applications), lambda _application: [self.asset],
            lambda asset, rect: replace(asset, rect=rect),
            delete_provider=delete_provider,
        )
        self.addCleanup(dialog.close)
        return dialog

    def test_automatic_tracked_application_is_editable_without_open_windows_ui(self):
        dialog = self.make_dialog()
        self.assertEqual(dialog.application_selector.itemText(0), "Example")
        self.assertEqual(dialog.current_rect(), (100, 5, 130, 35))
        self.assertIsNone(dialog.findChild(type(dialog.application_selector), "liveCalibrationTargetSelector"))
        self.assertIsNone(dialog.findChild(type(dialog.application_selector), "captureLiveApplicationButton"))
        self.assertIsNone(dialog.findChild(QPushButton, "refreshTrackedApplicationsButton"))
        self.assertIsNone(dialog.findChild(QSpinBox))

    def test_delete_requires_confirmation_then_refreshes_to_empty_state(self):
        applications = [self.application]
        deleted = []
        dialog = self.make_dialog(
            applications=applications,
            delete_provider=lambda app: (deleted.append(app), applications.clear()),
        )
        with patch("resurface.features.hover_window_controls.ui.calibration.QMessageBox.question", return_value=QMessageBox.StandardButton.Cancel):
            dialog._delete_selected_application()
        self.assertEqual(deleted, [])
        with patch("resurface.features.hover_window_controls.ui.calibration.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            dialog._delete_selected_application()
        self.assertEqual(deleted, [self.application])
        self.assertEqual(dialog.application_selector.count(), 0)
        self.assertFalse(dialog.delete_button.isEnabled())

    def test_polling_is_two_seconds_and_stops_when_dialog_closes(self):
        dialog = self.make_dialog()

        self.assertEqual(dialog._application_refresh_timer.interval(), 2_000)
        self.assertTrue(dialog._application_refresh_timer.isActive())
        dialog.close()
        self.assertFalse(dialog._application_refresh_timer.isActive())

    def test_poll_adds_new_application_without_changing_selection(self):
        applications = [self.application]
        other = TrackedApplication(
            "other", "Other", Path(self.temporary.name) / "manifest_other.json"
        )
        dialog = self.make_dialog(applications=applications)
        self.assertEqual(dialog.application_selector.currentData(), self.application)

        applications.append(other)
        dialog._poll_applications()

        self.assertEqual(dialog.application_selector.count(), 2)
        self.assertEqual(dialog.application_selector.currentData(), self.application)

    def test_poll_does_not_read_or_replace_dirty_editor(self):
        calls = []
        dialog = CalibrationDialog(
            lambda: calls.append("read") or [self.application],
            lambda _application: [self.asset],
            lambda asset, rect: replace(asset, rect=rect),
        )
        self.addCleanup(dialog.close)
        self.addCleanup(lambda: setattr(dialog, "_dirty", False))
        calls.clear()
        dialog.canvas.rectChanged.emit((90, 5, 130, 35))

        dialog._poll_applications()

        self.assertTrue(dialog._dirty)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()

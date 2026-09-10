import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from resurface.ui import styles
from resurface.ui.application_pages import HoverDataImportDialog
from resurface.ui.pages.hover_window_controls_page import HoverWindowControlsPage


def make_page():
    QApplication.instance() or QApplication([])
    return HoverWindowControlsPage({}, lambda *_args: None)


def test_hover_page_keeps_import_and_export_control():
    page = make_page()

    assert page.import_button.text() == "Import Hover Data"
    assert page.export_button.text() == "Export Hover Data"


def test_hover_page_uses_master_loaded_settings_values():
    page = HoverWindowControlsPage(
        {},
        lambda *_args: None,
        enabled=False,
        taskbar_restore_enabled=False,
        dwell_ms=1_000,
    )

    assert not page.enabled_button.isChecked()
    assert not page.taskbar_restore_button.isChecked()
    assert page.dwell_combo.currentData() == 1_000


def test_hover_page_export_button_follows_explicit_pending_state():
    pending = False
    page = HoverWindowControlsPage(
        {},
        lambda *_args: None,
        has_export_changes=lambda: pending,
    )

    assert page.export_button.isEnabled() is False

    pending = True
    page.refresh_export_button()

    assert page.export_button.isEnabled() is True


def test_hover_import_dialog_is_opaque_frameless_and_unmasked():
    app = QApplication.instance() or QApplication([])
    dialog = HoverDataImportDialog(None, "")

    assert dialog.testOption(dialog.Option.DontUseNativeDialog)
    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert not dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert dialog.mask().isEmpty()
    assert not dialog.isSizeGripEnabled()
    assert dialog.minimumSize() == dialog.maximumSize()
    dialog.deleteLater()
    app.processEvents()


def test_shared_file_dialog_style_does_not_draw_an_outer_frame():
    root_rule = re.search(r"QFileDialog \{(.*?)\}", styles.file_dialog_style(), re.DOTALL)

    assert root_rule is not None
    assert "border:" not in root_rule.group(1)

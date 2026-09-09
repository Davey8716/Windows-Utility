import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

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

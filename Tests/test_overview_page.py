from PySide6.QtWidgets import QApplication

from resurface.ui import styles
from resurface.ui.application_pages import OverviewPage


def test_master_backup_path_is_theme_aware_clickable_explorer_link():
    app = QApplication.instance() or QApplication([])
    opened = []
    page = OverviewPage(None, open_master_backup_path=lambda: opened.append(True))
    state = {
        "master_backup_output_path": r"C:\Backups & Exports",
        "quick_action_ids": [],
        "screen_mover_keyboard_hotkeys": {},
        "monitor_rules": [],
    }
    try:
        styles.set_theme(True)
        page.refresh(state, set())
        label = page.status_labels["backup_path"]
        assert 'href="open-master-backup"' in label.text()
        assert "color: #ffffff" in label.text()
        label.linkActivated.emit("open-master-backup")
        assert opened == [True]

        styles.set_theme(False)
        page.refresh(state, set())
        assert "color: #000000" in label.text()
    finally:
        styles.set_theme(True)
        page.deleteLater()
        app.processEvents()

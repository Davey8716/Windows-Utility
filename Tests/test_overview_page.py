from pathlib import Path

from PySide6.QtWidgets import QApplication

from resurface.ui import styles
from resurface.ui import application_pages
from resurface.ui.application_pages import OverviewPage


def test_master_backup_path_is_theme_aware_clickable_explorer_link():
    app = QApplication.instance() or QApplication([])
    opened_backup = []
    opened_app_data = []
    page = OverviewPage(
        None,
        open_master_backup_path=lambda: opened_backup.append(True),
        open_app_data_path=lambda: opened_app_data.append(True),
        get_app_data_path=lambda: r"C:\Users\Example\AppData\Local\Windows Resurface",
    )
    state = {
        "master_backup_output_path": r"C:\Backups & Exports",
        "quick_action_ids": [],
        "screen_mover_keyboard_hotkeys": {},
        "monitor_rules": [],
    }
    try:
        styles.set_theme(True)
        page.refresh(state, set())
        backup_label = page.status_labels["backup_path"]
        app_data_label = page.status_labels["app_data_path"]
        assert list(page.status_labels).index("app_data_path") == (
            list(page.status_labels).index("backup_path") + 1
        )
        assert 'href="open-master-backup"' in backup_label.text()
        assert 'href="open-app-data"' in app_data_label.text()
        assert "color: #ffffff" in backup_label.text()
        assert "color: #ffffff" in app_data_label.text()
        backup_label.linkActivated.emit("open-master-backup")
        app_data_label.linkActivated.emit("open-app-data")
        assert opened_backup == [True]
        assert opened_app_data == [True]

        styles.set_theme(False)
        page.refresh(state, set())
        assert "color: #000000" in backup_label.text()
        assert "color: #000000" in app_data_label.text()
    finally:
        styles.set_theme(True)
        page.deleteLater()
        app.processEvents()


def test_app_data_path_defaults_to_the_live_config_parent(monkeypatch):
    app = QApplication.instance() or QApplication([])
    config_path = Path(r"C:\Users\Example\AppData\Local\Windows Resurface\app_state.json")
    monkeypatch.setattr(application_pages, "get_config_path", lambda: config_path)
    page = OverviewPage(None)
    try:
        page.refresh({}, set())
        assert str(config_path.parent) in page.status_labels["app_data_path"].text()
    finally:
        page.deleteLater()
        app.processEvents()

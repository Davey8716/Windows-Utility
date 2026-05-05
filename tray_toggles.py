from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QObject
from screen_mover import SCREEN_MOVER


class TrayIconManager(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.tray = None
        self.zen_mode_action = None

    def create_tray_icon(self):
        self.tray = QSystemTrayIcon(self.app)

        icon = self.app.windowIcon()
        if icon.isNull():
            icon = QIcon.fromTheme("applications-system")

        self.tray.setIcon(icon)
        self.tray.setToolTip("Utility Suite")

        menu = QMenu()

        self.zen_mode_action = QAction("Zen Mode", self.app)
        self.zen_mode_action.setCheckable(True)
        self.zen_mode_action.toggled.connect(self.toggle_zen_mode)
        menu.addAction(self.zen_mode_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self.app)
        quit_action.triggered.connect(self.quit_from_tray)
        menu.addAction(quit_action)

        menu.aboutToShow.connect(self.sync_zen_mode_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()
        self.sync_zen_mode_action()

    def toggle_window(self):
        if self.app.isVisible():
            self.app.hide()
        else:
            self.app.restore_from_activation()

    def sync_zen_mode_action(self):
        if not self.zen_mode_action:
            return

        enabled = bool(getattr(self.app, "state", {}).get("desktop_zen_mode_enabled", False))
        self.zen_mode_action.blockSignals(True)
        self.zen_mode_action.setChecked(enabled)
        self.zen_mode_action.blockSignals(False)

    def toggle_zen_mode(self, enabled: bool):
        zen_button = getattr(self.app, "desktop_zen_btn", None)
        if zen_button is not None:
            if zen_button.isChecked() != enabled:
                zen_button.setChecked(enabled)
            else:
                self.sync_zen_mode_action()
            return

        if self.app.actions.desktop_zen_mode_toggle(enabled) is not None:
            self.app.state["desktop_zen_mode_enabled"] = enabled
            if hasattr(self.app, "save_all_settings"):
                self.app.save_all_settings()
            if enabled:
                self.app.hide()
            self.sync_zen_mode_action()
            return

        self.sync_zen_mode_action()

    def quit_from_tray(self):
        setattr(self.app, "_quit_requested", True)
        if hasattr(self.app, "prepare_for_shutdown"):
            self.app.prepare_for_shutdown()
        self.app.close()
        qt_app = QApplication.instance()
        if qt_app:
            qt_app.quit()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_window()

    def on_close_to_tray(self):
        self.app.hide()

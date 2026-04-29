from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QObject
from screen_mover import SCREEN_MOVER


class TrayIconManager(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.tray = None

    # ==================================================
    # Create Tray Icon
    # ==================================================

    def create_tray_icon(self):
        self.tray = QSystemTrayIcon(self.app)

        # Use app icon if set, otherwise fallback
        icon = self.app.windowIcon()
        if icon.isNull():
            icon = QIcon.fromTheme("applications-system")

        self.tray.setIcon(icon)
        self.tray.setToolTip("Utility Suite")

        menu = QMenu()

        toggle_action = QAction("Toggle Window", self.app)
        toggle_action.triggered.connect(self.toggle_window)
        menu.addAction(toggle_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self.app)
        quit_action.triggered.connect(self.quit_from_tray)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    # ==================================================
    # Actions
    # ==================================================

    def toggle_window(self):
        if self.app.isVisible():
            self.app.hide()
        else:
            self.app.showNormal()
            self.app.raise_()
            self.app.activateWindow()

    def quit_from_tray(self):
        try:
            SCREEN_MOVER.stop()
        except Exception:
            pass

        if self.tray:
            self.tray.hide()

        self.app.close()

    # ==================================================
    # Tray Click Behaviour
    # ==================================================

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_window()

    # ==================================================
    # Close → tray behaviour
    # ==================================================

    def on_close_to_tray(self):
        self.app.hide()

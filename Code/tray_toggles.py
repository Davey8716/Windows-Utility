import os
from pathlib import Path

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QObject
from screen_mover import SCREEN_MOVER


TRAY_ICON_ENV_VAR = "EXE_BUILDER_TRAY_ICON_PATH"
LOCAL_ICON_CANDIDATES = (
    Path(__file__).resolve().parent / "Icons" / "Windows_utility_Icon.ico",
    Path(__file__).resolve().parent / "Icons" / "WindowsIcon.ico",
)


class TrayIconManager(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.tray = None
        self.zen_mode_action = None

    def _resolve_tray_icon(self):
        icon = self.app.windowIcon()
        if not icon.isNull():
            return icon

        return resolve_application_icon()

    def create_tray_icon(self):
        self.tray = QSystemTrayIcon(self.app)

        icon = self._resolve_tray_icon()
        if hasattr(self.app, "setWindowIcon"):
            self.app.setWindowIcon(icon)

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
                minimize_self = getattr(self.app, "_minimize_self_if_configured", None)
                if callable(minimize_self):
                    minimize_self()
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


def resolve_application_icon(window=None):
    env_icon = os.environ.get(TRAY_ICON_ENV_VAR, "").strip()
    if env_icon:
        icon = QIcon(env_icon)
        if not icon.isNull():
            return icon

    base_dir = Path(__file__).resolve().parent.parent
    for candidate in (
        *(base_dir / "Exe Tray Icons" / path.name for path in LOCAL_ICON_CANDIDATES),
        *LOCAL_ICON_CANDIDATES,
    ):
        if candidate.is_file():
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon

    if window is not None and hasattr(window, "windowIcon"):
        icon = window.windowIcon()
        if not icon.isNull():
            return icon

    return QIcon.fromTheme("applications-system")

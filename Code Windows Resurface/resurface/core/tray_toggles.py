import os
import sys
from pathlib import Path

from resurface.ui import styles
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QObject


TRAY_ICON_ENV_VAR = "EXE_BUILDER_TRAY_ICON_PATH"
TRAY_ICON_BUNDLE_NAME = "_exe_builder_tray_icon.ico"
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
        self.screen_mover_action = None
        self.hover_controls_action = None
        self.monitor_rules_action = None

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
        styles.apply_popup_menu_style(menu)

        self.zen_mode_action = QAction("Zen Mode", self.app)
        self.zen_mode_action.setCheckable(True)
        self.zen_mode_action.toggled.connect(self.toggle_zen_mode)
        menu.addAction(self.zen_mode_action)

        self.screen_mover_action = QAction("Screen Mover Enabled", self.app)
        self.screen_mover_action.setCheckable(True)
        self.screen_mover_action.toggled.connect(self.toggle_screen_mover)
        menu.addAction(self.screen_mover_action)

        self.hover_controls_action = QAction(
            "Hover Window Controls Enabled", self.app
        )
        self.hover_controls_action.setCheckable(True)
        self.hover_controls_action.toggled.connect(self.toggle_hover_controls)
        menu.addAction(self.hover_controls_action)

        self.monitor_rules_action = QAction("Monitor Rules Enabled", self.app)
        self.monitor_rules_action.setCheckable(True)
        self.monitor_rules_action.toggled.connect(self.toggle_monitor_rules)
        menu.addAction(self.monitor_rules_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self.app)
        quit_action.triggered.connect(self.quit_from_tray)
        menu.addAction(quit_action)

        menu.aboutToShow.connect(self.sync_actions)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()
        self.sync_actions()

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

    def sync_screen_mover_action(self):
        if not self.screen_mover_action:
            return

        enabled = bool(
            getattr(self.app, "state", {}).get("title_bar_dock_enabled", True)
        )
        self.screen_mover_action.blockSignals(True)
        self.screen_mover_action.setChecked(enabled)
        self.screen_mover_action.blockSignals(False)

    def sync_actions(self):
        self.sync_zen_mode_action()
        self.sync_screen_mover_action()
        self.sync_hover_controls_action()
        self.sync_monitor_rules_action()

    def sync_hover_controls_action(self):
        if not self.hover_controls_action:
            return
        service = getattr(self.app, "hover_window_controls", None)
        enabled = bool(
            getattr(
                service,
                "enabled",
                getattr(self.app, "state", {}).get(
                    "hover_window_controls_enabled", True
                ),
            )
        )
        self.hover_controls_action.blockSignals(True)
        self.hover_controls_action.setChecked(enabled)
        self.hover_controls_action.blockSignals(False)

    def sync_monitor_rules_action(self):
        if not self.monitor_rules_action:
            return

        rules = getattr(self.app, "state", {}).get("monitor_rules", [])
        self.monitor_rules_action.blockSignals(True)
        self.monitor_rules_action.setEnabled(bool(rules))
        self.monitor_rules_action.setChecked(
            any(bool(rule.get("enabled", True)) for rule in rules)
        )
        self.monitor_rules_action.blockSignals(False)

    def toggle_zen_mode(self, enabled: bool):
        page = getattr(
            getattr(self.app, "pages", None), "user_interface_page", None
        )
        if page is not None:
            page.set_desktop_zen_enabled(enabled)
            self.sync_zen_mode_action()
            return

        if self.app.actions.desktop_zen_mode_toggle(enabled) is not None:
            self.app.state["desktop_zen_mode_enabled"] = enabled
            if hasattr(self.app, "save_all_settings"):
                self.app.save_all_settings()
            if enabled:
                controller = getattr(self.app, "organising_actions", None)
                minimize_self = getattr(controller, "minimize_self_if_configured", None)
                if callable(minimize_self):
                    minimize_self()
            self.sync_zen_mode_action()
            return

        self.sync_zen_mode_action()

    def toggle_screen_mover(self, enabled: bool):
        setter = getattr(self.app, "set_screen_mover_enabled", None)
        if callable(setter):
            setter(enabled)
        else:
            self.sync_screen_mover_action()

    def toggle_hover_controls(self, enabled: bool):
        setter = getattr(self.app, "set_hover_window_controls_enabled", None)
        if callable(setter):
            setter(enabled)
        else:
            self.sync_hover_controls_action()

    def toggle_monitor_rules(self, enabled: bool):
        setter = getattr(self.app, "set_monitor_rules_enabled", None)
        if callable(setter):
            setter(enabled)
        else:
            self.sync_monitor_rules_action()

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
    icon_path = application_icon_path(window)
    if icon_path is not None:
        return QIcon(str(icon_path))

    if window is not None and hasattr(window, "windowIcon"):
        icon = window.windowIcon()
        if not icon.isNull():
            return icon

    return QIcon.fromTheme("applications-system")


def application_icon_path(window=None):
    for candidate in application_icon_candidates(window):
        if candidate.is_file():
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return candidate
    return None


def application_icon_candidates(window=None):
    candidates = []

    env_icon = os.environ.get(TRAY_ICON_ENV_VAR, "").strip()
    if env_icon:
        candidates.append(Path(env_icon))

    bundle_dir = getattr(sys, "_MEIPASS", "")
    if bundle_dir:
        candidates.extend(_expanded_bundle_icon_candidates(Path(bundle_dir)))

    executable_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        _expanded_bundle_icon_candidates(executable_dir)
        + _expanded_bundle_icon_candidates(executable_dir / "_internal")
    )

    base_dir = Path(__file__).resolve().parents[3]
    candidates.extend(
        (
            *(base_dir / "Exe Tray Icons" / path.name for path in LOCAL_ICON_CANDIDATES),
            *LOCAL_ICON_CANDIDATES,
        )
    )

    return _dedupe_icon_candidates(candidates)


def _expanded_bundle_icon_candidates(base_dir):
    bundle_path = base_dir / TRAY_ICON_BUNDLE_NAME
    candidates = [bundle_path]
    if bundle_path.is_dir():
        candidates.extend(sorted(bundle_path.glob("*.ico")))
    return candidates


def _dedupe_icon_candidates(candidates):
    unique_candidates = []
    seen = set()
    for candidate in candidates:
        normalized = os.path.normcase(os.path.abspath(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_candidates.append(candidate)
    return unique_candidates

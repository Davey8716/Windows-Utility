import os
import sys
from pathlib import Path

from resurface.features.folder_creator.launcher import DEFAULT_WINDOW_TITLES
from resurface.features.windows.window_management import close_window_handles
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
        self.menu = None
        self.folder_creator_action = None
        self.theme_action = None
        self.zen_mode_action = None
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

        menu = QMenu()
        self.menu = menu
        self.refresh_menu_style()

        self.folder_creator_action = QAction("Turn Folder Creator On", self.app)
        self.folder_creator_action.triggered.connect(self.toggle_folder_creator)
        menu.addAction(self.folder_creator_action)

        menu.addSeparator()

        self.theme_action = QAction(self.app)
        self.theme_action.triggered.connect(self.toggle_theme)
        menu.addAction(self.theme_action)

        self.zen_mode_action = QAction("Zen Mode", self.app)
        self.zen_mode_action.triggered.connect(self.toggle_zen_mode)
        menu.addAction(self.zen_mode_action)

        self.monitor_rules_action = QAction("Turn Monitor Rules On", self.app)
        self.monitor_rules_action.triggered.connect(self.toggle_monitor_rules)
        menu.addAction(self.monitor_rules_action)

        quit_action = QAction("Quit", self.app)
        quit_action.triggered.connect(self.quit_from_tray)
        menu.addAction(quit_action)

        menu.aboutToShow.connect(self.refresh_menu)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()
        self.sync_actions()

    def refresh_menu(self):
        """Update the tray menu's live theme and checked-action state."""
        self.refresh_menu_style()
        self.sync_actions()

    def refresh_menu_style(self):
        if self.menu is not None:
            styles.apply_popup_menu_style(
                self.menu, radius=styles.BUTTON_CORNER_RADIUS
            )

    def toggle_folder_creator(self, _checked: bool = False):
        if not self._folder_creator_handles():
            self.open_folder_creator()
        else:
            close_window_handles(self._folder_creator_handles())
        self.sync_folder_creator_action()

    def toggle_theme(self):
        is_dark = bool(getattr(self.app, "state", {}).get("theme_dark", True))
        enabled = not is_dark
        page = getattr(
            getattr(self.app, "pages", None), "user_interface_page", None
        )
        setter = getattr(page, "set_theme_enabled", None)
        if callable(setter):
            setter(enabled)
        else:
            state = getattr(self.app, "state", None)
            if isinstance(state, dict):
                state["theme_dark"] = enabled
            apply_theme = getattr(self.app, "apply_theme", None)
            if callable(apply_theme):
                apply_theme(enabled)
            save_settings = getattr(self.app, "save_all_settings", None)
            if callable(save_settings):
                save_settings()

        self.refresh_menu()

    def open_folder_creator(self):
        actions = getattr(self.app, "folder_actions", None)
        opener = getattr(actions, "open_folder_creator", None)
        if callable(opener):
            opener()

    def toggle_window(self):
        if self.app.isVisible():
            self.app.hide()
        else:
            self.app.restore_from_activation()

    def sync_zen_mode_action(self):
        if not self.zen_mode_action:
            return

        enabled = bool(getattr(self.app, "state", {}).get("desktop_zen_mode_enabled", False))
        self.zen_mode_action.setText(
            "Turn Zen Mode Off" if enabled else "Turn Zen Mode On"
        )

    def sync_actions(self):
        self.sync_theme_action()
        self.sync_zen_mode_action()
        self.sync_folder_creator_action()
        self.sync_monitor_rules_action()

    def sync_theme_action(self):
        if not self.theme_action:
            return

        is_dark = bool(getattr(self.app, "state", {}).get("theme_dark", True))
        self.theme_action.setText(
            "Turn Light Mode On" if is_dark else "Turn Light Mode Off"
        )

    def sync_folder_creator_action(self):
        if not self.folder_creator_action:
            return

        is_open = bool(self._folder_creator_handles())
        self.folder_creator_action.setText(
            "Turn Folder Creator Off" if is_open else "Turn Folder Creator On"
        )

    def _folder_creator_handles(self) -> list[int]:
        launcher = getattr(self.app, "folder_creator_launcher", None)
        if launcher is None:
            return []
        try:
            root = launcher.resolve_project_root()
            target = launcher.resolve_launch_target(root / "Code Folder Creator")
            return (
                launcher.window_handles(DEFAULT_WINDOW_TITLES, target)
                if target
                else []
            )
        except Exception:
            return []

    def sync_monitor_rules_action(self):
        if not self.monitor_rules_action:
            return

        rules = getattr(self.app, "state", {}).get("monitor_rules", [])
        self.monitor_rules_action.setEnabled(bool(rules))
        enabled = any(bool(rule.get("enabled", True)) for rule in rules)
        self.monitor_rules_action.setText(
            "Turn Monitor Rules Off" if enabled else "Turn Monitor Rules On"
        )

    def toggle_zen_mode(self, _checked: bool = False):
        enabled = not bool(
            getattr(self.app, "state", {}).get("desktop_zen_mode_enabled", False)
        )
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

    def toggle_monitor_rules(self, _checked: bool = False):
        rules = getattr(self.app, "state", {}).get("monitor_rules", [])
        enabled = not any(bool(rule.get("enabled", True)) for rule in rules)
        setter = getattr(self.app, "set_monitor_rules_enabled", None)
        if callable(setter):
            setter(enabled)
            self.sync_monitor_rules_action()
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

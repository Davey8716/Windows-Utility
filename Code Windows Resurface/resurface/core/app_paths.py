import shutil
import sys
from pathlib import Path
import threading

from PySide6.QtCore import (
    QFileSystemWatcher,
    QObject,
    QStandardPaths,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QDialog, QFileDialog

from resurface.core.state_manager import save_state
from resurface.core.saved_folder_names import (
    get_saved_folder_names_path,
    load_saved_folder_names,
    save_saved_folder_names,
)
from resurface.ui import styles


class _MasterBackupPathAvailabilityRelay(QObject):
    """Deliver filesystem probe results back to the application's Qt thread."""

    availability_checked = Signal(str, bool)
from resurface.ui.opaque_rounded_frame import paint_opaque_rounded_frame


class MasterBackupDirectoryDialog(QFileDialog):
    """Themed, frameless PySide folder picker for the master backup path."""

    FRAME_WIDTH = 2

    def __init__(self, parent, directory: str) -> None:
        super().__init__(parent, "Choose Master Backup Folder", directory)
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self.setOption(QFileDialog.Option.ShowDirsOnly, True)
        self.setFileMode(QFileDialog.FileMode.Directory)
        self.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setStyleSheet(styles.file_dialog_style())
        self.setSizeGripEnabled(False)
        self.setFixedSize(self.sizeHint())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        paint_opaque_rounded_frame(
            self,
            radius=styles.BUTTON_CORNER_RADIUS,
            frame_width=self.FRAME_WIDTH,
        )


class MasterBackupPathsMixin:
    MASTER_BACKUP_PATH_UNAVAILABLE_KEY = "master_backup_path_unavailable"
    NO_MASTER_BACKUP_PATH_TEXT = "No master backup path set"
    DESKTOP_BACKUP_FOLDER_NAME = "Windows Resurface Backup"
    LEGACY_DESKTOP_BACKUP_FOLDER_NAME = "Windows Resurface Backups"
    HOVER_STAGING_ENTRY = ".hover-window-controls-staging"
    # These are the only top-level entries the application creates in a master
    # backup folder. Keeping this explicit protects unrelated files when the
    # default home directory is being used as the master path.
    MANAGED_BACKUP_ENTRIES = (
        "Bookmarks",
        "Clipboard Provenance",
        "Desktop Icon Layout",
        "Desktop Screenshots",
        "Folder Creator Templates",
        "Hover Window Controls",
        "Monitor Rules",
        "Saved Folder Names",
        "TaskBarApps",
        HOVER_STAGING_ENTRY,
    )
    MATERIAL_BACKUP_ENTRIES = MANAGED_BACKUP_ENTRIES[:-1]

    def _get_app_module_attr(self, name: str, default):
        module = sys.modules.get(self.__class__.__module__)
        return getattr(module, name, default)

    def _get_master_backup_dir(self) -> str:
        if self.state.get(self.MASTER_BACKUP_PATH_UNAVAILABLE_KEY, False):
            return ""
        path_type = self._get_app_module_attr("Path", Path)
        return (
            self.state.get("master_backup_output_path")
            or self.state.get("backup_output_path")
            or self.state.get("backup_folder_path")
            or str(path_type.home())
        )

    def _choose_master_backup_dir(self):
        path_type = self._get_app_module_attr("Path", Path)
        start_dir = self._get_master_backup_dir().strip() or str(path_type.home())
        dialog = MasterBackupDirectoryDialog(self, start_dir)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected_files = dialog.selectedFiles()
        selected_dir = selected_files[0] if selected_files else ""

        if selected_dir:
            def action():
                self._set_master_backup_dir(selected_dir)

            controller = getattr(self, "organising_actions", None)
            minimize_runner = getattr(controller, "run_with_optional_minimize", None)
            if callable(minimize_runner):
                minimize_runner(action)
            else:
                action()

    @staticmethod
    def _desktop_directory() -> Path:
        desktop = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DesktopLocation
        )
        return Path(desktop) if desktop else Path.home() / "Desktop"

    def _normalise_master_backup_dir(self, path: str) -> tuple[str, bool]:
        """Keep Desktop backups in an app-owned folder that can be removed."""
        selected = Path(path)
        try:
            selected_key = selected.resolve(strict=False).as_posix().casefold()
            desktop_key = (
                self._desktop_directory().resolve(strict=False).as_posix().casefold()
            )
        except OSError:
            return str(selected), False
        if selected_key == desktop_key:
            return str(selected / self.DESKTOP_BACKUP_FOLDER_NAME), True
        return str(selected), False

    def _migrate_desktop_master_backup_path(self) -> None:
        """Upgrade a legacy Desktop root to the dedicated backup folder."""
        configured_path = str(
            self.state.get("master_backup_output_path")
            or self.state.get("backup_output_path")
            or self.state.get("backup_folder_path")
            or ""
        ).strip()
        if not configured_path:
            return
        _normalised_path, is_desktop_selection = self._normalise_master_backup_dir(
            configured_path
        )
        if is_desktop_selection:
            self._set_master_backup_dir(configured_path)

    def _set_master_backup_dir(self, path: str):
        clean_path = path.strip()
        if not clean_path:
            return
        clean_path, is_desktop_selection = self._normalise_master_backup_dir(
            clean_path
        )

        new_root = Path(clean_path)
        if is_desktop_selection:
            try:
                new_root.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                self._show_master_backup_path_error(
                    "The Desktop backup folder could not be created.", error
                )
                return

        old_root = (
            new_root
            if self.state.get(self.MASTER_BACKUP_PATH_UNAVAILABLE_KEY, False)
            else Path(self._get_master_backup_dir())
        )
        if old_root != new_root:
            try:
                if is_desktop_selection:
                    self._migrate_legacy_desktop_backup_root(old_root, new_root)
                adopting = self._should_adopt_backup_root(old_root, new_root)
                self._validate_backup_relocation(
                    old_root, new_root, ignore_staging=adopting
                )
                hover_service = getattr(self, "hover_window_controls", None)
                if adopting:
                    self._adopt_backup_root(old_root, new_root, hover_service)
                else:
                    if hover_service is not None:
                        hover_service.relocate_data_root(
                            new_root / self.HOVER_STAGING_ENTRY
                        )
                    self._move_saved_folder_names(old_root, new_root)
                    self._move_managed_backups(old_root, new_root)
                # A master path can be the user's home directory or contain
                # unrelated files. Remove only an empty, dedicated old root.
                if (
                    old_root.exists()
                    and old_root != Path.home()
                    and not any(old_root.iterdir())
                ):
                    old_root.rmdir()
            except OSError as error:
                self._show_master_backup_path_error(
                    "The master backup path was not changed because existing "
                    "data could not be moved.",
                    error,
                )
                return

        self.backup_path = clean_path
        self.state[self.MASTER_BACKUP_PATH_UNAVAILABLE_KEY] = False
        self.state["master_backup_output_path"] = clean_path
        self.state["backup_output_path"] = clean_path
        self.state["backup_folder_path"] = clean_path

        self._refresh_master_backup_path_display()

        save_state_fn = self._get_app_module_attr("save_state", save_state)
        save_state_fn(self.state)
        self._watch_master_backup_path()

    def _show_master_backup_path_error(self, summary: str, error: Exception) -> None:
        args = (
            self._message_box_icon("Critical"),
            "Master Backup Path",
            f"{summary}\n\n{error}",
            self._message_box_button("Ok"),
            self._message_box_button("Ok"),
        )
        options = {
            "fixed_popup_width": 540,
            "text_block_width": 460,
            "popup_corner_radius": styles.BUTTON_CORNER_RADIUS,
        }
        try:
            self._show_modal_message(*args, **options)
        except TypeError:
            # Lightweight test and integration shims may expose the legacy
            # five-argument modal callback only.
            self._show_modal_message(*args)

    def _start_master_backup_path_monitor(self) -> None:
        """Watch the active path and poll for removable-drive removal."""
        watcher = QFileSystemWatcher(self)
        watcher.directoryChanged.connect(self._queue_master_backup_path_check)
        watcher.fileChanged.connect(self._queue_master_backup_path_check)
        self._master_backup_path_watcher = watcher

        timer = QTimer(self)
        timer.setInterval(2000)
        timer.timeout.connect(self._request_master_backup_path_check)
        timer.start()
        self._master_backup_path_check_timer = timer
        self._master_backup_path_probe_lock = threading.Lock()
        self._master_backup_path_probe_in_flight = False
        self._master_backup_path_probe_pending = ""
        relay = _MasterBackupPathAvailabilityRelay(self)
        relay.availability_checked.connect(
            self._handle_master_backup_path_check
        )
        self._master_backup_path_probe_relay = relay
        self._watch_master_backup_path()

    def _watch_master_backup_path(self) -> None:
        watcher = getattr(self, "_master_backup_path_watcher", None)
        if watcher is None:
            return
        watched = watcher.directories() + watcher.files()
        if watched:
            watcher.removePaths(watched)

        path = self._get_master_backup_dir().strip()
        if not path:
            return
        target = Path(path)
        watched_paths = []
        if target.exists():
            watched_paths.append(str(target))
        if target.parent.exists():
            watched_paths.append(str(target.parent))
        if watched_paths:
            watcher.addPaths(list(dict.fromkeys(watched_paths)))

    def _queue_master_backup_path_check(self, _changed_path: str = "") -> None:
        QTimer.singleShot(0, self._request_master_backup_path_check)

    def _request_master_backup_path_check(self) -> None:
        """Check path availability without blocking the GUI event loop."""
        path = self._get_master_backup_dir().strip()
        if not path:
            return
        with self._master_backup_path_probe_lock:
            if self._master_backup_path_probe_in_flight:
                self._master_backup_path_probe_pending = path
                return
            self._master_backup_path_probe_in_flight = True
        threading.Thread(
            target=self._probe_master_backup_path_availability,
            args=(path,),
            name="MasterBackupPathProbe",
            daemon=True,
        ).start()

    def _probe_master_backup_path_availability(self, path: str) -> None:
        try:
            available = Path(path).is_dir()
        except OSError:
            available = False
        self._master_backup_path_probe_relay.availability_checked.emit(
            path, available
        )

    def _handle_master_backup_path_check(
        self, checked_path: str, available: bool
    ) -> None:
        with self._master_backup_path_probe_lock:
            self._master_backup_path_probe_in_flight = False
            pending_path = self._master_backup_path_probe_pending
            self._master_backup_path_probe_pending = ""

        # Ignore a result for a path the user has since replaced.
        if self._get_master_backup_dir().strip() == checked_path and not available:
            self._clear_unavailable_master_backup_path(checked_path)
        if pending_path and pending_path != checked_path:
            self._request_master_backup_path_check()

    def _check_master_backup_path_availability(self) -> None:
        """Compatibility entry point for direct callers and older tests."""
        path = self._get_master_backup_dir().strip()
        if not path:
            return
        try:
            available = Path(path).is_dir()
        except OSError:
            available = False
        if not available:
            self._clear_unavailable_master_backup_path(path)

    def _clear_unavailable_master_backup_path(self, previous_path: str) -> None:
        if self.state.get(self.MASTER_BACKUP_PATH_UNAVAILABLE_KEY, False):
            return
        self.backup_path = ""
        self.state[self.MASTER_BACKUP_PATH_UNAVAILABLE_KEY] = True
        self.state["master_backup_output_path"] = ""
        self.state["backup_output_path"] = ""
        self.state["backup_folder_path"] = ""
        self._refresh_master_backup_path_display()
        save_state_fn = self._get_app_module_attr("save_state", save_state)
        save_state_fn(self.state)
        self._watch_master_backup_path()
        self._show_modal_message(
            self._message_box_icon("Warning"),
            "Master Backup Path Unavailable",
            "The configured Master Backup Path was deleted or is no longer "
            f"available.\n\n{previous_path}\n\nChoose a new Master Backup Path "
            "before creating or exporting backups.",
            self._message_box_button("Ok"),
            self._message_box_button("Ok"),
            fixed_popup_width=540,
            text_block_width=460,
            popup_corner_radius=styles.BUTTON_CORNER_RADIUS,
        )

    def _should_adopt_backup_root(self, old_root: Path, new_root: Path) -> bool:
        """Return whether an existing backup set should become the active root."""
        old_has_backups = any(
            (old_root / name).exists() or (old_root / name).is_symlink()
            for name in self.MATERIAL_BACKUP_ENTRIES
        )
        new_has_backups = any(
            (new_root / name).exists() or (new_root / name).is_symlink()
            for name in self.MATERIAL_BACKUP_ENTRIES
        )
        return not old_has_backups and new_has_backups

    def _adopt_backup_root(self, old_root: Path, new_root: Path, hover_service) -> None:
        """Adopt an orphaned backup set without replacing any of its files."""
        old_staging = old_root / self.HOVER_STAGING_ENTRY
        new_staging = new_root / self.HOVER_STAGING_ENTRY
        if hover_service is not None:
            hover_service.adopt_data_root(new_staging)
            return

        if new_staging.exists() or new_staging.is_symlink():
            if old_staging.exists() or old_staging.is_symlink():
                if old_staging.is_dir() and not old_staging.is_symlink():
                    shutil.rmtree(old_staging)
                else:
                    old_staging.unlink()
        elif old_staging.exists() or old_staging.is_symlink():
            new_staging.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_staging), str(new_staging))

    def _validate_backup_relocation(
        self,
        old_root: Path,
        new_root: Path,
        *,
        ignore_staging: bool = False,
    ) -> None:
        """Reject unsafe nesting and file collisions before moving anything."""
        old_resolved = old_root.resolve(strict=False)
        new_resolved = new_root.resolve(strict=False)
        if new_resolved.is_relative_to(old_resolved) and not self._is_allowed_desktop_migration(
            old_resolved, new_resolved
        ):
            raise OSError("The new Master Backup Path cannot be inside the old path.")

        for name in self.MANAGED_BACKUP_ENTRIES:
            if name == "Saved Folder Names" or (
                ignore_staging and name == self.HOVER_STAGING_ENTRY
            ):
                continue
            source = old_root / name
            if source.exists() or source.is_symlink():
                self._validate_backup_entry(source, new_root / name)

    def _is_allowed_desktop_migration(
        self, old_root: Path, new_root: Path
    ) -> bool:
        desktop = self._desktop_directory().resolve(strict=False)
        dedicated_root = desktop / self.DESKTOP_BACKUP_FOLDER_NAME
        # Only the fixed app-owned Desktop child is exempt.  It is safe even
        # when a legacy path elsewhere happens to contain Desktop, because
        # relocation moves explicitly listed application entries only.
        return new_root == dedicated_root

    def _migrate_legacy_desktop_backup_root(
        self, old_root: Path, new_root: Path
    ) -> None:
        """Move data from the former plural Desktop folder when present."""
        legacy_root = self._desktop_directory() / self.LEGACY_DESKTOP_BACKUP_FOLDER_NAME
        if legacy_root == old_root or not legacy_root.exists():
            return
        self._validate_backup_relocation(legacy_root, new_root)
        self._move_saved_folder_names(legacy_root, new_root)
        self._move_managed_backups(legacy_root, new_root)
        if legacy_root.exists() and not any(legacy_root.iterdir()):
            legacy_root.rmdir()

    @classmethod
    def _validate_backup_entry(cls, source: Path, destination: Path) -> None:
        if not destination.exists() and not destination.is_symlink():
            return
        if source.is_dir() and not source.is_symlink() and destination.is_dir():
            for child in source.iterdir():
                cls._validate_backup_entry(child, destination / child.name)
            return
        raise OSError(f"Cannot move backup because it already exists: {destination}")

    @staticmethod
    def _move_saved_folder_names(old_root: Path, new_root: Path) -> None:
        """Merge saved names because both master paths can contain a list."""
        old_path = get_saved_folder_names_path(old_root)
        if not old_path.exists():
            return
        new_path = get_saved_folder_names_path(new_root)
        merged = [*load_saved_folder_names(new_path)]
        seen = {name.casefold() for name in merged}
        for name in load_saved_folder_names(old_path):
            if name.casefold() not in seen:
                merged.append(name)
                seen.add(name.casefold())
        if not save_saved_folder_names(merged[:20], new_path):
            raise OSError("Could not move saved folder names to the new Master Backup Path.")
        old_path.unlink()
        try:
            old_path.parent.rmdir()
        except OSError:
            pass

    def _move_managed_backups(self, old_root: Path, new_root: Path) -> None:
        """Relocate all application-owned backup entries to *new_root*.

        Existing destination folders are merged so changing a path never
        discards backups already stored at the new location.
        """
        for name in self.MANAGED_BACKUP_ENTRIES:
            source = old_root / name
            if source.exists() or source.is_symlink():
                self._move_backup_entry(source, new_root / name)

    @classmethod
    def _move_backup_entry(cls, source: Path, destination: Path) -> None:
        if not destination.exists() and not destination.is_symlink():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            return

        if source.is_dir() and not source.is_symlink() and destination.is_dir():
            for child in source.iterdir():
                cls._move_backup_entry(child, destination / child.name)
            source.rmdir()
            return

        # A file collision cannot be merged safely without overwriting an
        # existing backup. Leave both paths intact and keep the old setting.
        raise OSError(f"Cannot move backup because it already exists: {destination}")

    def _get_master_backup_path_display_text(self) -> str:
        full_path = self._get_master_backup_dir().strip()
        if not full_path:
            return ""

        page = getattr(
            getattr(self, "pages", None), "organising_utilities_page", None
        )
        if page is None:
            return full_path

        available_width = max(0, page.path_display_width() - 24)
        if available_width <= 0:
            return full_path

        metrics = QFontMetrics(page.path_display_font())
        if metrics.horizontalAdvance(full_path) <= available_width:
            return full_path

        return metrics.elidedText(
            full_path,
            Qt.TextElideMode.ElideRight,
            available_width,
        )

    def _refresh_master_backup_path_display(self) -> None:
        rules_page = getattr(
            getattr(self, "pages", None), "monitor_rules_page", None
        )
        if rules_page is not None:
            rules_page.refresh_export_button()
        page = getattr(
            getattr(self, "pages", None), "organising_utilities_page", None
        )
        if page is None:
            return

        display_text = self._get_master_backup_path_display_text()
        page.set_backup_path(
            display_text,
            unavailable=bool(
                self.state.get(self.MASTER_BACKUP_PATH_UNAVAILABLE_KEY, False)
            ),
        )
        refresh_overview = getattr(self, "refresh_overview", None)
        if refresh_overview is not None:
            refresh_overview()

    def _build_master_output_path(self, filename: str) -> str:
        path_type = self._get_app_module_attr("Path", Path)
        base_dir = self._get_master_backup_dir().strip()
        return str(path_type(base_dir) / filename) if base_dir else filename

    def has_master_backup_path(self) -> bool:
        return bool(self._get_master_backup_dir().strip())

    def get_default_taskbar_backup_dir(self) -> str:
        path_type = self._get_app_module_attr("Path", Path)
        base_dir = self._get_master_backup_dir().strip()
        if not base_dir:
            return ""
        return str(path_type(base_dir) / "TaskBarApps")

    def get_default_bookmarks_export_dir(self) -> str:
        path_type = self._get_app_module_attr("Path", Path)
        base_dir = self._get_master_backup_dir().strip()
        if not base_dir:
            return ""
        base_path = path_type(base_dir)
        if base_path.name.lower() == "bookmarks":
            return str(base_path)
        return str(base_path / "Bookmarks")

    def get_default_hover_controls_export_dir(self) -> str:
        path_type = self._get_app_module_attr("Path", Path)
        base_dir = self._get_master_backup_dir().strip()
        if not base_dir:
            return ""
        return str(path_type(base_dir) / "Hover Window Controls")

    def get_default_desktop_layout_path(self) -> str:
        path_type = self._get_app_module_attr("Path", Path)
        base_dir = self._get_master_backup_dir().strip()
        if not base_dir:
            return ""
        return str(
            path_type(base_dir) / "Desktop Icon Layout" / "desktop_icon_layout.json"
        )

    def get_default_screenshot_path(self) -> str:
        path_type = self._get_app_module_attr("Path", Path)
        base_dir = self._get_master_backup_dir().strip()
        if not base_dir:
            return ""
        return str(
            path_type(base_dir) / "Desktop Screenshots" / "desktop_screenshot.png"
        )

    def _refresh_taskbar_backup_folder_button(self):
        backup_dir = self.get_default_taskbar_backup_dir()
        refresh = getattr(self, "background_refresh", None)
        if refresh is not None:
            refresh.request_folder_open_check(backup_dir)
            return
        self._taskbar_backup_folder_open = bool(backup_dir) and self.explorer_windows.is_folder_open(backup_dir)

    def _apply_taskbar_backup_folder_open(self, path: str, is_open: bool) -> None:
        if path == self.get_default_taskbar_backup_dir():
            self._taskbar_backup_folder_open = bool(is_open)

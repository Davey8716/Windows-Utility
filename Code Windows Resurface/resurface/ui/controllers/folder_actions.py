from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer

from resurface.core.saved_folder_names import (
    add_saved_folder_name,
    load_saved_folder_names,
    remove_saved_folder_name,
)
from resurface.features.desktop.folder_service import FolderCreationStatus
from resurface.features.folder_creator.launcher import (
    DEFAULT_WINDOW_TITLES,
    FolderCreatorLaunchStatus,
)


class FolderActionsController:
    def __init__(self, app, folder_service, launcher, organising_actions):
        self.app = app
        self.folder_service = folder_service
        self.launcher = launcher
        self.organising_actions = organising_actions

    def create_desktop_folder(self, folder_input, *, save_name: bool | None = None) -> None:
        name = folder_input.strip() if isinstance(folder_input, str) else folder_input.text().strip()
        if not name:
            return

        def action():
            result = self.folder_service.create(Path.home() / "Desktop", name)
            if result.status is FolderCreationStatus.EXISTS:
                self.organising_actions.show_timed_message(
                    self.app._message_box_icon("NoIcon"), "Folder to Desktop",
                    "A folder with that name already exists on Desktop.",
                    show_close_now_button=True,
                )
                return
            if result.status is FolderCreationStatus.FAILED:
                self.organising_actions.show_timed_message(
                    self.app._message_box_icon("NoIcon"), "Folder to Desktop",
                    f"Could not create folder:\n{result.error}",
                    show_close_now_button=True,
                )
                return
            page = getattr(
                getattr(self.app, "pages", None), "folder_utilities_page", None
            )
            toggle = getattr(self.app, "save_folder_name_toggle", None)
            should_save = bool(save_name)
            if save_name is None and toggle is not None:
                should_save = toggle.isChecked()
            saved_names = add_saved_folder_name(name) if should_save else None
            if page is not None:
                page.folder_created(saved_names)
            else:
                refresh = getattr(self.app, "refresh_saved_folder_names", None)
                if saved_names is not None and callable(refresh):
                    refresh(saved_names)
                if toggle is not None:
                    toggle.setChecked(False)
                if not isinstance(folder_input, str):
                    folder_input.clear()
            self.organising_actions.show_timed_message(
                self.app._message_box_icon("Information"), "Folder to Desktop",
                f"Created desktop folder:\n{result.path}", show_close_now_button=True,
            )
        self.organising_actions.run_with_optional_minimize(action)

    def save_folder_name(self, name: str) -> None:
        clean_name = name.strip()
        if not clean_name:
            return
        saved_names = add_saved_folder_name(clean_name)
        page = getattr(
            getattr(self.app, "pages", None), "folder_utilities_page", None
        )
        if page is not None:
            page.folder_name_saved(saved_names, clean_name)

    def delete_saved_folder_name(self, name: str) -> None:
        clean_name = name.strip()
        saved_names = load_saved_folder_names()
        matching_name = next(
            (value for value in saved_names if value.casefold() == clean_name.casefold()),
            None,
        )
        if matching_name is None:
            return

        answer = self.app._show_modal_message(
            self.app._message_box_icon("Question"),
            "Delete Saved Folder Name",
            f'Delete the saved folder name "{matching_name}"?',
            self.app._message_box_button("Yes") | self.app._message_box_button("No"),
            self.app._message_box_button("No"),
        )
        if answer != self.app._message_box_button("Yes"):
            return

        updated_names = remove_saved_folder_name(matching_name)
        if any(value.casefold() == matching_name.casefold() for value in updated_names):
            return
        page = getattr(
            getattr(self.app, "pages", None), "folder_utilities_page", None
        )
        if page is not None:
            page.folder_name_deleted(updated_names)

    def open_folder_creator(self) -> None:
        root = self.launcher.resolve_project_root()
        project_dir = root / "Code Folder Creator"
        target = self.launcher.resolve_launch_target(project_dir)
        if target is None:
            self._show_launch_warning(project_dir)
            return
        self.app.showMinimized()
        result = self.launcher.launch_or_focus(root, DEFAULT_WINDOW_TITLES)
        if result.status is FolderCreatorLaunchStatus.FOCUSED:
            return
        if result.status is FolderCreatorLaunchStatus.LAUNCHED:
            QTimer.singleShot(100, lambda: self._focus_with_retry(result.target))
            return
        self._restore_parent()
        self._show_launch_warning(project_dir)

    def _focus_with_retry(self, target: Path, *, attempt: int = 0, max_attempts: int = 20) -> None:
        if self.launcher.focus_existing(DEFAULT_WINDOW_TITLES, target) or attempt >= max_attempts:
            return
        QTimer.singleShot(150, lambda: self._focus_with_retry(target, attempt=attempt + 1, max_attempts=max_attempts))

    def _restore_parent(self) -> None:
        self.app.showNormal()
        self.app.raise_()
        self.app.activateWindow()

    def _show_launch_warning(self, project_dir: Path) -> None:
        self.organising_actions.show_timed_message(
            self.app._message_box_icon("Warning"), "Folder Creator",
            f"Could not open Folder Creator from:\n{project_dir}",
            show_close_now_button=True,
        )

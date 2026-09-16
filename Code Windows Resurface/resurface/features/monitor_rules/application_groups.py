"""Built-in application groups understood by Monitor Rules."""

from __future__ import annotations

from resurface.features.folder_creator.launcher import FolderCreatorLauncher


WINDOWS_RESURFACE_GROUP = "windows_resurface"
WINDOWS_RESURFACE_GROUP_NAME = "Windows Resurface"
WINDOWS_RESURFACE_COMPONENT_EXECUTABLES = frozenset(
    {"windows resurface.exe", "folder creator.exe", "nested folder creator.exe"}
)


def is_windows_resurface_component_rule(rule: dict) -> bool:
    """Return whether a legacy executable rule names one bundled component."""
    return str(rule.get("executable_name", "")).strip().casefold() in (
        WINDOWS_RESURFACE_COMPONENT_EXECUTABLES
    )


def is_folder_creator_process(process_id: int) -> bool:
    """Identify the packaged or source-launched bundled companion."""
    if not process_id:
        return False
    launcher = FolderCreatorLauncher()
    root = launcher.resolve_project_root()
    target = launcher.resolve_launch_target(root / "Code Folder Creator")
    if target is None:
        return False
    return launcher.process_references_target(process_id, target)


def window_application_group(details: dict, *, app_hwnd=None) -> str:
    """Return the built-in group that owns a discovered window, if any."""
    if app_hwnd is not None and int(details.get("hwnd", 0)) == int(app_hwnd):
        return WINDOWS_RESURFACE_GROUP
    if is_folder_creator_process(int(details.get("process_id", 0))):
        return WINDOWS_RESURFACE_GROUP
    return ""

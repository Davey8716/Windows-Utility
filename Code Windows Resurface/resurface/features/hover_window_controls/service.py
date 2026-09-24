"""Windows Resurface lifecycle owner for Hover Window Controls."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from resurface.core.instance_runtime import current_instance_scope
from resurface.features.hover_window_controls.app.identity import (
    DEFAULT_DWELL_MS,
    DWELL_STEP_MS,
    MAX_DWELL_MS,
    MIN_DWELL_MS,
    windows_resurface_data_directory,
)
from resurface.features.hover_window_controls.app.data_export import (
    refresh_application_data_manifest,
    validate_application_data_export,
)
from resurface.features.hover_window_controls.core.hover_controller import HoverController
from resurface.features.hover_window_controls.platform.taskbar_preview import (
    InstalledAutoHotkeyRunner,
    TaskbarRestoreMonitor,
)
from resurface.features.hover_window_controls.platform.win32 import Win32WindowApi
from resurface.features.hover_window_controls.ui.calibration import CalibrationDialog
from resurface.features.hover_window_controls.vision.detection import (
    CaptionVisionDetector,
    VisionCache,
)


def normalized_dwell_ms(value: object) -> int:
    try:
        dwell_ms = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DWELL_MS
    dwell_ms = min(max(dwell_ms, MIN_DWELL_MS), MAX_DWELL_MS)
    offset = dwell_ms - MIN_DWELL_MS
    return MIN_DWELL_MS + round(offset / DWELL_STEP_MS) * DWELL_STEP_MS


class HoverWindowControlsService(QObject):
    settings_changed = Signal(bool, bool, int)

    def __init__(
        self,
        state: dict,
        save_state: Callable[[dict], None],
        parent: QObject | None = None,
        *,
        data_root: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self._save_state = save_state
        self.data_root = data_root or windows_resurface_data_directory()
        settings = self._load_data_settings()
        hover = settings.get("hover", {})
        self.enabled = bool(hover.get("enabled", state.get("hover_window_controls_enabled", True)))
        self.taskbar_restore_enabled = bool(hover.get("taskbar_restore_enabled", state.get("hover_taskbar_restore_enabled", True)))
        self.dwell_ms = normalized_dwell_ms(hover.get("dwell_ms", state.get("hover_window_controls_dwell_ms", DEFAULT_DWELL_MS)))
        self._pending_export = bool(hover.get("pending_export", False))

        cache = VisionCache(
            base_dir=self.data_root / "vision-cache",
            legacy_base_dir=None,
        )
        vision = CaptionVisionDetector(cache)
        self.window_api = Win32WindowApi(
            vision=vision,
            allowed_self_hwnd_provider=self._allowed_self_window_handle,
        )
        self.taskbar_monitor = TaskbarRestoreMonitor(dwell_ms=self.dwell_ms)
        self.controller = HoverController(
            self.window_api,
            auxiliary_monitor=self.taskbar_monitor,
            dwell_ms=self.dwell_ms,
            parent=self,
        )
        self.taskbar_restore_available = InstalledAutoHotkeyRunner().available()
        self._started = False
        self._busy = False
        self._write_data_settings()

    def _allowed_self_window_handle(self) -> int | None:
        if current_instance_scope()[0] != "exe":
            return None
        parent = self.parent()
        if parent is None or not hasattr(parent, "winId"):
            return None
        try:
            hwnd = int(parent.winId())
        except (RuntimeError, TypeError, ValueError):
            return None
        return hwnd or None

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        if self.enabled:
            # Starting the controller also starts its native caption detector
            # and vision/accessibility workers.  Do not create that runtime
            # infrastructure merely to keep a disabled preference on standby.
            self.controller.start()
            self._apply_runtime_settings()
            return

        # Taskbar restoration is intentionally independent of caption hover
        # controls, so retain it when explicitly enabled without bringing up
        # the caption-control infrastructure.
        if self.taskbar_restore_enabled and self.taskbar_restore_available:
            self.taskbar_monitor.start()

    def stop(self) -> None:
        if not self._started:
            return
        self.controller.stop()
        self._started = False

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self.enabled:
            self._emit_settings()
            return
        self.enabled = enabled
        if self._started and not self._busy:
            if enabled:
                self.controller.start()
            self.controller.set_caption_controls_enabled(enabled)
        self._persist(mark_export_pending=True)

    def set_taskbar_restore_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self.taskbar_restore_enabled:
            self._emit_settings()
            return
        self.taskbar_restore_enabled = enabled
        if self._started and not self._busy:
            if (
                enabled
                and not self.enabled
                and self.taskbar_restore_available
            ):
                self.taskbar_monitor.start()
            self._set_taskbar_monitor_enabled(enabled)
        self._persist(mark_export_pending=True)

    def set_dwell_ms(self, dwell_ms: object) -> None:
        normalized = normalized_dwell_ms(dwell_ms)
        if normalized == self.dwell_ms:
            self._emit_settings()
            return
        self.dwell_ms = normalized
        self.controller.set_dwell_ms(normalized)
        self._persist(mark_export_pending=True)

    def calibrate(self, parent=None) -> None:
        if self._busy:
            return
        self._busy = True
        self._suspend_for_operation()
        try:
            dialog = CalibrationDialog(
                self.window_api.list_tracked_calibration_apps,
                self.window_api.list_tracked_calibration_assets,
                self._save_tracked_calibration,
                target_provider=self.window_api.list_calibration_targets,
                capture_provider=self.window_api.capture_vision_calibration,
                save_provider=self._save_vision_calibration,
                clear_provider=self.clear_learned_buttons,
                parent=parent,
            )
            dialog.exec()
            self._write_data_settings()
        finally:
            self._finish_operation()

    def clear_learned_buttons(self) -> None:
        self.window_api.clear_vision_cache()
        self._mark_export_pending()

    def _save_tracked_calibration(self, asset, rect):
        updated = self.window_api.update_tracked_calibration(asset, rect)
        self._mark_export_pending()
        return updated

    def _save_vision_calibration(self, snapshot, assignments):
        profile = self.window_api.save_vision_calibration(snapshot, assignments)
        self._mark_export_pending()
        return profile

    def relocate_data_root(self, destination: Path) -> None:
        """Move the active cache to a new master backup folder safely."""
        destination = Path(destination)
        if destination == self.data_root:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        old_export_root = self.export_root
        new_export_root = destination.parent / "Hover Window Controls"
        if old_export_root.exists():
            if new_export_root.exists():
                shutil.copytree(old_export_root, new_export_root, dirs_exist_ok=True)
            else:
                shutil.copytree(old_export_root, new_export_root)
        if self.data_root.exists():
            if destination.exists():
                shutil.copytree(self.data_root, destination, dirs_exist_ok=True)
            else:
                shutil.copytree(self.data_root, destination)
        destination.mkdir(parents=True, exist_ok=True)
        old_root = self.data_root
        self.data_root = destination
        self.window_api._vision.cache.base_dir = destination / "vision-cache"
        self._write_data_settings()
        if old_root.exists():
            shutil.rmtree(old_root)
        if old_export_root.exists() and old_export_root != new_export_root:
            shutil.rmtree(old_export_root)

    def adopt_data_root(self, destination: Path) -> None:
        """Use an existing cache when an orphaned master backup is adopted."""
        destination = Path(destination)
        if destination == self.data_root:
            return
        if not destination.exists():
            self.relocate_data_root(destination)
            return
        if not destination.is_dir() or destination.is_symlink():
            raise OSError("The existing Hover Window Controls data is not a usable folder.")
        if self._busy:
            raise OSError("Hover Window Controls is busy and cannot change storage folders.")

        old_root = self.data_root
        old_values = (
            self.enabled,
            self.taskbar_restore_enabled,
            self.dwell_ms,
            self._pending_export,
        )
        self._busy = True
        self._suspend_for_operation()
        try:
            self.data_root = destination
            self.window_api._vision.cache.base_dir = destination / "vision-cache"
            hover = self._load_data_settings().get("hover", {})
            self.enabled = bool(hover.get("enabled", self.enabled))
            self.taskbar_restore_enabled = bool(
                hover.get("taskbar_restore_enabled", self.taskbar_restore_enabled)
            )
            self.dwell_ms = normalized_dwell_ms(
                hover.get("dwell_ms", self.dwell_ms)
            )
            self._pending_export = bool(
                hover.get("pending_export", self._pending_export)
            )
            self.controller.set_dwell_ms(self.dwell_ms)
            if old_root.exists():
                shutil.rmtree(old_root)
            self._emit_settings()
        except Exception:
            self.data_root = old_root
            self.window_api._vision.cache.base_dir = old_root / "vision-cache"
            (
                self.enabled,
                self.taskbar_restore_enabled,
                self.dwell_ms,
                self._pending_export,
            ) = old_values
            self.controller.set_dwell_ms(self.dwell_ms)
            raise
        finally:
            self._finish_operation()

    @property
    def export_root(self) -> Path:
        return self.data_root.parent / "Hover Window Controls"

    def _load_data_settings(self) -> dict:
        try:
            payload = json.loads((self.data_root / "settings.json").read_text(encoding="utf-8"))
            if payload.get("schema_version") == 1 and isinstance(payload.get("hover"), dict):
                return payload
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return {"schema_version": 1, "hover": {}}

    def _data_settings(self) -> dict:
        return {
            "schema_version": 1,
            "hover": {
                "enabled": self.enabled,
                "taskbar_restore_enabled": self.taskbar_restore_enabled,
                "dwell_ms": self.dwell_ms,
                "pending_export": self._pending_export,
            },
        }

    def _write_data_settings(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        temporary = self.data_root / ".settings.json.tmp"
        temporary.write_text(json.dumps(self._data_settings(), indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.data_root / "settings.json")
        refresh_application_data_manifest(self.data_root, self._data_settings())

    def has_export_changes(self) -> bool:
        return self._pending_export

    def export_all_data(self, destination_parent: Path | None = None):
        if self._busy:
            raise RuntimeError("Hover Window Controls is already busy")
        self._busy = True
        self._suspend_for_operation()
        try:
            pending_export = self._pending_export
            self._pending_export = False
            try:
                self._write_data_settings()
                destination = destination_parent or self.export_root
                destination.mkdir(parents=True, exist_ok=True)
                return self.window_api.export_all_data(
                    destination, settings=self._data_settings()
                )
            except Exception:
                self._pending_export = pending_export
                self._write_data_settings()
                raise
        finally:
            self._finish_operation()

    def validate_import(self, source_directory: Path) -> dict:
        return validate_application_data_export(source_directory)

    def import_all_data(self, source_directory: Path):
        if self._busy:
            raise RuntimeError("Hover Window Controls is already busy")
        self._busy = True
        self._suspend_for_operation()
        try:
            result = self.window_api.import_all_data(source_directory)
            hover = result.settings["hover"]
            self.enabled = bool(hover["enabled"])
            self.taskbar_restore_enabled = bool(
                hover["taskbar_restore_enabled"]
            )
            self.dwell_ms = normalized_dwell_ms(hover["dwell_ms"])
            self.controller.set_dwell_ms(self.dwell_ms)
            self._persist(mark_export_pending=True)
            return result
        finally:
            self._finish_operation()

    def _suspend_for_operation(self) -> None:
        if self._started:
            self.controller.suspend()

    def _finish_operation(self) -> None:
        self._busy = False
        if self._started:
            self.controller.resume()
            self._apply_runtime_settings()

    def _apply_runtime_settings(self) -> None:
        self.controller.set_caption_controls_enabled(self.enabled)
        self._set_taskbar_monitor_enabled(self.taskbar_restore_enabled)

    def _set_taskbar_monitor_enabled(self, enabled: bool) -> None:
        if enabled and self.taskbar_restore_available:
            self.taskbar_monitor.resume()
        else:
            self.taskbar_monitor.suspend()

    def _mark_export_pending(self) -> None:
        self._pending_export = True
        self._write_data_settings()

    def _persist(self, *, mark_export_pending: bool = False) -> None:
        if mark_export_pending:
            self._pending_export = True
        self.state["hover_window_controls_enabled"] = self.enabled
        self.state["hover_taskbar_restore_enabled"] = self.taskbar_restore_enabled
        self.state["hover_window_controls_dwell_ms"] = self.dwell_ms
        self._save_state(self.state)
        self._write_data_settings()
        self._emit_settings()

    def _emit_settings(self) -> None:
        self.settings_changed.emit(
            self.enabled,
            self.taskbar_restore_enabled,
            self.dwell_ms,
        )

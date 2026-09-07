"""Windows Resurface lifecycle owner for Hover Window Controls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from resurface.features.hover_window_controls.app.identity import (
    DEFAULT_DWELL_MS,
    DWELL_STEP_MS,
    MAX_DWELL_MS,
    MIN_DWELL_MS,
    windows_resurface_data_directory,
)
from resurface.features.hover_window_controls.app.data_export import (
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
        self.enabled = bool(state.get("hover_window_controls_enabled", True))
        self.taskbar_restore_enabled = bool(
            state.get("hover_taskbar_restore_enabled", True)
        )
        self.dwell_ms = normalized_dwell_ms(
            state.get("hover_window_controls_dwell_ms", DEFAULT_DWELL_MS)
        )

        cache = VisionCache(
            base_dir=self.data_root / "vision-cache",
            legacy_base_dir=None,
        )
        vision = CaptionVisionDetector(cache)
        self.window_api = Win32WindowApi(vision=vision)
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

    def start(self) -> None:
        if self._started:
            return
        self.controller.start()
        self._started = True
        self._apply_runtime_settings()

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
        self.state["hover_window_controls_enabled"] = enabled
        if self._started and not self._busy:
            self.controller.set_caption_controls_enabled(enabled)
        self._persist()

    def set_taskbar_restore_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self.taskbar_restore_enabled:
            self._emit_settings()
            return
        self.taskbar_restore_enabled = enabled
        self.state["hover_taskbar_restore_enabled"] = enabled
        if self._started and not self._busy:
            self._set_taskbar_monitor_enabled(enabled)
        self._persist()

    def set_dwell_ms(self, dwell_ms: object) -> None:
        normalized = normalized_dwell_ms(dwell_ms)
        self.dwell_ms = normalized
        self.state["hover_window_controls_dwell_ms"] = normalized
        self.controller.set_dwell_ms(normalized)
        self._persist()

    def calibrate(self, parent=None) -> None:
        if self._busy:
            return
        self._busy = True
        self._suspend_for_operation()
        try:
            dialog = CalibrationDialog(
                self.window_api.list_tracked_calibration_apps,
                self.window_api.list_tracked_calibration_assets,
                self.window_api.update_tracked_calibration,
                target_provider=self.window_api.list_calibration_targets,
                capture_provider=self.window_api.capture_vision_calibration,
                save_provider=self.window_api.save_vision_calibration,
                clear_provider=self.clear_learned_buttons,
                parent=parent,
            )
            dialog.exec()
        finally:
            self._finish_operation()

    def clear_learned_buttons(self) -> None:
        self.window_api.clear_vision_cache()

    def export_all_data(self, destination_parent: Path):
        if self._busy:
            raise RuntimeError("Hover Window Controls is already busy")
        self._busy = True
        self._suspend_for_operation()
        try:
            self.data_root.mkdir(parents=True, exist_ok=True)
            settings = {
                "schema_version": 1,
                "hover": {
                    "enabled": self.enabled,
                    "taskbar_restore_enabled": self.taskbar_restore_enabled,
                    "dwell_ms": self.dwell_ms,
                },
            }
            (self.data_root / "settings.json").write_text(
                json.dumps(settings, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            return self.window_api.export_all_data(destination_parent)
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
            self.state["hover_window_controls_enabled"] = self.enabled
            self.state["hover_taskbar_restore_enabled"] = (
                self.taskbar_restore_enabled
            )
            self.state["hover_window_controls_dwell_ms"] = self.dwell_ms
            self.controller.set_dwell_ms(self.dwell_ms)
            self._persist()
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

    def _persist(self) -> None:
        self._save_state(self.state)
        self._emit_settings()

    def _emit_settings(self) -> None:
        self.settings_changed.emit(
            self.enabled,
            self.taskbar_restore_enabled,
            self.dwell_ms,
        )

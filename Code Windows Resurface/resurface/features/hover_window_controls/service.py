"""Windows Resurface lifecycle owner for Hover Window Controls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from resurface.features.hover_window_controls.app.identity import (
    DEFAULT_DWELL_MS,
    MAX_DWELL_MS,
    MIN_DWELL_MS,
    windows_resurface_data_directory,
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
    return MIN_DWELL_MS + round((dwell_ms - MIN_DWELL_MS) / 250) * 250


class HoverWindowControlsService(QObject):
    settings_changed = Signal(bool, int)

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
        self.dwell_ms = normalized_dwell_ms(
            state.get("hover_window_controls_dwell_ms", DEFAULT_DWELL_MS)
        )
        cache = VisionCache(base_dir=self.data_root / "vision-cache", legacy_base_dir=None)
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
        self._calibrating = False
        self._application_discovery_timer = QTimer(self)
        self._application_discovery_timer.setInterval(2_000)
        self._application_discovery_timer.timeout.connect(
            self._discover_open_application
        )

    def start(self) -> None:
        if self._started:
            return
        self.controller.start()
        self._started = True
        if not self.enabled:
            self.controller.suspend()
        else:
            self._application_discovery_timer.start()
            self._discover_open_application()

    def stop(self) -> None:
        if not self._started:
            return
        self.controller.stop()
        self._application_discovery_timer.stop()
        self._started = False

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self.enabled:
            self._emit_settings()
            return
        self.enabled = enabled
        self.state["hover_window_controls_enabled"] = enabled
        if self._started and not self._calibrating:
            self.controller.resume() if enabled else self.controller.suspend()
        if self._started:
            if enabled:
                self._application_discovery_timer.start()
                self._discover_open_application()
            else:
                self._application_discovery_timer.stop()
        self._persist()

    def _discover_open_application(self) -> None:
        if not self._started or not self.enabled:
            return
        try:
            self.window_api.observe_next_open_application()
        except Exception:
            # Discovery is opportunistic; inaccessible or transient windows
            # must never affect hover controls or the settings UI.
            return

    def set_dwell_ms(self, dwell_ms: object) -> None:
        normalized = normalized_dwell_ms(dwell_ms)
        self.dwell_ms = normalized
        self.state["hover_window_controls_dwell_ms"] = normalized
        self.controller.set_dwell_ms(normalized)
        self._persist()

    def calibrate(self, parent=None) -> None:
        if self._calibrating:
            return
        self._calibrating = True
        if self._started and self.enabled:
            self.controller.suspend()
        try:
            dialog = CalibrationDialog(
                self.window_api.list_tracked_calibration_apps,
                self.window_api.list_tracked_calibration_assets,
                self.window_api.update_tracked_calibration,
                delete_provider=(
                    self.window_api.delete_tracked_calibration_application
                ),
                parent=parent,
            )
            dialog.exec()
        finally:
            self._calibrating = False
            if self._started and self.enabled:
                self.controller.resume()

    def clear_learned_buttons(self) -> None:
        self.window_api.clear_vision_cache()

    def export_all_data(self, destination_parent: Path):
        self.data_root.mkdir(parents=True, exist_ok=True)
        settings = {
            "schema_version": 1,
            "hover": {"enabled": self.enabled, "dwell_ms": self.dwell_ms},
        }
        (self.data_root / "settings.json").write_text(
            json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8"
        )
        return self.window_api.export_all_data(destination_parent)

    def _persist(self) -> None:
        self._save_state(self.state)
        self._emit_settings()

    def _emit_settings(self) -> None:
        self.settings_changed.emit(self.enabled, self.dwell_ms)

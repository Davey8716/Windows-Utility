"""Controls for Windows display output and individual DDC/CI monitors."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from resurface.features.system import display_power
from resurface.ui import styles
from resurface.ui.pages.page_controls import PageControls


class DisplayPowerPage(PageControls):
    def __init__(self, register_tooltip, parent=None):
        super().__init__("display_power", register_tooltip, parent)

        note = QLabel(
            "Turn off all screens while the PC stays awake, or put one supported "
            "external monitor in standby. Move the mouse or press a key to wake "
            "Windows-controlled screens. The iiyama temporarily disconnects in "
            "Windows, which may move windows; use Wake to restore it. Other monitors "
            "may need their physical power button if Wake does not work."
        )
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setFixedWidth(self.CONTROL_ROW_WIDTH)
        self.content_layout.addWidget(note, 0, Qt.AlignmentFlag.AlignHCenter)

        actions = QWidget(self)
        actions.setFixedWidth(self.CONTROL_ROW_WIDTH)
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(self.CONTROL_COLUMN_GAP)
        self.all_off_button = self._button("Turn Off All Screens")
        self.refresh_button = self._button("Refresh Monitors")
        action_layout.addWidget(self.all_off_button)
        action_layout.addWidget(self.refresh_button)
        self.content_layout.addWidget(actions, 0, Qt.AlignmentFlag.AlignHCenter)

        self.monitor_container = QWidget(self)
        self.monitor_container.setFixedWidth(self.CONTROL_ROW_WIDTH)
        self.monitor_layout = QVBoxLayout(self.monitor_container)
        self.monitor_layout.setContentsMargins(0, 0, 0, 0)
        self.monitor_layout.setSpacing(self.CONTROL_COLUMN_GAP)
        self.content_layout.addWidget(
            self.monitor_container, 0, Qt.AlignmentFlag.AlignHCenter
        )
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setFixedWidth(self.CONTROL_ROW_WIDTH)
        self.content_layout.addWidget(self.status, 0, Qt.AlignmentFlag.AlignHCenter)

        self.all_off_button.clicked.connect(self._turn_off_all)
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    def _button(self, label: str) -> QPushButton:
        button = QPushButton(label, self)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        styles.apply_page_control_size(button)
        button.setStyleSheet(styles.organizing_button_style(13))
        return button

    def refresh(self) -> None:
        while self.monitor_layout.count():
            item = self.monitor_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        try:
            displays = display_power.connected_displays()
        except Exception as error:
            self.status.setText(f"Could not list monitors: {error}")
            return
        if not displays:
            self.status.setText("No active monitors were found.")
            return
        self.status.setText("")
        for display in displays:
            label = QLabel(display.label, self.monitor_container)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.monitor_layout.addWidget(label)
            row = QWidget(self.monitor_container)
            controls = QHBoxLayout(row)
            controls.setContentsMargins(0, 0, 0, 0)
            controls.setSpacing(self.CONTROL_COLUMN_GAP)
            standby = self._button("Standby")
            wake = self._button("Wake")
            standby.clicked.connect(
                lambda _checked=False, device=display.device: self._set_power(device, False)
            )
            wake.clicked.connect(
                lambda _checked=False, device=display.device: self._set_power(device, True)
            )
            controls.addWidget(standby)
            controls.addWidget(wake)
            self.monitor_layout.addWidget(row)

    def _set_power(self, device: str, awake: bool) -> None:
        try:
            display_power.set_display_power(device, awake=awake)
        except Exception as error:
            self.status.setText(
                f"Individual control failed: {error}. Check that DDC/CI is enabled "
                "in the monitor's settings. If Wake fails, use its physical power button."
            )
        else:
            self.status.setText("Wake command sent." if awake else "Standby command sent.")

    def _turn_off_all(self) -> None:
        self.status.setText("Turning off Windows display output...")
        QTimer.singleShot(350, self._send_all_off)

    def _send_all_off(self) -> None:
        try:
            display_power.turn_off_all_displays()
        except Exception as error:
            self.status.setText(f"Could not turn off the screens: {error}")

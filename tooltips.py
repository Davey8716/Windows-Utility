from PySide6.QtCore import QObject, QTimer, QPoint
from PySide6.QtWidgets import QToolTip


class QtTooltipManager(QObject):
    def __init__(self, widget, text, delay=500):
        super().__init__(widget)

        self.widget = widget
        self.text = text
        self.delay = delay

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show_tooltip)

        # Attach events
        widget.installEventFilter(self)

    # --------------------------------------------------
    # Event filter
    # --------------------------------------------------

    def eventFilter(self, obj, event):
        etype = event.type()

        if etype == event.Type.Enter:
            self._schedule()

        elif etype in (event.Type.Leave, event.Type.MouseButtonPress):
            self._hide()

        return False

    # --------------------------------------------------
    # Tooltip logic
    # --------------------------------------------------

    def _schedule(self):
        self._timer.start(self.delay)

    def _show_tooltip(self):
        # Global toggle lives on app
        app = self.widget.window()
        if hasattr(app, "tooltips_enabled") and not app.tooltips_enabled:
            return

        pos = self.widget.mapToGlobal(QPoint(20, self.widget.height()))
        QToolTip.showText(pos, self.text, self.widget)

    def _hide(self):
        self._timer.stop()
        QToolTip.hideText()

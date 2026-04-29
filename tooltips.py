from PySide6.QtCore import QObject, QTimer, QPoint, QEvent
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

        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        etype = event.type()

        if etype == QEvent.Type.Enter:
            self._schedule()

        elif etype == QEvent.Type.ToolTip:
            return True

        elif etype in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress):
            self._hide()
        return False

    def _schedule(self):
        self._timer.start(self.delay)

    def _show_tooltip(self):
        app = self.widget.window()
        if hasattr(app, "tooltips_enabled") and not app.tooltips_enabled:
            return

        pos = self.widget.mapToGlobal(QPoint(20, self.widget.height()))
        QToolTip.showText(pos, self.text, self.widget)

    def _hide(self):
        self._timer.stop()
        QToolTip.hideText()

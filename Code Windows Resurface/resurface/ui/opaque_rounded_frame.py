"""Painting helper for opaque, frameless dialogs with a continuous outline."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen

from resurface.ui import style_tokens


def paint_opaque_rounded_frame(widget, *, radius: int, frame_width: int = 2) -> None:
    """Draw one antialiased outer frame without masks or transparency."""
    inset = frame_width / 2
    frame = QRectF(widget.rect()).adjusted(inset, inset, -inset, -inset)
    if frame.isEmpty():
        return
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(style_tokens.SURFACE_BORDER)
    pen.setWidthF(frame_width)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(frame, max(0, radius - inset), max(0, radius - inset))

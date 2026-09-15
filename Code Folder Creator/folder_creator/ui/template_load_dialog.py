from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QWidget

from folder_creator.ui import styles
from resurface.ui.opaque_rounded_frame import paint_opaque_rounded_frame


class TemplateLoadDialog(QFileDialog):
    """Themed, frameless picker for loading a saved folder template."""

    FRAME_WIDTH = 2
    NAME_FILTER = (
        "Templates (*.json *.txt *.md);;JSON Files (*.json);;"
        "Text Outline (*.txt);;Markdown Outline (*.md)"
    )

    def __init__(self, parent, user_template_dir: Path) -> None:
        super().__init__(
            parent if isinstance(parent, QWidget) else None,
            "Load Template",
            str(user_template_dir),
            self.NAME_FILTER,
        )
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self.setFileMode(QFileDialog.FileMode.ExistingFile)
        self.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setStyleSheet(styles.resurface_styles.file_dialog_style())
        self.setSizeGripEnabled(False)
        self.setFixedSize(self.sizeHint())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        paint_opaque_rounded_frame(
            self,
            radius=styles.resurface_styles.BUTTON_CORNER_RADIUS,
            frame_width=self.FRAME_WIDTH,
        )

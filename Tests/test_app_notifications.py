import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QWidget

from resurface.ui.app_notifications import WindowMessageMixin


class _MessageBoxHost(QWidget, WindowMessageMixin):
    pass


def test_compact_modal_message_wraps_and_centers_its_text_block(monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = _MessageBoxHost()
    captured = []

    def capture_dialog(dialog):
        captured.append(dialog)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "exec", capture_dialog)

    host._show_modal_message(
        QMessageBox.Icon.NoIcon,
        "Clear all learned buttons?",
        "This permanently removes all learned caption-button images and "
        "calibration data.\nHover preferences are kept.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
        text_block_width=420,
        center_text_block=True,
    )
    app.processEvents()

    dialog = captured[0]
    text_label = dialog.findChild(QLabel, "qt_msgbox_label")
    assert text_label.wordWrap()
    assert text_label.width() == 420
    assert text_label.minimumHeight() >= text_label.heightForWidth(420)
    assert text_label.alignment() & Qt.AlignmentFlag.AlignHCenter

    unconstrained_dialog = QMessageBox(host)
    host._apply_message_box_icon(unconstrained_dialog, QMessageBox.Icon.NoIcon)
    unconstrained_dialog.setText(
        "This permanently removes all learned caption-button images and "
        "calibration data.\nHover preferences are kept."
    )
    unconstrained_dialog.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
    )
    host._set_borderless_message_box(unconstrained_dialog)
    host._prepare_message_box_layout(unconstrained_dialog)

    assert dialog.sizeHint().width() < unconstrained_dialog.sizeHint().width()
    host.deleteLater()

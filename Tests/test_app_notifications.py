import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QWidget,
)

from resurface.ui.app_notifications import WindowMessageMixin


class _MessageBoxHost(QWidget, WindowMessageMixin):
    pass


def test_timed_message_uses_requested_text_width_without_changing_padding_or_close_button():
    app = QApplication.instance() or QApplication([])
    host = _MessageBoxHost()

    dialog = host._show_timed_message(
        QMessageBox.Icon.NoIcon,
        "Desktop Layout",
        "Captured desktop layout with 74 icon position(s) saved to:\n"
        "C:\\Users\\davey\\Desktop\\Administrator\\Backup\\Desktop Icon Layout\\desktop_icon_layout.json",
        text_block_width=360,
        show_close_now_button=True,
    )
    app.processEvents()

    text_label = dialog.findChild(QLabel, "qt_msgbox_label")
    button_box = dialog.findChild(QDialogButtonBox)
    layout = dialog.layout()

    assert text_label.width() == 360
    assert text_label.height() >= text_label.heightForWidth(360)
    assert text_label.minimumHeight() >= text_label.heightForWidth(360)
    assert layout.contentsMargins().left() == 16
    assert layout.contentsMargins().top() == 16
    assert layout.contentsMargins().right() == 16
    assert layout.contentsMargins().bottom() == 16
    assert [button.text() for button in button_box.buttons()] == ["Close now"]
    assert layout.itemAt(layout.indexOf(button_box)).alignment() & Qt.AlignmentFlag.AlignHCenter

    dialog.close()
    app.processEvents()
    host.deleteLater()


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

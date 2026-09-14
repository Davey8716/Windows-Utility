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


def test_disable_all_confirmation_policy_requires_an_explicit_enabled_preference():
    host = _MessageBoxHost()
    try:
        assert not host.disable_all_confirmations_enabled()
        host.state = {"disable_all_confirmations_enabled": True}
        assert host.disable_all_confirmations_enabled()
    finally:
        host.deleteLater()


def test_enabled_preference_bypasses_existing_modal_confirmations(monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = _MessageBoxHost()
    host.state = {"disable_all_confirmations_enabled": True}
    shown = []

    def capture_dialog(dialog):
        shown.append(dialog)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "exec", capture_dialog)
    try:
        answer = host._show_modal_message(
            QMessageBox.Icon.Warning,
            "Replace backup",
            "Replace the existing backup?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        app.processEvents()

        assert answer == QMessageBox.StandardButton.Yes
        assert shown == []
    finally:
        host.deleteLater()


def test_enabled_preference_bypasses_save_confirmations(monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = _MessageBoxHost()
    host.state = {"disable_all_confirmations_enabled": True}
    shown = []

    def capture_dialog(dialog):
        shown.append(dialog)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "exec", capture_dialog)
    try:
        answer = host._show_modal_message(
            QMessageBox.Icon.NoIcon,
            "Export Hover Data",
            "Export data?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        app.processEvents()

        assert answer == QMessageBox.StandardButton.Save
        assert shown == []
    finally:
        host.deleteLater()


def test_enabled_preference_keeps_non_confirmation_modal_messages(monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = _MessageBoxHost()
    host.state = {"disable_all_confirmations_enabled": True}
    shown = []

    def capture_dialog(dialog):
        shown.append(dialog)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "exec", capture_dialog)
    try:
        answer = host._show_modal_message(
            QMessageBox.Icon.Warning,
            "Problem",
            "The action could not be completed.",
            QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
        )
        app.processEvents()

        assert answer == QMessageBox.StandardButton.Ok
        assert len(shown) == 1
    finally:
        host.deleteLater()


def test_disable_all_confirmations_warning_has_danger_symbol_and_button(monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = _MessageBoxHost()
    captured = []

    def approve(dialog):
        captured.append(dialog)
        dialog.findChild(QWidget, "disableAllConfirmationsDangerButton").click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", approve)
    try:
        assert host.confirm_disable_all_confirmations()
        app.processEvents()

        dialog = captured[0]
        assert dialog.minimumWidth() >= 570
        assert dialog._popup_corner_radius == 18
        assert not dialog.iconPixmap().isNull()
        assert dialog.findChild(QWidget, "disableAllConfirmationsDangerButton")
    finally:
        host.deleteLater()


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


def test_acknowledged_message_applies_its_requested_corner_radius():
    app = QApplication.instance() or QApplication([])
    host = _MessageBoxHost()
    try:
        dialog = host._show_acknowledged_message(
            QMessageBox.Icon.NoIcon,
            "Drive Reminder",
            "An external drive is still connected.",
            popup_corner_radius=6,
        )
        app.processEvents()

        assert dialog._popup_corner_radius == 6
        assert not dialog.mask().isEmpty()
    finally:
        dialog.close()
        app.processEvents()
        host.deleteLater()


def test_fixed_width_modal_confirmation_wraps_and_centers_its_text_block(monkeypatch):
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
        fixed_popup_width=360,
        center_text_block=True,
    )
    app.processEvents()

    dialog = captured[0]
    text_label = dialog.findChild(QLabel, "qt_msgbox_label")
    button_box = dialog.findChild(QDialogButtonBox)
    assert text_label.wordWrap()
    assert text_label.width() == 328
    assert text_label.minimumHeight() >= text_label.heightForWidth(328)
    assert text_label.alignment() & Qt.AlignmentFlag.AlignHCenter
    assert dialog.minimumWidth() == 360
    assert dialog.maximumWidth() == 360
    assert dialog.defaultButton().text() == "Cancel"
    assert [button.text() for button in button_box.buttons()] == ["Yes", "Cancel"]
    host.deleteLater()

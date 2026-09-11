import os
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QDialog, QMessageBox

from resurface.ui import application_pages
from resurface.ui.application_pages import (
    ApplicationPageComposer,
    HOVER_CONTROLS_PROMPT_CORNER_RADIUS,
)


def _composer_for(app):
    composer = object.__new__(ApplicationPageComposer)
    composer.app = app
    composer._refresh_hover_export_button = MagicMock()
    return composer


def test_main_clear_confirmation_uses_monitor_export_styling():
    service = type("Service", (), {"clear_learned_buttons": MagicMock()})()
    app = type(
        "App",
        (),
        {
            "hover_window_controls": service,
            "_show_modal_message": MagicMock(
                return_value=QMessageBox.StandardButton.Cancel
            ),
        },
    )()
    composer = _composer_for(app)

    composer._clear_hover_controls_cache()

    app._show_modal_message.assert_called_once_with(
        QMessageBox.Icon.NoIcon,
        "Clear all learned buttons?",
        "This permanently removes all learned caption-button\n images and "
        "calibration data.\nHover preferences are kept.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
        text_block_width=420,
        center_text_block=True,
        popup_corner_radius=HOVER_CONTROLS_PROMPT_CORNER_RADIUS,
    )
    service.clear_learned_buttons.assert_not_called()


def test_hover_export_confirmation_uses_monitor_export_styling(tmp_path):
    service = type(
        "Service",
        (),
        {
            "has_export_changes": MagicMock(return_value=True),
            "export_all_data": MagicMock(return_value=None),
        },
    )()
    app = type(
        "App",
        (),
        {
            "hover_window_controls": service,
            "get_default_hover_controls_export_dir": lambda self: str(tmp_path),
            "_show_modal_message": MagicMock(
                return_value=QMessageBox.StandardButton.Cancel
            ),
        },
    )()
    composer = _composer_for(app)

    composer._export_hover_controls()

    args, kwargs = app._show_modal_message.call_args
    assert args[:5] == (
        QMessageBox.Icon.NoIcon,
        "Export Hover Data",
        args[2],
        QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Save,
    )
    assert str(Path(tmp_path)) in args[2]
    assert kwargs["popup_corner_radius"] == HOVER_CONTROLS_PROMPT_CORNER_RADIUS
    service.export_all_data.assert_not_called()


def test_hover_import_confirmation_uses_compact_centered_text(tmp_path):
    manifest_path = tmp_path / "export_manifest.json"
    service = type(
        "Service",
        (),
        {"validate_import": MagicMock()},
    )()
    app = type(
        "App",
        (),
        {
            "hover_window_controls": service,
            "get_default_hover_controls_export_dir": lambda self: str(tmp_path),
            "_show_modal_message": MagicMock(
                return_value=QMessageBox.StandardButton.Cancel
            ),
        },
    )()
    composer = _composer_for(app)
    dialog = MagicMock()
    dialog.exec.return_value = QDialog.DialogCode.Accepted
    dialog.selectedFiles.return_value = [str(manifest_path)]

    with patch.object(application_pages, "HoverDataImportDialog", return_value=dialog):
        composer._import_hover_controls()

    app._show_modal_message.assert_called_once_with(
        QMessageBox.Icon.Warning,
        "Import Hover Data",
        "Replace the current Hover Window Controls\n"
        "settings and learned button data with this backup?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
        text_block_width=420,
        center_text_block=True,
        popup_corner_radius=application_pages.styles.BUTTON_CORNER_RADIUS,
    )
    service.validate_import.assert_called_once_with(tmp_path)

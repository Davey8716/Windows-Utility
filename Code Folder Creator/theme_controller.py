
from typing import cast

from PySide6.QtWidgets import QApplication

class ThemeController:
    def __init__(self):
        self.current_index = -2
        self.current_accent = "#000000"
        
    
    def select_theme(self, index, service,window):
        self.current_index = -2
        app = self._application()
        app.setStyleSheet("""
            QWidget {
                background-color: #282832;
                color: #ffffff;
            }

            QLineEdit {
                background-color: #3a4860;
                border: 2px solid #ffffff;
                border-radius: 6px;
                color: #ffffff;
                font-family: "Segoe UI";
                font-size: 15px;
                font-weight: 700;
                padding: 4px 8px;
                selection-background-color: #4a6fa8;
            }

            QLabel {
                background: transparent;
                border: none;
                color: #ffffff;
                font-family: "Segoe UI";
                font-size: 14px;
                font-weight: 700;
            }

            QPushButton:disabled {
                background-color: #1c66c4;
                color: #ffffff;
                border: 1px solid #8ac6f6;
            }

            QPushButton {
                background-color: #1c66c4;
                color: #ffffff;
                border: 1px solid #8ac6f6;
                border-radius: 3px;
                font-weight: 700;
                font-family: "Segoe UI";
                font-size: 14px;
                text-align: center;
                padding: 4px 8px;
            }

            QPushButton:hover {
                background-color: #2a78da;
            }

            QPushButton:pressed,
            QPushButton:checked {
                background-color: #144e9a;
                color: #ffffff;
                border: 1px solid #8ac6f6;
            }

            QComboBox {
                background-color: #1c66c4;
                color: #ffffff;
                border: 1px solid #8ac6f6;
                border-radius: 3px;
                padding: 4px 8px;
                font-family: "Segoe UI";
                font-size: 14px;
                font-weight: 700;
            }

            QComboBox:disabled {
                background-color: #1c66c4;
                color: #ffffff;
                border: 1px solid #8ac6f6;
            }

            QComboBox QLineEdit {
                background: transparent;
                border: none;
                color: #ffffff;
                qproperty-alignment: AlignCenter;
            }

            QComboBox:hover,
            QComboBox:on {
                background-color: #2a78da;
            }

            QComboBox::drop-down {
                border: none;
                background: transparent;
                width: 22px;
            }

            QComboBox QAbstractItemView {
                background-color: #1c66c4;
                color: #ffffff;
                selection-background-color: #2a78da;
                selection-color: #ffffff;
                border: 1px solid #8ac6f6;
                padding: 4px;
                outline: 0;
            }

            QComboBox QAbstractItemView::item {
                padding: 4px 8px;
                border: none;
            }

            QComboBox QAbstractItemView::item:selected {
                background-color: #2a78da;
                color: #ffffff;
                border-left: 3px solid #144e9a;
            }

            QComboBox QAbstractItemView::item:hover {
                background-color: #2a78da;
                color: #ffffff;
            }

            QSpinBox {
                background-color: #3a4860;
                color: #ffffff;
                border: 2px solid #ffffff;
                border-radius: 6px;
                padding: 10px;
                text-align: center;
                font-family: "Segoe UI";
                font-size: 14px;
                font-weight: 700;
            }

            QSpinBox:disabled {
                background-color: #3a4860;
                color: #ffffff;
                border: 2px solid #ffffff;
            }
            
            QTreeWidget {
                background-color: #3a4860;
                color: #ffffff;
                border: 2px solid #ffffff;
                border-radius: 2px;
                selection-background-color: #3a4860;
                font-family: "Segoe UI";
                font-size: 14px;
                font-weight: 700;
            }

            QTreeWidget::item:selected {
                background-color: #3a4860;
                color: #ffffff;
                font-weight: 700;
                font-family: "Segoe UI";
                font-size: 14px;
            }

            QTreeWidget::item:selected:active {
                background-color: #4a6fa8;
                font-family: "Segoe UI";
                font-size: 14px;
            }

            QTreeWidget::item:selected:!active {
                background-color: #3a4860;
                font-family: "Segoe UI";
                font-size: 14px;
            }

            QSpinBox::up-button, QSpinBox::down-button {
                width: 4px;
            }
        """)
        self.current_accent = "#000000"
        service.state["theme_index"] = -2

    # ---------------------------------------------------------
    # Internal
    # ---------------------------------------------------------

    def _application(self) -> QApplication:
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("ThemeController requires an active QApplication instance.")
        return cast(QApplication, app)

    def _extract_accent_key(self, theme_name: str) -> str:
        return (
            theme_name
            .replace("dark_", "")
            .replace(".xml", "")
        )
    

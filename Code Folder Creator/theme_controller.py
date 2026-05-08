
from typing import cast

from PySide6.QtWidgets import QApplication

class ThemeController:
    def __init__(self):
        self.current_index = 0
        
    
    def select_theme(self, index, service,window):
        self.current_index = index

        if index == -2:
            # white theme
            app = self._application()
            app.setStyleSheet("""
            QWidget {
                background-color: #C5C5C5;
                color: #1a1a1a;
            }

            QLineEdit {
                    background-color: #e8e8e8;
                    border: 2px solid #444;
                    border-radius: 2px;
                    font-family: "Rubik UI";
                    font-size: 12px;
                    font-weight: 700;
                }

            QLabel {
                    background-color: #e8e8e8;
                    border: 2px solid #444;
                    border-radius: 2px;
                    font-family: "Rubik UI";
                    font-size: 12px;
                    font-weight: 700;
                }

            QPushButton:disabled {
                background-color: #858585;
                color: #696969;
                border: 1px solid #444;
            }

            QPushButton {
                background-color: #e8e8e8;
                color: #1a1a1a;
                border: 1px solid #cfcfcf;
                font-weight: 700;
                font-family: "Rubik UI";
                font-size: 12px;
                text-transform: uppercase;
                text-align: center;
                padding: 4px;
            }

            QPushButton:hover {
                background-color: #dcdcdc;
            }

            QPushButton:checked {
                background-color: #2a2a2a;
                color: white;
                border: 2px solid #2a2a2a;
            }

            QComboBox {
                background-color: #e8e8e8;
                color: #1a1a1a;
                border: 1px solid #cfcfcf;
                padding-left: 15px;
                padding-right: 15px;
                font-family: "Rubik UI";
                font-size: 13px;
            }

            QComboBox:disabled {
                background-color: #858585;
                color: #696969;
                border: 1px solid #444;
            }

            QComboBox QLineEdit {
                qproperty-alignment: AlignCenter;
            }

            QComboBox QAbstractItemView {
                padding: 4px;
            }

            QSpinBox {
                background-color: #e8e8e8;
                color: #1a1a1a;
                border: 1px solid #cfcfcf;
                padding: 10px;
                text-align: center;
                font-family: "Rubik UI";
                font-size: 13px;
            }

            QSpinBox:disabled {
                background-color: #858585;
                color: #696969;
                border: 1px solid #444;
            }
            
            QTreeWidget {
                selection-background-color: #e8e8e8;  /* fallback */
                font-family: "Rubik UI";
                font-size: 16px;
            }

            QTreeWidget::item:selected {
                background-color: #e8e8e8;
                color: #1a1a1a;
                font-weight: 700;
                font-family: "Rubik UI";
                font-size: 16px;
            }

            QTreeWidget::item:selected:active {
                background-color: #dcdcdc;
                font-family: "Rubik UI";
                font-size: 16px;
            }

            QTreeWidget::item:selected:!active {
                background-color: #e8e8e8;
                font-family: "Rubik UI";
                font-size: 16px;
            }

            QSpinBox::up-button, QSpinBox::down-button {
                width: 4px;
            }
        """)
            self.current_accent = "#000000"

        elif index == -1:
            # black theme
            app = self._application()
            app.setStyleSheet("""
                QWidget {
                    background-color: #121212;
                    color: #FFFFFF;
                }

                QLineEdit {
                    background-color: #0D0D0D;
                    border: 2px solid #444;
                    border-radius: 2px;
                    font-family: "Rubik UI";
                    font-size: 12px;
                    font-weight: 700;
                }
                
                QLabel {
                    background-color: #0D0D0D;
                    border: 2px solid #444;
                    border-radius: 2px;
                    font-family: "Rubik UI";
                    font-size: 12px;
                    font-weight: 700;
                }

                QPushButton:disabled {
                    background-color: #2a2a2a;
                    color: #777777;
                    border: 1px solid #444;
                }

                QPushButton {
                    background-color: #0D0D0D;
                    color: white;
                    font-weight: 700;
                    font-family: "Rubik UI";
                    font-size: 12px;
                    text-transform: uppercase;
                    text-align: center;
                    padding: 4px;
                }

                QPushButton:checked {
                    background-color: white;
                    color: black;
                    border: 2px solid white;
                    font-weight: 700;
                    text-transform: uppercase;
                }

                QComboBox {
                    background-color: #0D0D0D;
                    color: white;
                    padding-left: 15px;
                    padding-right: 15px;
                    font-family: "Rubik UI";
                    font-size: 13px;
                }

                QComboBox QLineEdit {
                    qproperty-alignment: AlignCenter;
                }
                
                QComboBox:disabled {
                        background-color: #2a2a2a;
                        color: #696969;
                        border: 1px solid #444;
                    }

                QSpinBox {
                    background-color: #0D0D0D;
                    color: white;
                    padding: 10px;
                    text-align: center;
                    font-family: "Rubik UI";
                    font-size: 13px;
                }
                
                QSpinBox:disabled {
                    background-color: #2a2a2a;
                    color: #696969;
                    border: 1px solid #444;
                }
            
                QSpinBox::up-button, QSpinBox::down-button {
                    width: 4px;
                }

                QTreeWidget {
                    selection-background-color: #444444;  /* fallback */
                    font-family: "Rubik UI";
                    font-size: 16px;
                }

                QTreeWidget::item:selected {
                    background-color: #2a2a2a;
                    color: white;
                    font-family: "Rubik UI";
                    font-size: 16px;
                }

                QTreeWidget::item:selected:active {
                    background-color: #3a3a3a;
                    font-family: "Rubik UI";
                    font-size: 16px;
                }

                QTreeWidget::item:selected:!active {
                    background-color: #2a2a2a;
                    font-family: "Rubik UI";
                    font-size: 16px;
                }

                QComboBox QAbstractItemView {
                    padding: 4px;
                }
            """)
            self.current_accent = "#FFFFFF"

        for i, btn in enumerate(window.theme_buttons):
            is_active = (
                (index == -2 and i == 0) or
                (index == -1 and i == 1)
            )

            btn.setChecked(is_active)
            btn.setEnabled(True)
            btn.setCheckable(True)

            if is_active:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #7a7a7a;
                        border: 2px solid #5a5a5a;
                        border-radius: 6px;
                    }
                """)
            elif i == 0:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #e8e8e8;
                        border: 2px solid #bdbdbd;
                        border-radius: 6px;
                    }
                    QPushButton:checked {
                        border: 3px solid black;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #1e1e1e;
                        border: 2px solid #444;
                        border-radius: 6px;
                    }
                    QPushButton:checked {
                        border: 3px solid white;
                    }
                """)
                    
        service.set_state("theme_index", index)

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
    

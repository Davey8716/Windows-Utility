from PySide6.QtCore import QTimer

class StatusController:
    def __init__(self, window, service):
        self.w = window
        self.service = service

        self.nested_timer = QTimer(window)
        self.nested_timer.setSingleShot(True)
        self.nested_timer.timeout.connect(lambda: self.reset("nested"))

    # ---------------------------------------------------------
    # SET STATUS
    # ---------------------------------------------------------
    def set(self, message: str, target: str = "nested", status_type: str = "info"):
        icon = self.w.smart_status_icon
        text = self.w.smart_status_text
        frame = self.w.smart_status_frame
        self.nested_timer.start(5000)

        # icon
        if status_type == "success":
            icon.setText("✓")
            color = "#2ecc71"   # green
        elif status_type == "error":
            icon.setText("✕")
            color = "#e74c3c"   # red
        else:
            icon.setText(">")
            color = self.service.theme_controller.current_accent
            

        # neutral frame
        frame.setStyleSheet("""
            QFrame#statusFrame {
                background-color: transparent;
            }
            QLabel {
                color: #ffffff;
                font-family: "Segoe UI";
                font-size: 14px;
                font-weight: 700;
            }
        """)

        # hide icon visually (your current behaviour)
        icon.setStyleSheet(f"font-weight: 700; color: {color};")

        text.setText(message)

    # ---------------------------------------------------------
    # RESET STATUS
    # ---------------------------------------------------------
    def reset(self, target: str):
        accent = self.service.theme_controller.current_accent

        icon = self.w.smart_status_icon
        text = self.w.smart_status_text
        frame = self.w.smart_status_frame

        icon.setText(">")
        icon.setStyleSheet(f"font-weight: 700; color: {accent};")
        text.setText("")

        frame.setStyleSheet("""
            QFrame#statusFrame {
                background-color: transparent;
            }
            QLabel {
                color: #ffffff;
                font-family: "Segoe UI";
                font-size: 14px;
                font-weight: 700;
            }
        """)

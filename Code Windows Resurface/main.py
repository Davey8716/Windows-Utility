"""Application entry point for Windows Resurface."""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from resurface.core.instance_runtime import ensure_single_instance
from resurface.ui.application_window import UtilityControlApp


def main() -> int:
    mutex = ensure_single_instance(Path(__file__))
    app = QApplication(sys.argv)
    window = UtilityControlApp()
    window._instance_mutex = mutex
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

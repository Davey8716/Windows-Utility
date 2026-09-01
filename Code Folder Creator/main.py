import ctypes
import sys
from ctypes import wintypes

from PySide6.QtWidgets import QApplication

from folder_creator.ui.main_window import MainWindow


ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "FolderCreator_SingleInstance"
_single_instance_mutex = None
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def already_running():
    global _single_instance_mutex

    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    create_mutex.restype = wintypes.HANDLE
    ctypes.set_last_error(0)
    handle = create_mutex(None, False, MUTEX_NAME)
    _single_instance_mutex = handle
    if handle is None or handle == 0:
        return False
    return ctypes.get_last_error() == ERROR_ALREADY_EXISTS


def main():
    if already_running():
        return
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

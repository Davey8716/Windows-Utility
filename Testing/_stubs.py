import sys
import types


class _DummySignal:
    def connect(self, *_args, **_kwargs):
        return None


class _DummyTrayActivationReason:
    Trigger = 1


class _DummyWindowType:
    WindowStaysOnTopHint = 1
    WindowMaximizeButtonHint = 2
    FramelessWindowHint = 3
    CustomizeWindowHint = 4
    WindowTitleHint = 5
    WindowSystemMenuHint = 6
    WindowCloseButtonHint = 7
    WindowMinimizeButtonHint = 8
    WindowContextHelpButtonHint = 9
    Tool = 10


class _DummyScrollBarPolicy:
    ScrollBarAlwaysOff = 0
    ScrollBarAsNeeded = 1
    ScrollBarAlwaysOn = 2


class _DummyAlignmentFlag:
    AlignTop = 0
    AlignCenter = 1
    AlignHCenter = 2


class _DummyCursorShape:
    PointingHandCursor = 0


class _DummySizePolicy:
    class Policy:
        Expanding = 0
        Fixed = 1


class _DummyArrowType:
    RightArrow = 0
    LeftArrow = 1
    DownArrow = 2
    UpArrow = 3


class _DummyQt:
    WindowType = _DummyWindowType
    ScrollBarPolicy = _DummyScrollBarPolicy
    AlignmentFlag = _DummyAlignmentFlag
    CursorShape = _DummyCursorShape
    ArrowType = _DummyArrowType
    class WindowModality:
        NonModal = 0
    class WidgetAttribute:
        WA_DeleteOnClose = 0
    class ItemDataRole:
        BackgroundRole = 0
        ForegroundRole = 1
    class TextElideMode:
        ElideNone = 0
    AlignCenter = 1


class _DummyPoint:
    def __init__(self, *_args, **_kwargs):
        pass


class _DummySize:
    def __init__(self, *_args, **_kwargs):
        pass


class _DummyModelIndex:
    def isValid(self):
        return False


class _DummyEvent:
    class Type:
        Enter = 10
        ToolTip = 11
        Leave = 12
        MouseButtonPress = 13


class _BaseWidget:
    def __init__(self, *args, **kwargs):
        self.activated = _DummySignal()
        self.clicked = _DummySignal()
        self.toggled = _DummySignal()
        self.triggered = _DummySignal()

    def __getattr__(self, _name):
        def _method(*_args, **_kwargs):
            return None

        return _method


class _DummyApplication(_BaseWidget):
    @staticmethod
    def instance():
        return None


class _DummyIcon:
    def __init__(self, *_args, **_kwargs):
        pass

    @staticmethod
    def fromTheme(_name):
        return _DummyIcon()

    def isNull(self):
        return False


class _DummyColor:
    class NameFormat:
        HexRgb = 0

    def __init__(self, red=0, green=0, blue=0):
        self._red = red
        self._green = green
        self._blue = blue

    def red(self):
        return self._red

    def green(self):
        return self._green

    def blue(self):
        return self._blue

    def name(self, _fmt=None):
        return f"#{self._red:02x}{self._green:02x}{self._blue:02x}"


class _DummySystemTrayIcon(_BaseWidget):
    ActivationReason = _DummyTrayActivationReason


class _DummyFont:
    def __init__(self, *_args, **_kwargs):
        pass


class _DummyFontMetrics:
    def __init__(self, *_args, **_kwargs):
        pass


class _DummyMessageBox:
    Yes = 1
    Cancel = 2

    @staticmethod
    def information(*_args, **_kwargs):
        return None

    @staticmethod
    def warning(*_args, **_kwargs):
        return None

    @staticmethod
    def question(*_args, **_kwargs):
        return _DummyMessageBox.Yes


class _DummyFileDialog:
    @staticmethod
    def getExistingDirectory(*_args, **_kwargs):
        return ""

    @staticmethod
    def getSaveFileName(*_args, **_kwargs):
        return ("", "")


class _DummyQTimer:
    @staticmethod
    def singleShot(*_args, **_kwargs):
        return None


class _DummyQProcess(_BaseWidget):
    class ProcessChannelMode:
        SeparateChannels = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.readyReadStandardOutput = _DummySignal()
        self.readyReadStandardError = _DummySignal()
        self.finished = _DummySignal()

    def readAllStandardOutput(self):
        return b""

    def readAllStandardError(self):
        return b""


class _DummyToolTip:
    @staticmethod
    def showText(*_args, **_kwargs):
        return None

    @staticmethod
    def hideText():
        return None


class _DummyScreenMover:
    title_bar_dock_enabled = True
    enable_mmb = True

    def configure(self, **_kwargs):
        return None

    def start(self):
        return None

    def stop(self):
        return None


def install_dependency_stubs():
    if "PySide6" not in sys.modules:
        pyside6 = types.ModuleType("PySide6")
        qtcore = types.ModuleType("PySide6.QtCore")
        qtwidgets = types.ModuleType("PySide6.QtWidgets")
        qtgui = types.ModuleType("PySide6.QtGui")
        qttest = types.ModuleType("PySide6.QtTest")

        qtcore.Qt = _DummyQt
        qtcore.QTimer = _DummyQTimer
        qtcore.QProcess = _DummyQProcess
        qtcore.QObject = _BaseWidget
        qtcore.QPoint = _DummyPoint
        qtcore.QModelIndex = _DummyModelIndex
        qtcore.QSize = _DummySize
        qtcore.QRectF = _DummyPoint
        qtcore.QEvent = _DummyEvent

        qtwidgets.QWidget = _BaseWidget
        qtwidgets.QGridLayout = _BaseWidget
        qtwidgets.QLabel = _BaseWidget
        qtwidgets.QPushButton = _BaseWidget
        qtwidgets.QToolButton = _BaseWidget
        qtwidgets.QComboBox = _BaseWidget
        qtwidgets.QVBoxLayout = _BaseWidget
        qtwidgets.QScrollArea = _BaseWidget
        qtwidgets.QHBoxLayout = _BaseWidget
        qtwidgets.QLineEdit = _BaseWidget
        qtwidgets.QTextEdit = _BaseWidget
        qtwidgets.QListWidgetItem = _BaseWidget
        qtwidgets.QListWidget = _BaseWidget
        qtwidgets.QApplication = _DummyApplication
        qtwidgets.QDialogButtonBox = _BaseWidget
        qtwidgets.QFrame = _BaseWidget
        qtwidgets.QSizePolicy = _DummySizePolicy
        qtwidgets.QFileDialog = _DummyFileDialog
        qtwidgets.QMessageBox = _DummyMessageBox
        qtwidgets.QSystemTrayIcon = _DummySystemTrayIcon
        qtwidgets.QMenu = _BaseWidget
        qtwidgets.QStyle = _BaseWidget
        qtwidgets.QStyledItemDelegate = _BaseWidget
        qtwidgets.QToolTip = _DummyToolTip

        qtgui.QIcon = _DummyIcon
        qtgui.QAction = _BaseWidget
        qtgui.QColor = _DummyColor
        qtgui.QFont = _DummyFont
        qtgui.QFontMetrics = _DummyFontMetrics
        qtgui.QPainter = _BaseWidget
        qtgui.QPainterPath = _BaseWidget
        qtgui.QPen = _BaseWidget
        qtgui.QPixmap = _BaseWidget
        qtgui.QRegion = _BaseWidget
        qttest.QTest = _BaseWidget

        pyside6.QtCore = qtcore
        pyside6.QtWidgets = qtwidgets
        pyside6.QtGui = qtgui
        pyside6.QtTest = qttest

        sys.modules["PySide6"] = pyside6
        sys.modules["PySide6.QtCore"] = qtcore
        sys.modules["PySide6.QtWidgets"] = qtwidgets
        sys.modules["PySide6.QtGui"] = qtgui
        sys.modules["PySide6.QtTest"] = qttest

    if "win32gui" not in sys.modules:
        win32gui = types.ModuleType("win32gui")
        win32gui.GetWindowText = lambda _hwnd: ""
        win32gui.GetClassName = lambda _hwnd: ""
        win32gui.IsWindow = lambda _hwnd: True
        win32gui.IsWindowVisible = lambda _hwnd: True
        win32gui.GetParent = lambda _hwnd: 0
        win32gui.GetWindowPlacement = lambda _hwnd: (None, 0)
        win32gui.ShowWindow = lambda *_args, **_kwargs: None
        win32gui.SetForegroundWindow = lambda *_args, **_kwargs: None
        win32gui.EnumWindows = lambda callback, extra: None
        win32gui.PostMessage = lambda *_args, **_kwargs: None
        sys.modules["win32gui"] = win32gui

    if "win32con" not in sys.modules:
        win32con = types.ModuleType("win32con")
        win32con.SW_MINIMIZE = 6
        win32con.SW_RESTORE = 9
        win32con.SW_SHOW = 5
        win32con.SW_SHOWMINIMIZED = 2
        win32con.WM_CLOSE = 16
        sys.modules["win32con"] = win32con

    if "PIL" not in sys.modules:
        pil = types.ModuleType("PIL")
        image_grab = types.ModuleType("PIL.ImageGrab")
        image_grab.grab = lambda: None
        pil.ImageGrab = image_grab
        sys.modules["PIL"] = pil
        sys.modules["PIL.ImageGrab"] = image_grab

    if "screen_mover" not in sys.modules:
        screen_mover = types.ModuleType("screen_mover")
        screen_mover.SCREEN_MOVER = _DummyScreenMover()
        sys.modules["screen_mover"] = screen_mover

    if "desktop_icon_layout" not in sys.modules:
        desktop_icon_layout = types.ModuleType("desktop_icon_layout")
        desktop_icon_layout.save_desktop_icon_layout = lambda _path: 0
        desktop_icon_layout.restore_desktop_icon_layout = lambda _path: 0
        desktop_icon_layout.desktop_icons_visible = lambda: True
        desktop_icon_layout.set_desktop_icons_visible = lambda _visible: None
        sys.modules["desktop_icon_layout"] = desktop_icon_layout

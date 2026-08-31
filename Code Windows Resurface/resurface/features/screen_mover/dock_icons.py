"""Dock icon discovery, contrast selection, and GDI+ rendering."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

import win32gui

from resurface.features.screen_mover.window_actions import DOCK_ACTIONS


DOCK_WIDTH = 180
DOCK_HEIGHT = 30
DOCK_ICON_FOLDER = "Icon Pngs"
DOCK_ICON_THEME_BLACK = "Black"
DOCK_ICON_THEME_WHITE = "White"
DOCK_ICON_DEFAULT_THEME = DOCK_ICON_THEME_BLACK
DOCK_DARK_BAR_ICON_THEME = DOCK_ICON_THEME_WHITE
DOCK_LIGHT_BAR_ICON_THEME = DOCK_ICON_THEME_BLACK
DOCK_THEME_LUMINANCE_THRESHOLD = 150
DOCK_THEME_HYSTERESIS = 5
DOCK_DARK_BAR_LUMINANCE_MAX = (
    DOCK_THEME_LUMINANCE_THRESHOLD - DOCK_THEME_HYSTERESIS
)
DOCK_LIGHT_BAR_LUMINANCE_MIN = (
    DOCK_THEME_LUMINANCE_THRESHOLD + DOCK_THEME_HYSTERESIS
)
DOCK_ACTION_ICON_FILES = {
    "FAR_LEFT": "Far Left.png",
    "LEFT": "Left.png",
    "RIGHT": "Right.png",
    "FAR_RIGHT": "Far Right.png",
    "MINIMIZE": "Minimize.png",
    "MAXIMIZE": "Maximize.png",
}


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ("GdiplusVersion", ctypes.c_uint32),
        ("DebugEventCallback", ctypes.c_void_p),
        ("SuppressBackgroundThread", ctypes.c_int),
        ("SuppressExternalCodecs", ctypes.c_int),
    ]


class DockIconRenderer:
    def __init__(self):
        self._gdiplus = None
        self._token = ctypes.c_void_p()
        self._images: dict[tuple[str, str], ctypes.c_void_p | None] = {}
        self._startup_attempted = False

    def draw_action(self, hdc, action: str, theme: str) -> bool:
        image = self._image_for_action(action, theme)
        if not image:
            return False

        graphics = ctypes.c_void_p()
        if self._gdiplus.GdipCreateFromHDC(int(hdc), ctypes.byref(graphics)) != 0:
            return False

        try:
            status = self._gdiplus.GdipDrawImageRectI(
                graphics,
                image,
                0,
                0,
                DOCK_WIDTH,
                DOCK_HEIGHT,
            )
            return status == 0
        finally:
            self._gdiplus.GdipDeleteGraphics(graphics)

    def dispose(self) -> None:
        if self._gdiplus is not None:
            for image in self._images.values():
                if image:
                    try:
                        self._gdiplus.GdipDisposeImage(image)
                    except Exception:
                        pass

            if self._token:
                try:
                    self._gdiplus.GdiplusShutdown(self._token)
                except Exception:
                    pass

        self._gdiplus = None
        self._token = ctypes.c_void_p()
        self._images.clear()
        self._startup_attempted = False

    def preload_themes(self, themes) -> None:
        for theme in themes:
            for action, _label in DOCK_ACTIONS:
                self._image_for_action(action, theme)

    def _image_for_action(self, action: str, theme: str):
        cache_key = (theme, action)
        if cache_key in self._images:
            return self._images[cache_key]

        image = self._load_image(action, theme)
        self._images[cache_key] = image
        return image

    def _load_image(self, action: str, theme: str):
        if not self._ensure_gdiplus():
            return None

        filename = DOCK_ACTION_ICON_FILES.get(action)
        if not filename:
            return None

        for icon_dir in _dock_icon_directories(theme):
            icon_path = icon_dir / filename
            if not icon_path.is_file():
                continue

            image = ctypes.c_void_p()
            status = self._gdiplus.GdipLoadImageFromFile(
                str(icon_path),
                ctypes.byref(image),
            )
            if status == 0 and image:
                return image

        return None

    def _ensure_gdiplus(self) -> bool:
        if self._gdiplus is not None:
            return True
        if self._startup_attempted:
            return False

        self._startup_attempted = True
        try:
            self._gdiplus = ctypes.windll.gdiplus
            startup_input = GdiplusStartupInput(1, None, 0, 0)
            status = self._gdiplus.GdiplusStartup(
                ctypes.byref(self._token),
                ctypes.byref(startup_input),
                None,
            )
            if status != 0:
                self._gdiplus = None
                return False
        except Exception:
            self._gdiplus = None
            return False

        return True


def _dock_icon_directories(theme: str | None = None) -> list[Path]:
    directories: list[Path] = []
    theme = str(theme or "").strip()

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        directories.extend(_dock_icon_directory_candidates(Path(bundle_root), theme))

    directories.extend(
        _dock_icon_directory_candidates(Path(sys.executable).resolve().parent, theme)
    )
    directories.extend(
        _dock_icon_directory_candidates(Path(__file__).resolve().parents[4], theme)
    )

    return directories


def _dock_icon_directory_candidates(root: Path, theme: str) -> list[Path]:
    base_dir = root / DOCK_ICON_FOLDER
    if not theme:
        return [base_dir]
    return [base_dir / theme, base_dir]


def _dock_icon_theme_for_luminance(
    luminance: float | None,
    current_theme: str | None = None,
) -> str:
    if luminance is None:
        return DOCK_ICON_DEFAULT_THEME
    if luminance <= DOCK_DARK_BAR_LUMINANCE_MAX:
        return DOCK_DARK_BAR_ICON_THEME
    if luminance >= DOCK_LIGHT_BAR_LUMINANCE_MIN:
        return DOCK_LIGHT_BAR_ICON_THEME
    if current_theme in {DOCK_ICON_THEME_BLACK, DOCK_ICON_THEME_WHITE}:
        return current_theme
    return DOCK_DARK_BAR_ICON_THEME


def _dock_icon_theme_for_rect(rect, current_theme: str | None = None) -> str:
    luminance = _average_screen_luminance(rect)
    return _dock_icon_theme_for_luminance(luminance, current_theme)


def _average_screen_luminance(rect) -> float | None:
    left, top, right, bottom = rect
    width = max(0, int(right - left))
    height = max(0, int(bottom - top))
    if width == 0 or height == 0:
        return None

    sample_x_count = min(9, width)
    sample_y_count = min(3, height)
    screen_hdc = None
    total = 0.0
    count = 0

    try:
        screen_hdc = win32gui.GetDC(0)
        for x_index in range(sample_x_count):
            x = int(left + ((x_index + 0.5) * width / sample_x_count))
            for y_index in range(sample_y_count):
                y = int(top + ((y_index + 0.5) * height / sample_y_count))
                color = win32gui.GetPixel(screen_hdc, x, y)
                if color == -1:
                    continue
                red = color & 0xFF
                green = (color >> 8) & 0xFF
                blue = (color >> 16) & 0xFF
                total += (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
                count += 1
    except Exception:
        return None
    finally:
        if screen_hdc is not None:
            try:
                win32gui.ReleaseDC(0, screen_hdc)
            except Exception:
                pass

    if count == 0:
        return None
    return total / count

from pathlib import Path
import ctypes
from ctypes import wintypes


def get_desktop_path() -> Path:
    csidl_desktop = 0x0000
    shgfp_type_current = 0

    buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)

    ctypes.windll.shell32.SHGetFolderPathW(
        None,
        csidl_desktop,
        None,
        shgfp_type_current,
        buf,
    )

    return Path(buf.value)

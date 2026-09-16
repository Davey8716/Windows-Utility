"""Make the bundled Windows Resurface package available to Folder Creator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


RESURFACE_SOURCE_ROOT = (
    Path(__file__).resolve().parents[2] / "Code Windows Resurface"
)


def ensure_resurface_importable() -> None:
    """Expose the sibling source package when it has not already been bundled."""

    if importlib.util.find_spec("resurface") is not None:
        return

    source_root = str(RESURFACE_SOURCE_ROOT)
    if source_root not in sys.path:
        sys.path.insert(0, source_root)

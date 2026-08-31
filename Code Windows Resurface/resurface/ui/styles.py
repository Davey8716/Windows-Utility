"""Stable public facade for the split UI styling modules."""

from resurface.ui import control_styles as _controls
from resurface.ui import shell_styles as _shell
from resurface.ui import style_helpers as _helpers
from resurface.ui import style_tokens as _tokens

_STYLE_MODULES = (_tokens, _helpers, _shell, _controls)


def __getattr__(name: str):
    for module in _STYLE_MODULES:
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    exported = set(globals())
    for module in _STYLE_MODULES:
        exported.update(name for name in vars(module) if not name.startswith("__"))
    return sorted(exported)


__all__ = [name for name in __dir__() if not name.startswith("_")]

"""VAPA Application Package."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .main import VAPAApplication, main

def __getattr__(name: str):
    if name in ("VAPAApplication", "main"):
        from . import main as _main
        return getattr(_main, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["VAPAApplication", "main"]

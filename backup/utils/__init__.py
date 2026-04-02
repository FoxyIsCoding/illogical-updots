#!/usr/bin/env python3
"""
Utilities package for illogical-updots.

This package centralizes subprocess and installer helpers.
It re-exports commonly used helpers from utils.process for convenience:

    from utils import spawn_setup_install, launch_install_external
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "build_color_env",
    "stream_process_lines",
    "spawn_setup_install",
    "launch_install_external",
]

if TYPE_CHECKING:
    # Type-checking only imports (no runtime cost)
    from .process import (
        build_color_env as _build_color_env,
    )
    from .process import (
        launch_install_external as _launch_install_external,
    )
    from .process import (
        spawn_setup_install as _spawn_setup_install,
    )
    from .process import (
        stream_process_lines as _stream_process_lines,
    )


def __getattr__(name: str):
    """
    Lazily expose helpers from utils.process to avoid importing
    the module unless a symbol is actually used.
    """
    if name in __all__:
        from . import process as _process  # Local import to keep it lazy

        mapping = {
            "build_color_env": _process.build_color_env,
            "stream_process_lines": _process.stream_process_lines,
            "spawn_setup_install": _process.spawn_setup_install,
            "launch_install_external": _process.launch_install_external,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

#!/usr/bin/env python3
"""
UI package for illogical-updots.

This package contains user interface components built with GTK.

Exports (lazily imported):
- ConsolePanel: A reusable console/logging panel widget.
- MainWindow:   The primary application window.

Lazy imports keep GTK-heavy modules from loading unless needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "ConsolePanel",
    "MainWindow",
]

if TYPE_CHECKING:
    # For type checkers only; avoids importing GTK at runtime unless needed.
    from .console_panel import ConsolePanel as _ConsolePanel
    from .main_window import MainWindow as _MainWindow


def __getattr__(name: str):
    """
    Lazily import UI components on first access to avoid unnecessary GTK imports.
    """
    if name == "ConsolePanel":
        from .console_panel import ConsolePanel as _ConsolePanel  # type: ignore

        return _ConsolePanel
    if name == "MainWindow":
        from .main_window import MainWindow as _MainWindow  # type: ignore

        return _MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

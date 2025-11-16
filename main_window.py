#!/usr/bin/env python3
"""
Thin compatibility wrapper for the refactored MainWindow.

This module re-exports the public API expected by existing imports:
    - MainWindow
    - APP_ID
    - APP_TITLE
    - SETTINGS
    - REPO_PATH
    - _save_settings

The actual implementation now lives in ui.main_window.
"""

from ui.main_window import (  # noqa: F401
    APP_ID,
    APP_TITLE,
    REPO_PATH,
    SETTINGS,
    MainWindow,
    _save_settings,
)

__all__ = [
    "MainWindow",
    "APP_ID",
    "APP_TITLE",
    "SETTINGS",
    "REPO_PATH",
    "_save_settings",
]

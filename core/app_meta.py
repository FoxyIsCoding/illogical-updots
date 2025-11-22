#!/usr/bin/env python3
"""
Core application metadata and settings management.

This module centralizes:
- Static app metadata (APP_ID, APP_TITLE)
- Settings directory/file paths
- Settings load/save (with defaults and atomic writes)
- Initial repository path detection and persistence
"""

from __future__ import annotations

import json
import os
from typing import Dict, Mapping, MutableMapping, Optional

# -------------------------------------------------------------------
# App metadata
# -------------------------------------------------------------------
APP_ID: str = "com.foxy.illogical-updots"
APP_TITLE: str = "illogical-updots"

# -------------------------------------------------------------------
# Settings storage
# -------------------------------------------------------------------
SETTINGS_DIR: str = os.path.join(os.path.expanduser("~"), ".config", "illogical-updots")
SETTINGS_FILE: str = os.path.join(SETTINGS_DIR, "settings.json")

# Defaults for persisted settings. Unknown keys in the file are ignored on load.
DEFAULT_SETTINGS: Dict[str, object] = {
    "repo_path": "",
    "auto_refresh_seconds": 60,
    "detached_console": False,  # Use external console window instead of embedded
    "installer_mode": "auto",  # auto / full / files-only
    "use_pty": True,  # Preserve color & interactive prompts
    "force_color_env": True,  # Force color env vars for spawned processes
    "send_notifications": True,  # Desktop notifications on completion
    "log_max_lines": 5000,  # Trim log buffer (0 = unlimited)
    "changes_lazy_load": True,  # Lazy load commit list
    "post_script_path": "",  # Optional script executed after install
    "show_details_button": True,  # Show small details link under banner
    "keep_fish_config": False,  # Backup & restore entire ~/.config/fish (config.fish, functions/, subfolders) before and after install
}


def get_settings_dir() -> str:
    """
    Returns the directory path where settings are stored.
    """
    return SETTINGS_DIR


def get_settings_path() -> str:
    """
    Returns the file path where settings are stored.
    """
    return SETTINGS_FILE


def load_settings() -> Dict[str, object]:
    """
    Load persisted settings from disk, merging with defaults.

    Behavior:
    - If the file does not exist, returns a copy of DEFAULT_SETTINGS.
    - Unknown keys from disk are ignored.
    - Any error while reading/parsing falls back to defaults.

    Returns:
        A new dict of merged settings.
    """
    data: Dict[str, object] = dict(DEFAULT_SETTINGS)
    try:
        if os.path.isfile(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, Mapping):
                data.update({k: v for k, v in loaded.items() if k in DEFAULT_SETTINGS})
    except Exception:
        # Corrupt or unreadable settings: return defaults
        pass
    return data


def save_settings(data: Mapping[str, object]) -> None:
    """
    Persist settings atomically (write to temp then replace).

    Args:
        data: Mapping of settings to persist. Only keys present in DEFAULT_SETTINGS
              are written; others are ignored.
    """
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        # Only persist known keys to keep the file tidy
        serializable = {k: data.get(k) for k in DEFAULT_SETTINGS.keys()}
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        os.replace(tmp, SETTINGS_FILE)
    except Exception:
        # Best-effort: settings persistence is non-critical
        pass


# Backward-compatible alias for refactors expecting an underscored function name
_save_settings = save_settings


def detect_initial_repo_path(settings: MutableMapping[str, object]) -> str:
    """
    Determine the initial repository path.

    Precedence:
    1) Use 'repo_path' from provided settings if it exists and is a directory.
    2) Fallback to '~/.cache/dots-hyprland' if present.
    3) Otherwise, return empty string.

    Side effects:
    - If a fallback is used, update the provided settings and persist immediately.

    Args:
        settings: Mutable mapping of current settings.

    Returns:
        The chosen repository path (possibly empty string if none found).
    """
    p = str(settings.get("repo_path") or "").strip()
    if p and os.path.isdir(p):
        return p

    fallback = os.path.expanduser("~/.cache/dots-hyprland")
    if os.path.isdir(fallback):
        settings["repo_path"] = fallback
        save_settings(settings)
        return fallback

    return ""


def get_auto_refresh_seconds(settings: Mapping[str, object]) -> int:
    """
    Read the auto refresh cadence from settings with sane fallback.

    Args:
        settings: Settings mapping.

    Returns:
        Positive integer seconds; defaults to 60 on invalid values.
    """
    try:
        v = int(settings.get("auto_refresh_seconds", 60))
        return v if v > 0 else 60
    except Exception:
        return 60


# -------------------------------------------------------------------
# Module-level singletons (used by the UI/application)
# -------------------------------------------------------------------
SETTINGS: Dict[str, object] = load_settings()
REPO_PATH: str = detect_initial_repo_path(SETTINGS)
AUTO_REFRESH_SECONDS: int = get_auto_refresh_seconds(SETTINGS)

__all__ = [
    "APP_ID",
    "APP_TITLE",
    "SETTINGS_DIR",
    "SETTINGS_FILE",
    "DEFAULT_SETTINGS",
    "get_settings_dir",
    "get_settings_path",
    "load_settings",
    "save_settings",
    "_save_settings",
    "detect_initial_repo_path",
    "get_auto_refresh_seconds",
    "SETTINGS",
    "REPO_PATH",
    "AUTO_REFRESH_SECONDS",
]

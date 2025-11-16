"""
Core package for illogical-updots.

This package centralizes non-UI logic such as:
- Application metadata and settings management (core.app_meta)
- Git helpers and repository status modeling (core.git_utils)

It also re-exports commonly used symbols for convenience, so callers can do:
    from core import SETTINGS, REPO_PATH, RepoStatus, check_repo_status
"""

from .app_meta import (
    APP_ID,
    APP_TITLE,
    AUTO_REFRESH_SECONDS,
    DEFAULT_SETTINGS,
    REPO_PATH,
    SETTINGS,
    SETTINGS_DIR,
    SETTINGS_FILE,
    _save_settings,
    detect_initial_repo_path,
    get_auto_refresh_seconds,
    load_settings,
    save_settings,
)
from .git_utils import (
    RepoStatus,
    check_repo_status,
    get_branch,
    get_dirty_count,
    get_upstream,
    run_git,
)

__all__ = [
    # app_meta
    "APP_ID",
    "APP_TITLE",
    "SETTINGS_DIR",
    "SETTINGS_FILE",
    "DEFAULT_SETTINGS",
    "load_settings",
    "save_settings",
    "_save_settings",
    "detect_initial_repo_path",
    "get_auto_refresh_seconds",
    "SETTINGS",
    "REPO_PATH",
    "AUTO_REFRESH_SECONDS",
    # git_utils
    "RepoStatus",
    "run_git",
    "get_branch",
    "get_upstream",
    "get_dirty_count",
    "check_repo_status",
]

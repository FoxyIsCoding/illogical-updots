#!/usr/bin/env python3
"""
Git utilities and repository status model for illogical-updots.

This module provides:
- A RepoStatus dataclass capturing a snapshot of a repository state
- Lightweight git helper functions:
  - run_git
  - get_branch
  - get_upstream
  - get_dirty_count
  - check_repo_status
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class RepoStatus:
    """
    Snapshot of repository state used by UI/logic.

    Attributes:
        ok (bool): Whether the repository is valid and accessible.
        repo_path (str): Path to the repository.
        branch (str|None): Current HEAD branch name.
        upstream (str|None): Upstream tracking reference (e.g. origin/main).
        behind (int): Number of commits local is behind upstream.
        ahead (int): Number of commits local is ahead of upstream.
        dirty (int): Count of modified/untracked files (`git status --porcelain`).
        fetch_error (str|None): Any error message from `git fetch`.
        error (str|None): Fatal error (invalid path / not a repo).
    """

    ok: bool
    repo_path: str
    branch: Optional[str] = None
    upstream: Optional[str] = None
    behind: int = 0
    ahead: int = 0
    dirty: int = 0
    fetch_error: Optional[str] = None
    error: Optional[str] = None

    @property
    def has_updates(self) -> bool:
        """
        Returns:
            bool: True if the repository is valid and there are upstream commits
                  not yet pulled locally (behind > 0).
        """
        return self.ok and self.behind > 0


def run_git(args: List[str], cwd: str, timeout: int = 15) -> Tuple[int, str, str]:
    """
    Run a git command and capture stdout/stderr.

    Args:
        args: Arguments after 'git'.
        cwd: Working directory (repository root).
        timeout: Seconds before process is killed.

    Returns:
        (returncode, stdout, stderr)

    Resilience:
        - On any exception returns (1, "", str(exc)).
    """
    try:
        cp = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        return cp.returncode, cp.stdout, cp.stderr
    except Exception as exc:  # pragma: no cover - defensive
        return 1, "", str(exc)


def get_branch(cwd: str) -> Optional[str]:
    """
    Get current branch name.

    Returns:
        str|None: Branch name or None if detached or error.
    """
    rc, out, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return out.strip() if rc == 0 else None


def get_upstream(cwd: str, branch: Optional[str]) -> Optional[str]:
    """
    Determine upstream remote reference for current branch.

    Strategy:
        - Try rev-parse @{u} which resolves tracking reference.
        - If that fails and branch is known, assume 'origin/<branch>'.

    Returns:
        str|None: Upstream or None if not found.
    """
    rc, out, _ = run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd
    )
    if rc == 0:
        return out.strip()
    if branch:
        return f"origin/{branch}"
    return None


def get_dirty_count(cwd: str) -> int:
    """
    Count modified/untracked files.

    Returns:
        int: Number of non-empty lines in `git status --porcelain`.
             Zero if error.
    """
    rc, out, _ = run_git(["status", "--porcelain"], cwd)
    if rc != 0:
        return 0
    return len([ln for ln in out.splitlines() if ln.strip()])


def check_repo_status(repo_path: str) -> RepoStatus:
    """
    Build a RepoStatus describing current repository update condition.

    Workflow:
        1. Validate path & presence of .git.
        2. Run 'git fetch --all --prune' (non-fatal if fails).
        3. Determine branch & upstream.
        4. Compute behind/ahead counts via rev-list comparisons.
        5. Count dirty files.

    Returns:
        RepoStatus: Complete snapshot (ok=False if invalid).
    """
    if not os.path.isdir(repo_path):
        return RepoStatus(
            ok=False, repo_path=repo_path, error="Repository path not found"
        )
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        return RepoStatus(ok=False, repo_path=repo_path, error="Not a git repository")

    fetch_error = None
    rc, _out, err = run_git(["fetch", "--all", "--prune"], repo_path)
    if rc != 0:
        fetch_error = (err or "fetch failed").strip()

    branch = get_branch(repo_path)
    upstream = get_upstream(repo_path, branch)

    behind = 0
    ahead = 0
    if upstream:
        # Count commits present in upstream but not local
        rc_b, out_b, _ = run_git(
            ["rev-list", "--count", f"HEAD..{upstream}"], repo_path
        )
        if rc_b == 0:
            try:
                behind = int((out_b or "").strip() or "0")
            except ValueError:
                behind = 0
        # Count commits present locally but not upstream
        rc_a, out_a, _ = run_git(
            ["rev-list", "--count", f"{upstream}..HEAD"], repo_path
        )
        if rc_a == 0:
            try:
                ahead = int((out_a or "").strip() or "0")
            except ValueError:
                ahead = 0

    dirty = get_dirty_count(repo_path)

    return RepoStatus(
        ok=True,
        repo_path=repo_path,
        branch=branch,
        upstream=upstream,
        behind=behind,
        ahead=ahead,
        dirty=dirty,
        fetch_error=fetch_error,
    )


__all__ = [
    "RepoStatus",
    "run_git",
    "get_branch",
    "get_upstream",
    "get_dirty_count",
    "check_repo_status",
]

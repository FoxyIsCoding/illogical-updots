#!/usr/bin/env python3
"""
Process spawning helpers for illogical-updots.

This module centralizes:
- Environment utilities for color-friendly subprocesses
- Generic line-streaming command runner
- Setup installer spawning with PTY support and fallbacks
- External terminal launcher for full installer runs
"""

from __future__ import annotations

import errno
import io
import os
import shlex
import subprocess
import threading
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
)


# -------------------------------------------------------------------
# Environment helpers
# -------------------------------------------------------------------
def build_color_env(
    base: Optional[Mapping[str, str]] = None, force_color: bool = True
) -> Dict[str, str]:
    """
    Build an environment suitable for colorized subprocess output.

    Args:
        base: Optional base environment to copy; defaults to os.environ.
        force_color: When True, injects color-related variables and removes NO_COLOR.

    Returns:
        A new environment dictionary safe to pass to subprocess calls.
    """
    env: Dict[str, str] = dict(base or os.environ)
    if force_color:
        env.update(
            {
                "FORCE_COLOR": "1",
                "CLICOLOR": "1",
                "CLICOLOR_FORCE": "1",
                "TERM": env.get("TERM", "xterm-256color") or "xterm-256color",
            }
        )
        # Prefer colors unless explicitly disabled by caller
        env.pop("NO_COLOR", None)
    return env


# -------------------------------------------------------------------
# Generic streaming runner
# -------------------------------------------------------------------
def stream_process_lines(
    cmd: Sequence[str],
    cwd: Optional[str],
    on_line: Callable[[str], None],
    env: Optional[Mapping[str, str]] = None,
    text: bool = True,
) -> int:
    """
    Run a command and stream its combined stdout/stderr line-by-line to a callback.

    Args:
        cmd: Command vector (argv).
        cwd: Working directory or None.
        on_line: Callback invoked for each output line (newline-preserving).
        env: Optional environment mapping; if None, inherits current process env.
        text: When True, opens pipes in text mode with utf-8 replacement.

    Returns:
        Exit code of the process. On spawn error, returns 1 and emits error text.
    """
    enc = "utf-8"
    try:
        p = subprocess.Popen(
            list(cmd),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=text,
            encoding=enc if text else None,
            errors="replace" if text else None,
            bufsize=1,
            env=dict(env) if env is not None else None,
        )
    except Exception as ex:
        on_line(f"[error] failed to spawn: {ex}\n")
        return 1

    assert p.stdout is not None
    try:
        for line in iter(p.stdout.readline, "" if text else b""):
            if not line:
                break
            on_line(line if text else line.decode(enc, "replace"))
    except Exception as ex:
        on_line(f"[stream error] {ex}\n")
    finally:
        try:
            p.stdout.close()  # type: ignore[union-attr]
        except Exception:
            pass

    rc = p.wait()
    on_line(f"[exit {rc}]\n")
    return rc


# -------------------------------------------------------------------
# Setup installer spawning (PTY-aware)
# -------------------------------------------------------------------
def spawn_setup_install(
    repo_path: str,
    logger: Callable[[str], None],
    extra_args: Optional[List[str]] = None,
    capture_stdout: bool = True,
    auto_input_seq: Optional[List[str]] = None,
    use_pty: bool = True,
):
    """
    Spawn the setup installer with progressive fallbacks and optional PTY.

    Strategy:
        1. Try './setup' directly.
        2. Fallback to 'fish ./setup'.
        3. Fallback to 'sh ./setup'.

    PTY usage:
        - When enabled, opens a pseudo terminal to preserve color + interactive prompts.
        - Wraps PTY reads in a custom PTYStdout class delivering line-based reads.

    Auto input:
        - If auto_input_seq provided, sends specified items plus final 'yesforall'.
        - Otherwise always sends 'yesforall'.

    Args:
        repo_path: Path to repo containing setup script.
        logger: Callable accepting message lines.
        extra_args: Additional arguments after './setup'.
        capture_stdout: Whether to capture/stream stdout/stderr (when not using PTY).
        auto_input_seq: Optional sequence of string inputs to feed.
        use_pty: Attempt PTY; fallback to pipe on failure.

    Returns:
        subprocess.Popen | None: Process object with p.stdout producing lines.

    Notes:
        The returned process may carry a non-standard attribute:
            - _pty_master_fd (int): master end of the PTY for writing.
    """
    import pty  # Imported locally to avoid hard dependency if not used

    extra_args = extra_args or []
    base_cmds: List[List[str]] = [
        ["./setup"] + extra_args,
        ["fish", "./setup"] + extra_args,
        ["sh", "./setup"] + extra_args,
    ]

    def _env():
        return build_color_env()

    for cmd in base_cmds:
        try:
            master_fd, slave_fd = None, None
            _use_pty = use_pty
            if _use_pty:
                try:
                    master_fd, slave_fd = pty.openpty()
                except Exception as ex:
                    logger(f"[pty-warn] failed to open pty: {ex}; fallback no-pty\n")
                    master_fd = slave_fd = None
                    _use_pty = False

            if _use_pty and master_fd is not None and slave_fd is not None:
                # PTY mode: single FD for in/out/err to preserve TTY behavior
                p = subprocess.Popen(
                    cmd,
                    cwd=repo_path,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    env=_env(),
                    close_fds=True,
                )
                # Close slave in parent
                try:
                    os.close(slave_fd)
                except Exception:
                    pass

                master_file = os.fdopen(master_fd, "rb", buffering=0)
                text_stream = io.TextIOWrapper(
                    master_file, encoding="utf-8", errors="replace", newline="\n"
                )

                class PTYStdout:
                    """
                    Simple line-buffered reader for PTY streams.
                    Collects until newline; returns lines preserving newline.
                    """

                    def __init__(self, stream):
                        self._stream = stream
                        self._buffer = ""

                    def readline(self):
                        while True:
                            chunk = self._stream.read(1)
                            if not chunk:
                                if self._buffer:
                                    out = self._buffer
                                    self._buffer = ""
                                    return out
                                return ""
                            self._buffer += chunk
                            if "\n" in self._buffer:
                                line, rest = self._buffer.split("\n", 1)
                                self._buffer = rest
                                return line + "\n"

                # Monkey-patch: emulate .stdout for stream consumers
                p.stdout = PTYStdout(text_stream)  # type: ignore[attr-defined]
                p._pty_master_fd = master_fd  # type: ignore[attr-defined]
                logger(f"[spawn/pty] {' '.join(cmd)}\n")
            else:
                # Pipe mode
                p = subprocess.Popen(
                    cmd,
                    cwd=repo_path,
                    stdout=subprocess.PIPE if capture_stdout else None,
                    stderr=subprocess.STDOUT if capture_stdout else None,
                    stdin=subprocess.PIPE,
                    universal_newlines=True,
                    bufsize=1,
                    env=_env(),
                )
                logger(f"[spawn] {' '.join(cmd)}\n")

            # Auto-input feeder
            if auto_input_seq:
                # Feed specified items then yesforall
                def _feed():
                    import time as _t

                    master_fd_local = getattr(p, "_pty_master_fd", None)
                    pipe = p.stdin if master_fd_local is None else None
                    if master_fd_local is None and not pipe:
                        logger(
                            "[auto-input] stdin unavailable; aborting auto sequence\n"
                        )
                        return
                    _t.sleep(0.2)
                    for item in auto_input_seq:
                        try:
                            if master_fd_local is not None:
                                os.write(
                                    master_fd_local, item.encode("utf-8", "replace")
                                )
                            else:
                                if pipe is None or getattr(pipe, "closed", False):
                                    logger("[auto-input] stdin closed; stopping\n")
                                    break
                                os.write(pipe.fileno(), item.encode("utf-8", "replace"))
                            logger(f"[auto-input] {repr(item)}\n")
                        except Exception as _ex:
                            logger(f"[auto-input-error] {_ex}\n")
                            break
                        _t.sleep(0.25)
                    try:
                        yesforall = "yesforall\n"
                        if master_fd_local is not None:
                            os.write(
                                master_fd_local, yesforall.encode("utf-8", "replace")
                            )
                        elif pipe:
                            os.write(
                                pipe.fileno(), yesforall.encode("utf-8", "replace")
                            )
                        logger(f"[auto-input] {repr(yesforall)}\n")
                    except Exception as _ex:
                        logger(f"[auto-input-error] {_ex}\n")

                threading.Thread(target=_feed, daemon=True).start()
            else:
                # Always send baseline 'yesforall' to allow unattended flows
                def _feed_yesforall():
                    import time as _t

                    _t.sleep(0.3)
                    master_fd_local = getattr(p, "_pty_master_fd", None)
                    pipe = p.stdin if master_fd_local is None else None
                    try:
                        msg = "yesforall\n"
                        if master_fd_local is not None:
                            os.write(master_fd_local, msg.encode("utf-8", "replace"))
                        elif pipe:
                            os.write(pipe.fileno(), msg.encode("utf-8", "replace"))
                        logger(f"[auto-input] {repr(msg)}\n")
                    except Exception as _ex:
                        logger(f"[auto-input-error] {_ex}\n")

                threading.Thread(target=_feed_yesforall, daemon=True).start()

            return p
        except OSError as ex:
            if ex.errno == errno.ENOEXEC:
                logger(
                    f"[warn] Exec format error with {' '.join(cmd)}; trying fallback...\n"
                )
                continue
            logger(f"[error] {ex}\n")
            return None
        except Exception as ex:
            logger(f"[error] {ex}\n")
            return None

    logger("[error] All setup execution fallbacks failed.\n")
    return None


# -------------------------------------------------------------------
# External terminal launcher
# -------------------------------------------------------------------
def launch_install_external(
    repo_path: str, extra_args: Optional[Iterable[str]] = None
) -> None:
    """
    Launch full installer in an external terminal emulator.

    Tries known terminals in order; first success returns immediately.
    Falls back to running directly if none found.

    Args:
        repo_path: Path to repository containing setup script.
        extra_args: Optional extra args after 'install' (e.g., ["--flag"]).
    """
    args = ["install"] + list(extra_args or [])
    cmd = ["./setup"] + args

    terminals: List[tuple[str, List[str]]] = [
        ("kitty", ["kitty", "-e"]),
        ("alacritty", ["alacritty", "-e"]),
        ("gnome-terminal", ["gnome-terminal", "--"]),
        ("xterm", ["xterm", "-e"]),
        ("konsole", ["konsole", "-e"]),
        ("foot", ["foot", "sh", "-c"]),
    ]
    for name, base in terminals:
        if shutil_which(name):
            if base[-1] == "-c":
                # Already expecting a shell command string
                shell_cmd = f"cd {shlex.quote(repo_path)} && {shlex.quote(cmd[0])} {' '.join(map(shlex.quote, cmd[1:]))}"
                full = base + [shell_cmd]
            elif base and base[-1] in ("--", "-e"):
                # Will pass the command vector directly
                full = base + [
                    "sh",
                    "-c",
                    f"cd {shlex.quote(repo_path)} && {shlex.join(cmd)}",
                ]
            else:
                full = base + [
                    "sh",
                    "-c",
                    f"cd {shlex.quote(repo_path)} && {shlex.join(cmd)}",
                ]
            try:
                subprocess.Popen(full)
                return
            except Exception:
                continue

    # Fallback: run directly in background (no terminal)
    subprocess.Popen(cmd, cwd=repo_path)


def shutil_which(prog: str) -> Optional[str]:
    """
    Small shim for shutil.which to avoid importing the whole module at top-level.
    """
    try:
        import shutil

        return shutil.which(prog)
    except Exception:
        return None


__all__ = [
    "build_color_env",
    "stream_process_lines",
    "spawn_setup_install",
    "launch_install_external",
]

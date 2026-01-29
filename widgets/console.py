import os
import shlex
import subprocess
import threading
import time
from typing import Optional
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from helpers.ansi import insert_ansi_formatted
from utils.process import installer_entry as _installer_entry


class SetupConsole(Gtk.Window):
    """
    Dedicated interactive console window for running the setup installer (or other
    commands). Streams stdout/stderr, supports sending input (Enter, Y, N), Ctrl+C,
    and masked password entry when a sudo/password prompt is detected.
    """

    # PASSWORD_PATTERNS disabled (no auto password detection)
    PASSWORD_PATTERNS: list[str] = []

    def __init__(self, parent: Gtk.Window, title: str = "Setup Console"):
        super().__init__(title=title, transient_for=parent)
        self.set_default_size(820, 500)
        self.set_border_width(0)

        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.props.title = title
        self.set_titlebar(hb)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.set_border_width(8)
        self.add(outer)

        # Log view
        self.textview = Gtk.TextView()
        self.textview.set_editable(False)
        self.textview.set_cursor_visible(False)
        self.textview.set_monospace(True)
        self._apply_css()

        self.buf = self.textview.get_buffer()
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(self.textview)
        outer.pack_start(sw, True, True, 0)
        # Ensure ANSI tags exist for console highlighting
        try:
            # Create a tiny hidden buffer to initialize tags used by _insert_ansi_formatted
            insert_ansi_formatted(self.buf, "")
        except Exception:
            pass

        # Controls
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.input_entry = Gtk.Entry()
        self.input_entry.set_placeholder_text("Type input (Enter to send)")
        self.input_entry.connect("activate", self._on_send)
        controls.pack_start(self.input_entry, True, True, 0)

        for label, payload in [("Y", "y\n"), ("N", "n\n"), ("Enter", "\n")]:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", lambda _b, t=payload: self._send_text(t))
            controls.pack_start(btn, False, False, 0)

        ctrlc_btn = Gtk.Button(label="Ctrl+C")
        ctrlc_btn.connect("clicked", self._on_ctrl_c)
        controls.pack_start(ctrlc_btn, False, False, 0)

        clear_btn = Gtk.Button(label="Clear")
        clear_btn.connect("clicked", lambda _b: self.buf.set_text(""))
        controls.pack_start(clear_btn, False, False, 0)

        outer.pack_end(controls, False, False, 0)

        self.show_all()

        # Track destruction to avoid UI updates after widget is gone
        self._destroyed = False
        try:
            self.connect("destroy", lambda *a: setattr(self, "_destroyed", True))
        except Exception:
            pass

        self._proc: Optional[subprocess.Popen] = None
        self._password_cached: Optional[str] = None
        self._finished_callback = None

    def _apply_css(self):
        css = """
        .setup-console {
            font-size: 12px;
            line-height: 1.25;
        }
        """
        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(css.encode("utf-8"))
            screen = Gdk.Screen.get_default()
            if screen:
                Gtk.StyleContext.add_provider_for_screen(
                    screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
            self.textview.get_style_context().add_class("setup-console")
        except Exception:
            pass

    def _append(self, text: str):
        # Guard against updates after destroy or before realization; degrade gracefully
        try:
            if getattr(self, "_destroyed", False) or not self.textview:
                return
            tv = self.textview
            if not tv.get_realized():
                # If not realized yet, just buffer text without scrolling
                self.buf.insert(self.buf.get_end_iter(), text)
                return
            # Safe insertion using offsets to avoid iterator reuse issues
            start_offset = self.buf.get_char_count()
            self.buf.insert(self.buf.get_end_iter(), text)
            end_offset = self.buf.get_char_count()
            start_it = self.buf.get_iter_at_offset(start_offset)
            end_it = self.buf.get_iter_at_offset(end_offset)
            # Scroll only if still visible
            if tv.get_visible():
                start_it = self.buf.get_iter_at_offset(start_offset)
                end_it = self.buf.get_iter_at_offset(end_offset)
                # Create mark at end and scroll
                mark = self.buf.create_mark(None, end_it, False)
                tv.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)
        except Exception:
            pass

    def run_process(self, argv: list[str], cwd: Optional[str] = None, on_finished=None):
        """
        Start the child process and stream its output. When finished, optionally call on_finished().
        """
        self._finished_callback = on_finished
        self._append(f"$ {' '.join(shlex.quote(a) for a in argv)}\n")
        try:
            repo_root = cwd or os.getcwd()
            installer_cmd = _installer_entry(repo_root)
            # If argv starts with the resolved installer entry attempt robust spawn with fallbacks
            if argv and argv[0] in ("./setup", installer_cmd):
                self._proc = _spawn_setup_install(
                    repo_root,
                    lambda msg: self._append(msg),
                    extra_args=argv[1:],
                    capture_stdout=True,
                )
            else:
                env = dict(os.environ)
                env.update(
                    {
                        "TERM": "xterm-256color",
                        "FORCE_COLOR": "1",
                        "CLICOLOR": "1",
                        "CLICOLOR_FORCE": "1",
                    }
                )
                env.pop("NO_COLOR", None)
                self._proc = subprocess.Popen(
                    argv,
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=env,
                )
        except Exception as ex:
            self._append(f"[spawn error] {ex}\n")
            if self._finished_callback:
                self._finished_callback()
            return

        if not self._proc or not self._proc.stdout:
            self._append("[spawn error] setup failed to start\n")
            if self._finished_callback:
                self._finished_callback()
            return
        threading.Thread(target=self._stream_loop, daemon=True).start()

    def _stream_loop(self):
        assert self._proc and self._proc.stdout
        for line in iter(self._proc.stdout.readline, ""):
            if not line:
                break

            # Schedule UI mutation on main thread to avoid iterator invalidation
            def _append_line(text_line=line):
                try:
                    insert_ansi_formatted(self.buf, text_line)
                except Exception:
                    self._append(text_line)
                mark = self.buf.create_mark(None, self.buf.get_end_iter(), False)
                self.textview.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)
                # Trim console lines if limit configured
                try:
                    # limit = int(SETTINGS.get("log_max_lines", 0))
                    # if limit and self.buf.get_line_count() > limit:
                    #     s_it = self.buf.get_start_iter()
                    #     e_it = self.buf.get_iter_at_line(
                    #         self.buf.get_line_count() - limit
                    #     )
                    #     self.buf.delete(s_it, e_it)
                    pass
                except Exception:
                    pass
                return False

            GLib.idle_add(_append_line)
            self._maybe_password_prompt(line)
        rc = self._proc.wait()

        def _final():
            try:
                insert_ansi_formatted(self.buf, f"[exit {rc}]\n")
            except Exception:
                self._append(f"[exit {rc}]\n")
            # Remember exit code for notification logic
            self._last_exit_code = rc
            self._after_finish()
            return False

        GLib.idle_add(_final)

    def _after_finish(self):
        # Run any supplied completion callback first
        if callable(self._finished_callback):
            try:
                self._finished_callback()
            finally:
                self._finished_callback = None
        # Send desktop notification about installer result (detached console case)
        try:
            rc = getattr(self, "_last_exit_code", None)
            # Prefer the window's application, fallback to global default
            app = self.get_application()
            # if not app:
            #     try:
            #         app = Gio.Application.get_default()
            #     except Exception:
            #         app = None
            # if (
            #     app
            #     and rc is not None
            #     and bool(SETTINGS.get("send_notifications", True))
            # ):
            #     notification = Gio.Notification.new(
            #         "Update successful" if rc == 0 else "Update finished (errors)"
            #     )
            #     body = (
            #         "Installer completed successfully."
            #         if rc == 0
            #         else f"Installer exited with code {rc}."
            #     )
            #     notification.set_body(body)
            #     try:
            #         app.send_notification("illogical-updots-installer", notification)
            #     except Exception:
            #         pass
        except Exception:
            pass
        # Close the console window automatically after process ends
        try:
            self.destroy()
        except Exception:
            pass

    def _on_send(self, _entry):
        txt = self.input_entry.get_text()
        if txt:
            if not txt.endswith("\n"):
                txt += "\n"
            self._send_text(txt)
        self.input_entry.set_text("")

    def _send_text(self, text: str):
        p = self._proc
        if not p:
            return
        try:
            mfd = getattr(p, "_pty_master_fd", None)
            if mfd is not None:
                import os

                os.write(mfd, text.encode("utf-8", "replace"))
            elif p.stdin:
                p.stdin.write(text)
                p.stdin.flush()
            else:
                self._append("[send error] no stdin available\n")
                return
            self._append(f"[sent] {text}")
        except Exception as ex:
            self._append(f"[send error] {ex}\n")

    def _on_ctrl_c(self, _btn):
        if self._proc:
            try:
                import signal

                self._proc.send_signal(signal.SIGINT)
                self._append("[signal] SIGINT sent\n")
            except Exception as ex:
                self._append(f"[ctrl-c error] {ex}\n")

    def _maybe_password_prompt(self, line: str):
        # Disabled: do not auto-handle password prompts
        return

    def _on_key_press(self, _widget, event) -> bool:
        # if event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval in (
        #     Gdk.KEY_i,
        #     Gdk.KEY_I,
        # ):
        #     self.run_install_external()
        #     return True
        return False

    # def _auto_inject(self, text: str) -> bool:
    #     # No auto injections; console removed.
    #     return False
    #     # Guard against automated inputs while a sudo password prompt is active
    #     block_until = getattr(self, "_auto_inject_block_until", 0.0)
    #     if time.time() < block_until:
    #         return False
    #     self.console.send_text(text)
    #     return False


def _spawn_setup_install(
    repo_path: str,
    logger,
    extra_args: list[str] | None = None,
    capture_stdout: bool = True,
    auto_input_seq: list[str] | None = None,
    use_pty: bool = True,
):
    """
    Spawn the resolved installer entry (./setup or ./install-ii-vynx.sh) with ANSI color + interactive support.

    If use_pty is True we allocate a pseudo-terminal so tools think they are in a real
    terminal (preserves colors, interactive prompts). Falls back to direct execution
    methods if PTY allocation fails.

    Returns a Popen object or None. When PTY is used we monkey-patch p.stdout with a
    text wrapper so existing readline loops continue to work.
    """
    import errno
    import io
    import os
    import pty

    extra_args = extra_args or []
    entry = _installer_entry(repo_path)
    skip_auto_input = entry.endswith("install-ii-vynx.sh")
    base_cmds = [
        [entry] + extra_args,
        ["fish", entry] + extra_args,
        ["bash", entry] + extra_args,
        ["sh", entry] + extra_args,
    ]

    def _env():
        env = dict(os.environ)
        env.update(
            {
                "FORCE_COLOR": "1",
                "CLICOLOR": "1",
                "CLICOLOR_FORCE": "1",
                "TERM": "xterm-256color",
            }
        )
        env.pop("NO_COLOR", None)
        return env

    for cmd in base_cmds:
        try:
            master_fd, slave_fd = None, None
            if use_pty:
                try:
                    master_fd, slave_fd = pty.openpty()
                except Exception as ex:
                    logger(f"[pty-warn] failed to open pty: {ex}; fallback no-pty\n")
                    master_fd = slave_fd = None
                    use_pty = False

            if use_pty and master_fd is not None and slave_fd is not None:
                p = subprocess.Popen(
                    cmd,
                    cwd=repo_path,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    env=_env(),
                    close_fds=True,
                )
                # Close slave end in parent; child keeps it
                try:
                    os.close(slave_fd)
                except Exception:
                    pass
                # Wrap master in text IO for readline compatibility (read-only)
                master_file = os.fdopen(master_fd, "rb", buffering=0)
                text_stream = io.TextIOWrapper(
                    master_file, encoding="utf-8", errors="replace", newline="\n"
                )

                class PTYStdout:
                    def __init__(self, stream):
                        self._stream = stream
                        self._buffer = ""

                    def readline(self):
                        # Accumulate until newline or EOF
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

                p.stdout = PTYStdout(text_stream)  # type: ignore[attr-defined]
                p._pty_master_fd = master_fd  # type: ignore[attr-defined]
                logger(f"[spawn/pty] {' '.join(cmd)}\n")
            else:
                # Non-PTY fallback
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

            # Auto input sequence (sent after slight delay to allow prompt rendering)
            if auto_input_seq and not skip_auto_input:

                def _feed():
                    import time as _t

                    master_fd = getattr(p, "_pty_master_fd", None)
                    pipe = p.stdin if master_fd is None else None
                    if master_fd is None and not pipe:
                        logger(
                            "[auto-input] stdin unavailable; aborting auto sequence\n"
                        )
                        return
                    _t.sleep(0.2)
                    for item in auto_input_seq:
                        try:
                            if master_fd is not None:
                                os.write(master_fd, item.encode("utf-8", "replace"))
                            else:
                                if pipe is None:
                                    logger("[auto-input] stdin unavailable; stopping\n")
                                    break
                                if getattr(pipe, "closed", False):
                                    logger("[auto-input] stdin closed; stopping\n")
                                    break
                                os.write(pipe.fileno(), item.encode("utf-8", "replace"))
                            logger(f"[auto-input] {repr(item)}\n")
                        except Exception as _ex:
                            logger(f"[auto-input-error] {_ex}\n")
                            break
                        _t.sleep(0.25)
                    # After auto-enters, append yesforall
                    try:
                        yesforall = "yesforall\n"
                        if master_fd is not None:
                            os.write(master_fd, yesforall.encode("utf-8", "replace"))
                        elif pipe:
                            os.write(
                                pipe.fileno(), yesforall.encode("utf-8", "replace")
                            )
                        logger(f"[auto-input] {repr(yesforall)}\n")
                    except Exception as _ex:
                        logger(f"[auto-input-error] {_ex}\n")

                threading.Thread(target=_feed, daemon=True).start()
            elif not auto_input_seq and not skip_auto_input:
                # Even without an explicit auto_input_seq, send a trailing 'yesforall'
                def _feed_yesforall():
                    import os
                    import time as _t

                    _t.sleep(0.3)
                    master_fd = getattr(p, "_pty_master_fd", None)
                    pipe = p.stdin if master_fd is None else None
                    try:
                        msg = "yesforall\n"
                        if master_fd is not None:
                            os.write(master_fd, msg.encode("utf-8", "replace"))
                        elif pipe:
                            os.write(pipe.fileno(), msg.encode("utf-8", "replace"))
                        logger(f"[auto-input] {repr(msg)}\n")
                    except Exception as _ex:
                        logger(f"[auto-input-error] {_ex}\n")

                threading.Thread(target=_feed_yesforall, daemon=True).start()

            return p
        except OSError as ex:
            if ex.errno == errno.ENOEXEC:  # Exec format
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

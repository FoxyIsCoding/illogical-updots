#!/usr/bin/env python3
"""
A reusable console/logging panel widget for illogical-updots.

This module encapsulates:
- A Gtk.Revealer hosting a framed console area
- A Gtk.TextView with ANSI color support for streaming logs
- Clear/Hide header controls
- Optional input entry + quick-send buttons (Y/N/Enter) and Ctrl+C
- Thread-safe append/clear operations with optional line-trimming
- Helpers to send input to a running subprocess (PTY or pipe)

Typical usage:

    from ui.console_panel import ConsolePanel
    from core.app_meta import SETTINGS

    panel = ConsolePanel(settings=SETTINGS)
    some_container.pack_start(panel.revealer, expand=False, fill=False, padding=0)

    panel.ensure_open()
    panel.append("[info] Hello\n")
    panel.set_process(popen_obj)  # so inputs/ctrl-c can be sent

    # When process ends:
    panel.set_process(None)

Notes:
- ANSI color sequences are converted via helpers. If unavailable, plain text is used.
- The panel is self-contained; callers do not need to manage CSS providers.
"""

from __future__ import annotations

import os
import threading
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

# Local imports (kept optional/defensive where possible)
try:
    from style.css import get_css  # type: ignore
except Exception:  # pragma: no cover - defensive
    get_css = None  # type: ignore[assignment]

try:
    from helpers.ansi import insert_ansi_formatted  # type: ignore
except Exception:  # pragma: no cover - defensive
    insert_ansi_formatted = None  # type: ignore[assignment]


class ConsolePanel:
    """
    Encapsulates a console UI component with:
    - header (title + clear/hide buttons)
    - scrollable TextView (monospace)
    - optional input controls
    - revealer container for easy show/hide

    Provide settings with key 'log_max_lines' to enable trimming.
    """

    def __init__(self, settings: Optional[dict] = None, title: str = "Console") -> None:
        self.settings = settings or {}
        self._current_proc = None

        # Revealer root
        self.revealer = Gtk.Revealer()
        self.revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.revealer.set_reveal_child(False)

        # Outer frame + vbox
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.IN)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_border_width(6)
        frame.add(vbox)

        # Header row
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl = Gtk.Label(label=title)
        lbl.set_xalign(0.0)
        header.pack_start(lbl, True, True, 0)

        self.clear_btn = Gtk.Button.new_from_icon_name(
            "edit-clear-symbolic", Gtk.IconSize.SMALL_TOOLBAR
        )
        self.clear_btn.set_tooltip_text("Clear console")
        self.clear_btn.connect("clicked", lambda _b: self.clear())
        header.pack_end(self.clear_btn, False, False, 0)

        self.hide_btn = Gtk.Button.new_from_icon_name(
            "go-up-symbolic", Gtk.IconSize.SMALL_TOOLBAR
        )
        self.hide_btn.set_tooltip_text("Hide console")
        self.hide_btn.connect(
            "clicked", lambda _b: self.revealer.set_reveal_child(False)
        )
        header.pack_end(self.hide_btn, False, False, 0)

        vbox.pack_start(header, False, False, 0)

        # Text view
        self.view = Gtk.TextView()
        self.view.set_editable(False)
        self.view.set_cursor_visible(False)
        self.view.set_monospace(True)
        self._apply_css()

        self.buffer = self.view.get_buffer()

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(320)
        sw.add(self.view)
        vbox.pack_start(sw, True, True, 0)

        # Input controls row
        self.controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.input_entry = Gtk.Entry()
        self.input_entry.set_placeholder_text("Type input (Enter to send)")
        self.input_entry.connect("activate", self._on_entry_activate)
        self.controls.pack_start(self.input_entry, True, True, 0)

        for label, payload in [("Y", "y\n"), ("N", "n\n"), ("Enter", "\n")]:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", lambda _b, t=payload: self.send_to_process(t))
            self.controls.pack_start(btn, False, False, 0)

        ctrlc_btn = Gtk.Button(label="Ctrl+C")
        ctrlc_btn.connect("clicked", self._on_ctrl_c)
        self.controls.pack_start(ctrlc_btn, False, False, 0)

        vbox.pack_start(self.controls, False, False, 0)

        # Key helpers when focus in the view
        self.view.connect("key-press-event", self._on_view_key_press)

        self.revealer.add(frame)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def ensure_open(self) -> None:
        """
        Reveal the console and show input controls.
        """
        try:
            self.revealer.set_reveal_child(True)
            self.controls.show_all()
        except Exception:
            pass

    def toggle(self) -> None:
        """
        Toggle the revealer visibility.
        """
        try:
            self.revealer.set_reveal_child(not self.revealer.get_reveal_child())
        except Exception:
            pass

    def set_process(self, proc) -> None:
        """
        Register a running process to enable input/ctrl-c.

        Expected interface:
        - If spawned with PTY: '._pty_master_fd' int attr may be present
        - Otherwise: '.stdin' file-like with fileno()
        """
        self._current_proc = proc

    def get_process(self):
        """
        Return the currently attached process object (or None).
        """
        return self._current_proc

    def append(self, text: str) -> None:
        """
        Append text to the console buffer (thread-safe).
        Applies ANSI styling if available; otherwise inserts plain text.
        Enforces optional line limit from settings.
        """

        def do_append() -> bool:
            buf = getattr(self, "buffer", None)
            view = getattr(self, "view", None)
            if not buf or not view:
                return False
            try:
                # If unrealized, do a simple insert (no scroll)
                if not view.get_realized():
                    buf.insert(buf.get_end_iter(), text)
                    return False
                try:
                    if insert_ansi_formatted:
                        insert_ansi_formatted(buf, text)
                    else:
                        buf.insert(buf.get_end_iter(), text)
                except Exception:
                    buf.insert(buf.get_end_iter(), text)

                # Scroll to end when visible
                if view.get_visible() and view.get_realized():
                    end_it = buf.get_end_iter()
                    mark = buf.create_mark(None, end_it, False)
                    view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

                # Optional trimming
                try:
                    limit = int(self.settings.get("log_max_lines", 0))
                    if limit and buf.get_line_count() > limit:
                        start_it = buf.get_start_iter()
                        end_it = buf.get_iter_at_line(buf.get_line_count() - limit)
                        buf.delete(start_it, end_it)
                except Exception:
                    pass
            except Exception:
                pass
            return False

        if threading.current_thread() is threading.main_thread():
            do_append()
        else:
            GLib.idle_add(do_append)

    def clear(self) -> None:
        """
        Clear the text buffer (thread-safe).
        """

        def do_clear() -> bool:
            try:
                if hasattr(self, "buffer"):
                    self.buffer.set_text("")
            except Exception:
                pass
            return False

        if threading.current_thread() is threading.main_thread():
            do_clear()
        else:
            GLib.idle_add(do_clear)

    def send_to_process(self, text: str) -> None:
        """
        Send raw input text to the active process (PTY or stdin pipe).
        """
        p = self._current_proc
        master_fd = getattr(p, "_pty_master_fd", None) if p else None
        if p and (master_fd is not None or getattr(p, "stdin", None)):
            try:
                if master_fd is not None:
                    os.write(master_fd, text.encode("utf-8", "replace"))
                else:
                    os.write(p.stdin.fileno(), text.encode("utf-8", "replace"))
                self.append(f"[sent] {text}")
            except Exception as ex:
                self.append(f"[send error] {ex}\n")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_entry_activate(self, _entry: Gtk.Entry) -> None:
        txt = self.input_entry.get_text()
        if txt and not txt.endswith("\n"):
            txt += "\n"
        if txt:
            self.send_to_process(txt)
        self.input_entry.set_text("")

    def _on_ctrl_c(self, _btn: Gtk.Button) -> None:
        p = self._current_proc
        if not p:
            return
        try:
            import signal

            p.send_signal(signal.SIGINT)
            self.append("[signal] SIGINT sent\n")
        except Exception as ex:
            self.append(f"[ctrl-c error] {ex}\n")

    def _on_view_key_press(self, _widget, event) -> bool:
        # Quick helpers for interactive prompts
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.send_to_process("\n")
            return True
        if event.keyval in (Gdk.KEY_y, Gdk.KEY_Y):
            self.send_to_process("y\n")
            return True
        if event.keyval in (Gdk.KEY_n, Gdk.KEY_N):
            self.send_to_process("n\n")
            return True
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _apply_css(self) -> None:
        """
        Apply application CSS for the log view if available and add 'log-view' style.
        """
        try:
            css_text = get_css() if get_css else None
            if css_text:
                provider = Gtk.CssProvider()
                provider.load_from_data(css_text.encode("utf-8"))
                screen = Gdk.Screen.get_default()
                if screen:
                    Gtk.StyleContext.add_provider_for_screen(
                        screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                    )
            # Always tag the view for rules to match
            try:
                self.view.get_style_context().add_class("log-view")
            except Exception:
                pass
        except Exception:
            # CSS is best-effort; proceed silently
            pass


__all__ = ["ConsolePanel"]

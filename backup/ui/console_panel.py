#!/usr/bin/env python3
"""
An interactive VTE-based console panel for illogical-updots.
Provides a real terminal experience with support for sudo, interactive prompts, etc.
"""

from __future__ import annotations

import os
import threading
from typing import Callable, Optional, List

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, GLib, Gtk, Vte, Pango


class ConsolePanel:
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
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        frame.add(vbox)

        # Header row
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.set_border_width(4)
        lbl = Gtk.Label(label=title)
        lbl.set_xalign(0.0)
        header.pack_start(lbl, True, True, 0)

        self.clear_btn = Gtk.Button.new_from_icon_name("edit-clear-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.clear_btn.set_tooltip_text("Reset terminal")
        self.clear_btn.connect("clicked", lambda _b: self.clear())
        header.pack_end(self.clear_btn, False, False, 0)

        self.hide_btn = Gtk.Button.new_from_icon_name("go-up-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.hide_btn.set_tooltip_text("Hide console")
        self.hide_btn.connect("clicked", lambda _b: self.revealer.set_reveal_child(False))
        header.pack_end(self.hide_btn, False, False, 0)

        vbox.pack_start(header, False, False, 0)

        # VTE Terminal
        self.terminal = Vte.Terminal()
        self.terminal.set_scrollback_lines(int(self.settings.get("log_max_lines", 5000)))
        self.terminal.set_font(Pango.FontDescription.from_string(f"Monospace {self.settings.get('console_font_size', 12)}"))
        
        # Colors (Adwaita Darkish)
        self.terminal.set_color_foreground(Gdk.RGBA(0.8, 0.8, 0.8, 1.0))
        self.terminal.set_color_background(Gdk.RGBA(0.1, 0.1, 0.1, 1.0))

        # ScrolledWindow for VTE
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(350)
        sw.add(self.terminal)
        vbox.pack_start(sw, True, True, 0)

        # Input controls row (keeping for accessibility/touch)
        self.controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.controls.set_border_width(4)

        for label, payload in [("Y", "y\n"), ("N", "n\n"), ("Enter", "\n")]:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", lambda _b, t=payload: self.feed_input(t))
            self.controls.pack_start(btn, False, False, 0)

        ctrlc_btn = Gtk.Button(label="Ctrl+C")
        ctrlc_btn.connect("clicked", lambda _b: self.terminal.feed_child(b"\x03"))
        self.controls.pack_start(ctrlc_btn, False, False, 0)

        vbox.pack_start(self.controls, False, False, 0)
        self.revealer.add(frame)

    def ensure_open(self) -> None:
        self.revealer.set_reveal_child(True)
        self.terminal.grab_focus()

    def toggle(self) -> None:
        self.revealer.set_reveal_child(not self.revealer.get_reveal_child())
        if self.revealer.get_reveal_child():
            self.terminal.grab_focus()

    def clear(self) -> None:
        self.terminal.reset(True, True)

    def append(self, text: str) -> None:
        """Feed text to the terminal display (simulated output)."""
        if isinstance(text, str):
            self.terminal.feed(text.encode("utf-8"))

    def feed_input(self, text: str) -> None:
        """Feed input to the child process running in VTE."""
        if isinstance(text, str):
            self.terminal.feed_child(text.encode("utf-8"))

    def run_command(self, argv: List[str], cwd: Optional[str] = None, on_finished: Optional[Callable] = None):
        """Run a command inside the VTE terminal."""
        self.ensure_open()
        
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        
        def callback(vte, pid, status):
            if on_finished:
                on_finished(status)

        try:
            success, pid = self.terminal.spawn_sync(
                Vte.PtyFlags.DEFAULT,
                cwd or os.getcwd(),
                argv,
                None,
                GLib.SpawnFlags.DO_NOT_REAP_CHILD,
                None,
                None,
            )
            if success:
                GLib.child_watch_add(pid, callback, self.terminal)
            return success
        except Exception as e:
            self.append(f"\n[Error] Failed to spawn: {e}\n")
            return False

    def set_process(self, proc):
        """Compatibility shim; VTE handles its own process."""
        self._current_proc = proc

    def get_process(self):
        return self._current_proc

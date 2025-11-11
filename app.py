#!/usr/bin/env python3
"""
GTK3 app that checks ~/dots-hyprland for git updates and shows a nice UI.

- If updates are available (local branch is behind its upstream), the Update button
  becomes blue and clickable.
- If no updates are available, the Update button is disabled (grey).
- You can refresh manually or wait for the periodic automatic refresh.

Requirements:
- Python 3
- GTK3 and PyGObject (python3-gi, gir1.2-gtk-3.0)
- git installed and available on PATH
"""

import os
import sys
from typing import Optional
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib

from main_window import MainWindow, APP_ID, APP_TITLE, REPO_PATH, SETTINGS, _save_settings


class App(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)

    def do_activate(self) -> None:  # type: ignore[override]
        global REPO_PATH
        # First-run selection if no repo path configured and no fallback found
        if not REPO_PATH or not os.path.isdir(REPO_PATH):
            # Explain the situation and ask user to continue to select a repository
            alert = Gtk.MessageDialog(
                transient_for=None,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.NONE,
                text="Repository not found",
            )
            alert.format_secondary_text(
                "No repository path is configured, and no default could be detected.\n"
                "Please select your repository folder to continue."
            )
            alert.add_button("Cancel", Gtk.ResponseType.CANCEL)
            alert.add_button("Continue", Gtk.ResponseType.OK)
            resp_alert = alert.run()
            alert.destroy()
            if resp_alert != Gtk.ResponseType.OK:
                return
            # Open file chooser after user confirms
            chooser = Gtk.FileChooserDialog(
                title="Select repository directory",
                transient_for=None,
                action=Gtk.FileChooserAction.SELECT_FOLDER,
            )
            chooser.add_buttons(
                "Cancel", Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.OK
            )
            try:
                start_dir = os.path.expanduser("~")
                if os.path.isdir(start_dir):
                    chooser.set_current_folder(start_dir)
            except Exception:
                pass
            resp = chooser.run()
            if resp == Gtk.ResponseType.OK:
                chosen = chooser.get_filename()
                if chosen and os.path.isdir(chosen):
                    SETTINGS["repo_path"] = chosen
                    _save_settings(SETTINGS)
                    REPO_PATH = chosen
            chooser.destroy()
            # If user canceled and we still don't have a valid path, do not open main window
            if not REPO_PATH or not os.path.isdir(REPO_PATH):
                return

        if not self.props.active_window:
            MainWindow(self)
        self.props.active_window.present()

    def do_shutdown(self) -> None:  # type: ignore[override]
        # Stop sudo keepalive thread cleanly
        win = self.props.active_window
        if win and hasattr(win, "_sudo_keepalive_stop"):
            try:
                win._sudo_keepalive_stop.set()
                t = getattr(win, "_sudo_keepalive_thread", None)
                if t and t.is_alive():
                    t.join(timeout=1.0)
            except Exception:
                pass
        Gtk.Application.do_shutdown(self)


def main(argv: Optional[list[str]] = None) -> int:
    app = App()
    return app.run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
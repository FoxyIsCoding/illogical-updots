import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Pango, GLib


def show_about_dialog(window, APP_TITLE, REPO_PATH, SETTINGS) -> None:
    dialog = Gtk.Window(title=f"About {APP_TITLE}")
    dialog.set_transient_for(window)
    dialog.set_modal(True)
    dialog.set_default_size(700, 520)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    outer.set_border_width(16)
    dialog.add(outer)

    header = Gtk.Label()
    header.set_use_markup(True)
    header.set_markup(
        f"<span size='xx-large' weight='bold'>{GLib.markup_escape_text(APP_TITLE)}</span>"
    )
    header.set_xalign(0.0)
    outer.pack_start(header, False, False, 0)

    subtitle = Gtk.Label()
    subtitle.set_use_markup(True)
    subtitle.set_markup(
        "<span size='large'>A simple End4 illogical-impulse dotfiles manager and updater.</span>"
    )
    subtitle.set_xalign(0.0)
    subtitle.set_line_wrap(True)
    subtitle.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    outer.pack_start(subtitle, False, False, 0)

    info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    info_box.set_hexpand(True)
    outer.pack_start(info_box, False, False, 0)

    path_lbl = Gtk.Label()
    path_lbl.set_xalign(0.0)
    path_lbl.set_use_markup(True)
    repo_txt = str(SETTINGS.get("repo_path") or REPO_PATH)
    path_lbl.set_markup(f"<b>Repository:</b> {GLib.markup_escape_text(repo_txt)}")
    info_box.pack_start(path_lbl, False, False, 0)

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.set_min_content_height(320)
    outer.pack_start(sw, True, True, 0)

    body = Gtk.TextView()
    body.set_editable(False)
    body.set_cursor_visible(False)
    body.set_monospace(True)
    buf = body.get_buffer()
    buf.set_text(
        "Features:\n"
        " - Detects when your local branch is behind its upstream\n"
        " - Shows a changes view with avatars and animations\n"
        " - Provides an interactive embedded console with color output\n"
        " - Runs your setup installer plus optional pre- and post-install scripts\n\n"
        "Tip: Configure the repository path and options in Settings."
    )
    sw.add(body)

    dialog.show_all()

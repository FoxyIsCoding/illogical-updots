import time
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


def show_logs_dialog(window) -> None:
    if not window._update_logs:
        show_details_dialog(window, "Git Logs", "No update logs yet.", "")
        return
    brief_lines = [
        f"{ts} | {event} | {summary.splitlines()[0] if summary else ''}"
        for (ts, event, summary) in window._update_logs
    ]
    brief_body = "\n".join(brief_lines)
    expanded = "\n\n----\n\n".join(
        f"{ts}\nEvent: {event}\n{summary}"
        for (ts, event, summary) in window._update_logs
    )
    show_details_dialog(window, "Update Logs", brief_body, expanded)


def show_details_dialog(
    parent: Gtk.Window, title: str, summary: str, details: str
) -> None:
    dialog = Gtk.Dialog(title=title, transient_for=parent, flags=0)
    dialog.add_button("Close", Gtk.ResponseType.CLOSE)
    content = dialog.get_content_area()

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_border_width(12)
    content.add(box)

    summary_lbl = Gtk.Label(label=summary or "")
    summary_lbl.set_xalign(0.0)
    box.pack_start(summary_lbl, False, False, 0)

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.set_min_content_height(240)

    tv = Gtk.TextView()
    tv.set_editable(False)
    tv.set_cursor_visible(False)
    buf = tv.get_buffer()
    buf.set_text(details or "(no details)")

    sw.add(tv)
    box.pack_start(sw, True, True, 0)

    dialog.show_all()
    dialog.run()
    dialog.destroy()

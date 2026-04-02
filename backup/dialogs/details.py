import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Pango, GLib


def show_repo_info_dialog(window, run_git) -> None:
    st = window._status
    if not st:
        show_details_dialog(window, "Repository Info", "Status not loaded yet.", "")
        return
    repo_path = st.repo_path
    # Gather extra git info
    status_rc, status_out, status_err = run_git(["status", "--short"], repo_path)
    remote_rc, remote_out, remote_err = run_git(["remote", "-v"], repo_path)
    branch = st.branch or "(unknown)"
    upstream = st.upstream or "(no upstream)"
    summary_lines = [
        f"Repo: {repo_path}",
        f"Branch: {branch}",
        f"Upstream: {upstream}",
        f"Ahead: {st.ahead}",
        f"Behind: {st.behind}",
        f"Dirty files: {st.dirty}",
    ]
    if st.fetch_error:
        summary_lines.append(f"Fetch warning: {st.fetch_error}")
    if st.error:
        summary_lines.append(f"Error: {st.error}")
    summary = "\n".join(summary_lines)
    details_parts = []
    details_parts.append("== git status --short ==")
    details_parts.append(status_out.strip() or "(clean)")
    if status_err.strip():
        details_parts.append("stderr:\n" + status_err.strip())
    details_parts.append("\n== git remote -v ==")
    details_parts.append(remote_out.strip() or "(none)")
    if remote_err.strip():
        details_parts.append("stderr:\n" + remote_err.strip())
    # Include pending commits and diffstat when updates are available
    if st.has_updates and st.upstream:
        log_rc, log_out, log_err = run_git(
            [
                "log",
                "--pretty=format:%h %s | %an, %ad",
                "--date=short",
                f"HEAD..{st.upstream}",
            ],
            repo_path,
        )
        details_parts.append("\n== commits to pull ==")
        details_parts.append(log_out.strip() or "(none)")
        if log_err.strip():
            details_parts.append("stderr:\n" + log_err.strip())
        diff_rc, diff_out, diff_err = run_git(
            ["diff", "--stat", f"HEAD..{st.upstream}"],
            repo_path,
        )
        details_parts.append("\n== diff stat ==")
        details_parts.append(diff_out.strip() or "(none)")
        if diff_err.strip():
            details_parts.append("stderr:\n" + diff_err.strip())
    details = "\n".join(details_parts)
    full_text = summary + "\n\n" + details

    dialog = Gtk.Window(title="Details…")
    dialog.set_transient_for(window)
    dialog.set_modal(True)
    dialog.set_default_size(900, 600)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    outer.set_border_width(12)
    dialog.add(outer)

    header = Gtk.Label()
    header.set_markup("<b>Repository Details</b>")
    header.set_xalign(0.0)
    outer.pack_start(header, False, False, 0)

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    outer.pack_start(sw, True, True, 0)

    tv = Gtk.TextView()
    tv.set_editable(False)
    tv.set_cursor_visible(False)
    tv.set_monospace(True)
    buf = tv.get_buffer()
    buf.set_text(full_text)
    sw.add(tv)

    dialog.show_all()


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

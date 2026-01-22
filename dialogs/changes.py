import re
import threading
import time
import webbrowser
from typing import Optional, Tuple

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

from helpers.ansi import insert_ansi_formatted
from widgets.avatars import guess_github_avatar


def parse_github_slug(remote_url: str) -> Optional[Tuple[str, str]]:
    """
    Parse a GitHub remote URL into (owner, repo) slug.

    Examples supported:
        - https://github.com/owner/repo.git
        - https://github.com/owner/repo
        - git@github.com:owner/repo.git
        - ssh://git@github.com/owner/repo.git
    """
    if not remote_url:
        return None

    url = remote_url.strip()

    # SSH forms
    m = re.match(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$", url)
    if m:
        return m.group("owner"), m.group("repo")

    m = re.match(
        r"^(?:ssh://)?git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
        url,
    )
    if m:
        return m.group("owner"), m.group("repo")

    # HTTPS forms
    m = re.match(
        r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?(?:/)?$",
        url,
    )
    if m:
        return m.group("owner"), m.group("repo")

    return None


def format_ago(iso_str: str) -> str:
    # Expect ISO-like date from git: "YYYY-MM-DD HH:MM:SS +/-HHMM"
    try:
        try:
            ts = time.mktime(time.strptime(iso_str[:19], "%Y-%m-%d %H:%M:%S"))
        except Exception:
            # Fallback: short date only
            ts = time.mktime(time.strptime(iso_str[:10], "%Y-%m-%d"))
        now = time.time()
        delta = max(0, int(now - ts))
        if delta < 60:
            return f"{delta}s ago"
        if delta < 3600:
            return f"{delta // 60}m ago"
        if delta < 86400:
            return f"{delta // 3600}h ago"
        days = delta // 86400
        return f"{days}d ago"
    except Exception:
        return iso_str


def build_row(
    c: dict, list_box: Gtk.ListBox, github_slug: Optional[Tuple[str, str]] = None
) -> Gtk.Widget:
    # Create an EventBox to make the entire row clickable
    event_box = Gtk.EventBox()

    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    row.set_hexpand(True)
    event_box.add(row)

    # Make the row clickable if we have a GitHub slug
    if github_slug:
        owner, repo = github_slug
        commit_hash = c.get("full", "")
        if commit_hash:
            url = f"https://github.com/{owner}/{repo}/commit/{commit_hash}"

            def on_click(widget, event):
                if event.button == 1:  # Left click only
                    try:
                        webbrowser.open(url)
                    except Exception as e:
                        print(f"Failed to open browser: {e}")
                    return True
                return False

            event_box.connect("button-press-event", on_click)

            # Add hover cursor
            def on_realize(widget):
                window = widget.get_window()
                if window:
                    window.set_cursor(
                        Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "pointer")
                    )

            event_box.connect("realize", on_realize)

    # Placeholder avatar inside rounded background container; lazy-load actual GitHub avatar
    avatar_bg = Gtk.EventBox()
    avatar_bg.set_size_request(36, 36)
    avatar_bg.get_style_context().add_class("avatar-bg")
    avatar = Gtk.Image.new_from_icon_name("avatar-default-symbolic", Gtk.IconSize.MENU)
    avatar_bg.add(avatar)
    row.pack_start(avatar_bg, False, False, 0)

    meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    meta.set_hexpand(True)

    # First line: short hash + subject
    subject_lbl = Gtk.Label()
    subject_lbl.set_xalign(0.0)
    subject_lbl.set_line_wrap(True)
    subject_lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    subject_lbl.set_use_markup(True)
    subject_markup = (
        f"<span foreground='#00ace6'>{GLib.markup_escape_text(c.get('short', ''))}</span> "
        f"{GLib.markup_escape_text(c.get('subject', ''))}"
    )
    subject_lbl.set_markup(subject_markup)
    meta.pack_start(subject_lbl, False, False, 0)

    # Second line: author — date (ago)
    info_lbl = Gtk.Label()
    info_lbl.set_xalign(0.0)
    info_lbl.set_use_markup(True)
    ago = format_ago(c.get("date_iso", c.get("date", "")))
    info_markup = (
        f"<small>{GLib.markup_escape_text(c.get('author', ''))} — "
        f"{GLib.markup_escape_text(c.get('date', ''))} ({GLib.markup_escape_text(ago)})</small>"
    )
    info_lbl.set_markup(info_markup)
    meta.pack_start(info_lbl, False, False, 0)

    row.pack_start(meta, True, True, 0)

    # Lazy-load avatar in a background thread and update on idle
    def load_avatar():
        try:
            url = c.get("avatar") or guess_github_avatar(c.get("email", ""))
            if not url:
                return
            import urllib.request

            with urllib.request.urlopen(url, timeout=5) as resp:
                data = resp.read()
            loader = GdkPixbuf.PixbufLoader()
            loader.write(data)
            loader.close()
            pixbuf = loader.get_pixbuf()
            if pixbuf:

                def set_img():
                    try:
                        import math

                        import cairo

                        size = 32
                        scaled = (
                            pixbuf.scale_simple(
                                size, size, GdkPixbuf.InterpType.BILINEAR
                            )
                            or pixbuf
                        )
                        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
                        ctx = cairo.Context(surface)
                        ctx.arc(size / 2.0, size / 2.0, size / 2.0, 0, 2 * math.pi)
                        ctx.clip()
                        Gdk.cairo_set_source_pixbuf(ctx, scaled, 0, 0)
                        ctx.paint()
                        rounded = Gdk.pixbuf_get_from_surface(surface, 0, 0, size, size)
                        if rounded:
                            avatar.set_from_pixbuf(rounded)
                        else:
                            avatar.set_from_pixbuf(scaled)
                    except Exception:
                        avatar.set_from_pixbuf(pixbuf)
                    return False

                GLib.idle_add(set_img)
        except Exception:
            pass

    threading.Thread(target=load_avatar, daemon=True).start()

    event_box.show_all()
    return event_box


def apply_filter(
    search_entry: Gtk.SearchEntry, list_box: Gtk.ListBox, commits_data: list
):
    q = search_entry.get_text().strip().lower()
    children = list_box.get_children()
    if not q:
        for ch in children:
            ch.show()
        return
    for i, ch in enumerate(children):
        if i >= len(commits_data):
            ch.hide()
            continue
        c = commits_data[i]
        hay = " ".join(
            [
                c.get("short", ""),
                c.get("subject", ""),
                c.get("author", ""),
                c.get("date", ""),
            ]
        ).lower()
        if q in hay:
            ch.show()
        else:
            ch.hide()


def on_view_changes_quick(window: Gtk.Window, run_git) -> None:
    """
    Faster, cleaner changes window that opens immediately and fills asynchronously.
    - Shows commit avatar, subject, author, date and 'ago'
    - If > 15 commits, shows a search box to filter results live
    - Incremental, lazy rendering with per-row reveal animation and lazy avatar fetch
    - Click on any commit to open it in GitHub
    """
    st = getattr(window, "_status", None)
    if not (st and st.upstream):
        show_details_dialog(window, "Changes", "No updates available", "")
        return
    repo_path = st.repo_path
    upstream = st.upstream

    # Get GitHub slug for clickable commits
    github_slug = None
    rc, out, _ = run_git(["remote", "get-url", "origin"], repo_path)
    remote_url = out.strip() if rc == 0 else ""
    if remote_url:
        github_slug = parse_github_slug(remote_url)

    dialog = Gtk.Window(title="Pending Commits")
    dialog.set_transient_for(window)
    dialog.set_modal(True)
    dialog.set_default_size(1100, 760)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    outer.set_border_width(12)
    dialog.add(outer)

    header = Gtk.Label()
    header.set_markup("<b>Loading commits…</b>")
    header.set_xalign(0.0)
    outer.pack_start(header, False, False, 0)

    tools_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    tools_box.set_hexpand(True)
    outer.pack_start(tools_box, False, False, 0)
    search_entry = Gtk.SearchEntry()
    search_entry.set_placeholder_text("Search commits…")
    search_entry.set_hexpand(True)
    search_entry.hide()
    tools_box.pack_start(search_entry, True, True, 0)

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    outer.pack_start(sw, True, True, 0)

    list_box = Gtk.ListBox()
    list_box.set_selection_mode(Gtk.SelectionMode.NONE)
    sw.add(list_box)

    # Apply CSS for rounded avatar backgrounds
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
        .avatar-bg {
            background-color: #2e3440;
            border-radius: 9999px;
            padding: 2px;
        }
        """)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
    except Exception:
        pass
    dialog.show_all()

    commits_data: list[dict] = []
    row_widgets: list[Gtk.Widget] = []

    def work():
        rc, out, err = run_git(
            [
                "log",
                "--pretty=format:%H|%h|%an|%ae|%ad|%s",
                "--date=iso",
                f"HEAD..{upstream}",
            ],
            repo_path,
        )
        if rc != 0:
            commits = None
            error = err or "Failed to load commits."
        else:
            lines = [ln for ln in out.splitlines() if ln.strip()]
            commits = []
            for ln in lines:
                parts = ln.split("|", 5)
                if len(parts) == 6:
                    full, short, author, email, date_iso, subject = parts
                    commits.append(
                        {
                            "full": full,
                            "short": short,
                            "author": author,
                            "email": email,
                            "date": date_iso.split(" ")[0],
                            "date_iso": date_iso,
                            "subject": subject,
                            "avatar": guess_github_avatar(email),
                        }
                    )
            error = None

        def done():
            if error:
                header.set_markup("<b>Error</b>")
                # Show error in a single row label
                list_box.foreach(lambda w: list_box.remove(w))
                lbl = Gtk.Label(label=error)
                lbl.set_xalign(0.0)
                list_box.add(lbl)
                dialog.show_all()
                return

            nonlocal commits_data
            commits_data = commits or []
            header.set_markup(f"<b>{len(commits_data)} commit(s) to pull</b>")

            # Clear list and incrementally add rows with reveal animation
            list_box.foreach(lambda w: list_box.remove(w))
            row_widgets.clear()

            index = {"i": 0}

            def add_next():
                i = index["i"]
                if i >= len(commits_data):
                    # Enable search if many
                    if len(commits_data) > 15:
                        search_entry.show()
                        search_entry.connect(
                            "changed", lambda e: apply_filter(e, list_box, commits_data)
                        )
                    return False
                c = commits_data[i]
                index["i"] = i + 1

                # Build row and wrap in revealer for animation
                row = build_row(c, list_box, github_slug)
                revealer = Gtk.Revealer()
                revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
                revealer.set_transition_duration(160)
                revealer.add(row)
                revealer.set_reveal_child(False)
                list_box.add(revealer)
                row_widgets.append(revealer)
                list_box.show_all()

                # Reveal after a tiny delay to animate
                def _reveal():
                    revealer.set_reveal_child(True)
                    return False

                GLib.timeout_add(30, _reveal)

                # Queue next row addition
                GLib.timeout_add(25, add_next)
                return False

            # Kick off incremental rendering
            GLib.idle_add(add_next)
            return False

        GLib.idle_add(done)

    threading.Thread(target=work, daemon=True).start()


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

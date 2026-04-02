#!/usr/bin/env python3
"""
Pull Requests dialog for illogical-updots.

This dialog detects the configured repository's GitHub remote and lists open
pull requests using the GitHub REST API.

Features:
- Auto-detects GitHub owner/repo from `origin` remote (SSH or HTTPS)
- Asynchronously fetches open PRs (first page, up to 50)
- Shows title, number, author, created date (with "ago")
- Click any PR row to open it in the browser
- Attempts to extract first image from PR body and shows it as a preview
  - If no image is found, falls back to the author's avatar
- Simple search box to filter PRs by title/author/number

Integration:
    from dialogs.pull_requests import show_pull_requests_dialog
    ...
    show_pull_requests_dialog(self, run_git)

Notes:
- Unauthenticated requests are used by default, and may be rate-limited by GitHub.
  You can set the environment variable GITHUB_TOKEN to use authenticated requests:
    export GITHUB_TOKEN=ghp_yourtokenhere
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from typing import Dict, List, Optional, Tuple

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gio", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def make_rounded_pixbuf(
    pixbuf: GdkPixbuf.Pixbuf, size: int
) -> Optional[GdkPixbuf.Pixbuf]:
    """
    Create a circular/rounded version of a pixbuf using cairo.
    Returns a new pixbuf with the image clipped to a circle.
    """
    try:
        import math

        import cairo

        # Scale the pixbuf to the desired size
        scaled = pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
        if not scaled:
            return pixbuf

        # Create a cairo surface and context
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        ctx = cairo.Context(surface)

        # Draw a circular clip path
        ctx.arc(size / 2.0, size / 2.0, size / 2.0, 0, 2 * math.pi)
        ctx.clip()

        # Draw the pixbuf onto the clipped surface
        Gdk.cairo_set_source_pixbuf(ctx, scaled, 0, 0)
        ctx.paint()

        # Convert the surface back to a pixbuf
        rounded = Gdk.pixbuf_get_from_surface(surface, 0, 0, size, size)
        return rounded or pixbuf
    except Exception:
        return pixbuf


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


def find_first_image_url(markdown_text: str) -> str:
    """
    Try to find the first image URL in a Markdown string.

    Strategy:
      1) Look for Markdown image: ![alt](url)
      2) Fallback: any http(s) URL ending in common image extensions
    """
    body = markdown_text or ""
    # Markdown image
    m = re.search(r"!\[[^\]]*\]\(([^)]+)\)", body)
    if m:
        return m.group(1).strip()

    # Plain image-ish URL
    m = re.search(
        r"(https?://\S+\.(?:png|jpg|jpeg|gif|webp|bmp|svg))",
        body,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return ""


def format_ago(iso_str: str) -> str:
    """
    Convert an ISO-ish timestamp into "Xd ago" format.
    Expects GitHub timestamps like "2024-01-10T13:37:00Z".
    """
    try:
        # Strip fractional or Z
        s = iso_str.strip()
        # Normalize: "YYYY-MM-DDTHH:MM:SS"
        s = s.split(".")[0].rstrip("Z")
        ts = time.mktime(time.strptime(s, "%Y-%m-%dT%H:%M:%S"))
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
        # Fallback to original
        return iso_str


def http_get_json(url: str, timeout: int = 12) -> Tuple[int, object, str]:
    """
    Minimal GET returning (status, parsed_json|None, error_message|empty).
    Adds a UA and optional Authorization header if GITHUB_TOKEN is present.
    """
    try:
        headers = {"User-Agent": "illogical-updots/1.0"}
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            data = resp.read().decode("utf-8", "replace")
        try:
            return status, json.loads(data), ""
        except Exception as jerr:
            return status, None, f"Failed to parse JSON: {jerr}"
    except Exception as ex:
        return 0, None, str(ex)


def load_image_pixbuf(url: str, timeout: int = 8) -> Optional[GdkPixbuf.Pixbuf]:
    """
    Download an image and decode as Pixbuf. Returns None on failure.
    """
    if not url:
        return None
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "illogical-updots/1.0"}, method="GET"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        loader = GdkPixbuf.PixbufLoader()
        loader.write(data)
        loader.close()
        return loader.get_pixbuf()
    except Exception:
        return None


def scale_to_fit(pixbuf: GdkPixbuf.Pixbuf, max_w: int, max_h: int) -> GdkPixbuf.Pixbuf:
    """
    Scale pixbuf to fit within max_w x max_h preserving aspect ratio.
    Returns the scaled pixbuf (or original if no scaling needed).
    """
    try:
        w = pixbuf.get_width()
        h = pixbuf.get_height()
        if w <= 0 or h <= 0:
            return pixbuf
        rx = max_w / float(w)
        ry = max_h / float(h)
        r = min(rx, ry, 1.0)
        new_w = max(1, int(w * r))
        new_h = max(1, int(h * r))
        if new_w == w and new_h == h:
            return pixbuf
        scaled = pixbuf.scale_simple(new_w, new_h, GdkPixbuf.InterpType.BILINEAR)
        return scaled or pixbuf
    except Exception:
        return pixbuf


def open_uri(url: str) -> None:
    """
    Launch default application (browser) for a URL.
    """
    try:
        Gio.AppInfo.launch_default_for_uri(url, None)
    except Exception:
        pass


def apply_filter(
    search_entry: Gtk.SearchEntry, list_box: Gtk.ListBox, prs_data: List[Dict]
) -> None:
    """
    Filter list box rows according to search query matching title/author/number.
    """
    q = (search_entry.get_text() or "").strip().lower()
    children = list(list_box.get_children())
    if not q:
        for ch in children:
            ch.show()
        return
    for i, ch in enumerate(children):
        if i >= len(prs_data):
            ch.hide()
            continue
        pr = prs_data[i]
        hay = " ".join(
            [
                str(pr.get("number", "")),
                pr.get("title", ""),
                pr.get("user_login", ""),
            ]
        ).lower()
        if q in hay:
            ch.show()
        else:
            ch.hide()


# -------------------------------------------------------------------
# UI construction
# -------------------------------------------------------------------


def build_pr_row(pr: Dict, preview_max: Tuple[int, int] = (128, 80)) -> Gtk.Widget:
    """
    Build a single PR row widget. Loads preview/avatar asynchronously.
    """
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    row.set_hexpand(True)

    # Clickable container
    eb = Gtk.EventBox()
    eb.add(row)

    # Check if we'll be showing an avatar (for proper sizing)
    preview_url = pr.get("body_image_url") or pr.get("user_avatar_url") or ""
    is_avatar = preview_url == pr.get("user_avatar_url", "")

    # Preview container - make square for avatars
    preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    if is_avatar:
        # Square container for circular avatars
        avatar_size = 80
        preview_box.set_size_request(avatar_size, avatar_size)
    else:
        preview_box.set_size_request(preview_max[0], preview_max[1])

    preview_img = Gtk.Image.new_from_icon_name("image-missing", Gtk.IconSize.DND)
    # Will add appropriate CSS class when image loads (pr-preview or pr-avatar)
    preview_box.pack_start(preview_img, True, True, 0)
    eb.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)

    # Meta
    meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    meta.set_hexpand(True)

    # Title
    title_lbl = Gtk.Label()
    title_lbl.set_xalign(0.0)
    title_lbl.set_line_wrap(True)
    title_lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    title_lbl.set_use_markup(True)
    safe_title = GLib.markup_escape_text(pr.get("title", ""))
    title_lbl.set_markup(f"<b>{safe_title}</b>")
    meta.pack_start(title_lbl, False, False, 0)

    # Subtitle
    subtitle_lbl = Gtk.Label()
    subtitle_lbl.set_xalign(0.0)
    subtitle_lbl.set_use_markup(True)
    n = pr.get("number")
    login = pr.get("user_login", "")
    created = pr.get("created_at", "")
    ago = format_ago(created)
    draft = " (draft)" if pr.get("draft") else ""
    subtitle_lbl.set_markup(
        f"<small>#{n} by {GLib.markup_escape_text(login)} — {GLib.markup_escape_text(ago)}{draft}</small>"
    )
    meta.pack_start(subtitle_lbl, False, False, 0)

    # Assemble row content
    row.pack_start(preview_box, False, False, 0)
    row.pack_start(meta, True, True, 0)

    # Click handler
    html_url = pr.get("html_url", "")
    if html_url:

        def on_click(_w, _e):
            open_uri(html_url)
            return True

        eb.connect("button-press-event", on_click)

    # Async image loading
    def load_preview():
        pb = load_image_pixbuf(preview_url)
        if pb:
            if is_avatar:
                # For avatars, make them circular at a good size
                avatar_size = 80
                pb = make_rounded_pixbuf(pb, avatar_size)
            else:
                # For preview images, just scale to fit
                pb = scale_to_fit(pb, preview_max[0], preview_max[1])

            def set_img():
                try:
                    preview_img.set_from_pixbuf(pb)
                    # Apply appropriate CSS class
                    if is_avatar:
                        preview_img.get_style_context().add_class("pr-avatar")
                    else:
                        preview_img.get_style_context().add_class("pr-preview")
                except Exception:
                    pass
                return False

            GLib.idle_add(set_img)

    if preview_url:
        threading.Thread(target=load_preview, daemon=True).start()

    eb.show_all()
    return eb


# -------------------------------------------------------------------
# Public entry point
# -------------------------------------------------------------------


def show_pull_requests_dialog(window: Gtk.Window, run_git) -> None:
    """
    Show a dialog listing open GitHub pull requests for the current repository.

    Args:
        window: Parent MainWindow (expects window._status to be populated)
        run_git: Callable(args: List[str], cwd: str) -> (rc, stdout, stderr)
    """
    st = getattr(window, "_status", None)
    if not (st and st.ok):
        _show_simple_dialog(window, "Pull Requests", "Repository is not ready.")
        return

    repo_path = st.repo_path

    # Create window UI immediately
    dialog = Gtk.Window(title="Pull Requests")
    dialog.set_transient_for(window)
    dialog.set_modal(True)
    dialog.set_default_size(1100, 760)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    outer.set_border_width(12)
    dialog.add(outer)

    header = Gtk.Label()
    header.set_xalign(0.0)
    header.set_markup("<b>Detecting GitHub repository…</b>")
    outer.pack_start(header, False, False, 0)

    tools_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    tools_box.set_hexpand(True)
    outer.pack_start(tools_box, False, False, 0)

    search_entry = Gtk.SearchEntry()
    search_entry.set_placeholder_text("Search pull requests…")
    search_entry.set_hexpand(True)
    search_entry.hide()
    tools_box.pack_start(search_entry, True, True, 0)

    refresh_btn = Gtk.Button.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON)
    refresh_btn.set_tooltip_text("Refresh")
    tools_box.pack_end(refresh_btn, False, False, 0)

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    outer.pack_start(sw, True, True, 0)

    list_box = Gtk.ListBox()
    list_box.set_selection_mode(Gtk.SelectionMode.NONE)
    sw.add(list_box)

    # Minimal CSS for preview rounding/background
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"""
            .pr-preview {
                background-color: #2e3440;
                border-radius: 6px;
                padding: 2px;
            }
            .pr-avatar {
                border-radius: 50%;
                min-width: 80px;
                min-height: 80px;
            }
            """
        )
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
    except Exception:
        pass

    dialog.show_all()

    prs_data: List[Dict] = []
    current_slug = {"slug": ""}

    def load_and_render():
        # 1) Determine remote slug
        rc, out, _ = run_git(["remote", "get-url", "origin"], repo_path)
        remote_url = out.strip() if rc == 0 else ""
        if not remote_url:
            rc2, out2, _ = run_git(["remote", "-v"], repo_path)
            # Find origin fetch line
            m = re.search(r"^origin\s+(\S+)\s+\(fetch\)", out2, flags=re.MULTILINE)
            if m:
                remote_url = m.group(1).strip()
        slug = parse_github_slug(remote_url)
        if not slug:

            def set_err():
                header.set_markup(
                    "<b>Not a GitHub repository (origin remote not recognized)</b>"
                )
                list_box.foreach(lambda w: list_box.remove(w))
                lbl = Gtk.Label(
                    label="Only GitHub remotes are supported for PR listing."
                )
                lbl.set_xalign(0.0)
                list_box.add(lbl)
                dialog.show_all()
                return False

            GLib.idle_add(set_err)
            return

        owner, repo = slug
        current_slug["slug"] = f"{owner}/{repo}"

        # 2) Fetch PRs
        def set_loading():
            header.set_markup(f"<b>Loading pull requests for {owner}/{repo}…</b>")
            # Clear list
            list_box.foreach(lambda w: list_box.remove(w))
            dialog.show_all()
            return False

        GLib.idle_add(set_loading)

        url = (
            f"https://api.github.com/repos/{owner}/{repo}/pulls?state=open&per_page=50"
        )
        status, data, err = http_get_json(url)

        # 3) Process results
        if status != 200 or not isinstance(data, list):
            msg = err or f"GitHub API error (HTTP {status})"

            def set_api_err():
                header.set_markup(f"<b>Failed to load PRs for {owner}/{repo}</b>")
                list_box.foreach(lambda w: list_box.remove(w))
                lbl = Gtk.Label(label=msg)
                lbl.set_xalign(0.0)
                list_box.add(lbl)
                dialog.show_all()
                return False

            GLib.idle_add(set_api_err)
            return

        items: List[Dict] = []
        for pr in data:
            if not isinstance(pr, dict):
                continue
            body = pr.get("body") or ""
            img = find_first_image_url(body)
            user = pr.get("user") or {}
            items.append(
                {
                    "number": pr.get("number"),
                    "title": pr.get("title") or "",
                    "created_at": pr.get("created_at") or "",
                    "html_url": pr.get("html_url") or "",
                    "user_login": user.get("login") or "",
                    "user_avatar_url": user.get("avatar_url") or "",
                    "draft": bool(pr.get("draft")),
                    "body_image_url": img,
                }
            )

        def render_items():
            nonlocal prs_data
            prs_data = items
            header.set_markup(
                f"<b>{len(items)} open pull request(s) — {owner}/{repo}</b>"
            )

            # Clear list
            list_box.foreach(lambda w: list_box.remove(w))

            # Incremental render with simple reveal
            index = {"i": 0}

            def add_next():
                i = index["i"]
                if i >= len(prs_data):
                    if len(prs_data) > 15:
                        search_entry.show()
                        search_entry.connect(
                            "changed",
                            lambda e: apply_filter(e, list_box, prs_data),
                        )
                    return False
                pr_item = prs_data[i]
                index["i"] = i + 1

                row = build_pr_row(pr_item)
                revealer = Gtk.Revealer()
                revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
                revealer.set_transition_duration(120)
                revealer.add(row)
                revealer.set_reveal_child(False)
                list_box.add(revealer)
                list_box.show_all()

                def _reveal():
                    revealer.set_reveal_child(True)
                    return False

                GLib.timeout_add(20, _reveal)
                GLib.timeout_add(18, add_next)
                return False

            GLib.idle_add(add_next)
            return False

        GLib.idle_add(render_items)

    def do_refresh(_btn=None):
        threading.Thread(target=load_and_render, daemon=True).start()

    refresh_btn.connect("clicked", do_refresh)

    # Initial load
    do_refresh()


# -------------------------------------------------------------------
# Simple fallback dialog
# -------------------------------------------------------------------


def _show_simple_dialog(parent: Gtk.Window, title: str, message: str) -> None:
    dlg = Gtk.Dialog(title=title, transient_for=parent, flags=0)
    dlg.add_button("Close", Gtk.ResponseType.CLOSE)
    box = dlg.get_content_area()
    box.set_border_width(12)
    lbl = Gtk.Label(label=message or "")
    lbl.set_xalign(0.0)
    box.add(lbl)
    dlg.show_all()
    dlg.run()
    dlg.destroy()


__all__ = ["show_pull_requests_dialog"]

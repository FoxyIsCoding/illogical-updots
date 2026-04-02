import urllib.request
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, GdkPixbuf


def fetch_github_avatar_url(email: str) -> str:
    """
    Naive attempt to guess GitHub avatar by using local-part as username.
    Returns direct PNG URL if reachable, else empty string.
    """
    try:
        local = (email or "").split("@")[0]
        if not local:
            return ""
        url = f"https://github.com/{local}.png"
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                return url
    except Exception:
        pass
    return ""


def make_avatar_image(url: str) -> Gtk.Image:
    if not url:
        return Gtk.Image.new_from_icon_name(
            "avatar-default-symbolic", Gtk.IconSize.MENU
        )
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = resp.read()
        loader = GdkPixbuf.PixbufLoader()
        loader.write(data)
        loader.close()
        pixbuf = loader.get_pixbuf()
        if pixbuf:
            # Scale to 32x32 preserving aspect
            scaled = pixbuf.scale_simple(32, 32, GdkPixbuf.InterpType.BILINEAR)
            return Gtk.Image.new_from_pixbuf(scaled or pixbuf)
    except Exception:
        pass
    return Gtk.Image.new_from_icon_name("avatar-default-symbolic", Gtk.IconSize.MENU)


def guess_github_avatar(email: str) -> str:
    """
    Try to extract username for GitHub-hosted emails, else fallback to local-part guess
    """
    em = email or ""
    local = em.split("@")[0]
    if em.endswith("@users.noreply.github.com"):
        # Formats: 12345+username@users.noreply.github.com or username@users.noreply.github.com
        if "+" in local:
            user = local.split("+", 1)[1]
        else:
            user = local
        return f"https://github.com/{user}.png"
    # Fallback to existing heuristic
    return f"https://github.com/{local}.png" if local else ""

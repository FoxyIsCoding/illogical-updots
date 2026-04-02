import re
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Pango


def insert_ansi_formatted(buf: Gtk.TextBuffer, raw: str) -> None:
    """
    Parse ANSI escape sequences and apply tags without reusing invalidated iterators.

    Strategy:
    - Scan raw once, splitting into (segment, tag-set) pairs.
    - Insert each segment capturing start_iter BEFORE insertion, end_iter AFTER insertion.
    - Apply tags using iter ranges (no stored iter reused across buffer mutations).
    """
    # Ensure base tags exist
    base_tags = {
        "ansi-bold": lambda t: t.set_property("weight", Pango.Weight.BOLD),
        "ansi-dim": lambda t: t.set_property("scale", 0.95),
        "ansi-italic": lambda t: t.set_property("style", Pango.Style.ITALIC),
        "ansi-underline": lambda t: t.set_property("underline", Pango.Underline.SINGLE),
        "ansi-red": lambda t: t.set_property("foreground", "#ff5555"),
        "ansi-green": lambda t: t.set_property("foreground", "#50fa7b"),
        "ansi-yellow": lambda t: t.set_property("foreground", "#f1fa8c"),
        "ansi-blue": lambda t: t.set_property("foreground", "#8be9fd"),
        "ansi-magenta": lambda t: t.set_property("foreground", "#ff79c6"),
        "ansi-cyan": lambda t: t.set_property("foreground", "#66d9ef"),
        "ansi-white": lambda t: t.set_property("foreground", "#f8f8f2"),
        "ansi-bright-black": lambda t: t.set_property("foreground", "#6272a4"),
        "ansi-bright-red": lambda t: t.set_property("foreground", "#ff6e6e"),
        "ansi-bright-green": lambda t: t.set_property("foreground", "#69ff94"),
        "ansi-bright-yellow": lambda t: t.set_property("foreground", "#ffffa5"),
        "ansi-bright-blue": lambda t: t.set_property("foreground", "#9aedfe"),
        "ansi-bright-magenta": lambda t: t.set_property("foreground", "#ff92df"),
        "ansi-bright-cyan": lambda t: t.set_property("foreground", "#82e9ff"),
        "ansi-bright-white": lambda t: t.set_property("foreground", "#ffffff"),
    }
    tag_table = buf.get_tag_table()
    for name, init in base_tags.items():
        if tag_table.lookup(name) is None:
            tg = Gtk.TextTag.new(name)
            init(tg)
            tag_table.add(tg)

    sgr_map = {
        "1": "ansi-bold",
        "2": "ansi-dim",
        "3": "ansi-italic",
        "4": "ansi-underline",
        "30": "ansi-bright-black",
        "31": "ansi-red",
        "32": "ansi-green",
        "33": "ansi-yellow",
        "34": "ansi-blue",
        "35": "ansi-magenta",
        "36": "ansi-cyan",
        "37": "ansi-white",
        "90": "ansi-bright-black",
        "91": "ansi-bright-red",
        "92": "ansi-bright-green",
        "93": "ansi-bright-yellow",
        "94": "ansi-bright-blue",
        "95": "ansi-bright-magenta",
        "96": "ansi-bright-cyan",
        "97": "ansi-bright-white",
    }
    bg_map = {
        "40": "#000000",
        "41": "#ff5555",
        "42": "#50fa7b",
        "43": "#f1fa8c",
        "44": "#8be9fd",
        "45": "#ff79c6",
        "46": "#66d9ef",
        "47": "#f8f8f2",
        "100": "#6272a4",
        "101": "#ff6e6e",
        "102": "#69ff94",
        "103": "#ffffa5",
        "104": "#9aedfe",
        "105": "#ff92df",
        "106": "#82e9ff",
        "107": "#ffffff",
    }

    ansi_re = re.compile(r"\x1b\[[0-9;]*m")
    pos = 0
    active = []

    def ensure_xterm_tag(kind: str, idx: int) -> str:
        name = f"ansi-xterm-{kind}-{idx}"
        if tag_table.lookup(name) is None:
            # Build color
            def xterm_color(n: int) -> str:
                if n < 16:
                    base = [
                        "#000000",
                        "#800000",
                        "#008000",
                        "#808000",
                        "#000080",
                        "#800080",
                        "#008080",
                        "#c0c0c0",
                        "#808080",
                        "#ff0000",
                        "#00ff00",
                        "#ffff00",
                        "#0000ff",
                        "#ff00ff",
                        "#00ffff",
                        "#ffffff",
                    ]
                    return base[n]
                if 16 <= n <= 231:
                    n -= 16
                    r = (n // 36) % 6
                    g = (n // 6) % 6
                    b = n % 6
                    conv = [0, 95, 135, 175, 215, 255]
                    return f"#{conv[r]:02x}{conv[g]:02x}{conv[b]:02x}"
                level = 8 + (n - 232) * 10
                return f"#{level:02x}{level:02x}{level:02x}"

            col = xterm_color(idx)
            tg = Gtk.TextTag.new(name)
            if kind == "38":
                tg.set_property("foreground", col)
            else:
                tg.set_property("background", col)
            tag_table.add(tg)
        return name

    while True:
        m = ansi_re.search(raw, pos)
        segment = raw[pos : m.start()] if m else raw[pos:]
        if segment:
            # compute offsets to avoid invalid iterators
            start_offset = buf.get_char_count()
            buf.insert(buf.get_end_iter(), segment)
            end_offset = buf.get_char_count()
            start_iter = buf.get_iter_at_offset(start_offset)
            end_iter = buf.get_iter_at_offset(end_offset)
            for t in active:
                tg = tag_table.lookup(t)
                if tg:
                    buf.apply_tag(tg, start_iter, end_iter)
        if not m:
            break
        seq = m.group()
        codes = seq[2:-1].split(";") if seq != "\x1b[m" else []
        if not codes or any(c == "0" for c in codes):
            active = []
        else:
            i = 0
            while i < len(codes):
                c = codes[i]
                if c in ("38", "48") and i + 2 < len(codes) and codes[i + 1] == "5":
                    try:
                        idx = int(codes[i + 2])
                        active.append(ensure_xterm_tag(c, idx))
                    except Exception:
                        pass
                    i += 3
                    continue
                mapped = sgr_map.get(c)
                if mapped and mapped not in active:
                    active.append(mapped)
                elif c in bg_map:
                    name = f"ansi-bg-{c}"
                    if tag_table.lookup(name) is None:
                        tg = Gtk.TextTag.new(name)
                        tg.set_property("background", bg_map[c])
                        tag_table.add(tg)
                    if name not in active:
                        active.append(name)
                i += 1
        pos = m.end()

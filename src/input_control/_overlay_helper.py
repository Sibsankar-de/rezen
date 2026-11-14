import io
import os
import sys
import threading

os.environ["GDK_BACKEND"] = "x11"

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib, Gtk


def _hex_to_rgba(hex_code: str) -> tuple[float, float, float, float]:
    clean = hex_code.lstrip("#")
    if len(clean) == 6:
        try:
            r = int(clean[0:2], 16) / 255.0
            g = int(clean[2:4], 16) / 255.0
            b = int(clean[4:6], 16) / 255.0
            return (r, g, b, 1.0)
        except ValueError:
            pass
    return (0.0, 0.9, 0.46, 1.0)


def _render_pixbuf(
    fill_rgba: tuple[float, float, float, float],
    outline_rgba: tuple[float, float, float, float],
    size: int = 18,
) -> GdkPixbuf.Pixbuf:
    pad = 4
    dim = size + pad
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, dim, dim)
    cr = cairo.Context(surface)

    s = size / 18.0
    cr.move_to(1, 1)
    cr.line_to(1, min(dim - 1, 1 + int(18 * s * 0.9)))
    cr.line_to(min(dim - 1, 1 + int(18 * s * 0.28)), min(dim - 1, 1 + int(18 * s * 0.68)))
    cr.line_to(min(dim - 1, 1 + int(18 * s * 0.55)), min(dim - 1, 1 + int(18 * s * 1.0)))
    cr.line_to(min(dim - 1, 1 + int(18 * s * 0.7)), min(dim - 1, 1 + int(18 * s * 0.9)))
    cr.line_to(min(dim - 1, 1 + int(18 * s * 0.44)), min(dim - 1, 1 + int(18 * s * 0.58)))
    cr.line_to(min(dim - 1, 1 + int(18 * s * 0.75)), min(dim - 1, 1 + int(18 * s * 0.58)))
    cr.close_path()

    cr.set_source_rgba(*fill_rgba)
    cr.fill_preserve()

    cr.set_source_rgba(*outline_rgba)
    cr.set_line_width(max(1.5, 1.5 * s))
    cr.stroke()

    buf = io.BytesIO()
    surface.write_to_png(buf)
    stream = Gio.MemoryInputStream.new_from_data(buf.getvalue())
    return GdkPixbuf.Pixbuf.new_from_stream(stream, None)


def main():
    color_hex = sys.argv[1] if len(sys.argv) > 1 else "#00E676"
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 18

    normal_rgba = _hex_to_rgba(color_hex)
    click_rgba = (1.0, 1.0, 1.0, 1.0)
    outline_rgba = (0.0, 0.0, 0.0, 1.0)

    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_title("Rezen Remote Pointer")
    win.set_decorated(False)
    win.set_keep_above(True)
    win.set_app_paintable(True)
    win.set_accept_focus(False)
    win.set_focus_on_map(False)

    screen = win.get_screen()
    visual = screen.get_rgba_visual()
    if visual:
        win.set_visual(visual)

    css = Gtk.CssProvider()
    css.load_from_data(b"window, .background { background-color: rgba(0, 0, 0, 0); }")
    Gtk.StyleContext.add_provider_for_screen(
        screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

    normal_pixbuf = _render_pixbuf(normal_rgba, outline_rgba, size)
    click_pixbuf = _render_pixbuf(click_rgba, outline_rgba, size)

    image = Gtk.Image.new_from_pixbuf(normal_pixbuf)
    win.add(image)
    win.realize()

    gdk_win = win.get_window()
    if hasattr(gdk_win, "set_pass_through"):
        gdk_win.set_pass_through(True)

    win.show_all()

    def stdin_listener():
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            cmd = parts[0]
            if cmd == "move" and len(parts) >= 3:
                try:
                    x, y = int(parts[1]), int(parts[2])
                    GLib.idle_add(win.move, x, y)
                except ValueError:
                    pass
            elif cmd == "click" and len(parts) >= 3:
                pressed = parts[2] == "1"
                pb = click_pixbuf if pressed else normal_pixbuf
                GLib.idle_add(image.set_from_pixbuf, pb)
            elif cmd == "quit":
                GLib.idle_add(Gtk.main_quit)
                break

    thread = threading.Thread(target=stdin_listener, daemon=True)
    thread.start()

    Gtk.main()


if __name__ == "__main__":
    main()

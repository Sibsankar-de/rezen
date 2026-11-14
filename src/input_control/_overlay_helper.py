import sys
import threading

import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk


def _hex_to_rgb(hex_code: str) -> tuple[float, float, float]:
    clean = hex_code.lstrip("#")
    if len(clean) == 6:
        try:
            r = int(clean[0:2], 16) / 255.0
            g = int(clean[2:4], 16) / 255.0
            b = int(clean[4:6], 16) / 255.0
            return (r, g, b)
        except ValueError:
            pass
    return (0.0, 0.9, 0.46)


def main():
    color_hex = sys.argv[1] if len(sys.argv) > 1 else "#00E676"
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 24

    normal_rgb = _hex_to_rgb(color_hex)
    click_rgb = (1.0, 1.0, 1.0)
    state = {"clicked": False}

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

    def draw_pointer(widget, cr):
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        fill = click_rgb if state["clicked"] else normal_rgb
        cr.set_source_rgb(*fill)

        s = size / 24.0
        cr.move_to(1, 1)
        cr.line_to(1, 18 * s)
        cr.line_to(5 * s, 14 * s)
        cr.line_to(10 * s, 22 * s)
        cr.line_to(13 * s, 20 * s)
        cr.line_to(8 * s, 12 * s)
        cr.line_to(14 * s, 12 * s)
        cr.close_path()
        cr.fill_preserve()

        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(max(1.5, 1.5 * s))
        cr.stroke()

    win.connect("draw", draw_pointer)
    pad = 4
    win.set_default_size(size + pad, size + pad)
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
                state["clicked"] = parts[2] == "1"
                GLib.idle_add(win.queue_draw)
            elif cmd == "quit":
                GLib.idle_add(Gtk.main_quit)
                break

    thread = threading.Thread(target=stdin_listener, daemon=True)
    thread.start()

    Gtk.main()


if __name__ == "__main__":
    main()

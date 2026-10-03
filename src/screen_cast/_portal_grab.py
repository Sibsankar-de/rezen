"""
Request a screen-share stream from the XDG Desktop Portal (Wayland).

This module runs as a standalone script under the *system* Python 3 because
the portal bindings (``dbus`` / ``gi``) live in the distribution packages and
are not visible to the project's virtualenv.

Protocol (line based, stdin/stdout):

    -> {"cmd": "grab"}
    <- {"ready": true, "width": 1920, "height": 1080, "node_id": 79}
    <- {"error": "..."}          (on failure)

Once ready the process stays alive to hold the PipeWire stream open, because
the portal tears the stream down when the requesting client disconnects. It
exits when stdin closes or on SIGTERM.

The user must approve the GNOME "Share" dialog raised by the ``Start``
request, so ``grab`` blocks until that is approved or the deadline passes.
"""

import json
import signal
import sys
import time

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SOURCE_MONITOR = 1
CURSOR_EMBEDDED = 1
CONSENT_TIMEOUT_SECONDS = 300.0
MAX_LIFETIME_SECONDS = 3600.0
POLL_INTERVAL_MS = 200

# The portal answers asynchronously over D-Bus signals, so the connection has to
# be attached to the GLib main loop before any receiver is registered.
_main_loop = dbus.mainloop.glib.DBusGMainLoop()
dbus.set_default_main_loop(_main_loop)
_bus = dbus.SessionBus(mainloop=_main_loop)

_loop = GLib.MainLoop()
_results = {}
_session = [None]
_deadline = [None]


def _screen_cast():
    return dbus.Interface(
        _bus.get_object(PORTAL_BUS, PORTAL_PATH),
        "org.freedesktop.portal.ScreenCast",
    )


def _recv(path, key, then=None):
    def handler(response, results):
        _results[key] = (int(response), dict(results) if results else {})
        if then:
            GLib.idle_add(then, _results[key])

    _bus.add_signal_receiver(
        handler,
        dbus_interface="org.freedesktop.portal.Request",
        signal_name="Response",
        path=path,
    )


def _select_sources(result):
    _session[0] = result[1]["session_handle"]
    _recv(
        _screen_cast().SelectSources(
            _session[0],
            {
                "types": dbus.UInt32(SOURCE_MONITOR),
                "multiple": False,
                "cursor_mode": dbus.UInt32(CURSOR_EMBEDDED),
            },
        ),
        "select",
        _start,
    )
    return False


def _start(_result):
    _recv(_screen_cast().Start(_session[0], "", {}), "start")
    return False


def _emit(payload):
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _poll():
    """Finish the handshake once the portal answers, or give up at the deadline."""
    if "start" in _results:
        code, results = _results["start"]
        streams = results.get("streams") if code == 0 else None
        if not streams:
            _emit({"error": f"portal refused the screencast request (code {code})"})
            _loop.quit()
            return False

        node_id = int(streams[0][0])
        size = streams[0][1].get("size") or (0, 0)
        width, height = int(size[0]), int(size[1])
        if width <= 0 or height <= 0:
            _emit({"error": "portal returned a stream with an invalid size"})
            _loop.quit()
            return False

        _emit({"ready": True, "node_id": node_id, "width": width, "height": height})
        GLib.timeout_add(int(MAX_LIFETIME_SECONDS * 1000), lambda: (_loop.quit(), False)[1])
        return False

    if _deadline[0] is not None and time.monotonic() > _deadline[0]:
        _emit({"error": "timed out waiting for the 'Share' consent dialog"})
        _loop.quit()
        return False

    return True


def _on_stdin(_source, _condition):
    line = sys.stdin.readline()
    if not line:
        _loop.quit()
        return False

    try:
        message = json.loads(line)
    except ValueError:
        return True

    if message.get("cmd") != "grab":
        return True

    _deadline[0] = time.monotonic() + CONSENT_TIMEOUT_SECONDS
    token = f"rezen{int(time.time() * 1000) % 100_000_000}"
    _recv(
        _screen_cast().CreateSession(
            {"session_handle_token": token, "persist_mode": "1"}
        ),
        "create",
        _select_sources,
    )
    return True


def main():
    signal.signal(signal.SIGTERM, lambda *_: _loop.quit())
    GLib.io_add_watch(sys.stdin, GLib.IO_IN | GLib.IO_HUP, _on_stdin)
    GLib.timeout_add(POLL_INTERVAL_MS, _poll)
    _loop.run()


if __name__ == "__main__":
    main()
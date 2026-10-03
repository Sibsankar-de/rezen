# Rezen

## Starting Rezen

### 1. Using the `rezen` Command

After cloning the repository, sync and install the package using `uv`:

```bash
uv sync
```

Launch the application directly with the `rezen` command:

```bash
uv run rezen
```

_Or, if installed globally or into an active virtual environment:_

```bash
rezen
```

---

## Screen capture

Rezen picks a capture backend automatically.

### X11 sessions

Uses [mss](https://pypi.org/project/mss/) to read the framebuffer directly. Nothing
extra to install.

### Wayland sessions

MSS reads the framebuffer over X11, which a Wayland compositor keeps hidden from
X11 clients, so every grab comes back black. On Wayland Rezen instead uses the
**XDG Desktop Portal** `ScreenCast` API and reads the resulting PipeWire stream
with GStreamer.

This needs two packages that are not Python dependencies:

```bash
sudo apt install gst-launch-1.0 gstreamer1.0-pipewire
```

The portal bindings (`dbus`, `gi`) come from the distribution's Python 3, which
Rezen locates automatically. `ScreenCapture` is re-exported as the helper
`screen_cast._portal_grab`, run under `/usr/bin/python3`.

**The first connection on a Wayland session shows a GNOME "Share" dialog.** Approve
it; the stream is torn down when you disconnect.

### Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `SCREEN_CAPTURE_BACKEND` | `auto` | `auto`, `mss`, or `pipewire` |
| `SCREEN_CAPTURE_MAX_WIDTH` | `1280` | Capture width cap |
| `SCREEN_CAPTURE_MAX_HEIGHT` | `720` | Capture height cap |

Capture throughput is pixel-bound: 1920x1080 reaches about 5 fps while
1280x720 reaches about 20 fps. Raise the caps for more detail, lower them for a
higher frame rate.

---

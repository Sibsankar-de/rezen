# Rezen

Remote device and screen control over the local network.

## Setup

Requires Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

### Screen capture on Wayland

Wayland compositors do not let X11 clients read the framebuffer, so Rezen shares
the screen through the XDG Desktop Portal instead. Install the two packages that
provide the PipeWire stream reader:

```bash
sudo apt install gst-launch-1.0 gstreamer1.0-pipewire
```

The portal bindings (`dbus`, `gi`) are taken from the distribution's Python 3,
which Rezen locates automatically.

The first connection on a Wayland session shows a GNOME **Share** dialog that must
be approved. The stream ends when you disconnect.

On an X11 session nothing extra is needed.

## Running

```bash
uv run rezen
```

_Or, if installed globally or into an active virtual environment:_

```bash
rezen
```

## Configuration

Optional environment variables, for example in `.env`:

| Variable | Default | Description |
| --- | --- | --- |
| `SCREEN_CAPTURE_BACKEND` | `auto` | Capture backend: `auto`, `mss`, or `pipewire` |
| `SCREEN_CAPTURE_MAX_WIDTH` | `1280` | Capture width cap |
| `SCREEN_CAPTURE_MAX_HEIGHT` | `720` | Capture height cap |
| `SCREEN_STREAM_BITRATE` | `8000000` | Encoder bitrate in bits per second |
| `SCREEN_STREAM_PRESET` | `veryfast` | x264 preset |
| `SCREEN_RENDER_WINDOW_NAME` | `Rezen - Remote screen` | Title of the playback window |
| `STREAM_CHUNK_SIZE` | `16384` | Bytes per streamed chunk |
| `APP_DEBUG` | `false` | Set to `true` for debug level logging |

Capture throughput is pixel-bound: 1920x1080 reaches about 5 fps while 1280x720
reaches about 21 fps. Raise the caps for more detail, lower them for a higher
frame rate.

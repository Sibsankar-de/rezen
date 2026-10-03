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

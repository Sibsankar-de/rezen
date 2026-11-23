# Rezen

Rezen is an open-source, cross-platform tool for remote device and screen control over a local network. It lets you view and control machines across different operating systems (such as Linux and Windows) from your own device, with no accounts, no cloud, and no relay servers involved. Both devices just need to be on the same LAN. Discovery won't work on networks with client isolation enabled (e.g. most public Wi-Fi).

It handles LAN device discovery automatically, streams the host screen using H.264 over TCP, and forwards keyboard and mouse input back to the host. It ships with a terminal UI as well as headless CLI modes for running on servers or scripts.

---

## Install

**Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/Sibsankar-de/rezen/main/install.sh | bash
```

After installation, open a new terminal or run `source ~/.bashrc` to pick up the `rezen` command.

> To install into a custom location:
>
> ```bash
> REZEN_INSTALL_DIR=/opt/rezen REZEN_BIN_DIR=/usr/local/bin \
>   curl -fsSL https://raw.githubusercontent.com/Sibsankar-de/rezen/main/install.sh | bash
> ```

**Windows**

Run in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/Sibsankar-de/rezen/main/install.ps1 | iex"
```

After installation, open a new terminal to pick up the `rezen` command.

---

## Run

```bash
rezen
```

This opens the terminal UI where you can see devices on the network, connect to one, and start a screen share session.

### Headless modes

**Broadcast your device on the network (no TUI):**

```bash
rezen --start-broadcast
```

**Scan for other Rezen devices (no TUI):**

```bash
rezen --start-discover
```

Both run continuously until you press `Ctrl+C`.

### CLI flags

| Flag                | Short | Description                                           |
| ------------------- | ----- | ----------------------------------------------------- |
| `--version`         | `-v`  | Show application version and exit                     |
| `--start-broadcast` | `-b`  | Run as a headless broadcaster                         |
| `--start-discover`  | `-d`  | Run as a headless device scanner                      |
| `--interval`        | `-i`  | Heartbeat / scan interval in seconds (default: `2.0`) |
| `--timeout`         | `-t`  | Per-scan timeout in seconds (default: `2.0`)          |

---

## Dev Setup

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), git

```bash
git clone git@github.com:Sibsankar-de/rezen.git
cd rezen
uv sync
```

**Run:**

```bash
uv run rezen
```

**Run tests:**

```bash
uv run pytest
```

**Lint and format:**

```bash
uv run ruff check .
uv run ruff format .
```

**Type check:**

```bash
uv run mypy src/
```

Logs are written to `logs/rezen.log`.

---

## Contributing

Contributions to Rezen are welcome! Whether it's fixing bugs, improving existing features, adding new functionality, or improving documentation, your contributions are appreciated.

Before contributing, please read the [Contributing Guidelines](CONTRIBUTING.md) for development setup instructions, coding conventions, testing requirements, and the pull request process.

If you find a bug or have a feature suggestion, feel free to [open an issue](https://github.com/Sibsankar-de/rezen/issues).



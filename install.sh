#!/usr/bin/env bash
# =============================================================================
# Rezen Installer — Remote Device & Screen Control CLI
# Usage: curl -fsSL https://raw.githubusercontent.com/Sibsankar-de/rezen/main/install.sh | bash
# =============================================================================

set -euo pipefail

# ── Colors & formatting ───────────────────────────────────────────────────────
BOLD="\033[1m"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
RESET="\033[0m"

info()    { echo -e "${CYAN}[rezen]${RESET} $*"; }
success() { echo -e "${GREEN}[rezen]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[rezen] WARN:${RESET} $*"; }
error()   { echo -e "${RED}[rezen] ERROR:${RESET} $*" >&2; }
die()     { error "$*"; exit 1; }

# ── Constants ─────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/Sibsankar-de/rezen.git"
INSTALL_DIR="${REZEN_INSTALL_DIR:-$HOME/.local/share/rezen}"
BIN_DIR="${REZEN_BIN_DIR:-$HOME/.local/bin}"
MIN_PYTHON_MINOR=12   # Python >= 3.12

# ── Helpers ───────────────────────────────────────────────────────────────────
command_exists() { command -v "$1" &>/dev/null; }

print_banner() {
  echo -e "${BOLD}"
  echo "  ____                              "
  echo " |  _ \    ___   ____   ___   _ __  "
  echo " | |_) |  / _ \ |_  /  / _ \ | '_ \ "
  echo " |  _ <  |  __/  / /  |  __/ | | | |"
  echo " |_| \_\  \___| /___|  \___| |_| |_|"
  echo -e "${RESET}"
  echo -e "  ${CYAN}Remote Device & Screen Control CLI${RESET}"
  echo
}

# ── OS check ─────────────────────────────────────────────────────────────────
check_os() {
  if [[ "$(uname -s)" != "Linux" ]]; then
    die "Rezen currently supports Linux only. Detected: $(uname -s)"
  fi
  info "Platform: Linux ✓"
}

# ── Dependency checks ─────────────────────────────────────────────────────────
check_python() {
  local python_bin=""

  for bin in python3.12 python3.13 python3.14 python3; do
    if command_exists "$bin"; then
      local ver
      ver="$("$bin" -c 'import sys; print(sys.version_info.minor)')"
      local major
      major="$("$bin" -c 'import sys; print(sys.version_info.major)')"
      if [[ "$major" -eq 3 && "$ver" -ge "$MIN_PYTHON_MINOR" ]]; then
        python_bin="$bin"
        info "Python: $("$bin" --version) ✓"
        break
      fi
    fi
  done

  if [[ -z "$python_bin" ]]; then
    warn "Python 3.12+ not found. Attempting to install via system package manager..."
    install_python
  fi
}

install_python() {
  if command_exists apt-get; then
    info "Installing python3.12 via apt..."
    sudo apt-get update -qq
    sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
  elif command_exists dnf; then
    info "Installing python3.12 via dnf..."
    sudo dnf install -y python3.12
  elif command_exists pacman; then
    info "Installing python via pacman..."
    sudo pacman -Sy --noconfirm python
  else
    die "Could not install Python automatically. Please install Python 3.12+ and re-run the installer."
  fi
}

check_git() {
  if ! command_exists git; then
    warn "git not found. Attempting to install..."
    if command_exists apt-get; then
      sudo apt-get install -y git
    elif command_exists dnf; then
      sudo dnf install -y git
    elif command_exists pacman; then
      sudo pacman -Sy --noconfirm git
    else
      die "git is required. Please install it and re-run the installer."
    fi
  fi
  info "git: $(git --version) ✓"
}

check_uv() {
  if ! command_exists uv; then
    info "uv not found. Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add uv to PATH for the rest of this script
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    if ! command_exists uv; then
      die "uv installation failed. Please install uv manually: https://docs.astral.sh/uv/"
    fi
  fi
  info "uv: $(uv --version) ✓"
}

# ── System packages needed for native deps ─────────────────────────────────
install_system_deps() {
  info "Checking system-level dependencies..."

  local pkgs_apt=()
  local pkgs_dnf=()
  local pkgs_pacman=()

  # OpenCV / libGL
  if ! ldconfig -p 2>/dev/null | grep -q libGL; then
    pkgs_apt+=(libgl1 libgl1-mesa-glx)
    pkgs_dnf+=(mesa-libGL)
    pkgs_pacman+=(mesa)
  fi

  # libglib2 (required by some gi / dbus bindings)
  pkgs_apt+=(libglib2.0-0)
  pkgs_dnf+=(glib2)
  pkgs_pacman+=(glib2)

  # evdev headers (for building evdev wheel if needed)
  pkgs_apt+=(python3-dev libevdev-dev)
  pkgs_dnf+=(libevdev-devel)
  pkgs_pacman+=(libevdev)

  # PipeWire / GStreamer (Wayland screen capture)
  pkgs_apt+=(gstreamer1.0-tools gstreamer1.0-pipewire)
  pkgs_dnf+=(gstreamer1-plugins-base pipewire-gstreamer)
  pkgs_pacman+=(gst-plugins-base pipewire-gst)

  if command_exists apt-get; then
    info "Installing system packages via apt..."
    sudo apt-get install -y "${pkgs_apt[@]}" 2>/dev/null || warn "Some apt packages could not be installed — continuing."
  elif command_exists dnf; then
    info "Installing system packages via dnf..."
    sudo dnf install -y "${pkgs_dnf[@]}" 2>/dev/null || warn "Some dnf packages could not be installed — continuing."
  elif command_exists pacman; then
    info "Installing system packages via pacman..."
    sudo pacman -Sy --noconfirm "${pkgs_pacman[@]}" 2>/dev/null || warn "Some pacman packages could not be installed — continuing."
  else
    warn "Unknown package manager — skipping system dependency installation."
    warn "If rezen fails to start, manually install: libGL, gstreamer + pipewire, libevdev."
  fi
}

# ── Clone or update repo ──────────────────────────────────────────────────────
IS_UPDATE=0

fetch_rezen() {
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    IS_UPDATE=1
    info "Existing installation found at $INSTALL_DIR - updating to latest version..."
    git -C "$INSTALL_DIR" fetch --depth 1 origin main 2>/dev/null && git -C "$INSTALL_DIR" reset --hard origin/main 2>/dev/null || git -C "$INSTALL_DIR" pull --ff-only
  else
    info "Cloning rezen into $INSTALL_DIR..."
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi

  if [[ ! -f "$INSTALL_DIR/.env" && -f "$INSTALL_DIR/.env.example" ]]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    info "Created default .env configuration."
  fi
}

# ── Install Python deps with uv ───────────────────────────────────────────────
install_python_deps() {
  info "Installing Python dependencies (this may take a moment)..."
  cd "$INSTALL_DIR"
  uv sync --no-dev
  success "Python dependencies installed."
}

# ── Create the rezen launcher script ─────────────────────────────────────────
install_launcher() {
  mkdir -p "$BIN_DIR"

  cat > "$BIN_DIR/rezen" <<EOF
#!/usr/bin/env bash
# Rezen launcher - auto-generated by install.sh

# Seamlessly activate 'input' group if configured in /etc/group but not yet active in current session
if command -v sg >/dev/null 2>&1 && ! id -Gn 2>/dev/null | grep -qw input && id -Gn "\${USER:-\$(id -un)}" 2>/dev/null | grep -qw input; then
  cmd=\$(printf '%q ' uv run --project "$INSTALL_DIR" python "$INSTALL_DIR/src/main.py" "\$@")
  exec sg input -c "\$cmd"
fi

exec uv run --project "$INSTALL_DIR" python "$INSTALL_DIR/src/main.py" "\$@"
EOF

  chmod +x "$BIN_DIR/rezen"
  success "Launcher installed at $BIN_DIR/rezen"
}

# ── Shell PATH setup ──────────────────────────────────────────────────────────
configure_shell() {
  if [[ ":$PATH:" == *":$BIN_DIR:"* ]]; then
    return
  fi

  local shell_rc=""
  case "$SHELL" in
    */zsh)  shell_rc="$HOME/.zshrc" ;;
    */fish) shell_rc="$HOME/.config/fish/config.fish" ;;
    *)      shell_rc="$HOME/.bashrc" ;;
  esac

  local export_line='export PATH="$HOME/.local/bin:$PATH"'
  if [[ "$SHELL" == */fish ]]; then
    export_line='fish_add_path $HOME/.local/bin'
  fi

  if ! grep -qF "$BIN_DIR" "$shell_rc" 2>/dev/null; then
    echo "" >> "$shell_rc"
    echo "# Added by rezen installer" >> "$shell_rc"
    echo "$export_line" >> "$shell_rc"
    warn "$BIN_DIR added to PATH in $shell_rc"
    warn "Run: source $shell_rc   (or open a new terminal) to use 'rezen' immediately."
  fi
}

# ── Wayland & evdev input permissions ─────────────────────────────────────────
configure_wayland_input() {
  local current_user="${SUDO_USER:-$(id -un)}"

  info "Configuring Wayland & evdev keyboard/mouse permissions..."

  # Ensure 'input' group exists
  if ! getent group input >/dev/null 2>&1; then
    if [[ "$EUID" -eq 0 ]]; then
      groupadd -r input 2>/dev/null || groupadd input 2>/dev/null || true
    else
      sudo groupadd -r input 2>/dev/null || sudo groupadd input 2>/dev/null || true
    fi
  fi

  # Add user to 'input' group for /dev/input/event* capture
  if ! id -Gn "$current_user" 2>/dev/null | grep -qw input; then
    info "Adding '$current_user' to 'input' group (sudo usermod -aG input $current_user)..."
    if [[ "$EUID" -eq 0 ]]; then
      usermod -aG input "$current_user"
    else
      sudo usermod -aG input "$current_user"
    fi
    success "Added '$current_user' to 'input' group ✓"
    warn "To enable global Wayland keyboard & mouse capture via evdev immediately, run:"
    warn "    newgrp input"
    warn "or log out and log back in to apply group membership across all sessions."
  else
    info "Input group membership: '$current_user' is already in 'input' group ✓"
  fi

  # Attempt to load uinput kernel module for evdev injection
  if [[ ! -e /dev/uinput ]] && command_exists modprobe; then
    if [[ "$EUID" -eq 0 ]]; then
      modprobe uinput 2>/dev/null || true
    else
      sudo modprobe uinput 2>/dev/null || true
    fi
  fi

  # Ensure uinput module loads on boot
  if [[ -d /etc/modules-load.d ]]; then
    if [[ "$EUID" -eq 0 ]]; then
      echo "uinput" > /etc/modules-load.d/uinput.conf 2>/dev/null || true
    else
      echo "uinput" | sudo tee /etc/modules-load.d/uinput.conf >/dev/null 2>&1 || true
    fi
  fi

  # Configure udev rules for /dev/uinput and /dev/input/event*
  local udev_dir="/etc/udev/rules.d"
  if [[ -d "$udev_dir" || -d "/etc/udev" ]]; then
    if [[ "$EUID" -eq 0 ]]; then
      mkdir -p "$udev_dir" 2>/dev/null || true
      echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' > "$udev_dir/99-uinput.rules" 2>/dev/null || true
      echo 'SUBSYSTEM=="input", KERNEL=="event*", GROUP="input", MODE="0660"' > "$udev_dir/99-input.rules" 2>/dev/null || true
    else
      sudo mkdir -p "$udev_dir" 2>/dev/null || true
      echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee "$udev_dir/99-uinput.rules" >/dev/null 2>&1 || true
      echo 'SUBSYSTEM=="input", KERNEL=="event*", GROUP="input", MODE="0660"' | sudo tee "$udev_dir/99-input.rules" >/dev/null 2>&1 || true
    fi

    if command_exists udevadm; then
      if [[ "$EUID" -eq 0 ]]; then
        udevadm control --reload-rules 2>/dev/null || true
        udevadm trigger 2>/dev/null || true
      else
        sudo udevadm control --reload-rules 2>/dev/null || true
        sudo udevadm trigger 2>/dev/null || true
      fi
    fi
  fi
}

# ── Verify installation ───────────────────────────────────────────────────────
verify() {
  if "$BIN_DIR/rezen" --help &>/dev/null; then
    success "Verification passed — rezen is ready!"
  else
    warn "Could not verify installation automatically. Try running: rezen --help"
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════
main() {
  print_banner
  info "Starting Rezen installation..."
  echo

  check_os
  check_git
  check_python
  check_uv
  install_system_deps
  fetch_rezen
  install_python_deps
  install_launcher
  configure_shell
  configure_wayland_input
  verify

  echo
  if [[ "$IS_UPDATE" -eq 1 ]]; then
    success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    success "  Rezen updated successfully! 🎉"
    success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  else
    success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    success "  Rezen installed successfully! 🎉"
    success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  fi
  echo
  info "Run it with:  ${BOLD}rezen${RESET}"
  info "If 'rezen' is not found, reload your shell:"
  info "  ${BOLD}source ~/.bashrc${RESET}  (or open a new terminal)"
  if ! id -Gn 2>/dev/null | grep -qw input; then
    echo
    warn "evdev Wayland capture requires group 'input'."
    warn "If you run outside the launcher without logging out, run:  ${BOLD}newgrp input${RESET}"
  fi
  echo
}

main "$@"

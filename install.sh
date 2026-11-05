#!/usr/bin/env bash
set -euo pipefail

# Colors for messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${YELLOW}=== Whispy Setup (Parakeet TDT 0.6b v3) ===${NC}"
echo ""

# Check for python3
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Error: python3 is not installed. Please install it and rerun this script.${NC}"
    exit 1
fi

# Audio capture uses sounddevice/PortAudio (a Python dependency installed
# below) — no sox or other system audio package is required.

OS="$(uname -s)"

# Uninstall option
if [[ "${1:-}" == "--uninstall" ]]; then
    VENV_DIR="$SCRIPT_DIR/.venv"
    if [ "$OS" = "Linux" ]; then
        echo -e "${YELLOW}Removing systemd user service and .venv directory...${NC}"
        if command -v systemctl &>/dev/null; then
            systemctl --user disable --now whispy.service 2>/dev/null || true
        fi
        rm -f "$HOME/.config/systemd/user/whispy.service"
        rm -f "$HOME/.local/bin/whispy" "$HOME/.local/bin/omarchy-dictation-whispy"
        rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/whispy-panel"
        command -v systemctl &>/dev/null && systemctl --user daemon-reload 2>/dev/null || true
    else
        # Remove any legacy LaunchAgents (the macOS install no longer creates
        # one). Two pre-rebrand ids exist: com.whisper-dictation (oldest,
        # "Whisper Dictation") and com.whispy (intermediate). bootout is the
        # modern unload; fall back to unload. Both ids listed in one place.
        echo -e "${YELLOW}Removing any legacy LaunchAgents and .venv directory...${NC}"
        for id in com.whisper-dictation com.whispy; do
            PLIST_PATH="$HOME/Library/LaunchAgents/$id.plist"
            launchctl bootout "gui/$(id -u)/$id" 2>/dev/null || true
            launchctl unload "$PLIST_PATH" 2>/dev/null || true
            rm -f "$PLIST_PATH"
        done
        # The login-item registration lives with the .app bundle (SMAppService),
        # so it clears when the app is removed. Toggle it off in-app first if the
        # app is still installed, then delete the bundle:
        echo "If installed, remove the app: rm -rf /Applications/Whispy.app"
        echo "(turn off \"Start at login\" in the menu first to drop the login item)"
    fi
    rm -rf "$VENV_DIR"

    # -------------------------------------------------------------------
    # User data (config incl. API token, logs, downloaded model) is kept by
    # default -- a reinstall would otherwise re-download the model (639 MB).
    # Only offer to remove it when there's an actual person at the prompt (a
    # TTY); non-interactive runs (e.g. bootstrap.sh piped via `curl | bash`)
    # always keep the data instead of blocking.
    # -------------------------------------------------------------------
    CONFIG_DIR="$HOME/.config/whispy"
    # The model is cached in the HuggingFace hub cache, which is SHARED with
    # any other tool that uses huggingface_hub -- never delete the whole hub
    # directory, only Whispy's own snapshot inside it.
    MODEL_CACHE_GLOB="$HOME/.cache/huggingface/hub/models--istupakov--parakeet-tdt-0.6b-v3-onnx"
    # Installs upgraded from the Whisper era leave these behind. They are no
    # longer used, but deleting another era's data on the user's behalf is not
    # this script's call -- point at them instead.
    STALE_WHISPER_GLOB="$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-*"

    REMOVE_DATA="n"
    if [ -t 0 ]; then
        read -r -p "Also remove config ($CONFIG_DIR, includes the API token), logs, and the downloaded model cache? [y/N] " REMOVE_DATA || true
    fi
    if [[ "$REMOVE_DATA" =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        rm -f "$HOME"/.whispy.log "$HOME"/.whispy.log.* "$HOME"/.whispy-error.log "$HOME"/.whispy-error.log.*
        rm -rf $MODEL_CACHE_GLOB
        echo -e "${GREEN}Removed config, logs, and the model cache.${NC}"
    else
        echo -e "${YELLOW}Keeping config, logs, and the model cache (rerun ./install.sh --uninstall to remove them later).${NC}"
    fi

    # shellcheck disable=SC2086
    if compgen -G "$STALE_WHISPER_GLOB" > /dev/null 2>&1; then
        echo -e "${YELLOW}Note: a faster-whisper model cache from an older Whispy is still present and no longer used:${NC}"
        # shellcheck disable=SC2086
        du -sh $STALE_WHISPER_GLOB 2>/dev/null || true
        echo -e "${YELLOW}Delete it manually if you want the space back.${NC}"
    fi

    echo -e "${GREEN}Uninstallation complete.${NC}"
    exit 0
fi

VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
fi

# Install (or update) dependencies. Editable install pulls the runtime deps
# declared in pyproject.toml. Pillow is only needed at build time (make app)
# and is installed there. Skip full resolution when pyproject.toml is unchanged.
DEPS_HASH_FILE="$VENV_DIR/.deps-hash"
# sha256sum on Linux, shasum on macOS -- neither is on both. Under `set -e`
# a missing binary aborts the install before any dependency is installed.
if command -v sha256sum &>/dev/null; then
    CURRENT_HASH=$(sha256sum "$SCRIPT_DIR/pyproject.toml" | cut -d' ' -f1)
else
    CURRENT_HASH=$(shasum -a 256 "$SCRIPT_DIR/pyproject.toml" | cut -d' ' -f1)
fi
if [ -f "$DEPS_HASH_FILE" ] && [ "$(cat "$DEPS_HASH_FILE")" = "$CURRENT_HASH" ]; then
    echo -e "${YELLOW}Dependencies unchanged, refreshing editable link...${NC}"
    "$VENV_DIR/bin/pip" install --no-deps -e "$SCRIPT_DIR" -q
else
    echo -e "${YELLOW}Installing dependencies...${NC}"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -e "$SCRIPT_DIR"
    echo "$CURRENT_HASH" > "$DEPS_HASH_FILE"
fi
echo -e "${GREEN}[OK] Dependencies installed${NC}"


PYTHON_BIN="$VENV_DIR/bin/python3"
DAEMON_PATH="$SCRIPT_DIR/whispy_daemon.py"

if [ "$OS" = "Linux" ]; then
    echo ""
    echo -e "${YELLOW}=== Linux environment check ===${NC}"

    # The session decides the toolset. X11: Whispy grabs the trigger key itself
    # and types with xdotool. Wayland: the compositor's key binding drives the
    # API (/start, /stop) and Whispy types with wtype.
    SESSION="x11"
    if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
        SESSION="wayland"
        echo -e "${GREEN}[OK] Wayland session: the trigger is your compositor's key binding${NC}"
        echo "    It calls the API (POST /start on press, POST /stop on release)."
        echo "    Omarchy: the F9 binding works once you run: omarchy-dictation-use whispy"
        echo ""
    elif [ -z "${DISPLAY:-}" ]; then
        echo -e "${YELLOW}[!] No DISPLAY set — this looks like a text-only session.${NC}"
        echo "    Whispy needs a running X11 or Wayland desktop to type the transcript."
        echo ""
    fi

    # Report what is missing by name. The daemon degrades silently without
    # these: no typing tool means dictation transcribes and types nothing.
    MISSING=""
    if [ "$SESSION" = "wayland" ]; then
        command -v wtype &>/dev/null || MISSING="$MISSING wtype"
        command -v wl-copy &>/dev/null || MISSING="$MISSING wl-clipboard"
    else
        command -v xdotool &>/dev/null || MISSING="$MISSING xdotool"
        { command -v xclip &>/dev/null || command -v xsel &>/dev/null; } || MISSING="$MISSING xclip"
    fi
    "$PYTHON_BIN" -c "import sounddevice" &>/dev/null || MISSING="$MISSING libportaudio2"

    if [ -n "$MISSING" ]; then
        echo -e "${RED}[!] Missing system packages:${NC}$MISSING"
        echo "    xdotool / wtype          types the transcript into the focused window (X11 / Wayland, required)"
        echo "    xclip, xsel / wl-clipboard  clipboard delivery mode, the default (required)"
        echo "    libportaudio2            audio capture (required)"
        echo ""
        echo "    Debian/Ubuntu: sudo apt install xdotool xclip libportaudio2   (Wayland: wtype wl-clipboard)"
        echo "    Fedora:        sudo dnf install xdotool xclip portaudio       (Wayland: wtype wl-clipboard)"
        echo "    Arch:          sudo pacman -S xdotool xclip portaudio         (Wayland: wtype wl-clipboard)"
        echo ""
        echo -e "${YELLOW}    Install these, then rerun this script.${NC}"
    else
        echo -e "${GREEN}[OK] Typing tool, clipboard tool and PortAudio present${NC}"
    fi

    # A `whispy` command on PATH (`whispy --doctor`, or the daemon in the
    # foreground). Omarchy also requires it: its dictation keys are bound only
    # when the selected backend's own program -- named like the backend -- is
    # installed, so without it F9 stays unbound after the next login.
    mkdir -p "$HOME/.local/bin"
    cat > "$HOME/.local/bin/whispy" << WHISPYEOF
#!/bin/sh
exec "$PYTHON_BIN" "$DAEMON_PATH" "\$@"
WHISPYEOF
    chmod +x "$HOME/.local/bin/whispy"
    echo -e "${GREEN}[OK] whispy command installed: ~/.local/bin/whispy (try: whispy --doctor)${NC}"

    # Omarchy picks its dictation backend by name: `omarchy-dictation` runs the
    # executable `omarchy-dictation-<backend>` found on PATH. A symlink keeps
    # the adapter current with this checkout.
    if command -v omarchy-dictation &>/dev/null; then
        ln -sf "$SCRIPT_DIR/packaging/omarchy/omarchy-dictation-whispy" "$HOME/.local/bin/omarchy-dictation-whispy"
        echo -e "${GREEN}[OK] Omarchy dictation backend linked: ~/.local/bin/omarchy-dictation-whispy${NC}"
        echo "    Select it (stops the previous backend), then reload Hyprland to bind F9:"
        echo "      omarchy-dictation-use whispy && hyprctl reload"

        # The bar widget: status icon, settings panel, dictation key picker
        # and the recording pill. A symlink, like the backend, so it follows
        # this checkout; the shell picks it up without a restart.
        PLUGIN_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins"
        if [ -d "$(dirname "$PLUGIN_DIR")" ]; then
            mkdir -p "$PLUGIN_DIR"
            ln -sfn "$SCRIPT_DIR/packaging/omarchy/whispy-panel" "$PLUGIN_DIR/whispy-panel"
            if command -v omarchy-bar &>/dev/null && ! grep -q '"whispy.panel"' "$(dirname "$PLUGIN_DIR")/shell.json" 2>/dev/null; then
                omarchy-bar put whispy.panel --section right --index 1 >/dev/null 2>&1 || true
            fi
            echo -e "${GREEN}[OK] Omarchy bar widget linked: $PLUGIN_DIR/whispy-panel (pick the dictation key there)${NC}"
            # The dictation key file Omarchy loads while Whispy is the backend,
            # for the saved preset; rewritten so a reinstall restores it.
            KEY=$("$SCRIPT_DIR/packaging/omarchy/omarchy-dictation-whispy" shortcuts) \
                && echo -e "${GREEN}[OK] Dictation key ($KEY) written to ~/.config/whispy/shortcuts.lua; apply with: hyprctl reload${NC}"
        fi
    fi
    echo ""
fi

# -------------------------------------------------------------------------
# Linux (X11 or Wayland): install a systemd --user service. macOS: no LaunchAgent below
# — see the SMAppService-based autostart note further down.
# -------------------------------------------------------------------------
if [ "$OS" = "Linux" ]; then
    if ! command -v systemctl &>/dev/null; then
        echo -e "${YELLOW}systemd not found. Start Whispy manually from your desktop session:${NC}"
        echo "  $PYTHON_BIN $DAEMON_PATH"
        echo ""
        echo "The model downloads automatically on first run (~639 MB)"
        exit 0
    fi
    UNIT_DIR="$HOME/.config/systemd/user"
    UNIT_PATH="$UNIT_DIR/whispy.service"
    mkdir -p "$UNIT_DIR"
    # A session that activates graphical-session.target (Hyprland under uwsm,
    # GNOME, KDE) imports WAYLAND_DISPLAY/DISPLAY into the user manager when it
    # does; binding the unit to that target starts Whispy only once they are
    # there, after every login. Other sessions never activate the target, so
    # the unit would never start there: they keep default.target.
    START_TARGET="default.target"
    if systemctl --user is-active --quiet graphical-session.target 2>/dev/null; then
        START_TARGET="graphical-session.target"
    fi
    cat > "$UNIT_PATH" << UNITEOF
[Unit]
Description=Whispy voice dictation daemon
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$PYTHON_BIN $DAEMON_PATH
WorkingDirectory=$SCRIPT_DIR
Restart=on-failure
# Inherit the session's display variables rather than guessing them.
PassEnvironment=DISPLAY XAUTHORITY WAYLAND_DISPLAY XDG_SESSION_TYPE
# Keep the user's own bin directories: xdotool and xclip are not always in /usr/bin.
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=$START_TARGET
UNITEOF
    echo -e "${GREEN}[OK] systemd user unit installed at $UNIT_PATH${NC}"
    # Unguarded, these abort the script under `set -e` on any machine with no
    # systemd user bus (SSH without lingering, containers, WSL) -- skipping the
    # package and X11 notes below, which are the part the user actually needs.
    if systemctl --user daemon-reload 2>/dev/null; then
        # Re-enable so a unit moved to another target drops its old symlink.
        systemctl --user disable whispy.service 2>/dev/null || true
        systemctl --user enable --now whispy.service || {
            echo -e "${YELLOW}Could not enable the service automatically. Start it with:${NC}"
            echo "  systemctl --user enable --now whispy.service"
        }
    else
        echo -e "${YELLOW}No systemd user session here. Enable it from a graphical login with:${NC}"
        echo "  systemctl --user enable --now whispy.service"
        echo "Or run it in the foreground: $PYTHON_BIN $DAEMON_PATH"
    fi
    echo ""
    echo -e "${YELLOW}=== Linux notes ===${NC}"
    echo "X11: Whispy listens to the trigger key itself and types with xdotool + xclip."
    echo "Wayland: your compositor's key binding calls /start and /stop; Whispy types"
    echo "with wtype + wl-clipboard (Omarchy: omarchy-dictation-use whispy, then F9)."
    echo "PortAudio is needed for audio capture on both:"
    echo "  Debian/Ubuntu: sudo apt install xdotool xclip libportaudio2   (Wayland: wtype wl-clipboard)"
    echo "  Fedora:        sudo dnf install xdotool xclip portaudio       (Wayland: wtype wl-clipboard)"
    echo ""
    echo "The model downloads automatically on first run (~639 MB)"
    echo "Logs: journalctl --user -u whispy -f"
    echo "Test: curl -H \"Authorization: Bearer \$(cat ~/.config/whispy/config.token)\" http://localhost:9090/status"
    echo ""
    echo -e "${YELLOW}To uninstall:${NC}"
    echo "./install.sh --uninstall"
    exit 0
fi

# -------------------------------------------------------------------------
# macOS: venv only. The supported macOS install is the signed Whispy.app
# bundle (stable "Whispy" TCC identity that survives Python upgrades), and
# autostart is the in-app "Start at login" toggle (SMAppService) — NOT a
# LaunchAgent. This script only provisions the build prerequisites; `make app`
# turns the venv into dist/Whispy.app. (Linux still gets a systemd unit above,
# since it has no .app/SMAppService equivalent.)
# -------------------------------------------------------------------------
echo -e "${GREEN}[OK] venv ready.${NC}"
echo ""
echo -e "${YELLOW}Next: build and install the app${NC}"
echo "  make app                          # builds & signs dist/Whispy.app"
echo "  cp -R dist/Whispy.app /Applications/"
echo "  open /Applications/Whispy.app"
echo ""
echo "The model downloads automatically on first run (~639 MB)."
echo "Grant the Whispy microphone prompt on first launch; enable autostart with"
echo "the in-app \"Start at login\" toggle."
echo ""
echo -e "${YELLOW}To uninstall:${NC}"
echo "./install.sh --uninstall"

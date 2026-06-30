#!/usr/bin/env bash
set -euo pipefail

# Colors for messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WHISPER_MODEL_NAME="${WHISPER_MODEL:-small}"

echo -e "${YELLOW}=== Whispy Setup (faster-whisper) ===${NC}"
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
    echo -e "${GREEN}Uninstallation complete.${NC}"
    exit 0
fi

VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
fi

# Install (or update) dependencies. Editable install pulls the runtime deps
# declared in pyproject.toml (faster-whisper, pyobjc-framework-Quartz, rumps,
# sounddevice); Pillow is needed by generate_icons.py. Idempotent, so rerunning
# the script after a code update picks up any new dependencies.
echo -e "${YELLOW}Installing dependencies...${NC}"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -e "$SCRIPT_DIR" Pillow
echo -e "${GREEN}[OK] Dependencies installed (whispy + Pillow)${NC}"

if [ ! -d "$SCRIPT_DIR/icons" ] || [ ! -f "$SCRIPT_DIR/icons/whispy.png" ]; then
    echo -e "${YELLOW}Generating menu bar icons...${NC}"
    "$VENV_DIR/bin/python" "$SCRIPT_DIR/generate_icons.py"
    echo -e "${GREEN}[OK] Icons generated${NC}"
else
    echo -e "${GREEN}[OK] Icons already exist${NC}"
fi

# Persist the chosen model into the config so the daemon actually uses it.
# The daemon runs detached (LaunchAgent/systemd) and does NOT inherit this
# shell's WHISPER_MODEL env, so honoring it means writing it to config.json.
# Only write when explicitly set, to avoid clobbering a user's chosen model
# with the default on every reinstall.
if [ -n "${WHISPER_MODEL:-}" ]; then
    "$VENV_DIR/bin/python" - "$WHISPER_MODEL_NAME" << 'PYEOF'
import json, sys
from pathlib import Path

model = sys.argv[1]
cfg_path = Path.home() / ".config" / "whispy" / "config.json"
cfg_path.parent.mkdir(parents=True, exist_ok=True)
cfg = {}
if cfg_path.exists():
    try:
        cfg = json.loads(cfg_path.read_text())
    except Exception:
        cfg = {}
cfg["model_size"] = model
cfg_path.write_text(json.dumps(cfg, indent=2))
print(f"[OK] model_size set to '{model}' in {cfg_path}")
PYEOF
fi


PYTHON_BIN="$VENV_DIR/bin/python3"
DAEMON_PATH="$SCRIPT_DIR/whispy_daemon.py"

# -------------------------------------------------------------------------
# Linux (X11): install a systemd --user service. macOS: a LaunchAgent below.
# -------------------------------------------------------------------------
if [ "$OS" = "Linux" ]; then
    if ! command -v systemctl &>/dev/null; then
        echo -e "${YELLOW}systemd not found. Start Whispy manually (X11 session):${NC}"
        echo "  $PYTHON_BIN $DAEMON_PATH"
        echo ""
        echo "The model downloads automatically on first run (model: $WHISPER_MODEL_NAME)"
        exit 0
    fi
    UNIT_DIR="$HOME/.config/systemd/user"
    UNIT_PATH="$UNIT_DIR/whispy.service"
    mkdir -p "$UNIT_DIR"
    cat > "$UNIT_PATH" << UNITEOF
[Unit]
Description=Whispy voice dictation daemon
After=graphical-session.target

[Service]
Type=simple
ExecStart=$PYTHON_BIN $DAEMON_PATH
WorkingDirectory=$SCRIPT_DIR
Restart=on-failure
Environment=PATH=/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
UNITEOF
    echo -e "${GREEN}[OK] systemd user unit installed at $UNIT_PATH${NC}"
    systemctl --user daemon-reload
    systemctl --user enable --now whispy.service || {
        echo -e "${YELLOW}Could not enable the service automatically. Start it with:${NC}"
        echo "  systemctl --user enable --now whispy.service"
    }
    echo ""
    echo -e "${YELLOW}=== Linux notes ===${NC}"
    echo "Whispy v1 requires an X11 session (global hotkeys/text injection do not"
    echo "work under Wayland). Install xdotool + xclip for text injection:"
    echo "  Debian/Ubuntu: sudo apt install xdotool xclip"
    echo "  Fedora:        sudo dnf install xdotool xclip"
    echo ""
    echo "The model downloads automatically on first run (model: $WHISPER_MODEL_NAME)"
    echo "Logs: journalctl --user -u whispy -f"
    echo "Test: curl http://localhost:9090/status"
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
echo "The model downloads automatically on first run (model: $WHISPER_MODEL_NAME)."
echo "Grant the Whispy microphone prompt on first launch; enable autostart with"
echo "the in-app \"Start at login\" toggle."
echo ""
echo -e "${YELLOW}To uninstall:${NC}"
echo "./install.sh --uninstall"

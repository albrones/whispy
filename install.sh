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
        echo -e "${YELLOW}Removing LaunchAgent and .venv directory...${NC}"
        PLIST_PATH="$HOME/Library/LaunchAgents/com.whispy.plist"
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
        rm -f "$PLIST_PATH"
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
# macOS: LaunchAgent
# -------------------------------------------------------------------------
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
LAUNCH_AGENT_NAME="com.whispy"
PLIST_PATH="$LAUNCH_AGENT_DIR/$LAUNCH_AGENT_NAME.plist"

mkdir -p "$LAUNCH_AGENT_DIR"

cat > "$PLIST_PATH" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LAUNCH_AGENT_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_BIN</string>
        <string>$DAEMON_PATH</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>$HOME/.whispy.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.whispy-error.log</string>
</dict>
</plist>
PLISTEOF

echo -e "${GREEN}[OK] LaunchAgent installed at $PLIST_PATH${NC}"

echo ""
echo -e "${YELLOW}=== Required Permissions ===${NC}"
echo ""
echo "1. Microphone:        System Settings -> Privacy & Security -> Microphone -> enable iTerm2/Terminal"
echo "2. Accessibility:     System Settings -> Privacy & Security -> Accessibility -> enable python"
echo "                      python path: $PYTHON_BIN"
echo "3. Input Monitoring:  System Settings -> Privacy & Security -> Input Monitoring -> enable python3"
echo "                      python path: $PYTHON_BIN"
echo ""

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo -e "${GREEN}[OK] LaunchAgent loaded. Daemon starting...${NC}"
echo ""
echo "The model will be downloaded automatically on first run (model: $WHISPER_MODEL_NAME)"
echo ""
echo "Logs: tail -f ~/.whispy.log ~/.whispy-error.log"
echo "Test: curl http://localhost:9090/status"
echo ""
echo -e "${YELLOW}To uninstall:${NC}"
echo "./install.sh --uninstall"

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

# Check for sox
if ! command -v sox &>/dev/null; then
    echo -e "${YELLOW}Warning: sox is not installed. Audio recording requires sox.${NC}"
    echo -e "${YELLOW}Install it with: brew install sox${NC}"
    echo -e "${YELLOW}Rerun this script after installing sox.${NC}"
    exit 1
fi

# Uninstall option
if [[ "${1:-}" == "--uninstall" ]]; then
    echo -e "${YELLOW}Removing LaunchAgent and .venv directory...${NC}"
    LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
    LAUNCH_AGENT_NAME="com.whispy"
    PLIST_PATH="$LAUNCH_AGENT_DIR/$LAUNCH_AGENT_NAME.plist"
    VENV_DIR="$SCRIPT_DIR/.venv"
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
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





LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
LAUNCH_AGENT_NAME="com.whispy"
PLIST_PATH="$LAUNCH_AGENT_DIR/$LAUNCH_AGENT_NAME.plist"

PYTHON_BIN="$VENV_DIR/bin/python3"

mkdir -p "$LAUNCH_AGENT_DIR"

DAEMON_PATH="$SCRIPT_DIR/whispy_daemon.py"

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

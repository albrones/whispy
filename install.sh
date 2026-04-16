#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KARABINER_DIR="$HOME/.config/karabiner/assets/complex_modifications"

WHISPER_MODEL_NAME="${WHISPER_MODEL:-small}"

echo "=== Wispy Setup (faster-whisper) ==="
echo ""

VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install faster-whisper pyobjc-framework-Quartz rumps Pillow
    echo "[OK] Virtual environment created with faster-whisper + pyobjc-framework-Quartz + rumps + Pillow"
else
    echo "[OK] Virtual environment already exists"
fi

if [ ! -d "$SCRIPT_DIR/icons" ] || [ ! -f "$SCRIPT_DIR/icons/mic-idle.png" ]; then
    echo "Generating menu bar icons..."
    "$VENV_DIR/bin/python" "$SCRIPT_DIR/generate_icons.py"
    echo "[OK] Icons generated"
else
    echo "[OK] Icons already exist"
fi

KARABINER_ENABLED=false
if command -v karabiner_cli &>/dev/null; then
    KARABINER_ENABLED=true
    echo "[OK] Karabiner-Elements found (optionnel — détection Fn native intégrée au daemon)"
else
    echo "[skip] Karabiner-Elements absent — détection Fn native via CGEventTap"
fi

if [ "$KARABINER_ENABLED" = "true" ]; then
    mkdir -p "$KARABINER_DIR"
    cat > "$KARABINER_DIR/whisper-dictation.json" << 'KARABINER'
{
    "title": "Wispy (Fn key push-to-talk)",
    "rules": [
        {
            "description": "Hold Fn to record, release to transcribe (Wispy)",
            "manipulators": [
                {
                    "type": "basic",
                    "from": {
                        "key_code": "fn"
                    },
                    "to": [
                        {
                            "shell_command": "curl -s -X POST http://localhost:9090/start >/dev/null 2>&1"
                        }
                    ],
                    "to_after_key_up": [
                        {
                            "shell_command": "curl -s -X POST http://localhost:9090/stop >/dev/null 2>&1"
                        }
                    ]
                }
            ]
        }
    ]
}
KARABINER
    echo "[OK] Karabiner config installed (optionnel, non requis)"
fi

LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
LAUNCH_AGENT_NAME="com.whisper-dictation"
PLIST_PATH="$LAUNCH_AGENT_DIR/$LAUNCH_AGENT_NAME.plist"

PYTHON_BIN="$VENV_DIR/bin/python3"

mkdir -p "$LAUNCH_AGENT_DIR"

DAEMON_PATH="$SCRIPT_DIR/whisper-dictation.py"

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
    <string>$HOME/.whisper-dictation.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.whisper-dictation-error.log</string>
</dict>
</plist>
PLISTEOF

echo "[OK] LaunchAgent installed at $PLIST_PATH"

echo ""
echo "=== Required Permissions ==="
echo ""
echo "1. Microphone:        System Settings -> Privacy & Security -> Microphone -> enable iTerm2/Terminal"
echo "2. Accessibility:     System Settings -> Privacy & Security -> Accessibility -> enable python"
echo "                      python path: $PYTHON_BIN"
echo "3. Input Monitoring:  System Settings -> Privacy & Security -> Input Monitoring -> enable python3"
echo "                      python path: $PYTHON_BIN"
echo ""

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "[OK] LaunchAgent loaded. Daemon starting..."
echo ""
echo "Model will be downloaded automatically on first run (model: $WHISPER_MODEL_NAME)"
echo "NOTE: Karabiner-Elements n'est plus requis. Le daemon écoute la touche Fn nativement."
echo ""
echo "Logs: tail -f ~/.whisper-dictation.log ~/.whisper-dictation-error.log"
echo "Test: curl http://localhost:9090/status"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS_DIR="$(dirname "$SCRIPT_DIR")"
KARABINER_DIR="$HOME/.config/karabiner/assets/complex_modifications"

echo "=== Whisper Dictation Setup ==="

if ! command -v karabiner_cli &>/dev/null; then
    echo "Karabiner-Elements not found."
    echo "Install it from https://karabiner-elements.pqrs.org/ and re-run this script."
    exit 1
fi
echo "[OK] Karabiner-Elements found"

MODEL_PATH="$TOOLS_DIR/whisper.cpp/models/ggml-small.bin"
if [ ! -f "$MODEL_PATH" ]; then
    echo "Downloading whisper small model..."
    (cd "$TOOLS_DIR/whisper.cpp/models" && bash download-ggml-model.sh small)
else
    echo "[OK] Whisper model found ($MODEL_PATH)"
fi

mkdir -p "$KARABINER_DIR"
cat > "$KARABINER_DIR/whisper-dictation.json" << 'KARABINER'
{
    "title": "Whisper Dictation (Fn key push-to-talk)",
    "rules": [
        {
            "description": "Hold Fn to record, release to transcribe (Whisper Dictation)",
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
echo "[OK] Karabiner config installed"

echo ""
echo "To enable the Fn dictation rule:"
echo "  1. Open Karabiner-Elements Settings"
echo "  2. Go to Complex Modifications -> Add rule"
echo "  3. Enable 'Hold Fn to record, release to transcribe'"
echo ""

LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
LAUNCH_AGENT_NAME="com.whisper-dictation"
PLIST_PATH="$LAUNCH_AGENT_DIR/$LAUNCH_AGENT_NAME.plist"

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
        <string>/opt/homebrew/bin/python3</string>
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
echo "1. Microphone: System Settings -> Privacy & Security -> Microphone -> enable Terminal/iTerm2"
echo "2. Accessibility: System Settings -> Privacy & Security -> Accessibility -> enable Terminal/iTerm2"
echo "   (needed for osascript to simulate keystrokes)"
echo "3. Input Monitoring: System Settings -> Privacy & Security -> Input Monitoring -> enable Karabiner-Elements"
echo ""

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "[OK] LaunchAgent loaded. Daemon starting..."
echo ""
echo "Logs: tail -f ~/.whisper-dictation.log"
echo "Test: curl http://localhost:9090/status"

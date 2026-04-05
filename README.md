# Whisper Dictation

Push-to-talk speech-to-text for macOS. Hold the Fn key, speak, release — your words are typed at the cursor.

## Requirements

- macOS
- [Karabiner-Elements](https://karabiner-elements.pqrs.org/)
- sox (`brew install sox`)
- Python 3
- whisper.cpp compiled in `../whisper.cpp/`

## Setup

```bash
# 1. Install dependencies
brew install sox

# 2. Install Karabiner-Elements from https://karabiner-elements.pqrs.org/

# 3. Run the install script
./install.sh

# 4. Grant permissions
# - Microphone: System Settings -> Privacy & Security -> Microphone -> enable iTerm2/Terminal
# - Accessibility: System Settings -> Privacy & Security -> Accessibility -> enable iTerm2/Terminal
# - Input Monitoring: enable Karabiner-Elements

# 5. Enable the Karabiner rule
# Open Karabiner-Elements Settings -> Complex Modifications -> Add rule
# Enable "Hold Fn to record, release to transcribe"
```

## Usage

1. Hold **Fn** — you'll hear a "Tink" sound, recording starts
2. Speak your command
3. Release **Fn** — you'll hear a "Pop" sound, text is transcribed and typed at cursor

## Manual control

```bash
# Check daemon status
curl http://localhost:9090/status

# Start/stop recording manually
curl -X POST http://localhost:9090/start
curl -X POST http://localhost:9090/stop

# Start daemon manually
python3 whisper-dictation.py

# View logs
tail -f ~/.whisper-dictation.log
```

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.whisper-dictation.plist
rm ~/Library/LaunchAgents/com.whisper-dictation.plist
rm ~/.config/karabiner/assets/complex_modifications/whisper-dictation.json
```

## Configuration

Edit the top of `whisper-dictation.py` to change:
- `PORT` — HTTP port (default: 9090)
- `WHISPER_MODEL` — model path (default: `ggml-base.bin`)
- Language is hardcoded to French (`-l fr`). Change in the `transcribe()` function.

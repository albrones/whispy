# Whispy (Voice Dictation for macOS)

## 🤖 AI Description / Overview

**Whispy is a powerful, local voice dictation utility for macOS.** It uses the `faster-whisper` model to provide real-time, offline transcription of speech input. The application runs as a background daemon (`LaunchAgent`), allowing users to initiate recording by holding the `Fn` key and automatically transcribing and inserting text into any active field (e.g., iTerm, web browser, or editor) upon release. Because all processing is done locally on your machine, **zero data leaves your computer**, ensuring complete privacy.

## 📘 Project Description (User Guide)

Whispy is a local voice dictation utility for macOS built on top of [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Hold the **Fn** key to record, and release it to automatically transcribe the text into the active field.

Everything runs locally; no data is sent over the internet.

## Quick Installation Guide

```bash
git clone https://github.com/<your-user>/whispy.git
cd whispy
./install.sh
```

## Prerequisites

- **macOS** (Apple Silicon or Intel)
- [Homebrew](https://brew.sh)
- `sox` (`brew install sox`)

## Detailed Installation

### 1. Install Dependencies

```bash
brew install sox
```

### 2. Clone and Run Install Script

```bash
git clone https://github.com/<your-user>/whispy.git
cd whispy
./install.sh
```

The script automatically manages:
- Python virtual environment creation
- Installation of `faster-whisper`
- Setup and launching the `LaunchAgent`

To use a different model:
```bash
WHISPER_MODEL=medium ./install.sh  # Options: small, base, tiny, medium, large-v3
```

### 3. Configure macOS Permissions (Crucial Step)

Without these permissions, the daemon cannot record audio or simulate keyboard input.

#### 3a. Microphone Access

The daemon needs microphone access to capture audio.

1. Go to **System Settings** → **Privacy & Security** → **Microphone**.
2. Enable access for **iTerm** (or Terminal).
3. The daemon (`python`) may also prompt you for microphone access during the first recording—please accept this popup.

#### 3b. Accessibility Access (Keyboard Simulation)

The daemon requires this permission to simulate keyboard input via `osascript`.

1. Go to **System Settings** → **Privacy & Security** → **Accessibility**.
2. Click the "+" button and add the python executable from the venv (`whispy/.venv/bin/python3`).
3. Verify that the toggle is **enabled**.

> **Without this permission**, transcription works, but the text will not be typed into the active field (look for `osascript timeout` in the logs).

### 4. Restart Daemon After Permissions Update

If you changed permissions, run these commands to ensure the daemon picks up the new settings:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.whispy.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.whispy.plist
```

## Usage

1. Place the cursor in a text field (iTerm, browser, editor...).
2. **Hold Fn** → The "Tink" sound indicates recording is in progress.
3. **Speak**.
4. **Release Fn** → The "Pop" sound indicates transcription and automatic typing/insertion of the text.

## Whisper Models Selection

| Model | Size | Speed | FR Quality |
|--------|------|-------|------------|
| tiny   | 75 MB | ++++  | --         |
| base   | 142 MB| +++    | -          |
| small  | 466 MB| ++     | ++         |
| medium | 1.5 GB| +      | +++        |
| large-v3 | 2.9 GB| -     | ++++       |

The default model is `small` (faster). To change it, use the command in Step 2.

## Manual Commands (API)

You can interact with the daemon via HTTP:

```bash
curl http://localhost:9090/status                          # Daemon status check
curl -X POST http://localhost:9090/start                   # Start recording
curl -X POST http://localhost:9090/stop                    # Stop and transcribe
tail -f ~/.whispy.log ~/.whispy-error.log  # Live logs
```

### Upgrading faster-whisper

```bash
./.venv/bin/pip install --upgrade faster-whisper
```

## Troubleshooting

| Symptom | Probable Cause | Solution |
|-----------|----------------|----------|
| Tink/Pop sounds but no text appears | Missing Accessibility Permission | Step 3b |
| `sox not found` error in logs | SOX not in LaunchAgent PATH | Rerun `install.sh` |
| `Operation not permitted` error | Incorrect Python interpreter (e.g., Xcode vs Homebrew) | Rerun `install.sh` |
| Inaccurate text / errors | Model is too small | `WHISPER_MODEL=medium ./install.sh` |
| Daemon fails to start | Port 9090 is occupied or Python executable cannot be found | Check the logs (`.whispy-error.log`) |
| Model not found | Virtual environment not created | Rerun `install.sh` |

## Configuration

You can modify the top of `whispy.py` to change:
- `PORT` — HTTP port (default: 9090)
- `WHISPER_MODEL_SIZE` — Model name (default: `small`)
- The language is set to French (`language="fr"`).

## Practical Usage & FAQ

### 🔄 How do I manually restart Whispy?

If you update the code or change permissions, you can restart the Whispy background service (daemon) with:

```bash
launchctl unload ~/Library/LaunchAgents/com.whispy.plist
launchctl load ~/Library/LaunchAgents/com.whispy.plist
```

Or simply rerun the install script:

```bash
./install.sh
```

### 🗑️ How do I uninstall Whispy?

With the new install script, you can uninstall everything in one command:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ton-org/whispy/main/install.sh) --uninstall
```

Or manually:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.whispy.plist
rm ~/Library/LaunchAgents/com.whispy.plist
rm -rf whispy/.venv
```

### 📄 Where are the logs?

- Standard log: `~/.whispy.log`
- Error log: `~/.whispy-error.log`

To follow logs in real time:

```bash
tail -f ~/.whispy.log ~/.whispy-error.log
```

### ❓ FAQ

**Q: Will Whispy start automatically at each reboot?**  
A: Yes, the LaunchAgent ensures Whispy starts at every login.

**Q: Can I use a different Python version or environment?**  
A: The install script creates its own virtual environment in `.venv` and uses it automatically.

**Q: How do I update Whispy?**  
A: Pull the latest code (`git pull`) and rerun `./install.sh`.

**Q: What if I want to use a different Whisper model?**  
A: Run `WHISPER_MODEL=medium ./install.sh` (see model table above).

**Q: How do I know if Whispy is running?**  
A: Check with `curl http://localhost:9090/status` or look for the process in Activity Monitor.

**Q: How do I extend or debug Whispy?**  
A: Edit the Python files, then reload the LaunchAgent as above.

---

## 🖥️ Linux & Windows Support (Coming Soon)

Support for Linux and Windows is planned!  
If you want to contribute or be notified of the release, open an issue or follow the project on GitHub.

- **Linux**: A systemd service or autostart script will be provided.
- **Windows**: An automatic installer (.exe) or a PowerShell script will be provided.

---

## License

This project is distributed under the **GPLv3** license. Please see the `LICENSE` file for more details.

## License

This project is distributed under the **GPLv3** license. Please see the `LICENSE` file for more details.
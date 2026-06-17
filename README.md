# Whispy (Voice Dictation for macOS & Linux)

## 🤖 AI Description / Overview

**Whispy is a powerful, local voice dictation utility for macOS and Linux (X11).** It uses the `faster-whisper` model to provide real-time, offline transcription of speech input. The application runs as a background daemon, allowing users to initiate recording by holding a configurable push-to-talk key and automatically transcribing and inserting text into any active field (e.g., iTerm, web browser, or editor) upon release. Because all processing is done locally on your machine, **zero data leaves your computer**, ensuring complete privacy.

## 📘 Project Description (User Guide)

Whispy is a local voice dictation utility built on top of [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Hold the trigger key (the **Fn** key on macOS, **Right Ctrl** by default on Linux) to record, and release it to automatically transcribe the text into the active field.

Everything runs locally; no data is sent over the internet.

> **Linux note:** Whispy v1 supports **X11 sessions only**. Global hotkeys and synthetic text input are restricted under Wayland's security model. If you run Wayland, log out and pick an "Xorg"/"X11" session at your display manager. Wayland support is deferred to a later release.

## Quick Installation Guide

**One-liner (recommended):**

```bash
curl -fsSL https://raw.githubusercontent.com/albrones/whispy/main/scripts/bootstrap.sh | bash
```

Downloads Whispy into `~/.local/share/whispy` and runs the installer (virtualenv,
icons, LaunchAgent). Pick a model with:

```bash
curl -fsSL https://raw.githubusercontent.com/albrones/whispy/main/scripts/bootstrap.sh | WHISPER_MODEL=medium bash
```

**Homebrew:**

```bash
brew install albrones/whispy/whispy
brew services start whispy
```

**Manual (for development):**

```bash
git clone https://github.com/albrones/whispy.git
cd whispy
./install.sh
```

To uninstall a one-liner install:

```bash
curl -fsSL https://raw.githubusercontent.com/albrones/whispy/main/scripts/bootstrap.sh | bash -s -- --uninstall
```

## Prerequisites

Audio capture uses [`sounddevice`](https://python-sounddevice.readthedocs.io)
(PortAudio), installed automatically as a Python dependency on every platform.

**macOS** (Apple Silicon or Intel):
- [Homebrew](https://brew.sh) (for the Homebrew install path)

**Linux** (X11 session):
- An **X11 session** (not Wayland — see the note above)
- `xdotool` — required for text injection
- `xclip` *or* `xsel` — optional, enables clipboard-paste injection mode
- PortAudio runtime (e.g. `libportaudio2`), pulled in with most distros

```bash
# Debian/Ubuntu
sudo apt install xdotool xclip libportaudio2
# Fedora
sudo dnf install xdotool xclip portaudio
# Arch
sudo pacman -S xdotool xclip portaudio
```

The per-OS Python packages resolve automatically via PEP 508 environment
markers: `pyobjc-framework-Quartz`/`rumps` on macOS, `pynput`/`pystray`/`Pillow`
on Linux.

## Detailed Installation

### 1. Install System Dependencies

On macOS the installer handles everything. On Linux, install `xdotool` (and
optionally `xclip`/`xsel`) plus the PortAudio runtime as shown above.

### 2. Clone and Run Install Script

```bash
git clone https://github.com/albrones/whispy.git
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
2. **Hold the trigger key** (Fn on macOS, Right Ctrl on Linux) → a sound indicates recording is in progress.
3. **Speak**.
4. **Release the trigger key** → a sound indicates transcription and automatic typing/insertion of the text.

## Whisper Models Selection

| Model | Size | Speed | FR Quality |
|--------|------|-------|------------|
| tiny   | 75 MB | ++++  | --         |
| base   | 142 MB| +++    | -          |
| small  | 466 MB| ++     | ++         |
| medium | 1.5 GB| +      | +++        |
| large-v3 | 2.9 GB| -     | ++++       |

The default model is `small` (faster). To change it, use the command in Step 2.

Models are downloaded automatically by `faster-whisper` on first use and cached under
`~/.cache/huggingface/hub/`. Expect the model's full size (see table) to be used on disk;
delete that folder to reclaim the space.

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

Run the built-in diagnostic first — it checks the audio backend, `xdotool`
(Linux), the model, the platform permissions, and whether the daemon is running:

```bash
python whispy_daemon.py --doctor   # or: make doctor
```

| Symptom | Probable Cause | Solution |
|-----------|----------------|----------|
| Sounds play but no text appears (macOS) | Missing Accessibility Permission | Step 3b |
| No text appears (Linux) | `xdotool` missing, or Wayland session | Install `xdotool`; switch to an X11 session |
| `sounddevice`/PortAudio import error | PortAudio runtime missing | Install it (e.g. `apt install libportaudio2`) |
| `Operation not permitted` error | Incorrect Python interpreter (e.g., Xcode vs Homebrew) | Rerun `install.sh` |
| Inaccurate text / errors | Model is too small | `WHISPER_MODEL=medium ./install.sh` |
| Daemon fails to start | Port 9090 is occupied or Python executable cannot be found | Check the logs (`.whispy-error.log`) |
| Model not found | Virtual environment not created | Rerun `install.sh` |

## Configuration

You can edit `~/.config/whispy/config.json` to change:
- `model_size` — Whisper model name (default: `small`)
- `language` — transcription language (default: `fr`)
- `copy_to_clipboard` — paste via the clipboard instead of synthesizing keystrokes
- `trigger` — the push-to-talk key/combo. Leave it `null` (or omit it) to use the
  platform default: the **Fn** key on macOS, **Right Ctrl** (`ctrl_r`) on Linux.
  Set a macOS keycode (integer) or a key/combo name (string) to override.

The HTTP `PORT` (default 9090) is defined near the top of `whispy_daemon.py`.

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
./install.sh --uninstall
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

## 🖥️ Platform Support

Whispy runs on **macOS** and **Linux (X11)**. The OS-coupled seams sit behind a
ports-and-adapters layer (`src/whispy/platform/`) and are bound at runtime by
`platform.detect()`:

| Seam | macOS | Linux (X11) |
|------|-------|-------------|
| Global hotkey | Quartz `CGEventTap` (Fn) | `pynput` (Right Ctrl by default) |
| Text injection | `osascript` | `xdotool` (+ `xclip`/`xsel`) |
| Audio capture | `sounddevice` (PortAudio) | `sounddevice` (PortAudio) |
| Tray/menu | `rumps` menu bar + overlay | `pystray` tray (no overlay in v1) |
| Sounds | `afplay` | `paplay`/`ffplay` |

**Not supported in v1:** Wayland (deferred — global hotkey + synthetic input are
restricted by its security model), Windows, native Linux packaging, and the
floating overlay window on Linux (state is shown through the tray instead).

Contributions and design input are welcome — start by reading [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Testing

Run the full test suite:

```bash
./.venv/bin/pytest
```

Run with coverage:

```bash
./.venv/bin/pytest --cov=src/whispy --cov-report=term-missing
```

Run a specific test file:

```bash
./.venv/bin/pytest tests/test_engine.py -v
./.venv/bin/pytest tests/test_e2e.py -v
```

Test files are organized by scope:

| File | Scope |
|------|-------|
| `tests/test_engine.py` | Core engine, state machine, config |
| `tests/test_audio.py` | AudioEngine, transcription, language detection |
| `tests/test_integration.py` | Multi-module integration |
| `tests/test_e2e.py` | End-to-end workflow tests |
| `tests/test_event_tap_e2e.py` | EventTapListener E2E tests |
| `tests/test_api/test_server.py` | HTTP API server tests |
| `tests/test_text_cleaning.py` | Whisper credit stripping |
| `tests/test_config_validation.py` | Config validation and migration |
| `tests/test_error_handling.py` | Error cases (sox, mic, model) |
| `tests/test_stress.py` | Concurrent access stress tests |

## License

This project is distributed under the **GPLv3** license. Please see the `LICENSE` file for more details.
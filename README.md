# Whispy (Voice Dictation for macOS & Linux)

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE) [![Platform: macOS | Linux](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20(X11)-lightgrey.svg)](#) &nbsp;·&nbsp; **[whispy-dun.vercel.app](https://whispy-dun.vercel.app)**

## 🤖 AI Description / Overview

**Whispy is a powerful, local voice dictation utility for macOS and Linux (X11).** It uses NVIDIA's `parakeet-tdt-0.6b-v3` model to provide real-time, offline transcription of speech input. The application runs as a background daemon, allowing users to initiate recording by holding a configurable push-to-talk key and automatically transcribing and inserting text into any active field (e.g., iTerm, web browser, or editor) upon release. Because all processing is done locally on your machine, **zero data leaves your computer**, ensuring complete privacy.

## 📘 Project Description (User Guide)

Whispy is a local voice dictation utility built on top of [NVIDIA Parakeet TDT 0.6b v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3), run on CPU through [onnx-asr](https://github.com/istupakov/onnx-asr). Hold the trigger key (the **Fn** key on macOS, **Right Ctrl** by default on Linux) to record, and release it to automatically transcribe the text into the active field.

Everything runs locally; no data is sent over the internet. You can bias recognition toward your own names and jargon with the manual custom vocabulary (`custom_vocabulary` in the config); automatic correction learning was removed and its reimplementation is tracked in [issue #8](https://github.com/albrones/whispy/issues/8).

> **Linux note:** Whispy v1 supports **X11 sessions only**. Global hotkeys and synthetic text input are restricted under Wayland's security model. If you run Wayland, log out and pick an "Xorg"/"X11" session at your display manager. Wayland support is deferred to a later release.

## Quick Installation Guide

**One-liner (recommended):**

```bash
curl -fsSL https://raw.githubusercontent.com/albrones/whispy/main/scripts/bootstrap.sh | bash
```

Works on macOS and Linux from one command. On **macOS** it builds and installs
the signed `Whispy.app` into `/Applications` (the only supported macOS install);
on **Linux/X11** it sets up a virtualenv and a `systemd --user` service. Source
lives in `~/.local/share/whispy`.

> The macOS build needs the Xcode Command Line Tools (`xcode-select --install`).
> If they're missing, the installer prints the manual `make app` steps instead.

**Native macOS app (by hand):**

```bash
git clone https://github.com/albrones/whispy.git
cd whispy && ./install.sh   # creates the .venv
make app                    # builds & signs dist/Whispy.app
cp -R dist/Whispy.app /Applications/
open /Applications/Whispy.app
```

This bundles Python *inside* `Whispy.app`, so the microphone / Accessibility /
Input-Monitoring grants attach to a stable **"Whispy"** identity and **survive
Python upgrades** — unlike the script/LaunchAgent paths, whose grant breaks
whenever the interpreter path changes (e.g. a 3.13 → 3.14 upgrade). On first
launch, accept the **Whispy** microphone prompt. To start at login, flip the
**Start at login** toggle in the menu bar menu (or add `Whispy.app` to
**System Settings → General → Login Items** by hand). Either way, remove any old
LaunchAgent — both the older `com.whisper-dictation` and the `com.whispy` ones
(`./install.sh --uninstall`) — so the daemon doesn't run twice.

`make app` also creates a free, self-signed **"Whispy Local Signing"**
certificate in your login keychain (via `packaging/macos/create_signing_cert.sh`)
and signs the bundle with it. This stable signing identity is what lets macOS
**remember** the permission across relaunches — a bare ad-hoc signature does
not persist TCC grants and re-prompts every launch. No Apple Developer account
needed; the cert is local-only (not for distribution).

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
- Xcode Command Line Tools (`xcode-select --install`) to build `Whispy.app`

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
- Installation of `onnx-asr` (Parakeet + onnxruntime)
- On **Linux/X11**, setup and launching of a `systemd --user` service. On
  **macOS** it only builds the venv — run `make app` to produce `Whispy.app`
  (autostart is the in-app "Start at login" toggle, no LaunchAgent)

### 3. Configure macOS Permissions (Crucial Step)

Without these permissions, the daemon cannot record audio or simulate keyboard input.

#### 3a. Microphone Access

The daemon needs microphone access to capture audio.

- **Native app (`make app`):** On first launch Whispy explicitly requests the
  mic and macOS shows a **"Whispy"** prompt — click **Allow**. The grant then
  shows as "Whispy" under **System Settings → Privacy & Security → Microphone**
  and persists across Python upgrades. If you ever clicked "Don't Allow", reset
  it with `tccutil reset Microphone com.whispy` and relaunch.
- **Dev (`make run`):** the responsible process is the bare Python
  interpreter. Enable **iTerm**/**Terminal** under Microphone, and accept the
  first-recording popup. Note: a bare interpreter has no usage-description
  Info.plist, so on recent macOS the prompt may never appear and capture
  silently returns silence — prefer the native app in that case.

#### 3b. Accessibility Access (Keyboard Simulation)

The daemon requires this permission to simulate keyboard input via `osascript`.

1. Go to **System Settings** → **Privacy & Security** → **Accessibility**.
2. Click the "+" button and add the python executable from the venv (`whispy/.venv/bin/python3`).
3. Verify that the toggle is **enabled**.

> **Without this permission**, transcription works, but the text will not be typed into the active field (look for `osascript timeout` in the logs).

> **Upgrading from the old name?** macOS keys these grants to the app's bundle
> identity. After the rebrand the bundle id is `com.whispy`, so the *old* grant
> no longer applies: the clipboard fills but nothing is typed and the logs show
> `osascript ... (1002)` ("not authorized to send keystrokes"). Whispy now
> surfaces this in the menu bar (**⚠ Can't type — fix permissions…**). To fix,
> reset and re-grant against the new identity:
>
> ```bash
> tccutil reset Accessibility com.whispy
> tccutil reset AppleEvents com.whispy
> ```
>
> Then relaunch Whispy and accept the re-prompts (or re-enable it under
> **Privacy & Security → Accessibility** and **Automation**).

### 4. Restart Daemon After Permissions Update

If you changed permissions, restart Whispy so the daemon picks up the new settings:

- **macOS:** Whispy menu bar → **Restart** (or quit and reopen `/Applications/Whispy.app`).
- **Linux:** `systemctl --user restart whispy.service`.

## Usage

1. Place the cursor in a text field (iTerm, browser, editor...).
2. **Hold the trigger key** (Fn on macOS, Right Ctrl on Linux) → a sound indicates recording is in progress.
3. **Speak**.
4. **Release the trigger key** → a sound indicates transcription and automatic typing/insertion of the text.

## The Transcription Model

Whispy ships one model: **`nvidia/parakeet-tdt-0.6b-v3`**, int8-quantized to ONNX
and run on CPU. There is nothing to choose, so there is no model setting.

| | |
|---|---|
| Download | **639 MB**, automatic on first use |
| Cached at | `~/.cache/huggingface/hub/models--istupakov--parakeet-tdt-0.6b-v3-onnx` |
| Resident memory | ~1.4 GB while loaded |
| Languages | 25, **detected automatically**. Speech outside this set will not transcribe |

The 25, per the [model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3):
Bulgarian, Croatian, Czech, Danish, Dutch, English, Estonian, Finnish, French,
German, Greek, Hungarian, Italian, Latvian, Lithuanian, Maltese, Polish,
Portuguese, Romanian, Slovak, Slovenian, Spanish, Swedish, Russian, Ukrainian.

There is no language setting, and adding one would make things worse: the model
detects language per utterance and handles switching mid-recording, while
forcing a language was measurably wrong (English speech came back translated
into French).

**Non-speech never reaches it.** Given silence or room noise, the model answers
with a short filler — `Yeah.`, `Okay.`, `Mm-hmm.` — which would be typed into
whatever you had focused. Two gates run before it, and a clip has to clear both:

| Gate | Discards |
|---|---|
| Loudness | Anything below 0.005 normalized RMS — a muted mic, a misfire, a quiet room |
| Voice detection | Anything with under 0.20 s of detected voice — steady noise, a fan, mains hum |

Both fail open: a clip that cannot be measured is transcribed rather than
dropped, because losing real dictation is worse than an occasional stray word.
Neither looks at *what* was said — `Okay.` and `No.` are legitimate one-word
dictations, so filtering by text would delete real speech. Holding the trigger
while you think is fine too: the second gate measures how much voice it heard,
not what fraction of the recording was voice.

In a genuinely loud room (above roughly 0.04 RMS of noise) voice detection stops
being able to tell noise from speech, and you are relying on the model, which
returned nothing for every such clip measured. If you do get a stray word in a
noisy environment, that is the gap.

**Upgrading from a Whisper-era Whispy?** The old model cache at
`~/.cache/huggingface/hub/models--Systran--faster-whisper-*` is no longer used.
`./install.sh --uninstall` points at it but will not delete another era's data —
remove it by hand to reclaim the space.

## Manual Commands (API)

The HTTP API is bound to loopback **and** protected by a per-install token, so a
web page open in your browser can't drive the daemon. Every request must carry
the token (`Authorization: Bearer <token>`). The token is stored next to your
config:

```bash
TOKEN=$(cat ~/.config/whispy/config.token)                 # per-install API token

curl -H "Authorization: Bearer $TOKEN" http://localhost:9090/status              # Daemon status check
curl -H "Authorization: Bearer $TOKEN" -X POST http://localhost:9090/start       # Start recording
curl -H "Authorization: Bearer $TOKEN" -X POST http://localhost:9090/stop        # Stop and transcribe
tail -f ~/.whispy.log ~/.whispy-error.log  # Live logs
```

### Upgrading the ASR runtime

```bash
./.venv/bin/pip install --upgrade onnx-asr
```

## Troubleshooting

Run the built-in diagnostic first — it checks the audio backend, `xdotool`
(Linux), the model, the platform permissions, and whether the daemon is running:

```bash
python whispy_daemon.py --doctor   # or: make doctor
```

### Validating the whole app (`make validate`)

`make doctor` checks prerequisites; `make validate` checks **behavior**. It runs
three honest layers for your OS and reports each feature as **PASS / FAIL /
UNVERIFIED** (an unexercisable seam is UNVERIFIED — never a silent pass):

1. **Preflight** — `doctor`.
2. **Live-drive** — boots the real daemon and drives a record→transcribe cycle
   over its HTTP API (no mocks).
3. **Operator** — a guided checklist for the human-only flow (hold the trigger,
   speak, confirm the text lands in the focused app).

```bash
make validate               # full run (asks you to dictate during the operator layer)
make validate-unattended    # preflight + live-drive only (no human)
```

Exit code is the verdict: `0` pass, `1` a real failure, `2` something
UNVERIFIED. `FEATURE_MATRIX.md` is the single source of truth mapping every
feature → its coverage tier → how it is verified. **Rule:** every fix or feature
must update its matrix row and add a regression case at the lowest tier that can
catch it (see the matrix header).

| Symptom | Probable Cause | Solution |
|-----------|----------------|----------|
| Sounds play but no text appears (macOS) | Missing Accessibility Permission | Step 3b |
| No text appears (Linux) | `xdotool` missing, or Wayland session | Install `xdotool`; switch to an X11 session |
| `sounddevice`/PortAudio import error | PortAudio runtime missing | Install it (e.g. `apt install libportaudio2`) |
| `Operation not permitted` error | Incorrect Python interpreter (e.g., Xcode vs Homebrew) | Rerun `install.sh` |
| Inaccurate text on names or jargon | The model renders unusual terms phonetically | Add them to `custom_vocabulary` (corrects close misses only) |
| Daemon fails to start | Port 9090 is occupied or Python executable cannot be found | Check the logs (`.whispy-error.log`) |
| Model not found | Virtual environment not created | Rerun `install.sh` |

## Configuration

You can edit `~/.config/whispy/config.json` to change any of the following keys
(each defined in `DEFAULT_CONFIG`, `src/whispy/core/config.py`):

| Key | Default | Description |
|-----|---------|-------------|
| `copy_to_clipboard` | `false` | Paste via the clipboard instead of synthesizing keystrokes |
| `start_at_login` | `false` | Register the app as a login item. macOS `.app` bundle only (via `SMAppService`); ignored on the loose-script path |
| `min_recording_duration` | `0.3` | Recordings shorter than this (seconds) are discarded rather than transcribed. Separately (and not configurable), near-silent audio is discarded on energy before it reaches the model — the model otherwise invents short fillers like "Okay." on a quiet room |
| `custom_vocabulary` | `[]` | User-curated terms (names, brands, jargon). Applied **after** transcription: an output word is corrected when its spelling *or* its pronunciation matches one of your terms (`wispy` → `Whispy`, `parakite` → `Parakeet`). Weaker than biasing the decoder — a word rendered far from the target on both counts is left alone — but it cannot leak your terms into text you did not say. Add proper nouns and anglicisms here; it is the intended fix for them |
| `trigger` | `null` | Push-to-talk key/combo. `null` uses the platform default: the **Fn** key on macOS, **Right Ctrl** (`ctrl_r`) on Linux. Set a macOS keycode (integer) or a key/combo name (string) to override |
| `streaming_enabled` | `true` | Transcribe audio in chunks during recording (typed near-instantly on release) instead of the legacy record-then-transcribe path |
| `pause_ms` | `600` | Minimum trailing silence (milliseconds) that closes a streaming chunk |
| `min_chunk_s` | `0.4` | A streaming chunk shorter than this (seconds) is discarded rather than transcribed |
| `max_chunk_s` | `12.0` | Hard cap (seconds) on streaming chunk length, so run-on speech with no pause still makes progress |
| `vad_aggressiveness` | `2` | WebRTC VAD aggressiveness (0-3); higher classifies more audio as non-speech when finding chunk boundaries |

On macOS you can also pick the trigger from the menu bar (**Settings → Trigger**:
Fn, Right Command, Right Option, or F13) — the change applies live, no restart.

The HTTP `PORT` (default 9090) is defined near the top of `src/whispy/api/server.py`.

## Practical Usage & FAQ

### 🔄 How do I manually restart Whispy?

- **macOS:** Whispy menu bar → **Restart**, or quit and reopen `/Applications/Whispy.app`.
- **Linux:** `systemctl --user restart whispy.service`.

Running from source (development)? `make run` launches the daemon in the
foreground against your working tree — no build or install step.

### 🗑️ How do I uninstall Whispy?

**macOS** (the `.app` is removed by deleting it; that also drops the "Start at
login" item):

```bash
# 1. Quit Whispy (menu bar → Quit).
# 2. Remove the venv and any legacy LaunchAgents (both the older
#    com.whisper-dictation and the com.whispy ones):
./install.sh --uninstall
# 3. Delete the app bundle:
rm -rf /Applications/Whispy.app
# 4. (optional) wipe settings, auth token, and logs:
rm -rf ~/.config/whispy ~/.whispy.log ~/.whispy-error.log
# Doing it by hand instead of ./install.sh --uninstall? Boot out and delete both:
#   launchctl bootout "gui/$(id -u)/com.whisper-dictation" 2>/dev/null || true
#   rm -f ~/Library/LaunchAgents/com.whisper-dictation.plist
#   launchctl bootout "gui/$(id -u)/com.whispy" 2>/dev/null || true
#   rm -f ~/Library/LaunchAgents/com.whispy.plist
```

**Linux** (removes the `systemd --user` unit and the venv):

```bash
./install.sh --uninstall
```

> macOS permission grants (Microphone / Accessibility / Input Monitoring) are
> tied to the `Whispy.app` identity and persist across reinstalls of the same
> bundle. A fresh `make app` build re-signs the bundle, so macOS may ask you to
> re-approve them after reinstalling — that is expected.

### 📄 Where are the logs?

- Standard log: `~/.whispy.log`
- Error log: `~/.whispy-error.log`

To follow logs in real time:

```bash
tail -f ~/.whispy.log ~/.whispy-error.log
```

### ❓ FAQ

**Q: Will Whispy start automatically at each reboot?**
A: On macOS, enable the in-app **Settings → Start at login** toggle (registered
via `SMAppService` — no LaunchAgent). On Linux, the `systemd --user` unit
installed by `install.sh` starts it at login.

**Q: Can I use a different Python version or environment?**
A: The install script creates its own virtual environment in `.venv` and uses it automatically.

**Q: How do I update Whispy?**
A: Pull the latest code (`git pull`), then on **macOS** rebuild and reinstall
the bundle: `./install.sh && make app && cp -R dist/Whispy.app /Applications/`,
then relaunch it. On **Linux**, rerun `./install.sh` (it reinstalls the venv and
reloads the systemd unit). Running `/Applications/Whispy.app` from an old build
is the usual reason a code or settings fix "doesn't take" — rebuild the bundle.

**Q: Can I use a different model?**
A: No. Whispy ships one model (see "The Transcription Model" above), so there is
no model setting and no `WHISPER_MODEL` variable any more.

**Q: I spoke and nothing was typed.**
A: A clip has to clear both non-speech gates (see "The Transcription Model"). The
usual causes are a recording under `min_recording_duration` (0.3 s — a tap rather
than a hold), a muted or wrong input device, or speech too far from the mic to
register as voice. `~/.whispy.log` says which gate discarded it and with what
measurement — `Recording too short`, `near-silent (RMS ...)`, or
`No speech detected (... of voiced frames)`.

**Q: My language isn't transcribing at all.**
A: Parakeet covers 25 languages, listed under "The Transcription Model" above.
Anything outside that set will not work — there is no setting that changes it.

**Q: How do I know if Whispy is running?**
A: Check with `curl -H "Authorization: Bearer $(cat ~/.config/whispy/config.token)" http://localhost:9090/status` or look for the process in Activity Monitor.

**Q: How do I extend or debug Whispy?**
A: Edit the Python files, then run `make run` to launch the daemon in the
foreground against your working tree (logs stream to the terminal). No bundle
rebuild needed for source runs; rebuild with `make app` only to ship the `.app`.

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
| `tests/test_audio.py` | AudioEngine, transcription, audio duration detection |
| `tests/test_integration.py` | Multi-module integration |
| `tests/test_e2e.py` | End-to-end workflow tests |
| `tests/test_event_tap_e2e.py` | EventTapListener E2E tests |
| `tests/test_api/test_server.py` | HTTP API server tests |
| `tests/test_text_cleaning.py` | whitespace normalization, custom-vocabulary correction |
| `tests/test_config_validation.py` | Config validation and migration |
| `tests/test_error_handling.py` | Error cases (capture-backend failure, mic unavailable) |

## License

This project is distributed under the **GPLv3** license. See the `LICENSE` file
for the full text.

The transcription model is a separate work under a different licence:
**`nvidia/parakeet-tdt-0.6b-v3`** is © NVIDIA Corporation, licensed
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). Whispy does not
redistribute it — the weights are downloaded from the Hugging Face Hub on first
run and cached on your machine, so no model files ship in this repository or in
any release artifact. See `NOTICE` for the full attribution, including the ONNX
conversion Whispy loads.

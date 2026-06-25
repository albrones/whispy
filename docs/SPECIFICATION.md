# Whispy — Codebase Specification

> **⚠️ V1 Release Note (2026-05-26):** This specification was written before the V1 stabilization. Several sections are now outdated:
> - `src/whispy/core/config.py` now exists (was not documented)
> - `src/whispy/core/text_cleaner.py` now exists (was not documented)
> - `whispy_legacy.py` has been removed
> - Model loading has been unified (`_load_model_async` + `_load_model_on_device` → single `_load_model_async`)
> - Config validation and migration are now implemented
> - Text cleaning is now in `text_cleaner.py` (was inline in `engine.py`)
> - See `CHANGELOG.md` for the full list of changes.
>
> Sections marked `[OBSOLETE]` below are superseded by the V1 implementation.

## 1. Overview

**Whispy** is a macOS local voice dictation utility that runs as a menu bar daemon. The user holds the **Fn** key to record audio and releases it to automatically transcribe and inject text into the active text field. All processing is local — no data leaves the machine.

### Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| STT Engine | `faster-whisper` (Whisper models 75MB → 2.9GB) |
| UI | `rumps` (menu bar) |
| Audio Recording | `sounddevice` / PortAudio (RawInputStream) |
| Fn Key Detection | `pyobjc-framework-Quartz` (CGEventTap) |
| Text Injection | `osascript` (AppleScript / System Events) |
| HTTP Server | `http.server` (stdlib, port 9090) |
| Daemon | macOS LaunchAgent (`com.whispy.plist`) |

---

## 2. Software Architecture

```
whispy_daemon.py             ← Entry point
  │
  ├── Engine (core/engine.py) ← Central orchestrator
  │     ├── StateMachine (core/state_machine.py)  ← FSM IDLE → RECORDING → TRANSCRIBING → IDLE
  │     ├── AudioEngine (core/audio.py)           ← sounddevice capture + Whisper transcription
  │     ├── EventTapListener (hardware/event_tap.py)  ← Fn key detection via CGEventTap
  │     └── TextInjector (hardware/injection.py)    ← Injection via osascript (clipboard/keystroke)
  │
  ├── WhisperMenuBarApp (ui/menu_bar.py)  ← rumps UI (status, menu, animation)
  │
  └── HTTP Server (api/server.py)         ← REST API (GET /status, POST /start, etc.)
```

### Main Data Flow

```
[Fn key pressed]
  → EventTapListener detects keycode=63 + NX_SECONDARYFNMASK
  → "Tink" sound (afplay)
  → Engine.start_recording()
    → AudioEngine.start()
      → FSM: IDLE → RECORDING
      → sounddevice.RawInputStream(samplerate=16000, channels=1, dtype="int16") streamed to a unique temp WAV
  → UI: animated icon (3 frames), status "Recording..."

[Fn key released]
  → Engine.stop_recording()
    → AudioEngine.stop()
      → FSM: RECORDING → TRANSCRIBING
      → stop + close the capture stream
  → Transcription worker detects _stop_event
  → WhisperModel.transcribe("/tmp/whispy.wav", ...)
  → TextInjector.inject(text)  → osascript (clipboard + Cmd+V or keystroke)
  → "Pop" sound (afplay)
  → FSM: TRANSCRIBING → IDLE
  → UI: idle icon, status "Ready"
```

---

## 3. Module Specifications

### 3.1 `whispy_daemon.py` — Entry Point

**Purpose:** Initialization and startup orchestration.

**Constants:**
- `CONFIG_DIR = Path.home() / ".config" / "whispy"`
- `CONFIG_PATH = CONFIG_DIR / "config.json"`

**`main()` function:**
1. `load_config(CONFIG_PATH)` — load config (fallback to defaults)
2. `DictationState()` — shared thread-safe state container
3. `Engine(state, config_path)` — central orchestrator
4. `WhisperMenuBarApp(engine)` — menu bar UI
5. `engine.start()` — starts Fn listener, transcription worker, async model loading
6. `start_http_server(engine)` — HTTP server on `127.0.0.1:9090`
7. `signal.SIGTERM` handler — graceful shutdown
8. `app.run()` — main rumps event loop

---

### 3.2 `src/whispy/core/engine.py` — Core Engine (~393 lines)

**`DEFAULT_CONFIG`:**
```python
{
    "model_size": "small",              # tiny, base, small, medium, large-v3
    "compute_key": "cpu-int8",          # cpu-int8, cpu-float32, cuda-float16, cuda-int8
    "language": "auto",                 # auto, fr, en
    "beam_size": 1,
    "best_of": 2,
    "copy_to_clipboard": True,
    "auto_detect_min_duration": 0.5,
}
```

**`MODEL_PRESETS`:** Mapping model_size → {label, description}

**`SUPPORTED_LANGUAGES`:** {"auto": ..., "fr": "French", "en": "English"}

**`COMPUTE_OPTIONS`:** Mapping compute_key → {label, device, compute_type}

#### Classes

**`DictationState`** — Shared state container between threads:

| Attribute | Type | Description |
|---|---|---|
| `is_recording` | bool | Recording active flag |
| `is_transcribing` | bool | Transcription active flag |
| `model` | WhisperModel \| None | Loaded Whisper model |
| `model_loading` | bool | Model loading in progress |
| `last_transcription` | str \| None | Last transcribed text |
| `fn_listener_active` | bool | Fn key listener active |
| `config` | dict | Current configuration |
| `lock` | threading.Lock | Thread-safe lock |
| `_stop_event` | threading.Event | Signal for transcription worker |
| `app` | WhisperMenuBarApp \| None | UI reference |

**`Engine`** — Central orchestrator:

| Method | Purpose |
|---|---|
| `__init__(state, config_path)` | Initializes FSM, AudioEngine, TextInjector, callbacks |
| `start()` | Starts Fn listener, transcription worker, async model loading |
| `stop()` | Stops worker and listener |
| `start_recording()` | Delegates to AudioEngine.start() |
| `stop_recording()` | Delegates to AudioEngine.stop() |
| `run_transcription()` | Executes sync transcription → injects text |
| `start_fn_listener()` | Creates and starts EventTapListener with press/release callbacks |
| `update_config(updates)` | Applies updates, saves to disk, returns bool if reload needed |
| `get_status()` | Returns dict: {is_recording, is_transcribing, fn_listener_active, model_loaded, model_loading, fsm} |
| `on_status_change(callback)` | Registers callback for state change notifications |
| `_notify_status_change()` | Notifies all registered callbacks |

**FSM Callbacks:**
- `_on_fsm_recording()` → syncs `state.is_recording = True`
- `_on_fsm_transcribing()` → syncs `state.is_recording = False, state.is_transcribing = True`
- `_on_fsm_idle()` → syncs `state.is_recording = False, state.is_transcribing = False`

**`load_config(config_path)`** → dict: loads JSON, falls back to DEFAULT_CONFIG, ignores unknown keys.

**`save_config(config, config_path)`** → persists dict as indented JSON, creates directories if needed.

**`_load_model(config)`** → instantiates `WhisperModel` from config.

**`load_model_async(engine)`** → loads model in daemon thread.

**`RECORDING_PATH = /tmp/whispy.wav`** — Temporary audio file.

---

### 3.3 `src/whispy/core/state_machine.py` — FSM (~160 lines)

**`State` (Enum):** `IDLE`, `RECORDING`, `TRANSCRIBING`

**`InvalidTransitionError`** — Exception raised for illegal transitions.

**`StateMachine`:**

Valid transitions:
```
IDLE     → RECORDING
RECORDING → TRANSCRIBING
TRANSCRIBING → IDLE
```

| Property/Method | Purpose |
|---|---|
| `current_state` | Current state (thread-safe) |
| `is_idle`, `is_recording`, `is_transcribing` | Bool properties |
| `transition_to(target)` | Transition with validation, callbacks, history |
| `start_recording()` | IDLE → RECORDING (returns False if already recording) |
| `stop_recording()` | RECORDING → TRANSCRIBING (returns False if not recording) |
| `transcription_complete()` | TRANSCRIBING → IDLE |
| `on_state_change(state, callback)` | Registers state change callback |
| `to_dict()` | {state, is_idle, is_recording, is_transcribing} |
| `transition_history` | List of transitions ["IDLE -> RECORDING", ...] |

Thread-safety: `threading.Lock` on all access to `_current_state` and `_transitions`.

---

### 3.4 `src/whispy/core/audio.py` — Audio Engine (~138 lines)

**`AudioEngine`:**

| Method | Purpose |
|---|---|
| `start()` | FSM IDLE→RECORDING + open a `sounddevice` capture stream to a unique temp WAV |
| `stop()` | Stop + close the capture stream + FSM RECORDING→TRANSCRIBING |
| `transcribe(audio_path, model, language, beam_size, best_of, auto_detect_min_duration)` | Transcription via WhisperModel |
| `_get_audio_duration(audio_path)` | Reads WAV header to calculate duration |
| `cleanup_audio_file(audio_path)` | Removes temporary file |
| `play_sound(sound_name)` | `afplay /System/Library/Sounds/{sound_name}` |
| `is_recording`, `is_transcribing` | Properties delegated to FSM |

**`transcribe()` logic:**
1. If `model is None` → returns `None`
2. If `language == "auto"` and `duration < auto_detect_min_duration` → warning (proceeds anyway)
3. `model.transcribe(audio_path, ...)` → joins `segments.text` with spaces
4. Returns text or `None`

---

### 3.5 `src/whispy/ui/menu_bar.py` — Menu Bar UI (~226 lines)

**`WhisperMenuBarApp(rumps.App)`:**

**Menu structure:**
```
[Status: Ready/Recording.../Transcribing.../Loading...]
---
Model
  Fast (tiny)      ●
  Light (base)
  Normal (small)   ●
  Accurate (medium)
  Maximum (large)
Language
  Auto-detect      ●
  French
  English
Compute
  CPU (int8) ⭐    ●
  CPU (float32)
  CUDA (float16)  (disabled on macOS)
  CUDA (int8)     (disabled on macOS)
[✓] Copy to clipboard
---
Fn: ✓ active
---
Restart
Quit [q]
```

**Animation:** 0.2s timer → cycles 3 icons `mic-recording-{1,2,3}.png` when recording, `mic-transcribing.png` when transcribing, `mic-idle.png` when idle.

**Methods:**
- `_animate()` — Icon animation (rumps.timer 0.2s)
- `update_status_display()` — Refreshes status text + icon
- `_on_model_select()`, `_on_language_select()`, `_on_compute_select()` — Menu callbacks
- `_on_toggle_copy()` — Clipboard toggle
- `_on_reload()` — Relaunches app + quit
- `_on_quit()` — Quits rumps
- `_load_icons()` — Loads icon file paths
- `_build_menu()` — Builds complete menu structure

---

### 3.6 `src/whispy/api/server.py` — HTTP API (~145 lines)

**Port:** `9090` (localhost only)

**GET Endpoints:**

| Endpoint | Response |
|---|---|
| `GET /status` | `{is_recording, is_transcribing, fn_listener_active, model_loaded, model_loading, fsm}` |
| `GET /config` | `{model_size, compute_key, language, beam_size, best_of, copy_to_clipboard, auto_detect_min_duration}` |
| `GET /last-transcription` | `{text: str \| None}` |
| `GET /<other>` | `404 {"error": "not found"}` |

**POST Endpoints:**

| Endpoint | Body | Response |
|---|---|---|
| `POST /start` | — | `{"status": "recording"}` + Tink sound |
| `POST /stop` | — | `{"status": "done", "text": str \| None}` + Pop sound (sync stop+transcribe) |
| `POST /stop-async` | — | `{"status": "stopping"}` + Pop sound (async) |
| `POST /config` | `{model_size, language, ...}` | `{"status": "ok", "config": {...}}` + reload if needed |
| `POST /<other>` | — | `404 {"error": "not found"}` |

**`RequestHandler.engine`** — Class attribute set by `start_http_server()`.

**`start_http_server(engine)`** — Starts `HTTPServer` in daemon thread.

---

### 3.7 `src/whispy/hardware/event_tap.py` — Fn Key Listener (~126 lines)

**`QUARTZ_AVAILABLE`** — bool: True if pyobjc-framework-Quartz imported.

**`FN_KEYCODE = 63`** — Apple keyboard code for Fn key.

**`NX_SECONDARYFNMASK = 0x800000`** — Flag to distinguish press vs release.

**`EventTapListener`:**

| Method | Purpose |
|---|---|
| `start()` | Creates CGEventTap, starts CFRunLoop in daemon thread |
| `stop()` | Marks inactive (daemon thread terminates automatically) |
| `_event_callback()` | Filters kCGEventFlagsChanged → keycode==63 → flags & NX_SECONDARYFNMASK |

**`_event_callback` logic:**
- `flags & NX_SECONDARYFNMASK` → Fn pressed → `on_fn_press()`
- Otherwise → Fn released → `on_fn_release()`

---

### 3.8 `src/whispy/hardware/injection.py` — Text Injection (~55 lines)

**`TextInjector`:**

| Mode | Method | Command |
|---|---|---|
| `copy_to_clipboard=True` | Clipboard | `osascript -e 'set the clipboard to "..."` + `keystroke "v" using command down` |
| `copy_to_clipboard=False` | Keystroke | `osascript -e 'tell application "System Events" to keystroke "..."` |

**Escaping:** `text.replace('"', '\\"')` for double quotes.

---

## 4. Configuration

**Location:** `~/.config/whispy/config.json`

| Key | Type | Default | Description |
|---|---|---|---|
| `model_size` | str | `"small"` | tiny, base, small, medium, large-v3 |
| `compute_key` | str | `"cpu-int8"` | cpu-int8, cpu-float32, cuda-float16, cuda-int8 |
| `language` | str | `"auto"` | auto, fr, en |
| `beam_size` | int | `1` | Beam search width |
| `best_of` | int | `2` | Best-of sampling |
| `copy_to_clipboard` | bool | `True` | Copy to system clipboard |
| `auto_detect_min_duration` | float | `0.5` | Min duration for reliable auto-detect |

---

## 5. Tests

**Execution:** `pytest` (from `tests/` directory)

**Infrastructure:**
- `conftest.py` — Mocks Quartz/rumps, shared fixtures (`engine`, `state`, `sm`, `mock_subprocess`, `mock_whisper_model`, `tmp_dir`, `config_path`)
- `test_api/conftest.py` — `mock_engine` fixture

**Test Coverage:**

| File | Covers | Lines |
|---|---|---|
| `test_state_machine.py` | FSM transitions, callbacks, thread safety, history | 434 |
| `test_engine.py` | Config load/save, Engine status, config updates, DictationState | 257 |
| `test_audio.py` | Audio start/stop, transcribe, cleanup, duration detection | 217 |
| `test_injection.py` | Clipboard/keystroke injection, escaping, empty text | 166 |
| `test_api/test_server.py` | HTTP endpoints (GET/POST), 404 handling | 202 |
| `test_integration.py` | Multi-module integration, concurrent config updates | 236 |
| `test_e2e.py` | Full workflow, config persistence, Engine lifecycle, FSM+Audio integration | 827 |
| `test_language_detection.py` | Auto-detect language, duration detection, config persistence | 301 |

**Total:** ~2600+ lines of tests covering all non-macOS-only code.

---

## 6. Installation & Deployment

**`install.sh`:**
1. Checks for python3
2. Creates `.venv` if needed → installs `faster-whisper`, `pyobjc-framework-Quartz`, `rumps`, `Pillow`
3. Generates icons via `generate_icons.py` if missing
4. Creates LaunchAgent `com.whispy.plist` → `~/Library/LaunchAgents/`
5. Loads the LaunchAgent

**LaunchAgent Plist:**
- Program: `.venv/bin/python3 whispy_daemon.py`
- RunAtLoad: true, KeepAlive: true
- StandardOut: `~/.whispy.log`, StandardError: `~/.whispy-error.log`
- PATH: `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin`

**`generate_icons.py`:** Creates 5 icons (22x22 PNG, black/transparent) via PIL:
- `mic-idle.png` — Microphone only
- `mic-recording-{1,2,3}.png` — Microphone + 1-3 wave arcs
- `mic-transcribing.png` — Microphone + 3 animation dots

---

## 7. Required macOS Permissions

| Permission | Why | Where to configure |
|---|---|---|
| **Microphone** | Audio capture via sounddevice/PortAudio | System Settings → Privacy → Microphone |
| **Input Monitoring** | CGEventTap for Fn key detection | System Settings → Privacy → Input Monitoring |
| **Accessibility** | osascript keystroke injection | System Settings → Privacy → Accessibility |

---

## 8. OpenSpec Specifications

| Spec | File | Content |
|---|---|---|
| **core-engine** | `openspec/specs/core-engine/spec.md` | Config loading, model reload |
| **api-interface** | `openspec/specs/api-interface/spec.md` | REST endpoints, config management |
| **event-listener** | `openspec/specs/event-listener/spec.md` | Fn key detection, event loop |
| **text-injection** | `openspec/specs/text-injection/spec.md` | System injection, clipboard |
| **language-detection** | `openspec/changes/tests-and-language-fix/specs/language-detection/spec.md` | Auto-detect reliability, config persistence |
| **testing** | `openspec/changes/tests-and-language-fix/specs/testing/spec.md` | Core engine, injection, API, audio, test infrastructure |

---

## 9. Directory Structure

```
whispy/
├── whispy_daemon.py             # Entry point
├── pyproject.toml               # Project config, dependencies, pytest
├── install.sh                   # Setup script (venv, LaunchAgent)
├── generate_icons.py            # Icon generation (PIL)
├── src/whispy/                  # Python package
│   ├── core/                    # Engine, state machine, audio, config
│   ├── hardware/                # Event tap, text injection
│   ├── ui/                      # Menu bar, indicators, audio level
│   └── api/                     # HTTP server
├── icons/                       # Menu bar icons (5 PNG files)
├── src/
│   └── whispy/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── engine.py        # Engine, DictationState, config
│       │   ├── state_machine.py # FSM (IDLE/RECORDING/TRANSCRIBING)
│       │   └── audio.py         # AudioEngine (sounddevice + Whisper)
│       ├── hardware/
│       │   ├── __init__.py
│       │   ├── event_tap.py     # Fn key detection (CGEventTap)
│       │   └── injection.py     # Text injection (osascript)
│       ├── ui/
│       │   ├── __init__.py
│       │   └── menu_bar.py      # rumps menu bar app
│       └── api/
│           ├── __init__.py
│           └── server.py        # HTTP server (port 9090)
├── tests/
│   ├── conftest.py              # Shared fixtures, macOS mocks
│   ├── test_state_machine.py    # FSM tests (434 lines)
│   ├── test_engine.py           # Engine + config tests (257 lines)
│   ├── test_audio.py            # AudioEngine tests (217 lines)
│   ├── test_injection.py        # TextInjector tests (166 lines)
│   ├── test_api/
│   │   ├── conftest.py
│   │   └── test_server.py       # HTTP API tests (202 lines)
│   ├── test_integration.py      # Multi-module integration (236 lines)
│   ├── test_e2e.py              # End-to-end tests (827 lines)
│   └── test_language_detection.py  # Auto-detect regression tests (301 lines)
├── openspec/
│   ├── specs/                   # Core specs
│   └── changes/                 # Changes + added specs
├── README.md                    # User documentation
├── AGENTS.md                    # Agent development guidelines
├── PROJECT_MAP.md               # Project navigation guide
└── CONTEXT.md                   # Technical context overview
```

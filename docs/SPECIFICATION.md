# Whispy — Codebase Specification

## 1. Overview

**Whispy** is a local voice dictation utility that runs as a menu bar / tray daemon on **macOS** and **Linux (X11)**. The user holds a push-to-talk trigger key — the **Fn** key by default on macOS, **Right Ctrl** on Linux, both selectable — to record audio, and releases it to transcribe and inject the text into the active text field. On macOS the trigger is selectable from the menu (Fn, Right Command, Right Option, F13). All processing is local — no audio or text leaves the machine.

By default transcription is **streaming**: while recording, the audio is segmented on silence and each chunk is transcribed in the background, so the assembled text is typed near-instantly on release rather than after a single whole-file pass.

### Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| STT Engine | `faster-whisper` (Whisper models 75 MB → 2.9 GB), always CPU int8 |
| UI | macOS: `rumps` (menu bar) · Linux: `pystray` (tray) |
| Audio Recording | `sounddevice` / PortAudio (`RawInputStream`, 16 kHz mono int16) |
| Voice-activity segmentation | `webrtcvad` (energy-gate fallback when absent) |
| Trigger Key Detection | macOS: `pyobjc-framework-Quartz` (CGEventTap) · Linux: `pynput` |
| Text Injection | macOS: `pbcopy` + `osascript`/System Events · Linux: `xdotool` |
| HTTP Server | `http.server` (stdlib, port 9090, per-install bearer token) |
| Daemon | macOS: `Whispy.app` bundle (autostart via in-app login item, `SMAppService`) · Linux: `systemd --user` unit |

---

## 2. Software Architecture

Whispy is **platform-abstracted**. The core engine depends only on a set of *ports* (structural `typing.Protocol` interfaces in `platform/ports.py`); concrete per-OS *adapters* are bound at runtime by `platform.detect()`, which selects a `PlatformAdapters` bundle based on `sys.platform`.

```
whispy_daemon.py                ← Entry point (main / --headless / --doctor)
  │
  ├── platform.detect() → PlatformAdapters
  │     ├── default_trigger          (macOS keycode 63 / Linux "ctrl_r")
  │     ├── make_audio_recorder()    → core/audio.py AudioEngine (cross-platform)
  │     ├── make_text_injector()     → macOS hardware/injection.py · Linux platform/linux/injection.py
  │     ├── make_notifier()          → macOS platform/macos/notifier.py · Linux platform/linux/notifier.py
  │     ├── make_hotkey_listener()   → macOS hardware/event_tap.py · Linux platform/linux/hotkey.py
  │     └── make_tray()              → macOS ui/menu_bar.py · Linux platform/linux/tray.py
  │
  ├── Engine (core/engine.py)        ← Central orchestrator, depends only on the ports
  │     ├── StateMachine (core/state_machine.py)  ← FSM IDLE → RECORDING → TRANSCRIBING → IDLE
  │     ├── AudioEngine (core/audio.py)           ← capture + segmentation + transcription
  │     ├── hotkey listener (port)                ← trigger-key press/release
  │     └── text injector (port)                  ← inject transcribed text
  │
  └── HTTP Server (api/server.py)    ← REST API on 127.0.0.1:9090, bearer-token auth,
                                       single-instance lock
```

### Main Data Flow (streaming, default)

```
[Trigger pressed]
  → hotkey listener resolves press → Engine._notify_fn_pressed()
  → notifier.recording_started()  (system "record" sound)
  → Engine.start_recording() → AudioEngine.start()
      → FSM: IDLE → RECORDING
      → sounddevice RawInputStream (16 kHz mono int16) → unique temp WAV
      → each captured block is fed to the VAD SpeechSegmenter
  → UI: waveform window shown; menu-bar braille title animates; status "Recording"

[during recording — streaming]
  → on a silence boundary (or max chunk length), AudioEngine emits a chunk WAV
  → Engine chunk worker transcribes each chunk in order (clean_text), accumulating text

[Trigger released]
  → Engine._handle_trigger_release() → AudioEngine.stop()  (flushes the tail chunk)
      → FSM: RECORDING → TRANSCRIBING
  → transcription worker waits for the chunk queue to drain, assembles the text,
    injects it once via the text injector (avoids mid-recording focus steal)
  → notifier.transcription_succeeded()  (success sound, only if text was produced)
  → FSM: TRANSCRIBING → IDLE; status "Ready"
```

When `streaming_enabled` is `False`, the legacy record-then-transcribe path runs: `run_transcription()` transcribes the whole WAV once on release.

---

## 3. Module Specifications

### 3.1 `whispy_daemon.py` — Entry Point

**Purpose:** initialization, SSL/logging setup, single-instance acquisition, startup orchestration.

- Points `SSL_CERT_FILE`/`SSL_CERT_DIR` at certifi (the `.app` bundle has no system CA file).
- Forces UTF-8 stdout/stderr and a UTF-8 file handler at `~/.whispy.log`.
- `CONFIG_PATH`: `~/.config/whispy/config.json`, or `$WHISPY_CONFIG` when set (used by the validation harness).

**`main()`:** `load_config` → `DictationState` → `Engine(state, config_path)` → acquire the single-instance lock by binding `:9090` (with the per-install token) **before** any heavy/device init; exit if another instance holds it → `engine._adapters.make_tray(engine)` → `engine.start()` → SIGTERM handler → `app.run()`.

**`run_headless()`** (`--headless`): boots `Engine` + HTTP server with no tray, lets the port drift (`max_attempts=10`), prints `WHISPY_HEADLESS_READY <port>`, blocks until SIGTERM/SIGINT. Used by the validation harness.

**`--doctor`:** runs `whispy.doctor.run_doctor()` and exits.

---

### 3.2 `src/whispy/core/config.py` — Configuration

Owns loading, validation, and migration of the config file (previously inline in `engine.py`; re-exported from `engine.py` for the UI/API).

**`DEFAULT_CONFIG`:**
```python
{
    "model_size": "small",            # tiny, base, small, medium, large-v3
    "language": "fr",                 # fr, en
    "beam_size": 1,
    "best_of": 2,
    "copy_to_clipboard": False,
    "start_at_login": False,          # macOS .app bundle only
    "auto_detect_min_duration": 0.5,
    "min_recording_duration": 0.3,
    "custom_vocabulary": [],          # terms to bias the decoder toward
    "trigger": None,                  # None = platform default; int keycode or key name
    # streaming / incremental transcription
    "streaming_enabled": True,
    "pause_ms": 600,                  # trailing silence that closes a chunk
    "min_chunk_s": 0.4,               # chunk shorter than this is discarded
    "max_chunk_s": 12.0,              # hard cap: force-flush run-on speech
    "vad_aggressiveness": 2,          # WebRTC VAD 0-3
}
```

There is **no** `compute_key` — the model always loads with `device="cpu", compute_type="int8"`.

- **`VALID_MODEL_SIZES`** = `["tiny", "base", "small", "medium", "large-v3"]`
- **`SUPPORTED_LANGUAGES`** = `{"fr": "French", "en": "English"}` (no `"auto"`)
- **`MODEL_PRESETS`** — `model_size → {label, description}` for the UI
- **`TRIGGER_PRESETS`** — ordered `[(label, value)]`: `("Fn", None)`, `("Right Command", 54)`, `("Right Option", 61)`, `("F13", 105)` (macOS keycodes; `None` = platform default)
- **`CONFIG_VERSION`** = `1`

**Functions:**

| Function | Purpose |
|---|---|
| `load_config(path)` | Load JSON → validate → migrate (only if the file loaded). Falls back to defaults on missing/corrupt file. |
| `save_config(config, path)` | Atomic write (temp + `os.replace`), filtered to known keys + `_version`. |
| `_validate_config(config)` | Returns a cleaned copy: starts from defaults, merges known keys, range/type-checks every field, drops unknown keys, normalizes `custom_vocabulary`/`trigger`. Invalid values fall back to the default with a stderr warning. |
| `_migrate_config(config, path)` | Adds any missing default keys, stamps `_version = CONFIG_VERSION`, persists. |
| `get_default_config_path()` | `~/.config/whispy/config.json`. |

---

### 3.3 `src/whispy/core/engine.py` — Core Engine

`Engine.__init__(state, config_path=None, adapters=None)` binds the OS seams via `adapters or detect()` and depends only on the ports. It builds the `StateMachine`, the audio recorder, the text injector, and the notifier from the adapter factories, and registers FSM callbacks that keep `DictationState` in sync.

**`DictationState`** — shared cross-thread state container:

| Attribute | Type | Description |
|---|---|---|
| `is_recording` / `is_transcribing` | bool | Lifecycle flags |
| `model` | WhisperModel \| None | Loaded model |
| `model_loading` | bool | Load in progress |
| `last_transcription` | str \| None | Last transcribed text |
| `fn_listener_active` | bool | Trigger listener active |
| `config` | dict | Current configuration |
| `lock` | threading.Lock | Thread-safe lock |
| `stop_event` | threading.Event | Wakes the transcription worker |
| `recording_process` | Any | Legacy field |
| `app` | tray app \| None | UI reference |

**`Engine` — selected methods:**

| Method | Purpose |
|---|---|
| `start()` | Platform pre-flight (Wayland warning on Linux; mic / Input Monitoring / Accessibility / Automation prompts on macOS), then start trigger listener, transcription worker, chunk worker, and async model load. |
| `stop()` | Stop worker, chunk worker, and listener. |
| `start_recording()` / `stop_recording()` / `get_level()` | Delegate to `AudioEngine`. |
| `resolve_trigger()` | Configured trigger, or `adapters.default_trigger` (Fn keycode 63 / `"ctrl_r"`) when unset. |
| `start_fn_listener()` / `stop_fn_listener()` | Build/start/stop the hotkey listener from the adapter; press starts recording, release stops + wakes the worker. |
| `run_transcription()` | Whole-file path: transcribe `recording_path`, `clean_text`, inject, cleanup. |
| `_enqueue_chunk` / `_chunk_worker_loop` / `start_chunk_worker` / `stop_chunk_worker` | Streaming chunk pipeline: a single FIFO worker transcribes chunk WAVs in order and accumulates text; the assembled text is injected once on release. |
| `transcribe_file(path)` | Deterministic seam: transcribe an allow-listed WAV with the current config; no inject, no delete. (`POST /transcribe-file`) |
| `stream_file(path)` | Deterministic seam: replay a WAV through live segmentation + per-chunk transcription; returns ordered chunk texts. (`POST /stream-file`) |
| `update_config(updates)` | Apply known keys, persist, react live: clipboard toggle, model reload flag, restart listener on trigger change, re-wire streaming on streaming-key change. Returns `True` if a model reload is needed. |
| `get_status()` | `{is_recording, is_transcribing, fn_pressed, fn_listener_active, model_loaded, model_loading, fsm}`. |
| Callback registries | `on_status_change`, `on_recording_start/stop`, `on_fn_pressed/released`, `on_injection_permission_denied`, `on_model_load_failed`. |

**Model loading:** `_load_model(config)` builds `WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=…)`, trying the local HF cache first (`local_files_only=True`) and falling back to an online download. `load_model_async(engine)` runs it in a daemon thread with one retry, surfacing failure via the model-load-failed callback.

**`RECORDING_PATH`** lives in `core/audio.py` (`<tempdir>/whispy.wav`); each recording actually uses a unique temp path.

---

### 3.4 `src/whispy/core/state_machine.py` — FSM

**`State` (Enum):** `IDLE`, `RECORDING`, `TRANSCRIBING`. **`InvalidTransitionError`** for illegal transitions.

Valid transitions: `IDLE → RECORDING → TRANSCRIBING → IDLE`. `start_recording()` force-resets a stuck `TRANSCRIBING` to `IDLE` first. Methods: `transition_to`, `start_recording`, `stop_recording`, `transcription_complete`, `on_state_change`, `to_dict`, `transition_history` (bounded `deque(maxlen=1000)`), and `is_idle/is_recording/is_transcribing` properties. Thread-safe via a single `threading.Lock`; callbacks fire outside the lock.

---

### 3.5 `src/whispy/core/audio.py` — Audio Engine

`AudioEngine` captures via `sounddevice` (`RawInputStream`, 16 kHz mono int16) into a unique temp WAV, integrating with the FSM. The same recorder serves macOS and Linux; the import is guarded so the module still loads on a host without PortAudio.

| Method | Purpose |
|---|---|
| `start()` | FSM IDLE→RECORDING, open the capture stream, wait until audio actually flows (cold-start), arm the segmenter when streaming. |
| `stop()` | Stop/close the stream, flush the tail chunk, FSM RECORDING→TRANSCRIBING. |
| `get_level()` | Live mic level 0.0–1.0 for the waveform UI. |
| `transcribe(...)` | `WhisperModel.transcribe` with beam/best-of, VAD filter, optional `initial_prompt` (custom vocabulary), min-duration gating. |
| `configure_streaming(enabled, on_chunk, *, pause_ms, min_chunk_s, max_chunk_s, aggressiveness)` | Enable/disable live segmentation and register the chunk sink. |
| `segment_pcm(pcm, ...)` | Replay raw PCM through the live segmenter; returns chunk WAV paths (drives `stream_file`). |
| `_get_audio_duration` / `cleanup_audio_file` | WAV-header duration; temp-file cleanup. |

`strip_whisper_credit()` here is a legacy regex; the canonical cleaning is `core/text_cleaner.clean_text`.

---

### 3.6 `src/whispy/core/segmentation.py` — Voice-Activity Segmentation

`SpeechSegmenter` decides chunk boundaries frame-by-frame for streaming. It uses `webrtcvad` when available (gain-independent), falling back to a normalized-RMS energy gate. Capture is 16 kHz mono int16; frames are 30 ms (480 samples / 960 bytes). A boundary is emitted when buffered speech is followed by ≥ `pause_ms` of silence (and ≥ `min_chunk_s`), or when the buffer reaches `max_chunk_s` (forced flush). `feed(raw) → bool` (boundary occurred), `flush_tail() → bool` (pending chunk on stop), `reset_chunk()`, `has_pending`. The segmenter never drops audio — it only decides cut points.

---

### 3.7 `src/whispy/core/text_cleaner.py` — Output Cleaning

`clean_text(text)` strips Whisper watermark credit phrases (French/English, prefix-anchored) and known hallucination phrases (anywhere), then collapses whitespace. Returns `None` for `None`, `""` when nothing meaningful remains. Applied to every transcription before injection.

---

### 3.8 `src/whispy/core/auth.py` — Per-Install API Token

Loopback is not a boundary against the browser (any page can `fetch()` `127.0.0.1`; DNS rebinding can pose as it), so the HTTP API requires a per-install bearer token. `AUTH_HEADER="Authorization"`, `AUTH_SCHEME="Bearer"`. The token lives beside the config (`config.json` → `config.token`) with `0600` permissions, so a throwaway `$WHISPY_CONFIG` gets its own token. `load_or_create_token(config_path)` (daemon boot), `read_token(config_path)` (native clients: doctor, harness), `token_path(config_path)`.

---

### 3.9 `src/whispy/core/paths.py` — Path Resolution

Pure, rumps-free path helpers. `resolve_daemon_script()` / `daemon_script_exists()` (anchored to the package, not the CWD), `resolve_app_bundle()` (the `.app` ancestor of `sys.executable`, else `None`), and `transcribe_allow_dir()` — the only directory `POST /transcribe-file` / `/stream-file` may read (defaults to `tests/fixtures/audio`, overridable via `WHISPY_TRANSCRIBE_DIR`).

---

### 3.10 `src/whispy/ui/menu_bar.py` — Menu Bar UI (macOS)

`WhisperMenuBarApp(rumps.App)` is created with `icon=None`; the menu-bar **title** is an animated unicode braille waveform (no PNG icons in the title). An always-on `rumps.Timer` (interval `WAVEROWS_INTERVAL = 0.09 s`) ticks `_tick_anim`, which scrolls the waveform only while *active* (listening / recording / transcribing / loading) and otherwise shows the static idle frame. It also rebuilds the green accent colors when the system flips light/dark and drains queued permission warnings on the main thread.

**Menu structure (English):**
```
Whispy · voice dictation        (header, disabled)
Ready / Recording / Transcribing… / Loading model (…)… / ⚠ Model not loaded
⚠ Can't type — fix permissions…  (hidden until a keystroke is denied)
---
Settings                        (section header, disabled)
Model: <current>                (submenu of MODEL_PRESETS, checkmarked)
Language: <current>             (French / English, checkmarked)
Copy to clipboard               (toggle)
Trigger: <current>              (Fn / Right Command / Right Option / F13, checkmarked)
Start at login                  (toggle — macOS .app bundle only, when SMAppService available)
---
Restart
Quit (⌘Q)
```

There is **no** Compute submenu and **no** "Fn: ✓ active" line. Streaming is always on (no toggle). Selecting a model/language/trigger/clipboard option calls `engine.update_config(...)` and applies live (model reload, listener restart). **Restart** spawns a detached waiter (`_RELAUNCH_WAITER`) that polls the `:9090` single-instance lock until this instance releases it, then relaunches — so the new daemon never races the old one onto a fallback port. A `WaveformWindow` shows an audio-reactive visualization during recording, driven by `engine.get_level()` (never a second mic stream).

---

### 3.11 `src/whispy/api/server.py` — HTTP API

**Bind:** `127.0.0.1:9090`. Binding the port is the **single-instance lock**: `start_http_server(engine, auth_token=None, start_port=9090, max_attempts=1)` binds `start_port` exclusively — with the default `max_attempts=1` a busy port raises `OSError` (no port drift), so a second daemon fails fast. The headless harness passes a higher `max_attempts` to drift to a free port.

**Per-request defenses (`_authorized`)**, applied to every GET and POST before any side effect:
1. **Host pinning** — `Host` must be `127.0.0.1:<port>` or `localhost:<port>` (DNS-rebinding defense) → `403`.
2. **Origin/Referer rejection** — any `Origin`/`Referer` (native clients send neither; browsers always do) → `403`.
3. **Bearer token** — `Authorization: Bearer <token>` compared in constant time → `401` on mismatch.

**Body cap:** `MAX_BODY_BYTES = 64 KiB`; oversized → `413`, invalid JSON → `400`.

**GET:**

| Endpoint | Response |
|---|---|
| `/status` | `engine.get_status()` |
| `/config` | full `engine.state.config` dict (no `compute_key`) |
| `/last-transcription` | `{text: str \| None}` |
| other | `404 {"error": "not found"}` |

**POST:**

| Endpoint | Body | Response |
|---|---|---|
| `/start` | — | `{"status": "recording"}` + record sound |
| `/stop` | — | `{"status": "done", "text": …}` (sync stop + transcribe) + success sound |
| `/stop-async` | — | `{"status": "stopping"}` (wakes the worker) |
| `/transcribe-file` | `{path}` | `{"text": …}`; path must resolve inside `transcribe_allow_dir()` (else `403`); `409` if model unloaded/file missing |
| `/stream-file` | `{path}` | `{"texts": [...], "text": "…"}`; same allow-dir guard; `500` on internal error, `409` if model unloaded/file missing |
| `/config` | `{…}` | `{"status": "ok", "config": …}`; rejects deprecated `trigger_key` and `compute_key` with `400`; reloads model if needed |
| other | — | `404 {"error": "not found"}` |

---

### 3.12 `src/whispy/hardware/event_tap.py` + `event_decode.py` — Trigger Listener (macOS)

`event_tap.py` is the thin OS shell: a **listen-only** `CGEventTap` (needs only Input Monitoring; never modifies events) on a dedicated CFRunLoop thread, listening for `FlagsChanged` + `KeyDown` + `KeyUp`. It re-arms itself if macOS disables the tap, and contains callback exceptions so the listener thread never dies. `EventTapListener(trigger_keycode=DEFAULT_TRIGGER_KEYCODE, on_trigger_press, on_trigger_release)` — the trigger keycode is now **configurable**, resolved by `Engine.resolve_trigger()` (the trigger is selectable from the menu, no longer hard-coded Fn).

`event_decode.py` is the pure, unit-testable decoding layer (no Quartz import):
- `DEFAULT_TRIGGER_KEYCODE = 63` (Fn / Globe), `NX_SECONDARYFNMASK = 0x800000`.
- `_KEYCODE_TO_NAME` — keycode → human name table; `keycode_to_name(keycode)`.
- `decode_trigger_event(kind, keycode, flags, trigger_keycode, prev_flags)` — returns `"press"`/`"release"`/`None`. Fn uses the secondary-Fn flag bit; a non-default *modifier* trigger derives press/release from the flag-bit transition between `prev_flags` and `flags`; a regular key uses key-down/up.
- `decode_key_match(kind, key_name, trigger_key)` — platform-neutral key-match decode used by the Linux/pynput listener.

---

### 3.13 `src/whispy/hardware/injection.py` — Text Injection (macOS)

AppleScript **string interpolation** was removed for security: text is now passed as **data**, never built into a script source. `TextInjector(copy_to_clipboard=…)`:
- **Clipboard mode** (`copy_to_clipboard=True`): write text to `pbcopy`'s stdin, then a constant `osascript`/System Events `keystroke "v" using command down`.
- **Keystroke mode** (`copy_to_clipboard=False`): an `osascript - <text>` script read from stdin that types `item 1 of argv` — the text reaches it via `argv`, so no escaping and no injection.

System Events is Apple-signed, so it can post synthetic keystrokes even though Whispy is self-signed (a direct `CGEventPost` would be dropped). It needs Whispy's Accessibility + Automation grants. A denied keystroke (osascript error `1002`, locale-independent) leaves the text on the clipboard and fires a debounced `on_permission_denied` callback so the UI can prompt the user.

---

### 3.14 `src/whispy/platform/` — Platform Abstraction

- **`ports.py`** — `runtime_checkable` `Protocol`s: `HotkeyListener`, `TextInjector`, `AudioRecorder`, `Notifier`, `TrayUI`, plus the `Make*` factory type aliases.
- **`detect.py`** — `detect(platform=None)` returns a frozen `PlatformAdapters(name, default_trigger, make_audio_recorder, make_text_injector, make_notifier, make_hotkey_listener, make_tray)`. Factories import their concrete modules lazily so selecting one OS never drags in the other's optional deps. `darwin → macOS` (default trigger keycode 63), `linux* → Linux` (default trigger `"ctrl_r"`); any other platform raises `NotImplementedError`.
- **`platform/macos/`** — `notifier.py` (`MacNotifier`, `afplay` system sounds), `permissions.py` (mic / Input Monitoring / Accessibility / Automation prompts), `login_item.py` (`SMAppService` "start at login": `available`, `is_enabled`, `enable`, `disable`).
- **`platform/linux/`** — `hotkey.py` (`PynputHotkeyListener`), `injection.py` (`XdotoolInjector`), `notifier.py` (`LinuxNotifier`), `tray.py` (`PystrayApp`), `session.py` (`warn_if_wayland`).

---

### 3.15 `src/whispy/ui/` — Other UI Modules

- **`unicode_anim.py`** — vendored braille `WAVEROWS` frames (16), `WAVEROWS_INTERVAL = 0.09`, `IDLE_FRAME`, `select_frame(frame_index, is_active)`. Pure data, no dependency.
- **`menu_theme.py`** — brand-green accented menu titles (`status_title`, `section_title`, `check_title`, `toggle_title`, `apply_title`, `is_dark_appearance`), re-picking colors for light/dark.
- **`waveform_window.py`** — `WaveformWindow`, the audio-reactive recording visualization driven by `engine.get_level()`.
- **`level_math.py`** — pure helpers for mapping mic level → bar heights (unit-tested).

---

### 3.16 `src/whispy/doctor.py` — Environment Diagnostic

Run via `python whispy_daemon.py --doctor` (or `make doctor`). Each check returns a `CheckResult(name, status, detail)` with status `ok`/`warn`/`fail`; `run_doctor()` prints a report and returns `1` if any check failed. Checks: audio backend (`sounddevice`), `xdotool` (Linux only), Whisper model presence in the HF cache, Input Monitoring, Accessibility, Microphone (macOS), and whether the daemon answers on `:9090` (authenticated with the per-install token).

---

## 4. Configuration

**Location:** `~/.config/whispy/config.json` (or `$WHISPY_CONFIG`). Token: sibling `config.token` (`0600`).

| Key | Type | Default | Notes |
|---|---|---|---|
| `model_size` | str | `"small"` | tiny, base, small, medium, large-v3 |
| `language` | str | `"fr"` | fr, en (no auto) |
| `beam_size` | int | `1` | ≥ 1 |
| `best_of` | int | `2` | ≥ 1 |
| `copy_to_clipboard` | bool | `False` | clipboard-paste vs. direct keystroke |
| `start_at_login` | bool | `False` | macOS `.app` bundle only |
| `auto_detect_min_duration` | float | `0.5` | ≥ 0 |
| `min_recording_duration` | float | `0.3` | ≥ 0 |
| `custom_vocabulary` | list[str] | `[]` | terms biasing the decoder (`initial_prompt`) |
| `trigger` | int \| str \| null | `null` | `null` = platform default; macOS keycode or key name |
| `streaming_enabled` | bool | `True` | streaming vs. whole-file transcription |
| `pause_ms` | number | `600` | > 0 |
| `min_chunk_s` | number | `0.4` | ≥ 0 |
| `max_chunk_s` | number | `12.0` | > `min_chunk_s` |
| `vad_aggressiveness` | int | `2` | 0–3 |

A hidden `_version` key tracks migrations (`CONFIG_VERSION = 1`). There is **no** `compute_key`. Config is validated on load (invalid values fall back to defaults; unknown keys dropped) and migrated to add missing keys.

---

## 5. Tests

**Execution:** `./.venv/bin/pytest` from the repo root.

**Infrastructure:** `tests/conftest.py` (mocks Quartz/rumps, shared fixtures), `tests/test_api/conftest.py` (`mock_engine`), `tests/fixtures/` (audio fixtures), `tests/validation/` (the release-validation harness: `harness.py`, `matrix.py`, `operator.py`, `outcomes.py`, `preflight.py`, `run.py`).

**Test files** (`tests/`):

`test_state_machine.py`, `test_engine.py`, `test_audio.py`, `test_injection.py`, `test_integration.py`, `test_e2e.py`, `test_e2e_smoke.py`, `test_e2e_smoke_linux.py`, `test_event_tap_e2e.py`, `test_event_decode.py`, `test_language_detection.py`, `test_transcription_quality.py`, `test_segmentation.py`, `test_text_cleaning.py`, `test_config_validation.py`, `test_simplify_config_ui.py`, `test_menu_bar.py`, `test_menu_theme.py`, `test_waveform.py`, `test_anim_frames.py`, `test_level_math.py`, `test_auth.py`, `test_paths.py`, `test_permissions.py`, `test_platform_detect.py`, `test_linux_adapters.py`, `test_doctor.py`, `test_error_handling.py`, `test_install_scripts.py`, `test_deploy_workflow.py`, `test_validation_core.py`, `test_website.py`, plus `tests/test_api/test_server.py`.

---

## 6. Installation & Deployment

**`install.sh`:**
1. Checks for python3
2. Creates `.venv` if needed → installs `faster-whisper`, `pyobjc-framework-Quartz`, `rumps`, `Pillow`
3. Generates icons via `generate_icons.py` if missing
4. **macOS:** provisions the venv only — `make app` then builds `Whispy.app` (py2app). Autostart is the in-app "Start at login" toggle (`SMAppService`); **no LaunchAgent is created**.
5. **Linux:** installs and enables a `systemd --user` unit (`whispy.service`).

`install.sh --uninstall` removes the venv and, on macOS, boots out + deletes any legacy `com.whisper-dictation` / `com.whispy` LaunchAgent left by a pre-rebrand install.

**Distribution:** the signed `Whispy.app` is the sole recommended macOS install — built locally (so it is **not** Gatekeeper-quarantined), no Homebrew and no notarized download. The `curl | bash` one-liner (`scripts/bootstrap.sh`) automates clone → `install.sh` → `make app` → copy to `/Applications`. Linux installs via the same one-liner or `./install.sh` directly (venv + systemd).

**`generate_icons.py`:** generates the single brand waveform glyph `icons/whispy.png` via PIL — 5 rounded bars (center-tall, mirroring `website/assets/logo.svg`) painted with a vertical mint→teal gradient (`#3fe0bd → #17a8b0`), faded edge bars, and a soft glow, rendered at 2× (44×44) for retina sharpness. (This is a brand asset; the menu-bar *title* is the animated braille waveform, not this PNG.)

---

## 7. Required macOS Permissions

| Permission | Why | Where to configure |
|---|---|---|
| **Microphone** | Audio capture via sounddevice/PortAudio | System Settings → Privacy → Microphone |
| **Input Monitoring** | CGEventTap for the trigger key | System Settings → Privacy → Input Monitoring |
| **Accessibility** | osascript keystroke injection | System Settings → Privacy → Accessibility |
| **Automation (Apple Events)** | osascript driving System Events | System Settings → Privacy → Automation |

The engine requests all four explicitly on macOS at startup. On Linux/X11, `xdotool` is required for injection (the daemon warns, but does not block, under Wayland).

---

## 8. OpenSpec Specifications

Capabilities under `openspec/specs/`:

| Spec | Content |
|---|---|
| `api-interface` | HTTP endpoints, auth, config management |
| `audio-capture` | sounddevice capture, lifecycle |
| `ci-cd-pipeline` | CI/CD pipeline |
| `core-engine` | Orchestration, model load/reload |
| `end-to-end-smoke` | E2E smoke coverage |
| `event-listener` | Trigger detection / event loop |
| `linux-support` | Linux/X11 adapters |
| `login-item-autostart` | macOS "start at login" (SMAppService) |
| `macos-install` | macOS `.app` install/distribution |
| `menu-bar-theming` | Menu-bar accent/theme behavior |
| `platform-abstraction` | Ports + adapters |
| `promotional-website` | Website sync rules |
| `recording-visualization` | Waveform window |
| `release-validation` | Release validation harness/outcomes |
| `single-instance-lock` | `:9090` single-instance bind |
| `streaming-transcription` | Segmentation + chunk pipeline |
| `text-cleaning` | Credit/hallucination stripping |
| `text-injection` | Clipboard/keystroke injection |
| `transcription-quality` | Decoder params, quality |
| `trigger-selection-ui` | Selectable push-to-talk trigger |

---

## 9. Directory Structure

Whispy supports **macOS and Linux (X11)**.

```
whispy/
├── whispy_daemon.py             # Entry point (main / --headless / --doctor)
├── pyproject.toml               # Project config, dependencies, pytest
├── Makefile                     # app / doctor / test targets
├── install.sh                   # Setup (venv; macOS .app via make app, Linux systemd)
├── generate_icons.py            # Brand waveform glyph (PIL)
├── src/whispy/                  # Python package
│   ├── core/
│   │   ├── engine.py            # Engine, DictationState, model load, streaming pipeline
│   │   ├── config.py            # DEFAULT_CONFIG, validation, migration
│   │   ├── state_machine.py     # FSM (IDLE/RECORDING/TRANSCRIBING)
│   │   ├── audio.py             # AudioEngine (sounddevice capture + transcription)
│   │   ├── segmentation.py      # SpeechSegmenter (WebRTC VAD streaming)
│   │   ├── text_cleaner.py      # clean_text (credits / hallucinations)
│   │   ├── auth.py              # per-install API bearer token
│   │   └── paths.py             # daemon/app-bundle/allow-dir path resolution
│   ├── hardware/                # macOS hardware seams
│   │   ├── event_tap.py         # CGEventTap shell (configurable trigger)
│   │   ├── event_decode.py      # pure trigger-event decoding + keycode table
│   │   └── injection.py         # pbcopy + osascript/System Events injection
│   ├── platform/                # Platform abstraction
│   │   ├── ports.py             # Protocol ports
│   │   ├── detect.py            # detect() → PlatformAdapters
│   │   ├── macos/               # notifier, permissions, login_item
│   │   └── linux/               # hotkey, injection, notifier, tray, session
│   ├── ui/
│   │   ├── menu_bar.py          # rumps menu bar app (macOS)
│   │   ├── menu_theme.py        # accent/theme titles
│   │   ├── unicode_anim.py      # braille waveform frames
│   │   ├── waveform_window.py   # audio-reactive recording window
│   │   └── level_math.py        # level→bar math
│   ├── api/
│   │   └── server.py            # HTTP server (port 9090, auth, single-instance lock)
│   └── doctor.py                # environment diagnostic (--doctor)
├── icons/                       # Brand waveform PNG
├── tests/                       # Test suite (+ test_api/, validation/, fixtures/)
├── scripts/                     # bootstrap.sh (curl | bash installer), etc.
├── packaging/
│   └── macos/                   # py2app / .app packaging
├── website/                     # Promotional site (kept in sync with features)
├── docs/                        # Documentation (this file, deployment, …)
├── openspec/                    # specs/ (capabilities) + changes/
├── README.md                    # User documentation
├── AGENTS.md / CLAUDE.md        # Agent development guidelines
└── CHANGELOG.md                 # Release history
```

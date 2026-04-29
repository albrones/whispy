# Graph Report - whispy  (2026-04-28)

## Corpus Check
- 30 files · ~152,362 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1042 nodes · 3977 edges · 65 communities detected
- Extraction: 20% EXTRACTED · 80% INFERRED · 0% AMBIGUOUS · INFERRED: 3163 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]

## God Nodes (most connected - your core abstractions)
1. `StateMachine` - 447 edges
2. `AudioEngine` - 433 edges
3. `State` - 419 edges
4. `Engine` - 414 edges
5. `TextInjector` - 378 edges
6. `DictationState` - 374 edges
7. `EventTapListener` - 228 edges
8. `RequestHandler` - 156 edges
9. `InvalidTransitionError` - 49 edges
10. `TestFullFnWorkflowIntegration` - 34 edges

## Surprising Connections (you probably didn't know these)
- `Tests for TextInjector with mocked subprocess calls.` --uses--> `TextInjector`  [INFERRED]
  tests/test_injection.py → src/whispy/hardware/injection.py
- `Test clipboard-based text injection.` --uses--> `TextInjector`  [INFERRED]
  tests/test_injection.py → src/whispy/hardware/injection.py
- `Test direct keystroke text injection.` --uses--> `TextInjector`  [INFERRED]
  tests/test_injection.py → src/whispy/hardware/injection.py
- `Test that empty or None text does not call subprocess.` --uses--> `TextInjector`  [INFERRED]
  tests/test_injection.py → src/whispy/hardware/injection.py
- `Whitespace text is not empty, so it should call subprocess.` --uses--> `TextInjector`  [INFERRED]
  tests/test_injection.py → src/whispy/hardware/injection.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.02
Nodes (209): AudioEngine, Detect audio file duration in seconds using the wave module.          Falls back, Manages audio recording and transcription operations.      Integrates with the S, BaseHTTPRequestHandler, mock_engine(), Create a mock Engine with common return values., Create a mock Engine with common return values., Create a temporary directory that is cleaned up after the test. (+201 more)

### Community 1 - "Community 1"
Cohesion: 0.04
Nodes (36): Start audio recording via FSM -> AudioEngine., Stop recording and transition to TRANSCRIBING., Convert the configured trigger_key to a keycode., Transition from IDLE to RECORDING. Returns False if already recording., Transition from RECORDING to TRANSCRIBING. Returns False if not recording., Transition from TRANSCRIBING to IDLE. Returns False if not transcribing., Register a callback for when the FSM enters a specific state., Call all registered callbacks for the new state. (+28 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (82): Stop recording and transition to TRANSCRIBING. Returns False if not recording., Stop recording and transition to TRANSCRIBING. Returns False if not recording., Transcribe an audio file. Returns None if transcription fails., Transcribe an audio file. Returns None if transcription fails., Detect audio file duration in seconds using the wave module.          Falls back, Detect audio file duration in seconds using the wave module.          Falls back, Remove the temporary audio file after transcription., Remove the temporary audio file after transcription. (+74 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (79): Instantiate WhisperModel from config dict., Load the whisper model in a background thread., Load the whisper model in a background thread., Shared state between threads for recording and transcription., Shared state between threads for recording and transcription., Central orchestrator that integrates FSM, audio, hardware, and injection.      R, Central orchestrator that integrates FSM, audio, hardware, and injection.      R, Sync DictationState when FSM enters RECORDING. (+71 more)

### Community 4 - "Community 4"
Cohesion: 0.04
Nodes (24): Audio recording and transcription logic.  Handles audio capture via sox and tran, Core engine — state management, model loading, and transcription orchestration., Apply config updates. Returns True if model reload was triggered., Enum, keycode_to_label(), _keycode_to_name(), Trigger key listener via macOS CGEventTap.  Monitors hardware-level keyboard eve, Convert a macOS keycode to a human-readable name. (+16 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (24): load_config(), Load config from disk, falling back to defaults., Persist config to disk., save_config(), Tests for config validation in save_config and restart path resolution., Test that save_config filters unknown keys., Test that the restart path resolves correctly., The restart path (whispy_daemon.py) should exist at project root. (+16 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (21): Stop recording and transition to TRANSCRIBING. Returns False if not recording., Start recording audio. Returns False if already recording.          Waits for so, Wait for sox to start writing audio to the output file.          Polls the file, Start HTTP server in a daemon thread., start_http_server(), Tests for AudioEngine with mocked subprocess calls., Test AudioEngine.start() behavior., Test AudioEngine.stop() behavior. (+13 more)

### Community 7 - "Community 7"
Cohesion: 0.06
Nodes (22): Return current engine status as a dict., Notify all registered callbacks of state changes., Return current engine status as a dict., Send a JSON HTTP response., Handle POST requests., Stop recording and transcribe synchronously (for /stop endpoint)., engine(), Test Engine start/stop lifecycle. (+14 more)

### Community 8 - "Community 8"
Cohesion: 0.07
Nodes (20): Inject transcribed text into the active application., Copy text to clipboard and paste via Cmd+V., Simulate keystrokes for each character to avoid clipboard interaction., Test TextInjector in both clipboard and keystroke modes., Test text injection via clipboard (default mode)., Test text injection via direct keystrokes., Test that injecting empty text does nothing., Test that quotes in text are properly escaped. (+12 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (16): Remove Whisper credit/watermark prefixes from transcribed text.      Strips Fren, strip_whisper_credit(), Tests for whisper credit stripping in text-cleaning module.  Covers French/Engli, Test that credit matching is case-insensitive., Test edge cases for credit stripping., Text that only contains a credit returns empty string., Test that French Whisper credit prefixes are correctly stripped., Test that English Whisper credit prefixes are correctly stripped. (+8 more)

### Community 10 - "Community 10"
Cohesion: 0.09
Nodes (17): _get(), _post(), Tests for the HTTP API server endpoints.  Uses a real HTTP server with a mock en, Test GET /config endpoint., Test GET /last-transcription endpoint., Test POST /config endpoint., Test POST /start and /stop endpoints., Test unknown endpoint handling. (+9 more)

### Community 11 - "Community 11"
Cohesion: 0.1
Nodes (10): Transcribe an audio file. Returns None if transcription fails., Remove the temporary audio file after transcription., Execute transcription synchronously (called from worker thread)., Test cleanup_audio_file behavior., Test cleanup with default RECORDING_PATH., Test AudioEngine.transcribe() behavior., TestCleanupAudioFile, TestTranscribe (+2 more)

### Community 12 - "Community 12"
Cohesion: 0.14
Nodes (11): Callback invoked for each relevant CGEvent., Test EventTap event callback routing., Simulate a keydown event with keycode 63 (Fn) and secondary flag → on_trigger_pr, Simulate a keyup event for keycode 63 → on_trigger_release., Keycode different from trigger should not trigger callbacks., Test with a custom keycode (e.g., keycode 0 for 'a')., For non-Fn keys, flagschanged event should also trigger press., Fn key with NX_SECONDARYFNMASK flag should trigger press. (+3 more)

### Community 13 - "Community 13"
Cohesion: 0.11
Nodes (17): config_path(), engine(), mock_subprocess(), mock_whisper_model(), Fixtures for HTTP API tests., Mock subprocess.run and subprocess.Popen., Create a temporary directory that is cleaned up after the test., Create a temporary config directory and return the config file path. (+9 more)

### Community 14 - "Community 14"
Cohesion: 0.16
Nodes (10): Start learning mode for the trigger key.          Returns True if learning was s, Stop learning mode and return the learned keycode.          Returns None if no k, Test EventTapListener learning mode., start_learning() then simulate keydown → stop_learning() returns captured keycod, During learning, the current trigger key should be ignored., Non-keydown events during learning should not capture a keycode., stop_learning() without start_learning() should return None., stop_learning() should clear learning state. (+2 more)

### Community 15 - "Community 15"
Cohesion: 0.12
Nodes (9): load_model_async(), Load the whisper model in a background thread., Start the trigger key event tap listener., Stop the trigger key event tap listener., Update the trigger key in config and restart the listener., Start the background transcription worker thread., Stop the background transcription worker thread., Start all engine components. (+1 more)

### Community 16 - "Community 16"
Cohesion: 0.12
Nodes (15): audio(), captured_callbacks(), mock_subprocess(), mock_whisper_model(), E2E tests for EventTapListener and the full FN key → recording → transcription w, Mock subprocess.run and subprocess.Popen., Create a mock WhisperModel with transcribe output., Create a temporary config directory and return the config file path. (+7 more)

### Community 17 - "Community 17"
Cohesion: 0.2
Nodes (6): Test EventTapListener start/stop lifecycle., When Quartz is not available, start() should print a message and not crash., When Quartz is mocked, start() should create and start a thread., Stop should set _stop_event and join the thread., Active flag should be True after start, False after stop., TestEventTapListenerStartStop

### Community 18 - "Community 18"
Cohesion: 0.7
Nodes (4): _draw_mic(), _draw_wave_arc(), generate_icons(), _new_image()

### Community 19 - "Community 19"
Cohesion: 1.0
Nodes (1): Whispy — macOS menu bar speech-to-text daemon.

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (1): Register a callback to be called when state changes.

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (1): Sync DictationState when FSM enters IDLE.

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (1): Enable learning mode — captures the next key press keycode.

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (1): Start the event tap listener in a dedicated thread.

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (1): Disable learning mode and return the learned keycode (if any).

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (1): Sync DictationState when FSM enters RECORDING.

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (1): Update the clipboard copy setting.

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (1): Stop the event tap listener.

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (1): All PRESET_TRIGGERS should map to valid keycodes.

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (2): _load_model(), Instantiate WhisperModel from config dict.

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (1): Get the current state (thread-safe).

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): Return the history of state transitions.

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): Monitors keyboard events via CGEventTap and emits events for a configurable trig

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Start the event tap listener in a dedicated thread.

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): Enable learning mode — captures the next key press keycode.

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): Disable learning mode and return the learned keycode (if any).

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): Stop the event tap listener.

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): Callback invoked for each relevant CGEvent.

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a human-readable name.

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a display label for the UI.

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Injects text into the focused application via osascript.

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Update the clipboard copy setting.

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Inject transcribed text into the active application.

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Copy text to clipboard and paste via Cmd+V.

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Simulate keystrokes for each character to avoid clipboard interaction.

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Monitors keyboard events via CGEventTap and emits events for a configurable trig

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Start the event tap listener in a dedicated thread.

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Enable learning mode — captures the next key press keycode.

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): Disable learning mode and return the learned keycode (if any).

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Stop the event tap listener.

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Callback invoked for each relevant CGEvent.

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a human-readable name.

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a display label for the UI.

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): Possible states of the dictation system.

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Raised when an illegal state transition is attempted.

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): Thread-safe FSM that manages the dictation lifecycle.      Valid transitions:

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): Register a callback for when the FSM enters a specific state.

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): Call all registered callbacks for the new state.

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): Get the current state (thread-safe).

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (1): Return current state as a dictionary.

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Attempt to transition to a new state.          Returns True if the transition wa

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): Transition from IDLE to RECORDING. Returns False if already recording.

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): Transition from RECORDING to TRANSCRIBING. Returns False if not recording.

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (1): Transition from TRANSCRIBING to IDLE. Returns False if not transcribing.

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (1): Return the history of state transitions.

## Knowledge Gaps
- **87 isolated node(s):** `Tests for config validation in save_config and restart path resolution.`, `Test that save_config filters unknown keys.`, `Test that the restart path resolves correctly.`, `The restart path (whispy_daemon.py) should exist at project root.`, `Verify whispy.py does NOT exist (should use whispy_daemon.py).` (+82 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 19`** (2 nodes): `Whispy — macOS menu bar speech-to-text daemon.`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 20`** (2 nodes): `._on_fsm_transcribing()`, `Register a callback to be called when state changes.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 21`** (2 nodes): `._on_fsm_idle()`, `Sync DictationState when FSM enters IDLE.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (2 nodes): `.start_learning()`, `Enable learning mode — captures the next key press keycode.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (2 nodes): `.start()`, `Start the event tap listener in a dedicated thread.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (2 nodes): `.stop_learning()`, `Disable learning mode and return the learned keycode (if any).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (2 nodes): `._on_fsm_recording()`, `Sync DictationState when FSM enters RECORDING.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (2 nodes): `Update the clipboard copy setting.`, `.update_config()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (2 nodes): `.stop()`, `Stop the event tap listener.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (2 nodes): `All PRESET_TRIGGERS should map to valid keycodes.`, `.test_preset_trigger_keys_map_correctly()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (2 nodes): `_load_model()`, `Instantiate WhisperModel from config dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `Get the current state (thread-safe).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `Return the history of state transitions.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `Monitors keyboard events via CGEventTap and emits events for a configurable trig`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Start the event tap listener in a dedicated thread.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `Enable learning mode — captures the next key press keycode.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `Disable learning mode and return the learned keycode (if any).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `Stop the event tap listener.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `Callback invoked for each relevant CGEvent.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `Convert a macOS keycode to a human-readable name.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `Convert a macOS keycode to a display label for the UI.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `Injects text into the focused application via osascript.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `Update the clipboard copy setting.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `Inject transcribed text into the active application.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Copy text to clipboard and paste via Cmd+V.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Simulate keystrokes for each character to avoid clipboard interaction.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `Monitors keyboard events via CGEventTap and emits events for a configurable trig`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `Start the event tap listener in a dedicated thread.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `Enable learning mode — captures the next key press keycode.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `Disable learning mode and return the learned keycode (if any).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `Stop the event tap listener.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Callback invoked for each relevant CGEvent.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Convert a macOS keycode to a human-readable name.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `Convert a macOS keycode to a display label for the UI.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `Possible states of the dictation system.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `Raised when an illegal state transition is attempted.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `Thread-safe FSM that manages the dictation lifecycle.      Valid transitions:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `Register a callback for when the FSM enters a specific state.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `Call all registered callbacks for the new state.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `Get the current state (thread-safe).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `Return current state as a dictionary.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `Attempt to transition to a new state.          Returns True if the transition wa`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `Transition from IDLE to RECORDING. Returns False if already recording.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `Transition from RECORDING to TRANSCRIBING. Returns False if not recording.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `Transition from TRANSCRIBING to IDLE. Returns False if not transcribing.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `Return the history of state transitions.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Engine` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 10`, `Community 11`, `Community 12`, `Community 13`, `Community 14`, `Community 15`, `Community 16`, `Community 17`, `Community 20`, `Community 21`, `Community 25`, `Community 28`?**
  _High betweenness centrality (0.223) - this node is a cross-community bridge._
- **Why does `StateMachine` connect `Community 2` to `Community 0`, `Community 1`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 9`, `Community 11`, `Community 12`, `Community 13`, `Community 14`, `Community 15`, `Community 16`, `Community 17`, `Community 20`, `Community 21`, `Community 25`, `Community 28`, `Community 29`?**
  _High betweenness centrality (0.194) - this node is a cross-community bridge._
- **Why does `AudioEngine` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 11`, `Community 12`, `Community 14`, `Community 15`, `Community 16`, `Community 17`, `Community 20`, `Community 21`, `Community 25`, `Community 28`, `Community 29`?**
  _High betweenness centrality (0.155) - this node is a cross-community bridge._
- **Are the 437 inferred relationships involving `StateMachine` (e.g. with `TestEventTapListenerStartStop` and `TestEventTapCallback`) actually correct?**
  _`StateMachine` has 437 INFERRED edges - model-reasoned connections that need verification._
- **Are the 423 inferred relationships involving `AudioEngine` (e.g. with `TestEventTapListenerStartStop` and `TestEventTapCallback`) actually correct?**
  _`AudioEngine` has 423 INFERRED edges - model-reasoned connections that need verification._
- **Are the 416 inferred relationships involving `State` (e.g. with `TestEventTapListenerStartStop` and `TestEventTapCallback`) actually correct?**
  _`State` has 416 INFERRED edges - model-reasoned connections that need verification._
- **Are the 391 inferred relationships involving `Engine` (e.g. with `Start Whispy: engine, UI, and HTTP server.` and `Start Whispy: engine, UI, and HTTP server.`) actually correct?**
  _`Engine` has 391 INFERRED edges - model-reasoned connections that need verification._
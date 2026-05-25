# Graph Report - whispy  (2026-04-29)

## Corpus Check
- 35 files · ~179,225 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1261 nodes · 4855 edges · 63 communities detected
- Extraction: 18% EXTRACTED · 82% INFERRED · 0% AMBIGUOUS · INFERRED: 3974 edges (avg confidence: 0.54)
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
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
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

## God Nodes (most connected - your core abstractions)
1. `StateMachine` - 554 edges
2. `AudioEngine` - 540 edges
3. `State` - 526 edges
4. `Engine` - 524 edges
5. `TextInjector` - 485 edges
6. `DictationState` - 470 edges
7. `EventTapListener` - 292 edges
8. `RequestHandler` - 209 edges
9. `InvalidTransitionError` - 49 edges
10. `AudioLevelMonitor` - 39 edges

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
Cohesion: 0.03
Nodes (286): AudioEngine, Stop recording and transition to TRANSCRIBING. Returns False if not recording., Stop recording and transition to TRANSCRIBING. Returns False if not recording., Transcribe an audio file. Returns None if transcription fails., Transcribe an audio file. Returns None if transcription fails., Detect audio file duration in seconds using the wave module.          Falls back, Detect audio file duration in seconds using the wave module.          Falls back, Remove the temporary audio file after transcription. (+278 more)

### Community 1 - "Community 1"
Cohesion: 0.02
Nodes (244): BaseHTTPRequestHandler, config_path(), engine(), mock_engine(), mock_subprocess(), mock_whisper_model(), Fixtures for HTTP API tests., Mock subprocess.run and subprocess.Popen. (+236 more)

### Community 2 - "Community 2"
Cohesion: 0.03
Nodes (54): AudioLevelMonitor, Thread-safe audio level monitor using the system microphone.  Reads real-time au, Monitors real-time microphone audio level via sounddevice.      Runs a backgroun, Start monitoring the microphone. Returns False if already started., Stop monitoring and release the microphone device., Compute RMS amplitude from audio input and apply smoothing., Return the current smoothed audio level (0.0-1.0).          Returns 0.0 if the m, FerrofluidView (+46 more)

### Community 3 - "Community 3"
Cohesion: 0.03
Nodes (52): Exception, InvalidTransitionError, Transition from IDLE to RECORDING. Returns False if already recording., Transition from RECORDING to TRANSCRIBING. Returns False if not recording., Transition from TRANSCRIBING to IDLE. Returns False if not transcribing., Raised when an illegal state transition is attempted., Register a callback for when the FSM enters a specific state., Call all registered callbacks for the new state. (+44 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (25): Stop recording and transition to TRANSCRIBING. Returns False if not recording., Start recording audio. Returns False if already recording.          Waits for so, Wait for sox to start writing audio to the output file.          Polls the file, Start HTTP server in a daemon thread, trying consecutive ports if needed., start_http_server(), Tests for AudioEngine with mocked subprocess calls., Test AudioEngine.start() behavior., Test AudioEngine.stop() behavior. (+17 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (21): load_config(), save_config(), Tests for config validation in save_config and restart path resolution., Test that save_config filters unknown keys., Test that the restart path resolves correctly., Test that the restart path resolves correctly., Verify whispy.py does NOT exist (should use whispy_daemon.py)., TestRestartPath (+13 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (17): Remove the temporary audio file after transcription., Callback invoked for each relevant CGEvent., Test cleanup_audio_file behavior., Test cleanup with default RECORDING_PATH., TestCleanupAudioFile, audio(), captured_callbacks(), engine() (+9 more)

### Community 7 - "Community 7"
Cohesion: 0.06
Nodes (17): load_model_async(), Send a JSON HTTP response., Handle POST requests., Stop recording and transcribe synchronously (for /stop endpoint)., engine(), Test Engine start/stop lifecycle., Test Engine config updates work correctly., Test Engine config updates work correctly. (+9 more)

### Community 8 - "Community 8"
Cohesion: 0.07
Nodes (20): Inject transcribed text into the active application., Copy text to clipboard and paste via Cmd+V., Simulate keystrokes for each character to avoid clipboard interaction., Test TextInjector in both clipboard and keystroke modes., Test text injection via clipboard (default mode)., Test text injection via direct keystrokes., Test that injecting empty text does nothing., Test that quotes in text are properly escaped. (+12 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (16): Remove Whisper credit/watermark prefixes from transcribed text.      Strips Fren, strip_whisper_credit(), Tests for whisper credit stripping in text-cleaning module.  Covers French/Engli, Test that credit matching is case-insensitive., Test edge cases for credit stripping., Text that only contains a credit returns empty string., Test that French Whisper credit prefixes are correctly stripped., Test that English Whisper credit prefixes are correctly stripped. (+8 more)

### Community 10 - "Community 10"
Cohesion: 0.07
Nodes (29): audio(), config_dir(), config_path(), _find_free_port(), _http_get(), _http_post(), mock_subprocess(), mock_whisper_model() (+21 more)

### Community 11 - "Community 11"
Cohesion: 0.08
Nodes (16): Transcribe an audio file. Returns None if transcription fails., Detect audio file duration in seconds using the wave module.          Falls back, Test AudioEngine.transcribe() behavior., TestTranscribe, Regression tests for auto-detect language fix.  Tests that the auto-detect langu, Test duration detection for short audio (< 1s)., Test that short audio (< 1s) is handled gracefully., Short audio with language='auto' should not crash. (+8 more)

### Community 12 - "Community 12"
Cohesion: 0.1
Nodes (9): Audio recording and transcription logic.  Handles audio capture via sox and tran, _load_model(), Enum, _keycode_to_name(), Trigger key listener via macOS CGEventTap.  Monitors hardware-level keyboard eve, Convert a macOS keycode to a human-readable name., Text injection via macOS accessibility APIs (osascript).  Handles injecting tran, HTTP API server for external control and status monitoring.  Provides RESTful en (+1 more)

### Community 13 - "Community 13"
Cohesion: 0.13
Nodes (8): _get(), _post(), TestGetConfig, TestGetLastTranscription, TestGetStatus, TestPostConfig, TestPostStartStop, TestUnknownEndpoints

### Community 14 - "Community 14"
Cohesion: 0.7
Nodes (4): _draw_mic(), _draw_wave_arc(), generate_icons(), _new_image()

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (1): Update the clipboard copy setting.

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (1): Start the event tap listener in a dedicated thread.

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (1): Stop the event tap listener.

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (1): Get the current state (thread-safe).

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (1): Return the history of state transitions.

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (1): The restart path (whispy_daemon.py) should exist at project root.

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (1): Verify whispy.py does NOT exist (should use whispy_daemon.py).

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (1): Monitors keyboard events via CGEventTap and emits events for a configurable trig

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (1): Start the event tap listener in a dedicated thread.

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (1): Enable learning mode — captures the next key press keycode.

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (1): Disable learning mode and return the learned keycode (if any).

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (1): Stop the event tap listener.

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (1): Callback invoked for each relevant CGEvent.

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a human-readable name.

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a display label for the UI.

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (1): Monitors keyboard events via CGEventTap and emits events for a configurable trig

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): Start the event tap listener in a dedicated thread.

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): Enable learning mode — captures the next key press keycode.

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Disable learning mode and return the learned keycode (if any).

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): Stop the event tap listener.

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): Callback invoked for each relevant CGEvent.

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a human-readable name.

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a display label for the UI.

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): Injects text into the focused application via osascript.

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): Update the clipboard copy setting.

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Inject transcribed text into the active application.

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Copy text to clipboard and paste via Cmd+V.

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Simulate keystrokes for each character to avoid clipboard interaction.

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Monitors keyboard events via CGEventTap and emits events for a configurable trig

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Start the event tap listener in a dedicated thread.

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Enable learning mode — captures the next key press keycode.

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Disable learning mode and return the learned keycode (if any).

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Stop the event tap listener.

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): Callback invoked for each relevant CGEvent.

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a human-readable name.

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a display label for the UI.

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Possible states of the dictation system.

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): Raised when an illegal state transition is attempted.

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): Thread-safe FSM that manages the dictation lifecycle.      Valid transitions:

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Register a callback for when the FSM enters a specific state.

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): Call all registered callbacks for the new state.

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): Get the current state (thread-safe).

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): Return current state as a dictionary.

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): Attempt to transition to a new state.          Returns True if the transition wa

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (1): Transition from IDLE to RECORDING. Returns False if already recording.

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Transition from RECORDING to TRANSCRIBING. Returns False if not recording.

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): Transition from TRANSCRIBING to IDLE. Returns False if not transcribing.

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): Return the history of state transitions.

## Knowledge Gaps
- **122 isolated node(s):** `Tests for config validation in save_config and restart path resolution.`, `Test that save_config filters unknown keys.`, `Test that the restart path resolves correctly.`, `Test that the restart path resolves correctly.`, `Verify whispy.py does NOT exist (should use whispy_daemon.py).` (+117 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 15`** (2 nodes): `Update the clipboard copy setting.`, `.update_config()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (2 nodes): `.start()`, `Start the event tap listener in a dedicated thread.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 17`** (2 nodes): `.stop()`, `Stop the event tap listener.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 20`** (1 nodes): `Get the current state (thread-safe).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 21`** (1 nodes): `Return the history of state transitions.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (1 nodes): `The restart path (whispy_daemon.py) should exist at project root.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (1 nodes): `Verify whispy.py does NOT exist (should use whispy_daemon.py).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (1 nodes): `Monitors keyboard events via CGEventTap and emits events for a configurable trig`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (1 nodes): `Start the event tap listener in a dedicated thread.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (1 nodes): `Enable learning mode — captures the next key press keycode.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (1 nodes): `Disable learning mode and return the learned keycode (if any).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `Stop the event tap listener.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (1 nodes): `Callback invoked for each relevant CGEvent.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `Convert a macOS keycode to a human-readable name.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (1 nodes): `Convert a macOS keycode to a display label for the UI.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `Monitors keyboard events via CGEventTap and emits events for a configurable trig`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `Start the event tap listener in a dedicated thread.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `Enable learning mode — captures the next key press keycode.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Disable learning mode and return the learned keycode (if any).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `Stop the event tap listener.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `Callback invoked for each relevant CGEvent.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `Convert a macOS keycode to a human-readable name.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `Convert a macOS keycode to a display label for the UI.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `Injects text into the focused application via osascript.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `Update the clipboard copy setting.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `Inject transcribed text into the active application.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `Copy text to clipboard and paste via Cmd+V.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `Simulate keystrokes for each character to avoid clipboard interaction.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Monitors keyboard events via CGEventTap and emits events for a configurable trig`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Start the event tap listener in a dedicated thread.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `Enable learning mode — captures the next key press keycode.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `Disable learning mode and return the learned keycode (if any).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `Stop the event tap listener.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `Callback invoked for each relevant CGEvent.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `Convert a macOS keycode to a human-readable name.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Convert a macOS keycode to a display label for the UI.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Possible states of the dictation system.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `Raised when an illegal state transition is attempted.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `Thread-safe FSM that manages the dictation lifecycle.      Valid transitions:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `Register a callback for when the FSM enters a specific state.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `Call all registered callbacks for the new state.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `Get the current state (thread-safe).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `Return current state as a dictionary.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `Attempt to transition to a new state.          Returns True if the transition wa`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `Transition from IDLE to RECORDING. Returns False if already recording.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `Transition from RECORDING to TRANSCRIBING. Returns False if not recording.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `Transition from TRANSCRIBING to IDLE. Returns False if not transcribing.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `Return the history of state transitions.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Engine` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 10`, `Community 11`, `Community 12`, `Community 13`?**
  _High betweenness centrality (0.301) - this node is a cross-community bridge._
- **Why does `AudioEngine` connect `Community 0` to `Community 1`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 10`, `Community 11`, `Community 12`?**
  _High betweenness centrality (0.152) - this node is a cross-community bridge._
- **Why does `StateMachine` connect `Community 0` to `Community 1`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 9`, `Community 10`, `Community 11`, `Community 12`?**
  _High betweenness centrality (0.150) - this node is a cross-community bridge._
- **Are the 544 inferred relationships involving `StateMachine` (e.g. with `TestEventTapListenerStartStop` and `TestEventTapCallback`) actually correct?**
  _`StateMachine` has 544 INFERRED edges - model-reasoned connections that need verification._
- **Are the 530 inferred relationships involving `AudioEngine` (e.g. with `TestEventTapListenerStartStop` and `TestEventTapCallback`) actually correct?**
  _`AudioEngine` has 530 INFERRED edges - model-reasoned connections that need verification._
- **Are the 523 inferred relationships involving `State` (e.g. with `TestEventTapListenerStartStop` and `TestEventTapCallback`) actually correct?**
  _`State` has 523 INFERRED edges - model-reasoned connections that need verification._
- **Are the 500 inferred relationships involving `Engine` (e.g. with `Start Whispy: engine, UI, and HTTP server.` and `Start Whispy: engine, UI, and HTTP server.`) actually correct?**
  _`Engine` has 500 INFERRED edges - model-reasoned connections that need verification._
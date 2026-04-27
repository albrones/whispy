# Graph Report - whispy  (2026-04-27)

## Corpus Check
- 28 files · ~118,140 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 936 nodes · 3645 edges · 54 communities detected
- Extraction: 21% EXTRACTED · 79% INFERRED · 0% AMBIGUOUS · INFERRED: 2885 edges (avg confidence: 0.55)
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

## God Nodes (most connected - your core abstractions)
1. `StateMachine` - 401 edges
2. `AudioEngine` - 395 edges
3. `Engine` - 392 edges
4. `State` - 373 edges
5. `DictationState` - 353 edges
6. `TextInjector` - 340 edges
7. `EventTapListener` - 190 edges
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
Cohesion: 0.04
Nodes (226): AudioEngine, Stop recording and transition to TRANSCRIBING. Returns False if not recording., Transcribe an audio file. Returns None if transcription fails., Detect audio file duration in seconds using the wave module.          Falls back, Remove the temporary audio file after transcription., Manages audio recording and transcription operations.      Integrates with the S, Manages audio recording and transcription operations.      Integrates with the S, Start recording audio. Returns False if already recording.          Waits for so (+218 more)

### Community 1 - "Community 1"
Cohesion: 0.02
Nodes (176): BaseHTTPRequestHandler, config_path(), engine(), mock_engine(), mock_subprocess(), mock_whisper_model(), Fixtures for HTTP API tests., Mock subprocess.run and subprocess.Popen. (+168 more)

### Community 2 - "Community 2"
Cohesion: 0.04
Nodes (19): load_model_async(), Handle POST requests., Transition from IDLE to RECORDING. Returns False if already recording., Transition from RECORDING to TRANSCRIBING. Returns False if not recording., Transition from TRANSCRIBING to IDLE. Returns False if not transcribing., Register a callback for when the FSM enters a specific state., Call all registered callbacks for the new state., Return current state as a dictionary. (+11 more)

### Community 3 - "Community 3"
Cohesion: 0.03
Nodes (25): Audio recording and transcription logic.  Handles audio capture via sox and tran, _load_model(), Enum, keycode_to_label(), _keycode_to_name(), Trigger key listener via macOS CGEventTap.  Monitors hardware-level keyboard eve, Convert a macOS keycode to a human-readable name., Convert a macOS keycode to a display label for the UI. (+17 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (20): Stop recording and transition to TRANSCRIBING. Returns False if not recording., Start recording audio. Returns False if already recording.          Waits for so, Wait for sox to start writing audio to the output file.          Polls the file, Start HTTP server in a daemon thread., start_http_server(), Tests for AudioEngine with mocked subprocess calls., Test AudioEngine.start() behavior., Test AudioEngine.stop() behavior. (+12 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (14): load_config(), save_config(), Test config load/save roundtrip., Test saving and loading config preserves all values., Test loading a corrupted JSON file falls back to defaults., Test that partial config saves and loads correctly., Test that partial config saves and loads correctly., Test that save_config writes to the exact path passed, not a hardcoded one. (+6 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (16): Transcribe an audio file. Returns None if transcription fails., Detect audio file duration in seconds using the wave module.          Falls back, Test AudioEngine.transcribe() behavior., TestTranscribe, Regression tests for auto-detect language fix.  Tests that the auto-detect langu, Test duration detection for short audio (< 1s)., Test that short audio (< 1s) is handled gracefully., Short audio with language='auto' should not crash. (+8 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (11): Send a JSON HTTP response., engine(), Test Engine start/stop lifecycle., Test Engine starts in a clean state., Test that TextInjector config stays in sync with engine config., Test that status change callbacks are invoked., Test that all registered callbacks are invoked., Test that get_status includes valid FSM dict. (+3 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (23): audio(), config_dir(), config_path(), _find_free_port(), _http_get(), _http_post(), mock_subprocess(), mock_whisper_model() (+15 more)

### Community 9 - "Community 9"
Cohesion: 0.1
Nodes (13): Inject transcribed text into the active application., Copy text to clipboard and paste via Cmd+V., Simulate keystrokes for each character to avoid clipboard interaction., Tests for TextInjector with mocked subprocess calls., Test double quote escaping in osascript commands., Test clipboard-based text injection., Test direct keystroke text injection., Test that empty or None text does not call subprocess. (+5 more)

### Community 10 - "Community 10"
Cohesion: 0.13
Nodes (9): Callback invoked for each relevant CGEvent., captured_callbacks(), mock_subprocess(), mock_whisper_model(), sm(), state(), TestEventTapCallback, TestEventTapLearningMode (+1 more)

### Community 11 - "Community 11"
Cohesion: 0.12
Nodes (8): Remove the temporary audio file after transcription., Stop recording and transcribe synchronously (for /stop endpoint)., Test cleanup_audio_file behavior., Test cleanup with default RECORDING_PATH., TestCleanupAudioFile, Integration tests for multi-module interactions., Test Engine + AudioEngine integration with mocked subprocess., TestEngineAudioWithMocks

### Community 12 - "Community 12"
Cohesion: 0.7
Nodes (4): _draw_mic(), _draw_wave_arc(), generate_icons(), _new_image()

### Community 13 - "Community 13"
Cohesion: 1.0
Nodes (1): Whispy — macOS menu bar speech-to-text daemon.

### Community 14 - "Community 14"
Cohesion: 1.0
Nodes (1): Update the clipboard copy setting.

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (1): Start the event tap listener in a dedicated thread.

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (1): Enable learning mode — captures the next key press keycode.

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (1): Disable learning mode and return the learned keycode (if any).

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (1): Stop the event tap listener.

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (1): Get the current state (thread-safe).

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (1): Return the history of state transitions.

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (1): Monitors keyboard events via CGEventTap and emits events for a configurable trig

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (1): Start the event tap listener in a dedicated thread.

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (1): Enable learning mode — captures the next key press keycode.

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (1): Disable learning mode and return the learned keycode (if any).

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (1): Stop the event tap listener.

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (1): Callback invoked for each relevant CGEvent.

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a human-readable name.

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a display label for the UI.

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (1): Injects text into the focused application via osascript.

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (1): Update the clipboard copy setting.

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): Inject transcribed text into the active application.

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): Copy text to clipboard and paste via Cmd+V.

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Simulate keystrokes for each character to avoid clipboard interaction.

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): Monitors keyboard events via CGEventTap and emits events for a configurable trig

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): Start the event tap listener in a dedicated thread.

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): Enable learning mode — captures the next key press keycode.

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): Disable learning mode and return the learned keycode (if any).

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): Stop the event tap listener.

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): Callback invoked for each relevant CGEvent.

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a human-readable name.

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a display label for the UI.

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Possible states of the dictation system.

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Raised when an illegal state transition is attempted.

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Thread-safe FSM that manages the dictation lifecycle.      Valid transitions:

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Register a callback for when the FSM enters a specific state.

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Call all registered callbacks for the new state.

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Get the current state (thread-safe).

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): Return current state as a dictionary.

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Attempt to transition to a new state.          Returns True if the transition wa

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Transition from IDLE to RECORDING. Returns False if already recording.

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Transition from RECORDING to TRANSCRIBING. Returns False if not recording.

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): Transition from TRANSCRIBING to IDLE. Returns False if not transcribing.

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): Return the history of state transitions.

## Knowledge Gaps
- **73 isolated node(s):** `Whispy — macOS menu bar speech-to-text daemon.`, `Text injection via macOS accessibility APIs (osascript).  Handles injecting tran`, `Injects text into the focused application via osascript.`, `Update the clipboard copy setting.`, `Inject transcribed text into the active application.` (+68 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 13`** (2 nodes): `Whispy — macOS menu bar speech-to-text daemon.`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 14`** (2 nodes): `Update the clipboard copy setting.`, `.update_config()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 15`** (2 nodes): `.start()`, `Start the event tap listener in a dedicated thread.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (2 nodes): `.start_learning()`, `Enable learning mode — captures the next key press keycode.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 17`** (2 nodes): `.stop_learning()`, `Disable learning mode and return the learned keycode (if any).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 18`** (2 nodes): `.stop()`, `Stop the event tap listener.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 21`** (1 nodes): `Get the current state (thread-safe).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (1 nodes): `Return the history of state transitions.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (1 nodes): `Monitors keyboard events via CGEventTap and emits events for a configurable trig`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (1 nodes): `Start the event tap listener in a dedicated thread.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (1 nodes): `Enable learning mode — captures the next key press keycode.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (1 nodes): `Disable learning mode and return the learned keycode (if any).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (1 nodes): `Stop the event tap listener.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `Callback invoked for each relevant CGEvent.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (1 nodes): `Convert a macOS keycode to a human-readable name.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `Convert a macOS keycode to a display label for the UI.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (1 nodes): `Injects text into the focused application via osascript.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `Update the clipboard copy setting.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `Inject transcribed text into the active application.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `Copy text to clipboard and paste via Cmd+V.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Simulate keystrokes for each character to avoid clipboard interaction.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `Monitors keyboard events via CGEventTap and emits events for a configurable trig`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `Start the event tap listener in a dedicated thread.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `Enable learning mode — captures the next key press keycode.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `Disable learning mode and return the learned keycode (if any).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `Stop the event tap listener.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `Callback invoked for each relevant CGEvent.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `Convert a macOS keycode to a human-readable name.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `Convert a macOS keycode to a display label for the UI.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `Possible states of the dictation system.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Raised when an illegal state transition is attempted.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Thread-safe FSM that manages the dictation lifecycle.      Valid transitions:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `Register a callback for when the FSM enters a specific state.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `Call all registered callbacks for the new state.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `Get the current state (thread-safe).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `Return current state as a dictionary.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `Attempt to transition to a new state.          Returns True if the transition wa`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Transition from IDLE to RECORDING. Returns False if already recording.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Transition from RECORDING to TRANSCRIBING. Returns False if not recording.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `Transition from TRANSCRIBING to IDLE. Returns False if not transcribing.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `Return the history of state transitions.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Engine` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 10`, `Community 11`?**
  _High betweenness centrality (0.248) - this node is a cross-community bridge._
- **Why does `StateMachine` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 10`, `Community 11`?**
  _High betweenness centrality (0.166) - this node is a cross-community bridge._
- **Why does `AudioEngine` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 10`, `Community 11`?**
  _High betweenness centrality (0.143) - this node is a cross-community bridge._
- **Are the 391 inferred relationships involving `StateMachine` (e.g. with `TestEventTapListenerStartStop` and `TestEventTapCallback`) actually correct?**
  _`StateMachine` has 391 INFERRED edges - model-reasoned connections that need verification._
- **Are the 385 inferred relationships involving `AudioEngine` (e.g. with `TestEventTapListenerStartStop` and `TestEventTapCallback`) actually correct?**
  _`AudioEngine` has 385 INFERRED edges - model-reasoned connections that need verification._
- **Are the 369 inferred relationships involving `Engine` (e.g. with `Start Whispy: engine, UI, and HTTP server.` and `Start Whispy: engine, UI, and HTTP server.`) actually correct?**
  _`Engine` has 369 INFERRED edges - model-reasoned connections that need verification._
- **Are the 370 inferred relationships involving `State` (e.g. with `TestEventTapListenerStartStop` and `TestEventTapCallback`) actually correct?**
  _`State` has 370 INFERRED edges - model-reasoned connections that need verification._
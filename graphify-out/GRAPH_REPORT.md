# Graph Report - whispy  (2026-04-23)

## Corpus Check
- 29 files · ~118,908 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 801 nodes · 2876 edges · 55 communities detected
- Extraction: 27% EXTRACTED · 73% INFERRED · 0% AMBIGUOUS · INFERRED: 2090 edges (avg confidence: 0.57)
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

## God Nodes (most connected - your core abstractions)
1. `StateMachine` - 285 edges
2. `AudioEngine` - 284 edges
3. `Engine` - 267 edges
4. `State` - 259 edges
5. `TextInjector` - 236 edges
6. `DictationState` - 228 edges
7. `EventTapListener` - 142 edges
8. `RequestHandler` - 98 edges
9. `InvalidTransitionError` - 38 edges
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
Cohesion: 0.05
Nodes (141): AudioEngine, Stop recording and transition to TRANSCRIBING. Returns False if not recording., Transcribe an audio file. Returns None if transcription fails., Detect audio file duration in seconds using the wave module.          Falls back, Remove the temporary audio file after transcription., Manages audio recording and transcription operations.      Integrates with the S, Manages audio recording and transcription operations.      Integrates with the S, Start recording audio. Returns False if already recording.          Waits for so (+133 more)

### Community 1 - "Community 1"
Cohesion: 0.03
Nodes (80): Detect audio file duration in seconds using the wave module.          Falls back, config_path(), engine(), mock_engine(), mock_subprocess(), mock_whisper_model(), Fixtures for HTTP API tests., Create a mock Engine with common return values. (+72 more)

### Community 2 - "Community 2"
Cohesion: 0.04
Nodes (42): Exception, InvalidTransitionError, Transition from IDLE to RECORDING. Returns False if already recording., Transition from RECORDING to TRANSCRIBING. Returns False if not recording., Transition from TRANSCRIBING to IDLE. Returns False if not transcribing., Raised when an illegal state transition is attempted., Register a callback for when the FSM enters a specific state., Call all registered callbacks for the new state. (+34 more)

### Community 3 - "Community 3"
Cohesion: 0.04
Nodes (56): BaseHTTPRequestHandler, Send a JSON HTTP response., HTTP request handler for Whispy control API., Handle POST requests., Stop recording and transcribe synchronously (for /stop endpoint)., RequestHandler, audio(), config_dir() (+48 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (30): Stop recording and transition to TRANSCRIBING. Returns False if not recording., Start recording audio. Returns False if already recording.          Waits for so, Wait for sox to start writing audio to the output file.          Polls the file, Start HTTP server in a daemon thread., start_http_server(), Tests for AudioEngine with mocked subprocess calls., Test AudioEngine.start() behavior., Test AudioEngine.stop() behavior. (+22 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (15): Inject transcribed text into the active application., Copy text to clipboard and paste via Cmd+V., Simulate keystrokes for each character to avoid clipboard interaction., Test that update_config switches injection mode., TestTextInjector, Tests for TextInjector with mocked subprocess calls., Test clipboard-based text injection., Test direct keystroke text injection. (+7 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (13): Audio recording and transcription logic.  Handles audio capture via sox and tran, _load_model(), Enum, keycode_to_label(), _keycode_to_name(), Trigger key listener via macOS CGEventTap.  Monitors hardware-level keyboard eve, Convert a macOS keycode to a human-readable name., Convert a macOS keycode to a display label for the UI. (+5 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (10): Menu bar application for Whispy control and status display., Load icon paths for animation frames., Construct the full menu structure., WhisperMenuBarApp, Test Engine config updates work correctly., Test that config update returns True when model reload is needed., Test Engine.update_config behavior., TestEngineConfigUpdate (+2 more)

### Community 8 - "Community 8"
Cohesion: 0.12
Nodes (11): Callback invoked for each relevant CGEvent., audio(), captured_callbacks(), engine(), mock_subprocess(), mock_whisper_model(), sm(), state() (+3 more)

### Community 9 - "Community 9"
Cohesion: 0.11
Nodes (10): load_config(), save_config(), Tests for Engine, DictationState, config loading/saving, and status reporting., Test that save_config overwrites the config at the given path., Test load_config behavior., Test save_config behavior., TestLoadConfig, TestSaveConfig (+2 more)

### Community 10 - "Community 10"
Cohesion: 0.13
Nodes (7): Test that engine notifies callbacks on state changes., test_engine_status_callbacks(), Test Engine starts in a clean state., Test that get_status includes valid FSM dict., TestEngineLifecycle, Test Engine.get_status() and status callbacks., TestEngineStatus

### Community 11 - "Community 11"
Cohesion: 0.19
Nodes (5): Transcribe an audio file. Returns None if transcription fails., Test AudioEngine.transcribe() behavior., TestTranscribe, Test that language='auto' is passed through correctly., TestAutoDetectTranscription

### Community 12 - "Community 12"
Cohesion: 0.32
Nodes (4): Remove the temporary audio file after transcription., Test cleanup with default RECORDING_PATH., Test cleanup_audio_file behavior., TestCleanupAudioFile

### Community 13 - "Community 13"
Cohesion: 0.7
Nodes (4): _draw_mic(), _draw_wave_arc(), generate_icons(), _new_image()

### Community 14 - "Community 14"
Cohesion: 1.0
Nodes (1): Whispy — macOS menu bar speech-to-text daemon.

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (1): Update the clipboard copy setting.

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (1): Start the event tap listener in a dedicated thread.

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (1): Enable learning mode — captures the next key press keycode.

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (1): Stop the event tap listener.

### Community 19 - "Community 19"
Cohesion: 1.0
Nodes (1): Disable learning mode and return the learned keycode (if any).

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (1): Get the current state (thread-safe).

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (1): Return the history of state transitions.

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
Nodes (1): Injects text into the focused application via osascript.

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): Update the clipboard copy setting.

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): Inject transcribed text into the active application.

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Copy text to clipboard and paste via Cmd+V.

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): Simulate keystrokes for each character to avoid clipboard interaction.

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): Monitors keyboard events via CGEventTap and emits events for a configurable trig

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): Start the event tap listener in a dedicated thread.

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): Enable learning mode — captures the next key press keycode.

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): Disable learning mode and return the learned keycode (if any).

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): Stop the event tap listener.

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Callback invoked for each relevant CGEvent.

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a human-readable name.

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Convert a macOS keycode to a display label for the UI.

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Possible states of the dictation system.

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Raised when an illegal state transition is attempted.

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Thread-safe FSM that manages the dictation lifecycle.      Valid transitions:

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Register a callback for when the FSM enters a specific state.

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Call all registered callbacks for the new state.

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): Get the current state (thread-safe).

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Return current state as a dictionary.

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Attempt to transition to a new state.          Returns True if the transition wa

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Transition from IDLE to RECORDING. Returns False if already recording.

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): Transition from RECORDING to TRANSCRIBING. Returns False if not recording.

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): Transition from TRANSCRIBING to IDLE. Returns False if not transcribing.

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Return the history of state transitions.

## Knowledge Gaps
- **67 isolated node(s):** `Whispy — macOS menu bar speech-to-text daemon.`, `Text injection via macOS accessibility APIs (osascript).  Handles injecting tran`, `Injects text into the focused application via osascript.`, `Update the clipboard copy setting.`, `Inject transcribed text into the active application.` (+62 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 14`** (2 nodes): `Whispy — macOS menu bar speech-to-text daemon.`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 15`** (2 nodes): `Update the clipboard copy setting.`, `.update_config()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (2 nodes): `.start()`, `Start the event tap listener in a dedicated thread.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 17`** (2 nodes): `.start_learning()`, `Enable learning mode — captures the next key press keycode.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 18`** (2 nodes): `.stop()`, `Stop the event tap listener.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 19`** (2 nodes): `.stop_learning()`, `Disable learning mode and return the learned keycode (if any).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (1 nodes): `Get the current state (thread-safe).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (1 nodes): `Return the history of state transitions.`
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
- **Thin community `Community 32`** (1 nodes): `Injects text into the focused application via osascript.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `Update the clipboard copy setting.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `Inject transcribed text into the active application.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Copy text to clipboard and paste via Cmd+V.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `Simulate keystrokes for each character to avoid clipboard interaction.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `Monitors keyboard events via CGEventTap and emits events for a configurable trig`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `Start the event tap listener in a dedicated thread.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `Enable learning mode — captures the next key press keycode.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `Disable learning mode and return the learned keycode (if any).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `Stop the event tap listener.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `Callback invoked for each relevant CGEvent.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `Convert a macOS keycode to a human-readable name.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `Convert a macOS keycode to a display label for the UI.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Possible states of the dictation system.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Raised when an illegal state transition is attempted.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `Thread-safe FSM that manages the dictation lifecycle.      Valid transitions:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `Register a callback for when the FSM enters a specific state.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `Call all registered callbacks for the new state.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `Get the current state (thread-safe).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `Return current state as a dictionary.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Attempt to transition to a new state.          Returns True if the transition wa`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Transition from IDLE to RECORDING. Returns False if already recording.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `Transition from RECORDING to TRANSCRIBING. Returns False if not recording.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `Transition from TRANSCRIBING to IDLE. Returns False if not transcribing.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `Return the history of state transitions.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Engine` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 9`, `Community 10`, `Community 11`?**
  _High betweenness centrality (0.250) - this node is a cross-community bridge._
- **Why does `StateMachine` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 9`, `Community 10`, `Community 11`, `Community 12`?**
  _High betweenness centrality (0.176) - this node is a cross-community bridge._
- **Why does `AudioEngine` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 9`, `Community 10`, `Community 11`, `Community 12`?**
  _High betweenness centrality (0.144) - this node is a cross-community bridge._
- **Are the 275 inferred relationships involving `StateMachine` (e.g. with `TestEventTapListenerStartStop` and `TestEventTapCallback`) actually correct?**
  _`StateMachine` has 275 INFERRED edges - model-reasoned connections that need verification._
- **Are the 274 inferred relationships involving `AudioEngine` (e.g. with `TestEventTapListenerStartStop` and `TestEventTapCallback`) actually correct?**
  _`AudioEngine` has 274 INFERRED edges - model-reasoned connections that need verification._
- **Are the 244 inferred relationships involving `Engine` (e.g. with `Start Whispy: engine, UI, and HTTP server.` and `TestEventTapListenerStartStop`) actually correct?**
  _`Engine` has 244 INFERRED edges - model-reasoned connections that need verification._
- **Are the 256 inferred relationships involving `State` (e.g. with `TestEventTapListenerStartStop` and `TestEventTapCallback`) actually correct?**
  _`State` has 256 INFERRED edges - model-reasoned connections that need verification._
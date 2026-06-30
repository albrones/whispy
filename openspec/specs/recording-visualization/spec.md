# recording-visualization Specification

## Purpose
Real-time recording feedback: microphone level monitoring, the floating
visualization window, audio-reactive rendering, and the menu-bar waveform
animation. Scenario test tiers follow the convention in `../TESTING-TIERS.md`.

NOTE: some scenarios below describe an earlier "ferrofluid sphere" rendering
that has since been replaced by the braille waveform; reconciling that wording
is tracked separately and out of scope for the pure-logic extraction.
## Requirements
### Requirement: Audio level monitoring during recording
The system SHALL monitor real-time microphone audio levels during recording and expose them as a normalized value (0.0 to 1.0) with exponential moving average smoothing.

#### Scenario: Audio level monitor starts with recording
- **WHEN** recording begins via Fn key press or API `/start` endpoint
- **THEN** an audio level monitor is initialized and begins sampling the default microphone input

#### Scenario: Audio level returns valid range
- **WHEN** the audio level monitor is active
- **THEN** `get_level()` returns a float value between 0.0 (silence) and 1.0 (maximum)

#### Scenario: Audio level smoothing prevents jitter
- **WHEN** raw audio amplitude fluctuates rapidly
- **THEN** the smoothed level changes gradually with a configurable decay rate (default: 0.85 smoothing factor)

#### Scenario: Audio level monitor stops with recording
- **WHEN** recording ends via Fn key release or API `/stop` endpoint
- **THEN** the audio level monitor thread is stopped and releases the microphone device

### Requirement: Ferrofluid visualization window
The system SHALL display a floating borderless window containing a ferrofluid-like sphere visualization during recording.

#### Scenario: Visualization appears on recording start
- **WHEN** recording begins
- **THEN** a 220x220 borderless window appears centered slightly above the menu bar on the primary display

#### Scenario: Visualization disappears on recording stop
- **WHEN** recording ends
- **THEN** the visualization window is hidden and destroyed immediately

#### Scenario: Visualization window is non-intrusive
- **WHEN** the visualization window is visible
- **THEN** mouse events pass through the window to underlying applications (click-through behavior)

#### Scenario: Visualization window is above most windows
- **WHEN** the visualization window is visible
- **THEN** it uses `NSPopUpMenuWindowLevel` window level to stay above regular application windows

#### Scenario: Visualization auto-cleans on app termination
- **WHEN** the application terminates (normally or via crash)
- **THEN** the visualization window is removed from the window server via `removeOnExit` collection behavior

### Requirement: Audio-reactive sphere rendering
The system SHALL render a ferrofluid sphere whose spikes respond to the current audio level.

#### Scenario: Sphere renders in idle audio state
- **WHEN** audio level is near 0.0 (silence)
- **THEN** the sphere shows subtle, barely-visible surface undulation

#### Scenario: Sphere spikes scale with audio level
- **WHEN** audio level increases from 0.3 to 0.7
- **THEN** spike height scales proportionally from medium to pronounced

#### Scenario: Sphere shows maximum spike at high audio
- **WHEN** audio level exceeds 0.7
- **THEN** spikes reach maximum height with dramatic, spiky appearance

#### Scenario: Sphere renders at consistent frame rate
- **WHEN** the visualization is active
- **THEN** the sphere is redrawn at approximately 30fps via `NSTimer`

#### Scenario: Sphere uses ferrofluid color palette
- **WHEN** the sphere is rendered
- **THEN** it uses a deep purple-to-black gradient with subtle blue highlights

### Requirement: Visualization integration with recording lifecycle
The system SHALL automatically show and hide the visualization based on the recording state.

#### Scenario: Show visualization when recording starts
- **WHEN** the engine transitions to RECORDING state
- **THEN** the visualization window is shown and the audio level monitor is started

#### Scenario: Hide visualization when recording stops
- **WHEN** the engine transitions to TRANSCRIBING state
- **THEN** the visualization window is hidden and the audio level monitor is stopped

#### Scenario: Show/hide works via Fn key
- **WHEN** the user presses and releases the Fn key to record
- **THEN** the visualization appears and disappears correctly with each recording session

#### Scenario: Show/hide works via API
- **WHEN** the user calls `POST /start` and `POST /stop` endpoints
- **THEN** the visualization appears and disappears correctly with each recording session

### Requirement: Pure visualization computation
The audio-level value and the menu-bar animation frame SHALL be produced by pure, unit-tested functions independent of `sounddevice` and `rumps`. The audio-level function SHALL map a raw RMS sample to a smoothed 0.0–1.0 level (normalize, clamp to 1.0, then apply exponential moving average against the previous level). The frame-selection function SHALL return the scrolling waveform frame for the current index when active and the idle frame when inactive. The UI callbacks SHALL delegate to these functions.

#### Scenario: RMS maps to clamped normalized level
- **WHEN** `rms_to_level` receives an RMS value whose normalized form exceeds 1.0
- **THEN** it SHALL clamp the contribution to 1.0 before smoothing

_Tier: unit-pure — `test_level_math.py`._

#### Scenario: Exponential moving average applied
- **WHEN** `rms_to_level` is called with a previous smoothed level and a smoothing factor
- **THEN** it SHALL return `smoothing * prev + (1 - smoothing) * normalized`

_Tier: unit-pure — `test_level_math.py`._

#### Scenario: Active animation cycles frames
- **WHEN** `select_frame` is called with `is_active` true for increasing frame indices
- **THEN** it SHALL return successive waveform frames, wrapping modulo the frame count

_Tier: unit-pure — `test_anim_frames.py`._

#### Scenario: Idle shows the idle frame
- **WHEN** `select_frame` is called with `is_active` false
- **THEN** it SHALL return the idle frame regardless of index

_Tier: unit-pure — `test_anim_frames.py`._

### Requirement: Visualization platform availability
The floating overlay visualization window SHALL be a macOS-only surface. On Linux (v1), the overlay SHALL NOT be required; recording state SHALL be conveyed through the tray UI instead, and the absence of the overlay SHALL NOT affect the recording lifecycle. Audio-level monitoring and the engine's RECORDING/TRANSCRIBING transitions SHALL behave identically across platforms regardless of overlay presence.

#### Scenario: Overlay shown on macOS
- **WHEN** recording starts on macOS
- **THEN** the floating overlay window SHALL appear as today

_Tier: macos-real — requires AppKit; not verifiable in CI._

#### Scenario: No overlay on Linux, lifecycle intact
- **WHEN** recording starts on Linux v1
- **THEN** no overlay window SHALL be required, the tray SHALL reflect the recording state, and the audio-level monitor and state transitions SHALL run unchanged

_Tier: linux-real — deferred to a Linux smoke run._

### Requirement: UI updates are marshaled to the main thread
UI updates triggered by engine callbacks that fire on background threads (event-tap, transcription worker) SHALL be marshaled to the main thread before mutating AppKit, so the app does not crash or corrupt UI state from off-main-thread access.

#### Scenario: Status update fires from a background thread
- **WHEN** an engine status callback fires on the event-tap or transcription-worker thread and updates the menu title
- **THEN** the AppKit mutation SHALL execute on the main thread (deferred via the main run loop if necessary)

### Requirement: Visualization tolerates a display-less session
Visualization SHALL not crash when no display is available.

#### Scenario: No screens available
- **WHEN** a visualization window is asked to show on a session with no screens
- **THEN** it SHALL bail safely without raising (no unguarded `screens()[0]` index)

### Requirement: Pill appears above the active full-screen Space on every recording

The floating waveform pill SHALL appear above the currently active Space — including another application's full-screen Space — on every recording start, not only on the process's first show. Its Space-joining collection behavior and window level SHALL be (re)applied and its position resolved against the active Space each time it is shown.

#### Scenario: Pill shows over a full-screen app

- **WHEN** another application is frontmost in a full-screen Space and recording begins
- **THEN** the pill appears floating above that full-screen Space, near the bottom center of the active screen

#### Scenario: Pill shows reliably on repeated recordings without restart

- **WHEN** the daemon has already shown and hidden the pill at least once and recording begins again while a full-screen app is frontmost
- **THEN** the pill appears above the full-screen Space without requiring the daemon to be restarted

#### Scenario: Pill stays click-through and non-activating over full screen

- **WHEN** the pill is visible over a full-screen app
- **THEN** mouse events pass through to the underlying app and the pill does not steal focus or exit the app's full-screen Space


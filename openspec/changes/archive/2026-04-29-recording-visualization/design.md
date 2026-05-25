## Context

Whispy is a macOS menu bar speech-to-text daemon. Currently, during recording, visual feedback is limited to:
- A cycling menu bar icon (3 frames at 5Hz)
- A status text change ("Recording..." with red circle emoji)

The app uses `rumps` (built on AppKit) for the menu bar UI, `sox` for audio capture, and `faster-whisper` for transcription. The codebase is modular under `src/whispy/` with separate modules for core logic, hardware, UI, and API.

## Goals / Non-Goals

**Goals:**
- Add a floating visualization window that appears during recording
- Drive visualization by real-time microphone audio levels
- Integrate cleanly with existing recording lifecycle (no state machine changes)
- Keep the visualization non-intrusive (click-through, auto-hide)

**Non-Goals:**
- Configurable visualization style or colors (fixed ferrofluid design)
- Per-user customization of the visualization
- Waveform or frequency display (only amplitude-reactive sphere)
- Cross-platform support (macOS only)
- Making the visualization configurable via the menu bar

## Decisions

### 1. Floating borderless window (not popover or status bar icon)
**Decision:** Use a standalone `NSWindow` with `level: NSPopUpMenuWindowLevel` for the visualization.

**Rationale:** 
- A popover would be too small and intrusive for a sphere visualization
- The menu bar icon is already in use for the basic icon animation (keep existing behavior)
- A floating window gives enough space for a 200x200 pixel visualization
- `NSPopUpMenuWindowLevel` keeps it above most windows but below full-screen apps

**Alternatives considered:**
- Status bar icon with dynamic rendering: too small for meaningful visualization
- NSPopover: requires user interaction to appear, not ideal for auto-show
- Full-screen overlay: too intrusive, blocks user workflow

### 2. Real-time audio level via `sounddevice`
**Decision:** Use the `sounddevice` library to read the microphone input in real-time and compute RMS amplitude.

**Rationale:**
- `sounddevice` provides low-latency access to the system's default audio input
- It wraps PortAudio, which is well-maintained and works across macOS versions
- RMS amplitude is the right metric for ferrofluid spike height (perceived loudness)
- Exponential moving average smoothing prevents jitter

**Alternatives considered:**
- Reading `/tmp/whispy.wav` growth rate: less accurate, higher latency, not real-time
- `pyaudio`: more complex setup, `sounddevice` is simpler for this use case
- CoreAudio directly via pyobjc: too low-level, more error-prone, `sounddevice` is mature

### 3. CoreGraphics-based rendering (not Metal or OpenGL)
**Decision:** Use `CoreGraphics` (CGContext) via pyobjc for the ferrofluid rendering.

**Rationale:**
- CoreGraphics is already available via `pyobjc-framework-Quartz` (existing dependency)
- No additional dependencies needed
- Sufficient performance for a ~200x200 sphere with spikes at 30fps
- Simpler than Metal/OpenGL for this complexity level

**Alternatives considered:**
- Metal: GPU-accelerated but requires `pyobjc-framework-Metal` (new dep) and shader code
- OpenGL: Similar to Metal, overkill for this complexity
- `NSTimer` with `NSBezierPath`: less flexible for the spike geometry

### 4. Audio level monitor as a separate thread
**Decision:** The `AudioLevelMonitor` runs in its own daemon thread, continuously reading audio and exposing a thread-safe `get_level()` method.

**Rationale:**
- Audio callback runs on a separate thread from `sounddevice`
- The visualization UI thread can poll at 30fps without blocking audio
- Thread-safe via a lock-protected value

**Alternatives considered:**
- Callback-based push to UI: would require `NSApp.performSelector` for thread safety
- Polling in the visualization view's timer: simpler but couples audio to rendering

### 5. Window centering on the primary display
**Decision:** Center the visualization window on the primary display, slightly above the menu bar.

**Rationale:**
- Primary display is where the menu bar app icon sits (user's focus point)
- Slightly above the menu bar keeps it visible without overlapping it
- Single-monitor simplicity; multi-monitor support is a future enhancement

## Risks / Trade-offs

### [Risk: sounddevice conflicts with sox for mic access]
**Mitigation:** Test on target macOS. If sox and sounddevice cannot both access the mic simultaneously, fall back to reading the WAV file size growth rate as a proxy for audio activity. This is a known macOS limitation where only one process can typically access the default mic.

### [Risk: Visualization window stays visible after crash]
**Mitigation:** The `WhisperMenuBarApp` destructor and the daemon SIGTERM handler both call `hide_visualization()`. Additionally, `ferrofluid_window.py` uses `NSWindow` with `collectionBehavior: removeOnExit` to auto-remove on app termination.

### [Risk: Performance impact during transcription]
**Mitigation:** The audio level monitor only runs during recording (not transcription). The visualization window is destroyed when recording stops. CoreGraphics rendering at 200x200 with ~16 spikes is lightweight on Apple Silicon.

### [Risk: macOS permission requirements]
**Mitigation:** The app already has Microphone permission for sox recording. `sounddevice` uses the same system input device, so no additional permissions are needed. The user will have already granted permission when sox first records.

### [Trade-off: Single visualization style]
The ferrofluid design is fixed, not customizable. This keeps the implementation focused and avoids a configuration surface. Future versions could add style options.

### [Trade-off: No multi-monitor support]
The window is centered on the primary display only. If the menu bar app icon is on a secondary display, the window may not appear where the user expects. This is a low-priority enhancement.

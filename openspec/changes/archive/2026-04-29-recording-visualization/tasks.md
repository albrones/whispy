## 1. Dependency & Setup

- [x] 1.1 Add `sounddevice` to `pyproject.toml` dependencies
- [x] 1.2 Create `src/whispy/ui/__init__.py` exports for new UI modules

## 2. Audio Level Monitor

- [x] 2.1 Create `src/whispy/ui/audio_level.py` with `AudioLevelMonitor` class
- [x] 2.2 Implement RMS amplitude calculation with exponential moving average smoothing
- [x] 2.3 Implement thread-safe `get_level()` method
- [x] 2.4 Implement `start()` and `stop()` lifecycle methods

## 3. Ferrofluid Rendering

- [x] 3.1 Create `src/whispy/ui/ferrofluid_view.py` with `FerrofluidView` NSView subclass
- [x] 3.2 Implement sphere base rendering with CoreGraphics radial gradient
- [x] 3.3 Implement spike geometry (12-16 spikes with height driven by audio level)
- [x] 3.4 Implement color palette (deep purple-to-black gradient with blue highlights)
- [x] 3.5 Implement audio-reactive animation loop via `NSTimer` at 30fps

## 4. Floating Window

- [x] 4.1 Create `src/whispy/ui/ferrofluid_window.py` with `FerrofluidWindow` class
- [x] 4.2 Implement borderless NSWindow with `NSPopUpMenuWindowLevel`
- [x] 4.3 Implement click-through behavior (ignore mouse events)
- [x] 4.4 Implement primary display centering, slightly above menu bar
- [x] 4.5 Implement `show()` and `hide()` lifecycle methods
- [x] 4.6 Implement auto-cleanup via `removeOnExit` collection behavior

## 5. Engine Integration

- [x] 5.1 Add `on_recording_start` / `on_recording_stop` callback system to `Engine`
- [x] 5.2 Wire FSM recording/transcribing transitions to visualization callbacks

## 6. Menu Bar App Integration

- [x] 6.1 Create `FerrofluidWindow` instance in `WhisperMenuBarApp.__init__`
- [x] 6.2 Wire visualization show/hide to existing `update_status_display` callback
- [x] 6.3 Ensure visualization is destroyed on app quit

## 7. Testing

- [x] 7.1 Create `tests/test_audio_level.py` with unit tests for `AudioLevelMonitor`
- [x] 7.2 Test RMS calculation on mock audio data
- [x] 7.3 Test smoothing behavior
- [x] 7.4 Test thread-safe `get_level()` under concurrent access
- [x] 7.5 Run full test suite to verify no regression

## 8. Polish

- [x] 8.1 Ensure no logging noise from audio level monitor during normal operation
- [x] 8.2 Verify visualization window does not appear in Mission Control or Spaces
- [x] 8.3 Mark TODO.md task 7 as done `[x]`

## Why

Currently, Whispy only provides minimal visual feedback during recording: a cycling menu bar icon and a status text change. Users have no intuitive, engaging indication that the application is actively listening. A ferrofluid-like visualization reactive to audio levels provides immediate, satisfying confirmation that recording is working, improving the overall user experience.

## What Changes

- Add a floating, borderless visualization window that appears when recording starts and disappears when recording stops
- Real-time ferrofluid sphere animation driven by microphone audio levels
- Add `sounddevice` dependency for real-time audio level monitoring
- New UI module with audio level monitor, ferrofluid view, and window controller

## Capabilities

### New Capabilities
- `recording-visualization`: Audio-reactive ferrofluid visualization window that appears during recording. Includes real-time audio level monitoring, a custom NSView with CoreGraphics-based ferrofluid rendering, and a borderless floating window integrated with the recording lifecycle.

### Modified Capabilities
- `core-engine`: The Engine gains recording start/stop lifecycle callbacks to notify the visualization window when to show/hide.

## Impact

- **New dependency**: `sounddevice` added to `pyproject.toml`
- **New files**: `src/whispy/ui/audio_level.py`, `src/whispy/ui/ferrofluid_view.py`, `src/whispy/ui/ferrofluid_window.py`
- **Modified files**: `src/whispy/ui/menu_bar.py` (integration), `src/whispy/core/engine.py` (lifecycle callbacks)
- **New tests**: `tests/test_audio_level.py`
- No breaking changes to existing APIs or behavior

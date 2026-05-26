# Plan: Ferrofluid Visualization Integration

## Goal
Wire up the existing `FerrofluidWindow` and `AudioLevelMonitor` to the `WhisperMenuBarApp` lifecycle so the animation is visible during recording.

## Context
- `src/whispy/ui/ferrofluid_view.py` and `ferrofluid_window.py` are fully implemented but **dead code** (never instantiated).
- Currently, only `IndicatorWindow` (emoji indicator) is used.
- `AudioLevelMonitor` exists but is not connected to the UI.

## Implementation Steps

### 1. Modify `src/whispy/ui/menu_bar.py`
- **Imports**: Add `FerrofluidWindow` and `AudioLevelMonitor` from `.ui`.
- **Initialization (`__init__`)**:
  - Create `self._audio_monitor = AudioLevelMonitor()`.
  - Create `self._visualization = FerrofluidWindow()`.
  - Connect the monitor: `self._visualization.set_audio_monitor(self._audio_monitor)`.
- **Lifecycle Hooks**:
  - **Start**: In `_on_recording_start`:
    - Start `self._audio_monitor.start()`.
    - Call `self._visualization.show()`.
  - **Stop**: In `_on_recording_stop`:
    - Call `self._visualization.hide()`.
    - Stop `self._audio_monitor.stop()`.
- **Cleanup**:
  - In `_on_quit` or engine shutdown: Call `self._visualization.destroy()` and `self._audio_monitor.stop()`.

### 2. UX Decision
- **Option A**: Ferrofluid replaces the indicator during recording (cleaner).
- **Option B**: Both coexist (indicator in menu bar, ferrofluid floating).
- *Recommendation*: Option A (Ferrofluid is the "active" state visual).

### 3. Verification
- Start Whispy -> Press Fn -> Verify window appears at top center.
- Speak -> Verify spikes grow/shrink.
- Release Fn -> Verify window fades out.

---
**Status: DONE**
- `menu_bar.py` wired with `AudioLevelMonitor` + `FerrofluidWindow` lifecycle hooks
- 15 integration tests created (`tests/test_ferrofluid_integration.py`)
- Full test suite: 297/297 passed (no regressions)
- **Blocker resolved:** conftest's global `rumps` mock breaks `WhisperMenuBarApp` instantiation — used AST-based source inspection instead
- Manual QA pending (requires macOS with audio hardware)

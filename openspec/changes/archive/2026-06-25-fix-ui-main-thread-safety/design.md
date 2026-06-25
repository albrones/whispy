## Context

The menu bar app (rumps + pyobjc) runs its UI on the main run loop, but engine status callbacks fire on the event-tap and transcription-worker threads. `WaveformWindow` already demonstrates the correct pattern: it hops to the main thread via `AppHelper.callAfter` and guards against a missing screen. The status-title update and the (dead) `IndicatorWindow` do not. The current UI tests inspect source strings (`_method_body` substring checks) rather than running the AppKit path, so these threading violations pass CI today.

## Goals / Non-Goals

**Goals:**
- All AppKit mutation happens on the main thread.
- No crash on a headless / no-display session.
- Remove the dead `IndicatorWindow` and `AudioLevelMonitor`.

**Non-Goals:**
- Redesigning the visualization or theming.
- Adding a full UI-integration test harness (a targeted marshaling assertion is enough).

## Decisions

### Status update marshaling
Wrap the `update_status_display` body so it runs on the main thread: if not on the main thread, re-dispatch via `AppHelper.callAfter`; otherwise run inline. Mirror exactly what `WaveformWindow.show/hide` do, for consistency.

### IndicatorWindow: remove
`IndicatorWindow` is allocated but its `show()` is never called (callbacks only `hide()` it and show the waveform). Removing it deletes the off-main-thread `hide()` calls, the `screens()[0]` headless crash, and a leaked `NSWindow` in one move. If a future design wants it back, it returns with correct marshaling from day one. The `screens()` guard is therefore only needed if the window is kept.

### AudioLevelMonitor: remove
The live waveform reads `engine.get_level`; `AudioLevelMonitor` is unused (a test even asserts it is absent from the menu content). Remove the module and its references.

## Risks / Trade-offs

- Removing modules touches tests — update the source-inspection tests that reference the removed names.
- `AppHelper.callAfter` defers the title update by a run-loop tick; visually imperceptible and already accepted for the waveform.

## Migration Plan

Pure UI-internal change; no config/API impact. Verify nothing external imports `IndicatorWindow` or `AudioLevelMonitor` before deletion.

## Open Questions

- Keep vs. remove `IndicatorWindow`: leaning remove (dead). If product wants the indicator, scope a separate change to wire it with correct threading.

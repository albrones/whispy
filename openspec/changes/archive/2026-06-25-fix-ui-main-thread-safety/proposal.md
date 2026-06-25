## Why

AppKit requires UI mutation on the main thread. Several UI updates run on the wrong thread:

- **`update_status_display`** is registered as `engine.on_status_change` and fires from the `trigger-event-tap` daemon thread and the transcription-worker thread; it calls `menu_theme.apply_title → setAttributedTitle_`, mutating AppKit off the main thread.
- **`IndicatorWindow.hide()`/`show()`** call `orderOut_`/`orderFrontRegardless_` directly with no main-thread hop, and are invoked from the event-tap thread. (`WaveformWindow` already marshals correctly via `AppHelper.callAfter` — the pattern to copy.)

Both are crash/UB risks on a multi-threaded run, and are invisible to the current tests, which verify menu-bar wiring only by source-string inspection, not threading.

Plus a headless crash and dead code: `IndicatorWindow.show()` indexes `screens()[0]` with no guard (IndexError on a no-display session), `IndicatorWindow` is never actually shown anywhere (dead UI that still allocates an NSWindow), and `AudioLevelMonitor` is unused by the live app (the waveform reads `engine.get_level`). Dead-code removal was a deferred follow-up from `2026-06-15-code-health-audit-and-fixes`.

## What Changes

- Marshal `update_status_display` to the main thread (wrap the body in an `AppHelper.callAfter` / `NSThread.isMainThread` guard, matching `WaveformWindow`).
- Route `IndicatorWindow.show()/hide()` through the main thread (or remove the window — see below).
- Guard `screens()` for emptiness before indexing (bail like `WaveformWindow` does when `mainScreen()` is `None`).
- Remove dead code: `IndicatorWindow` (never shown) and `AudioLevelMonitor` (unused) — eliminating both the leaked window and the headless crash surface. If `IndicatorWindow` is removed, the marshaling/guard for it is moot; otherwise apply them.
- Add a test that asserts status/UI callbacks marshal to the main thread.

## Capabilities

### Added Capabilities
- `recording-visualization`: UI updates triggered from background threads SHALL be marshaled to the main thread, and visualization SHALL not crash on a display-less session.

## Impact

- `src/whispy/ui/menu_bar.py` — marshal `update_status_display`; route/remove `IndicatorWindow` usage.
- `src/whispy/ui/indicator_window.py` — guard `screens()`; or remove the module if `IndicatorWindow` is dropped.
- `src/whispy/ui/audio_level.py` — remove unused `AudioLevelMonitor` (and its test references).
- `tests/` — main-thread-marshaling assertion; update tests that reference removed dead code.

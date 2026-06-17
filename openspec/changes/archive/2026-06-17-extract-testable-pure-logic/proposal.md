## Why

The `define-test-perimeter` change classified several behaviors as `macos-real` or `manual-ui` — verified only by hand or by tests that mock the OS boundary. But part of that logic is actually pure (event flag-decoding, daemon path resolution, audio-level math, animation frame selection); it only *looks* untestable because it lives inside Quartz/rumps/sounddevice call sites. This is step **C** of the agreed D→C→B→A sequence: extract that pure logic into standalone functions so it becomes `unit-pure` and CI-verifiable, leaving only the irreducible OS calls as `macos-real` (step A).

## What Changes

- **event-listener**: extract the Fn press/release decision (`event_type` + `keycode` + `flags` + `trigger_keycode` → press / release / none) out of `EventTapListener._event_callback` into a pure function. Add unit tests; the callback becomes a thin wrapper that calls it. `_keycode_to_name` (already pure) gains direct test coverage.
- **core-engine (restart)**: extract daemon-script path resolution and the existence check from `menu_bar._on_reload` into a pure helper. The "resolves to daemon" and "any cwd" scenarios become `unit-pure`; only the relaunch + `rumps.quit_application()` stays `manual-ui`.
- **recording-visualization**: extract the audio-level computation (RMS → normalize → exponential moving average) from `AudioLevelMonitor._audio_callback` into a pure function, and extract the waveform animation frame-by-index selection. Add unit tests.
- **text-injection**: add spec requirements for the pure injection behaviors already implemented and tested but unspecced — quote escaping, empty-text no-op, clipboard/keystroke mode switch (noted as a gap in `define-test-perimeter`).
- **Re-tier** the affected scenarios from `macos-real`/`manual-ui` to `unit-pure` once a real test backs them, per the tier convention in `openspec/specs/TESTING-TIERS.md`.
- **No behavior change.** Extraction is refactor-only: call sites must produce identical runtime behavior. New code is pure functions + their tests.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `event-listener`: add a requirement that trigger-event decoding is a pure, unit-tested function (keycode→name mapping and Fn flag press/release decision), independent of the live event tap.
- `core-engine`: re-scope the "Restart uses correct entry point" requirement so path resolution is a pure, unit-tested helper (relaunch stays manual).
- `recording-visualization`: add a requirement that audio-level computation and animation frame selection are pure, unit-tested functions independent of sounddevice/rumps.
- `text-injection`: add requirements covering quote escaping, empty-text no-op, and clipboard/keystroke mode selection (pure, unit-tested).

## Impact

- **Source**: `src/whispy/hardware/event_tap.py`, `src/whispy/ui/menu_bar.py`, `src/whispy/ui/audio_level.py`, `src/whispy/ui/waveform_window.py` (frame selection), `src/whispy/hardware/injection.py` — extract pure functions; call sites delegate to them. No signature changes to public engine API.
- **Tests**: new `unit-pure` tests for each extracted function.
- **Coverage config**: `pyproject.toml` `coverage.run.omit` currently excludes `ui/*` and `event_tap.py`; the extracted pure functions should NOT be omitted (move them to a coverable module or narrow the omit).
- **Specs**: deltas to `event-listener`, `core-engine`, `recording-visualization`, `text-injection`, with re-tiered scenarios.
- **Downstream**: shrinks the `macos-real` work-list that step A must cover to the truly irreducible OS calls.

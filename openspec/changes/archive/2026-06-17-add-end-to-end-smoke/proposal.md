## Why

After D→C→B, the only untested behaviors left are the irreducible OS seams that mocks and logic-extraction can never cover: capturing real microphone audio via `sox`, injecting text via real `osascript`, and arming a live `CGEventTap`. This is step **A** of the D→C→B→A sequence — a real, unattended smoke layer that exercises those seams on a developer Mac with the right permissions, closing the last `macos-real` gap the test perimeter identified.

## What Changes

- **New capability `end-to-end-smoke`**: an unattended `macos-real` test layer (no human, no synthetic keypress) covering the three OS seams that only run for real:
  - **Real audio capture**: drive `AudioEngine.start()/stop()` against the default input device and assert the produced file is a valid 16 kHz mono WAV that grew past the readiness threshold.
  - **Real osascript clipboard seam**: set the clipboard via real `osascript` and read it back with `pbpaste`, proving the automation layer text injection relies on actually works on this machine. (The Cmd+V-into-focused-field paste stays operator-verified — out of unattended scope.)
  - **Live event tap**: start a real `EventTapListener` in a **subprocess** (the suite's `conftest.py` mocks `Quartz` globally, so real Quartz must be loaded outside that process) and assert it becomes active; **skip** when Input Monitoring is not granted or no device is available.
- All tests marked `@pytest.mark.macos` and tier `macos-real`; excluded from the default run, opt-in via `pytest -m macos`. Each seam **skips cleanly** when its permission/device is absent rather than failing.

## Capabilities

### New Capabilities
- `end-to-end-smoke`: unattended real-seam verification — real mic capture yields a valid WAV, real osascript clipboard round-trips, and a live CGEventTap arms when permission is granted.

### Modified Capabilities
<!-- none — additive test layer, no behavior change -->

## Impact

- **Tests**: new `tests/test_e2e_smoke.py`, `@pytest.mark.macos`; uses `sox`, `osascript`, `pbpaste` (all present) and a subprocess for the live tap.
- **No source impact**: `src/` unchanged.
- **CI**: untouched — these stay deselected by the existing `addopts = -m 'not macos'`.
- **Operator note**: the full human-in-the-loop flow (hold Fn, speak, see text appear in a focused app) is documented as a manual check; this change automates everything that can run without a human or synthetic input.
- **Downstream**: closes the last `macos-real` gap — every capability now has either an automated test or an explicit, documented manual/operator boundary.

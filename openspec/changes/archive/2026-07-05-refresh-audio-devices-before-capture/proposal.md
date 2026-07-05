# Refresh Audio Devices Before Capture

## Why

The daemon initializes PortAudio once at startup (when `sounddevice` is imported), which freezes the audio device list. When the default input device changes afterwards — a Bluetooth headset connects or disconnects, or the Mac wakes from sleep — the cached default device becomes stale and opening the capture stream fails with `PaErrorCode -9986`. The failure is silent for the user: `AudioEngine.start()` still returns `True`, the UI shows a recording in progress, and nothing is captured. Observed in production logs (`~/.whispy.log`) after a Bluetooth headset disconnect.

## What Changes

- Re-enumerate PortAudio devices (terminate + re-initialize the `sounddevice` host API) before opening each capture stream, so the stream always targets the current system default input device.
- If opening the stream still fails after a refresh, retry once after a second refresh before giving up.
- Surface a stream-open failure to the user instead of failing silently: log at warning level (already done) and notify via the existing UI notification path so the user knows no audio is being captured.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `audio-capture`: the "Capture stream fails to open" behavior changes — the engine must refresh the device list before opening the stream, retry once on failure, and report the failure to the user rather than only logging it. A new requirement covers following the system default input device across device changes (Bluetooth connect/disconnect, sleep/wake).

## Impact

- `src/whispy/core/audio.py` — `AudioEngine.start()` (stream opening path, `sd.RawInputStream` at ~line 322).
- `src/whispy/core/engine.py` — wiring for the user-facing failure notification (if not already reachable from the audio layer).
- `tests/test_audio.py` — new unit-mocked scenarios for refresh-before-open and retry-on-failure.
- No dependency changes; `sounddevice` already exposes `_terminate()`/`_initialize()`.
- No website impact (internal reliability fix, no user-facing feature or setting change).

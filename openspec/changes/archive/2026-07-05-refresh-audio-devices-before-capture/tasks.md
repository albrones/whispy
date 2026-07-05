# Tasks — Refresh Audio Devices Before Capture

## 1. Audio layer (src/whispy/core/audio.py)

- [x] 1.1 Add a `_refresh_devices()` helper on `AudioEngine`: `sd._terminate()` + `sd._initialize()`, no-op when `sd is None`, try/except that logs and continues on failure
- [x] 1.2 Call `_refresh_devices()` at the top of the stream-open path in `start()` (after the state-machine guard, before `sd.RawInputStream`)
- [x] 1.3 On stream-open exception, refresh once more and retry `sd.RawInputStream` exactly once; keep the existing give-up behavior (warning + `_ready.set()` + return True) when the retry also fails
- [x] 1.4 Record the final failure on the instance (e.g. `self._capture_failed: str | None`, reset at each `start()`) and expose it so the engine can report it

## 2. Engine notification (src/whispy/core/engine.py)

- [x] 2.1 Add `on_capture_failed(callback)` / `_notify_capture_failed(message)` pair mirroring `on_model_load_failed` (list of callbacks, try/except fan-out, warning log)
- [x] 2.2 Fire `_notify_capture_failed` from the recording-start path when the audio layer reports a capture failure

## 3. Menu bar UI (src/whispy/ui/menu_bar.py)

- [x] 3.1 Subscribe to `on_capture_failed` and post the existing-style notification (e.g. "No microphone available — check your input device")

## 4. Tests (tests/test_audio.py, tests/test_core.py)

- [x] 4.1 Unit-mocked: `start()` calls the refresh (terminate+initialize on the mocked `sd`) before opening the stream — pins the private-API usage
- [x] 4.2 Unit-mocked: refresh raising does not prevent the stream-open attempt
- [x] 4.3 Unit-mocked: first open raises, retry succeeds → recording proceeds, no capture failure recorded
- [x] 4.4 Unit-mocked: open raises twice → exactly one retry, failure recorded, `start()` still returns True and readiness wait released
- [x] 4.5 Unit-mocked: engine fires `on_capture_failed` callbacks with a message when audio reports failure; no fire on success
- [x] 4.6 Run full suite `./.venv/bin/pytest` — green

## 5. Validation & sync

- [x] 5.1 Manual smoke on macOS: start dictation, disconnect/reconnect a Bluetooth headset between recordings, verify capture follows the default input and a notification appears when no device is available
- [x] 5.2 Run `graphify update .` after code changes
- [x] 5.3 Website check: no user-facing feature/setting change → confirm no `website/index.html` update needed (`tests/test_website.py` still green via 4.6)

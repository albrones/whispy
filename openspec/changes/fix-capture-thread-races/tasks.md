## 1. WAV handle thread-safety (audio.py)

- [ ] 1.1 Add a lock guarding every access to `self._wave` (create/write/close/null)
- [ ] 1.2 Wrap the capture callback body in `try/except`; log once and set the ready event; never propagate into PortAudio

## 2. Per-recording file isolation (audio.py + engine.py)

- [ ] 2.1 Derive a unique path at recording start (replace the fixed `RECORDING_PATH`)
- [ ] 2.2 Thread the path through to transcription and cleanup as a parameter
- [ ] 2.3 Confirm cleanup removes the per-recording file on success and error paths

## 3. Gate stop_event on a real transition (engine.py)

- [ ] 3.1 Use the bool returned by `audio_engine.stop()`; set `stop_event` only on `RECORDING → TRANSCRIBING`
- [ ] 3.2 A release with no active recording is a no-op (no worker wake)

## 4. Surface model-load failure (engine.py)

- [ ] 4.1 Route `load_model_async` failure to the status/notifier callback instead of silent `model = None`
- [ ] 4.2 (Optional) one retry with backoff before reporting permanent failure

## 5. Tests

- [ ] 5.1 Concurrent callback-vs-stop does not raise and produces a valid or cleanly-discarded file
- [ ] 5.2 Trigger during TRANSCRIBING writes a different file than the worker is reading
- [ ] 5.3 Stray release (no active recording) does not start transcription
- [ ] 5.4 Model-load failure invokes the status/notifier callback

## 6. Verification

- [ ] 6.1 Run the full test suite; confirm no regression
- [ ] 6.2 `ruff check` / `ruff format --check` on changed files
- [ ] 6.3 `openspec validate fix-capture-thread-races --strict`

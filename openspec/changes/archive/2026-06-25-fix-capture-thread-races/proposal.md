## Why

The audio capture path has thread-safety and resource races that rapid hotkey toggling can hit in normal v1 use:

- **Unlocked `self._wave`**: the PortAudio callback thread writes/creates the WAV while `stop()` (hotkey thread) closes and nulls it, with no lock. `writeframes` on a just-closed wave raises inside the unguarded callback — corrupting/truncating the file or killing the audio thread.
- **Single shared `RECORDING_PATH`**: one fixed path is reused for record and transcribe. If the trigger fires during `TRANSCRIBING`, a new capture reopens the *same* file while the worker is still reading it → transcribe garbage or delete a file mid-write.
- **`stop_event` always set**: `_on_trigger_release` calls `stop_recording()` then unconditionally `state.stop_event.set()`. A stray release (no matching press) wakes the worker to transcribe a stale/missing file.
- **Silent model-load failure**: `load_model_async` swallows all errors into `model = None` with no user-facing signal. A failed download/SSL/mic error leaves the model permanently unloaded and every dictation silently returns nothing, forever, with no notification or retry.

These are the capture-orchestration follow-ups left open after `2026-06-15-code-health-audit-and-fixes`.

## What Changes

- Guard all `self._wave` access with a lock and wrap the capture callback body in `try/except` (log once, never let it propagate into the PortAudio C callback).
- Use a unique per-recording temp path captured at recording start and threaded through to transcription and cleanup, so concurrent record/transcribe never collide.
- Only set `stop_event` when `audio_engine.stop()` actually transitioned `RECORDING → TRANSCRIBING` (it already returns that bool); ignore stray releases.
- Surface model-load failure to a status/notifier callback so the UI/log tells the user (instead of silent permanent failure); consider a single retry.

## Capabilities

### Added Capabilities
- `audio-capture`: capture SHALL be thread-safe under concurrent stop, SHALL isolate each recording to its own file, and the callback SHALL never raise into the audio backend.
- `core-engine`: a stray trigger release SHALL NOT start transcription; model-load failure SHALL be surfaced to the user.

## Impact

- `src/whispy/core/audio.py` — lock around `_wave`; `try/except` in the callback; per-recording temp path instead of the fixed `RECORDING_PATH`.
- `src/whispy/core/engine.py` — gate `stop_event.set()` on the `stop()` transition result; surface model-load failure via the status/notifier callback; thread the per-recording path to transcription/cleanup.
- `tests/` — callback-vs-stop race, rapid-toggle file isolation, stray-release no-op, model-load-failure surfacing.

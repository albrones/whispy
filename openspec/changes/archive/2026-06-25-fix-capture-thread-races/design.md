## Context

Capture runs on the PortAudio callback thread; stop runs on the hotkey (event-tap) thread; transcription runs on a worker thread; the HTTP API runs on yet another. The state machine itself is already thread-safe, but the audio layer shares mutable handles (`self._wave`, the fixed `RECORDING_PATH`) across these threads without synchronization. The current tests don't see it because `test_audio`'s spy stream fires the callback synchronously inside `start()`, so real concurrency is never exercised.

## Goals / Non-Goals

**Goals:**
- No data race on the WAV handle; no callback exception reaching PortAudio.
- Each recording owns a distinct file; rapid toggle cannot cross-contaminate.
- Stray releases are no-ops; model-load failure is visible.

**Non-Goals:**
- Re-architecting the capture/transcribe orchestration into one shared engine path (separate, larger change).
- Changing the audio backend or model loader API.

## Decisions

### `_wave` locking + callback isolation
Introduce a `threading.Lock` guarding every read/write/close of `self._wave`. Wrap the callback body in `try/except Exception` that logs once and sets the ready event, so a disk-full / closed-handle error degrades to a lost recording with a log line instead of a dead audio thread or UB in the C callback.

### Per-recording path
At recording start, derive a unique path (e.g. `tempfile` or a counter/uuid suffix) and store it on the recording context. Transcription and cleanup take the path as a parameter rather than reading a module-level constant. A new recording during `TRANSCRIBING` therefore writes a different file than the one the worker reads.

### `stop_event` gating
`audio_engine.stop()` already returns whether it transitioned `RECORDING → TRANSCRIBING`. Set `stop_event` only when that is `True`. A release with no active recording returns `False` → no worker wake, no stale-file transcription.

### Model-load failure surfacing
`load_model_async` currently does `except Exception: model = None`. Route the failure to the existing status/notifier callback (the same channel the UI uses for permission/inject failures) so the user sees "model failed to load" and the menu state reflects it. Optionally one retry with backoff before giving up.

## Risks / Trade-offs

- Adding a lock to the hot capture callback: the critical section is a single `writeframes`, negligible cost vs. audio block cadence.
- Per-recording temp files must be cleaned even on error paths — covered by the existing temp-cleanup requirement; ensure the new path flows into it.

## Migration Plan

Pure correctness fixes; no config or API-shape change. The fixed `RECORDING_PATH` constant is removed/internalized — verify nothing else (tests, docs) references it.

## Open Questions

- Whether to retry model load once or surface-and-stop. Leaning surface + one retry, then stop with a clear status.

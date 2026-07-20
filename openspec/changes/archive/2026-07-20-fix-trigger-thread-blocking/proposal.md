## Why

An audit of the trigger and API paths found two HIGH-severity bugs plus related thread-safety gaps.

1. **Blocking work runs on the event-tap/hotkey callback thread.** `Engine.start_fn_listener()`'s
   `_on_trigger_press` closure runs directly on the macOS `CGEventTapListener` run-loop thread
   (`event_tap.py`'s `_event_callback`) and synchronously calls `_detect_corrections()` (blocking
   Accessibility reads), `_notifier.recording_started()`, then `start_recording()` →
   `AudioEngine.start()`, which itself calls `_refresh_devices()` (`sd._terminate`/`_initialize`,
   slow) and blocks up to 2.0s in `_wait_for_recording_ready()`. Symmetrically, on release,
   `_handle_trigger_release` → `stop_recording()` → `AudioEngine.stop()` does `stream.stop()`/`close()`
   plus a synchronous WAV flush, still on the callback thread. A slow listen-only `CGEventTap`
   callback risks macOS disabling the tap (`kCGEventTapDisabledByTimeout` — code already handles the
   symptom, not the cause). The same class of bug exists on Linux: `PynputHotkeyListener` runs
   press/release callbacks on pynput's single listener thread, so a blocking press handler stalls
   release detection too. Both platforms route through the *same* `Engine`-level closures, so the fix
   belongs in `Engine.start_fn_listener()`, not in either platform shell.
2. **`POST /stop` returns empty text in streaming mode** (the default, `streaming_enabled=True`).
   `RequestHandler._sync_stop_and_transcribe` calls `engine.run_transcription()`, which reads
   `_audio_engine.recording_path` — but in streaming mode no whole-file WAV is ever written, so it
   returns `None`. The streamed `_chunk_texts` accumulated by the chunk worker are never drained or
   assembled by `/stop`. Worse, `_sync_stop_and_transcribe` hand-rolls FSM/state mutations
   (`engine.state.is_recording`/`is_transcribing`, `engine._state_machine.transcription_complete()`)
   directly on the HTTP thread instead of going through the existing background transcription worker,
   so a concurrent hardware trigger release and an HTTP `/stop` can both observe a successful
   `stop_recording()` transition and race — risking double transcription/injection.

Related MED cleanups folded into the same change: `DictationState.lock` is constructed but never
acquired (dead code) while `_chunk_texts`/`_chunk_any_text` are mutated unlocked from three different
threads (the chunk worker appending, the transcription worker reading/assembling, and the FSM
recording-entry callback / watchdog force-recovery resetting them).

## What Changes

- Add a dedicated `trigger-worker` thread with a FIFO queue in `Engine`. The macOS/Linux callback
  closures wired in `start_fn_listener()` now only enqueue `"press"`/`"release"`; all of the actual
  work (`_detect_corrections()`, `_notify_fn_pressed()`/`_notify_fn_released()`, notifier sounds,
  `start_recording()`/`stop_recording()`) moves to the worker, preserving today's exact call order
  per event. This fixes both the macOS `CGEventTap` thread and the Linux `pynput` thread with a
  single change, since both funnel through the same `Engine` closures.
- Add `Engine.stop_and_wait_for_transcription()`: stops recording, and — only if that actually
  transitioned `RECORDING → TRANSCRIBING` — hands off to the *existing* background transcription
  worker via `state.stop_event` and waits (bounded) on a new `_transcription_done_event` for it to
  finish, then returns `state.last_transcription`. A stop request with nothing recording is a no-op
  that returns `None` immediately, without touching the stop event.
- `RequestHandler._sync_stop_and_transcribe` (`POST /stop`) now delegates to
  `Engine.stop_and_wait_for_transcription()` instead of hand-rolling FSM transitions and calling
  `run_transcription()` directly. This makes `/stop` correct in streaming mode (the worker already
  drains and assembles chunk text) and removes the HTTP-thread/worker race. As a side effect, `/stop`'s
  returned `text` now reflects the same cleaned/corrected text that was actually injected
  (`state.last_transcription`) in both streaming and non-streaming modes, instead of the raw
  pre-cleaning transcript the non-streaming path returned before. The endpoint also stops
  independently firing the success-cue sound — the worker's existing "sound only on real
  transcription" logic is now the single source of truth, fixing a latent always-plays-the-sound bug.
- Repurpose `DictationState.lock` to guard every read/mutation of `_chunk_texts` and
  `_chunk_any_text` across the chunk worker, the transcription worker, the FSM recording-entry
  callback, and the watchdog's forced recovery — closing the three unlocked cross-thread access
  points identified by the audit.

## Capabilities

### New Capabilities
<!-- none: this hardens existing behaviors -->

### Modified Capabilities
- `core-engine`: trigger press/release handling moves off the hardware-callback thread onto a
  dedicated worker; the stray-release no-op guard generalizes to any stop request (hardware release
  or `/stop`); `_chunk_texts`/`_chunk_any_text` access is now lock-guarded.
- `api-interface`: `POST /stop` reuses the background transcription worker (correct streaming
  behavior, no HTTP-thread race, no duplicate success sound) instead of transcribing ad hoc.

## Impact

- Code: `src/whispy/core/engine.py` (trigger queue + worker thread, `stop_and_wait_for_transcription`,
  `_transcription_done_event`, lock-guarded chunk state), `src/whispy/api/server.py`
  (`_sync_stop_and_transcribe` delegates to the new engine method).
- No changes needed in `src/whispy/hardware/event_tap.py` or `src/whispy/platform/linux/hotkey.py` —
  both already just invoke the `Engine`-supplied callbacks, so fixing the closures in
  `start_fn_listener()` fixes both platforms.
- Behavior: happy-path latency for press/release feedback is effectively unchanged (the worker thread
  is idle and picks up queued events immediately); `/stop`'s JSON response now carries the cleaned,
  corrected, actually-injected text rather than the raw pre-cleaning transcript.
- Tests: new unit tests for trigger-callback handoff ordering (press-then-release processed in order,
  callback returns immediately), for `stop_and_wait_for_transcription` (streaming assembly, stray
  no-op, timeout fallback), and a regression test asserting `/stop` returns assembled chunk text in
  streaming mode without racing the worker.
- No API/config surface changes, no new dependencies. No `website/index.html` update needed — this is
  an internal correctness fix with no new/changed/removed user-facing setting or feature.

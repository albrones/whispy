## ADDED Requirements

### Requirement: Trigger callbacks hand off to a dedicated worker thread

The engine SHALL NOT perform blocking work — Accessibility reads for correction detection, audio
device start/stop, or WAV flush — directly on the hardware trigger listener's own thread (the macOS
`CGEventTap` run-loop thread or the Linux `pynput` listener thread). Instead, the press/release
callbacks registered with the hotkey adapter SHALL only enqueue a signal onto a dedicated queue; a
single dedicated `trigger-worker` thread SHALL consume that queue in arrival order and perform the
actual work (correction detection, pressed/released notifications, notifier sounds, and
`start_recording()`/`stop_recording()`), preserving the same call order used before this requirement
existed. Because both the macOS and Linux hotkey adapters invoke the same engine-level callbacks,
this handoff SHALL cover both platforms without platform-specific changes to the hotkey adapters
themselves.

#### Scenario: Press callback returns without blocking

- **WHEN** the hotkey adapter invokes the engine's trigger-press callback
- **THEN** the callback SHALL return after only enqueuing the press signal, without calling
  correction detection or starting audio recording itself

_Tier: unit-mocked — `test_engine.py` (callback timing/ordering asserted with audio/AX mocked)._

#### Scenario: Release callback returns without blocking

- **WHEN** the hotkey adapter invokes the engine's trigger-release callback
- **THEN** the callback SHALL return after only enqueuing the release signal, without stopping audio
  recording itself

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Press and release are processed in arrival order

- **WHEN** a press signal and a subsequent release signal are enqueued in quick succession
- **THEN** the trigger-worker thread SHALL process the press before the release, matching the order
  the hardware events arrived in

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Worker preserves the pre-handoff call order on press

- **WHEN** the trigger-worker thread processes a press signal
- **THEN** it SHALL perform correction detection, then notify pressed listeners, then play the
  recording-started cue, then call `start_recording()`, in that order

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Worker preserves the pre-handoff call order on release

- **WHEN** the trigger-worker thread processes a release signal
- **THEN** it SHALL notify released listeners, then call `stop_recording()`, and SHALL set the
  transcription stop event only if that call actually transitioned `RECORDING` to `TRANSCRIBING`

_Tier: unit-mocked — `test_engine.py`._

### Requirement: Chunk accumulation state is thread-safe

Every access to `_chunk_texts` and `_chunk_any_text` SHALL be guarded by `DictationState.lock`, held only around the field access itself and never across a blocking call (transcription, injection, or a lock wait). These fields are written and read from three different threads: the chunk worker appending recognized chunk text, the transcription worker reading them to assemble and inject, and the FSM recording-entry callback / watchdog forced-recovery resetting them for a new cycle.

#### Scenario: Chunk worker append is lock-guarded

- **WHEN** the chunk worker appends a recognized chunk's text to `_chunk_texts`
- **THEN** it SHALL hold `DictationState.lock` for the append and the `_chunk_any_text` update

_Tier: unit-mocked — `test_engine.py` (lock acquisition asserted via a mock/spy lock)._

#### Scenario: Transcription worker read is lock-guarded

- **WHEN** the transcription worker reads `_chunk_texts`/`_chunk_any_text` to assemble the release
  text and decide whether a success cue is warranted
- **THEN** it SHALL take a lock-guarded snapshot of both fields before releasing the lock and
  performing injection

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Recording-entry reset is lock-guarded

- **WHEN** the FSM enters `RECORDING` and the engine resets `_chunk_texts`/`_chunk_any_text` for the
  new cycle
- **THEN** the reset SHALL be performed under `DictationState.lock`

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Watchdog forced-recovery reset is lock-guarded

- **WHEN** the watchdog force-recovers a wedged FSM and resets `_chunk_texts`/`_chunk_any_text`
- **THEN** the reset SHALL be performed under `DictationState.lock`

_Tier: unit-mocked — `test_engine.py`._

### Requirement: Synchronous stop reuses the background transcription worker

The engine SHALL expose a method (`stop_and_wait_for_transcription`) that stops recording and, only
if that actually transitioned `RECORDING` to `TRANSCRIBING`, hands off to the existing background
transcription worker via `state.stop_event` and waits — bounded by an internal timeout — for a
dedicated completion signal before returning the resulting text. This SHALL be the single code path
used both by the trigger-release flow's asynchronous handling and by any caller needing a synchronous
result (e.g. the HTTP API), so streaming-mode chunk draining/assembly is never reimplemented outside
the worker.

#### Scenario: Streaming mode returns assembled chunk text

- **WHEN** `stop_and_wait_for_transcription` is called while streaming produced one or more chunks
- **THEN** it SHALL wait for the worker to drain the chunk queue and assemble the chunks' text, and
  SHALL return that assembled, injected text

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Nothing was recording is a no-op

- **WHEN** `stop_and_wait_for_transcription` is called while the system is not recording
- **THEN** it SHALL NOT set the transcription stop event and SHALL return `None` immediately,
  without waiting on the completion signal

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Worker completion unblocks the wait promptly

- **WHEN** the background transcription worker finishes handling the stop signal
- **THEN** it SHALL set the completion signal so a caller blocked in
  `stop_and_wait_for_transcription` returns without waiting for the full timeout

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Watchdog recovery also unblocks a waiter

- **WHEN** the watchdog force-recovers a wedged `TRANSCRIBING` state
- **THEN** it SHALL also set the completion signal, so a caller blocked in
  `stop_and_wait_for_transcription` does not wait out the full timeout after the watchdog already
  resolved the cycle

_Tier: unit-mocked — `test_engine.py`._

## MODIFIED Requirements

### Requirement: Stray trigger release does not start transcription

The engine SHALL set the transcription stop event only when stopping actually transitioned the
system from `RECORDING` to `TRANSCRIBING`, so that any stop request with no active recording — a
trigger release, or a call to `stop_and_wait_for_transcription` (used by e.g. the HTTP `/stop`
endpoint) — is a no-op that starts no transcription of a stale or missing file.

#### Scenario: Release with no active recording

- **WHEN** a trigger release is handled while the system is not recording
- **THEN** the engine SHALL NOT set the stop event and SHALL NOT start transcription of a stale or
  missing file

#### Scenario: Stop request with no active recording

- **WHEN** `stop_and_wait_for_transcription` is called while the system is not recording
- **THEN** the engine SHALL NOT set the stop event, SHALL NOT start transcription of a stale or
  missing file, and SHALL return `None` immediately

_Tier: unit-mocked — `test_engine.py`._

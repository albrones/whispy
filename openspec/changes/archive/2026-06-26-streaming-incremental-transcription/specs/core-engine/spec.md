## ADDED Requirements

### Requirement: Chunk pipeline runs during RECORDING without a composite FSM state
When streaming is enabled, the engine SHALL run chunk transcription and injection
through an ordered pipeline that is active **during** the `RECORDING` state,
without introducing a new state machine state. The state machine SHALL keep
`IDLE → RECORDING → TRANSCRIBING → IDLE` and SHALL keep `RECORDING` as the sole
owner of the recording lifecycle. `TRANSCRIBING` (and therefore `is_transcribing`)
SHALL denote only the final tail flush after trigger release, so existing
status/UI consumers that read `is_recording`/`is_transcribing` are unaffected.

#### Scenario: Chunks transcribe while still recording
- **WHEN** streaming is enabled and chunks are emitted during recording
- **THEN** the engine SHALL transcribe and inject them while the state machine remains in `RECORDING`, without entering `TRANSCRIBING`

#### Scenario: is_transcribing reflects only the tail flush
- **WHEN** the engine is injecting mid-recording chunks
- **THEN** `is_transcribing` SHALL remain false until the trigger-release tail flush

#### Scenario: No new FSM state is introduced
- **WHEN** the streaming pipeline is active
- **THEN** the state machine's set of valid states SHALL remain `IDLE`, `RECORDING`, and `TRANSCRIBING`

## MODIFIED Requirements

### Requirement: Transcription worker always returns the FSM to IDLE
The transcription worker SHALL, upon receiving a stop signal, always return the
state machine to `IDLE` after handling the recording — whether transcription
produced text, produced no usable text (empty or cleaned-to-empty output), or
raised an error. When streaming is enabled, the stop signal handling SHALL flush
and transcribe the final tail chunk; when disabled, it SHALL transcribe the whole
recording as before. In either mode, a failure in transcription SHALL NOT
terminate the worker thread or leave the system wedged in the `TRANSCRIBING`
state.

#### Scenario: Empty transcription completes the FSM
- **WHEN** the worker is signaled to stop and transcription yields no usable text (empty or cleaned-to-empty)
- **THEN** the worker SHALL call `transcription_complete()` so the FSM returns to `IDLE`

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Transcription error does not wedge the FSM
- **WHEN** transcription raises an exception while the worker is handling a stop signal
- **THEN** the worker SHALL log the error, return the FSM to `IDLE`, and remain alive to handle the next recording

#### Scenario: Streaming tail flush completes the FSM
- **WHEN** streaming is enabled and the worker handles the stop signal for the final tail chunk
- **THEN** the worker SHALL transcribe/inject the tail chunk (if any usable text) and return the FSM to `IDLE`

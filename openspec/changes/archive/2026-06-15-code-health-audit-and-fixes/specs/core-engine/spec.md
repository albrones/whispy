## ADDED Requirements

### Requirement: Transcription worker always returns the FSM to IDLE
The transcription worker SHALL, upon receiving a stop signal, always return the state machine to `IDLE` after handling the recording — whether transcription produced text, produced no usable text (empty or cleaned-to-empty output), or raised an error. A failure in transcription SHALL NOT terminate the worker thread or leave the system wedged in the `TRANSCRIBING` state.

#### Scenario: Empty transcription completes the FSM
- **WHEN** the worker is signaled to stop and transcription yields no usable text (empty or cleaned-to-empty)
- **THEN** the worker SHALL call `transcription_complete()` so the FSM returns to `IDLE`

#### Scenario: Transcription error does not wedge the FSM
- **WHEN** transcription raises an exception while the worker is handling a stop signal
- **THEN** the worker SHALL log the error, return the FSM to `IDLE`, and remain alive to handle the next recording

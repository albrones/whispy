## ADDED Requirements

### Requirement: Stray trigger release does not start transcription
The engine SHALL set the transcription stop event only when stopping actually transitioned the system from `RECORDING` to `TRANSCRIBING`, so a trigger release with no active recording is a no-op.

#### Scenario: Release with no active recording
- **WHEN** a trigger release is handled while the system is not recording
- **THEN** the engine SHALL NOT set the stop event and SHALL NOT start transcription of a stale or missing file

### Requirement: Model-load failure is surfaced
When the transcription model fails to load, the engine SHALL report the failure through the status/notifier callback rather than leaving the model silently unloaded.

#### Scenario: Model fails to load
- **WHEN** asynchronous model loading raises (download, SSL, or backend error)
- **THEN** the engine SHALL invoke the status/notifier callback with a failure signal so the user is informed, instead of silently returning no text on every subsequent dictation

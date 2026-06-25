## ADDED Requirements

### Requirement: Capture is thread-safe under concurrent stop
Audio capture SHALL synchronize access to the WAV handle so the capture callback thread and the stop thread cannot race, and the capture callback SHALL never propagate an exception into the audio backend.

#### Scenario: Stop during an in-flight callback
- **WHEN** `stop()` closes the recording while the PortAudio callback is mid-write
- **THEN** access to the WAV handle SHALL be serialized so neither thread writes to a closed handle, and any callback error SHALL be logged and contained (never raised into PortAudio)

### Requirement: Each recording is isolated to its own file
Each recording SHALL write to a unique path captured at recording start, so a recording started while a previous transcription is still reading does not corrupt or delete the in-use file.

#### Scenario: Trigger fires during transcription
- **WHEN** a new recording starts while the transcription worker is still reading the prior recording
- **THEN** the new recording SHALL write to a different file and the worker's file SHALL remain intact until cleanup

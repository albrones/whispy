## ADDED Requirements

### Requirement: State Management and Lifecycle
The core engine SHALL manage the lifecycle of recording and transcription processes, ensuring that only one primary activity (recording or transcribing) is active at any given time.

#### Scenario: Transition from Idle to Recording
- **WHEN** a recording command is received while the system is in IDLE state
- **THEN** the engine SHALL start the audio recording process and transition to RECORDING state

#### Scenario: Transition from Recording to Transcribing
- **WHEN** a stop command is received while the system is in RECORDING state
- **THEN** the engine SHALL terminate the recording process, transition to TRANSCRIBING state, and initiate the transcription task

#### Scenario: Transition from Transcribing to Idle
- **WHEN** the transcription process completes successfully
- **THEN** the engine SHALL transition to IDLE state and notify listeners of the result

### Requirement: Audio File Management
The engine SHALL manage the creation, usage, and cleanup of temporary audio files used for transcription.

#### Scenario: Successful Audio Cleanup
- **WHEN** a transcription task is completed or fails
- **THEN** the engine SHALL ensure the temporary audio file used for that task is deleted from the filesystem

## ADDED Requirements

### Requirement: Configuration Loading
The engine SHALL load and maintain the application configuration, providing access to model settings and language preferences.

#### Scenario: Configuration Update
- **WHEN** a configuration change (e.s. model size) is detected
- **THEN** the engine SHALL trigger a reload of the transcription model to reflect the new settings

# core-engine Specification

## Purpose
TBD - created by archiving change architectural-retrospective-and-stabilization. Update Purpose after archive.
## Requirements
### Requirement: Configuration Loading
The engine SHALL load and maintain the application configuration, providing access to model settings and language preferences. The default language SHALL be French (`"fr"`) and clipboard copy SHALL be disabled by default (`False`). The engine SHALL also apply text cleaning to strip Whisper watermark credits from transcription output before text injection. The engine SHALL validate configuration keys against `DEFAULT_CONFIG` before persisting to disk.

#### Scenario: Configuration Update
- **WHEN** a configuration change (e.g. model size) is detected
- **THEN** the engine SHALL trigger a reload of the transcription model to reflect the new settings

#### Scenario: Default language is French
- **WHEN** the application starts with no saved config
- **THEN** the engine SHALL use French (`"fr"`) as the default language

#### Scenario: Default copy to clipboard is disabled
- **WHEN** the application starts with no saved config
- **THEN** the engine SHALL use `copy_to_clipboard: False` as the default

#### Scenario: Whisper credit is stripped from output
- **WHEN** transcription produces text starting with a known Whisper credit phrase
- **THEN** the credit prefix is removed before the text is injected into the active field

#### Scenario: Config validation filters unknown keys
- **WHEN** `save_config` is called with keys not in `DEFAULT_CONFIG`
- **THEN** only known keys are saved and a warning is logged to stderr

### Requirement: Restart uses correct entry point
The menu bar "Restart" item SHALL launch the application using the correct entry point file `whispy_daemon.py` located at the project root.

#### Scenario: Restart path resolves to daemon
- **WHEN** user clicks the "Restart" menu item
- **THEN** the application launches `whispy_daemon.py` from the project root directory

#### Scenario: Restart path works from any working directory
- **WHEN** the application is launched from any working directory
- **THEN** the restart path correctly resolves to `whispy_daemon.py` at the project root

#### Scenario: Restart exits current instance
- **WHEN** user clicks the "Restart" menu item
- **THEN** the current menu bar application instance quits after launching the new instance

### Requirement: Transcription worker always returns the FSM to IDLE
The transcription worker SHALL, upon receiving a stop signal, always return the state machine to `IDLE` after handling the recording — whether transcription produced text, produced no usable text (empty or cleaned-to-empty output), or raised an error. A failure in transcription SHALL NOT terminate the worker thread or leave the system wedged in the `TRANSCRIBING` state.

#### Scenario: Empty transcription completes the FSM
- **WHEN** the worker is signaled to stop and transcription yields no usable text (empty or cleaned-to-empty)
- **THEN** the worker SHALL call `transcription_complete()` so the FSM returns to `IDLE`

#### Scenario: Transcription error does not wedge the FSM
- **WHEN** transcription raises an exception while the worker is handling a stop signal
- **THEN** the worker SHALL log the error, return the FSM to `IDLE`, and remain alive to handle the next recording


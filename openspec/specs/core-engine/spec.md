# core-engine Specification

## Purpose
TBD - created by archiving change architectural-retrospective-and-stabilization. Update Purpose after archive.

Scenario test tiers follow the convention in `../TESTING-TIERS.md`.

## Requirements
### Requirement: Configuration Loading
The engine SHALL load and maintain the application configuration, providing access to model settings and language preferences. The default language SHALL be French (`"fr"`) and clipboard copy SHALL be disabled by default (`False`). The engine SHALL also apply text cleaning to strip Whisper watermark credits from transcription output before text injection. The engine SHALL validate configuration keys against `DEFAULT_CONFIG` before persisting to disk.

#### Scenario: Configuration Update
- **WHEN** a configuration change (e.g. model size) is detected
- **THEN** the engine SHALL trigger a reload of the transcription model to reflect the new settings

_Tier: unit-mocked — `test_e2e.py` (model reload flag asserted; WhisperModel mocked)._

#### Scenario: Default language is French
- **WHEN** the application starts with no saved config
- **THEN** the engine SHALL use French (`"fr"`) as the default language

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Default copy to clipboard is disabled
- **WHEN** the application starts with no saved config
- **THEN** the engine SHALL use `copy_to_clipboard: False` as the default

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Whisper credit is stripped from output
- **WHEN** transcription produces text starting with a known Whisper credit phrase
- **THEN** the credit prefix is removed before the text is injected into the active field

_Tier: unit-mocked — `test_e2e.py` (injection path with subprocess mocked)._

#### Scenario: Config validation filters unknown keys
- **WHEN** `save_config` is called with keys not in `DEFAULT_CONFIG`
- **THEN** only known keys are saved and a warning is logged to stderr

_Tier: unit-pure — `test_config_validation.py`._

### Requirement: Restart uses correct entry point
The menu bar "Restart" item SHALL launch the application using the correct entry point file `whispy_daemon.py` located at the project root. The resolution of that path and the check for its existence SHALL be performed by a pure, unit-tested helper independent of the menu bar UI; the menu callback SHALL delegate path resolution to that helper and only then perform the relaunch and quit.

#### Scenario: Restart path resolves to daemon
- **WHEN** the path-resolution helper is invoked
- **THEN** it SHALL return the path to `whispy_daemon.py` at the project root

_Tier: unit-pure — `test_paths.py`, `test_config_validation.py::TestRestartPath`._

#### Scenario: Restart path works from any working directory
- **WHEN** the path-resolution helper is invoked from any current working directory
- **THEN** it SHALL return the same project-root `whispy_daemon.py` path (resolution is independent of cwd)

_Tier: unit-pure — `test_paths.py::test_resolution_is_independent_of_cwd`._

#### Scenario: Missing daemon script is detected before relaunch
- **WHEN** the existence check reports that the resolved script does not exist
- **THEN** the restart action SHALL NOT spawn a process and SHALL surface a "Restart file not found" condition

_Tier: unit-pure (existence check) — `test_paths.py::TestDaemonScriptExists`; the alert/relaunch UI stays manual-ui._

#### Scenario: Restart exits current instance
- **WHEN** the user clicks the "Restart" menu item and the script exists
- **THEN** the application launches the new instance and the current menu bar instance quits

_Tier: manual-ui — relaunch + quit is not unit-testable._

### Requirement: Transcription worker always returns the FSM to IDLE
The transcription worker SHALL, upon receiving a stop signal, always return the state machine to `IDLE` after handling the recording — whether transcription produced text, produced no usable text (empty or cleaned-to-empty output), or raised an error. A failure in transcription SHALL NOT terminate the worker thread or leave the system wedged in the `TRANSCRIBING` state.

#### Scenario: Empty transcription completes the FSM
- **WHEN** the worker is signaled to stop and transcription yields no usable text (empty or cleaned-to-empty)
- **THEN** the worker SHALL call `transcription_complete()` so the FSM returns to `IDLE`

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Transcription error does not wedge the FSM
- **WHEN** transcription raises an exception while the worker is handling a stop signal
- **THEN** the worker SHALL log the error, return the FSM to `IDLE`, and remain alive to handle the next recording

_Tier: unit-mocked — `test_engine.py`._

### Requirement: Custom vocabulary biases transcription
The engine SHALL support an optional `custom_vocabulary` configuration value (a list of words or phrases). When the list is non-empty, the engine SHALL pass it to the transcription call as an `initial_prompt` so that recognition is biased toward the user's habitual terms. When the list is empty or absent, transcription SHALL behave exactly as before (no prompt passed).

#### Scenario: Vocabulary present biases the decoder
- **WHEN** `custom_vocabulary` contains one or more terms and a recording is transcribed
- **THEN** the engine SHALL pass an `initial_prompt` built from those terms to the Whisper transcription call

_Tier: unit-mocked — `test_engine.py` (initial_prompt asserted; WhisperModel mocked). Whether the prompt actually improves recognition is a `macos-real` concern → step B._

#### Scenario: Empty vocabulary changes nothing
- **WHEN** `custom_vocabulary` is empty or absent
- **THEN** the engine SHALL NOT pass an `initial_prompt` (transcription behaves as before)

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Invalid vocabulary falls back safely
- **WHEN** `custom_vocabulary` is loaded with a non-list value or with non-string entries
- **THEN** config validation SHALL coerce it to a list containing only the valid string entries (an entirely invalid value becomes an empty list) and SHALL NOT raise

_Tier: unit-pure — `test_config_validation.py`._

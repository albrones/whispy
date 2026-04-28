## MODIFIED Requirements

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

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Configuration Loading
The engine SHALL load and maintain the application configuration, providing access to model settings and language preferences. The default language SHALL be French (`"fr"`) and clipboard copy SHALL be disabled by default. The engine SHALL always use `"cpu-int8"` as the compute backend. The trigger key is always hardcoded to `"fn"` (keycode 44) and is no longer configurable.

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

#### Scenario: Compute backend is always cpu-int8
- **WHEN** the engine loads a model
- **THEN** the engine SHALL always use `"cpu-int8"` as the compute backend, regardless of any saved config value

#### Scenario: Trigger key is always fn
- **WHEN** the engine starts the Fn listener
- **THEN** the engine SHALL always use keycode 44 (Fn key) as the trigger, regardless of any saved config value

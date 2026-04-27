## MODIFIED Requirements

### Requirement: Configuration Loading
The engine SHALL load and maintain the application configuration, providing access to model settings and language preferences. The default language SHALL be French (`"fr"`) and clipboard copy SHALL be disabled by default.

#### Scenario: Configuration Update
- **WHEN** a configuration change (e.g. model size) is detected
- **THEN** the engine SHALL trigger a reload of the transcription model to reflect the new settings

#### Scenario: Default language is French
- **WHEN** the application starts with no saved config
- **THEN** the engine SHALL use French (`"fr"`) as the default language

#### Scenario: Default copy to clipboard is disabled
- **WHEN** the application starts with no saved config
- **THEN** the engine SHALL use `copy_to_clipboard: False` as the default

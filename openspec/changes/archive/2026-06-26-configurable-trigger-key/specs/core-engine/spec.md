## MODIFIED Requirements

### Requirement: Configuration Loading
The engine SHALL load and maintain the application configuration, providing access to model settings and language preferences. The default language SHALL be French (`"fr"`) and clipboard copy SHALL be disabled by default (`False`). The engine SHALL also apply text cleaning to strip Whisper watermark credits from transcription output before text injection. The engine SHALL validate configuration keys against `DEFAULT_CONFIG` before persisting to disk. When a configuration update changes the `trigger` key, the engine SHALL restart the key listener so the new trigger takes effect without a manual Restart.

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

#### Scenario: Trigger change restarts the listener
- **WHEN** `update_config` is called with a new `trigger` value while the key listener is active
- **THEN** the engine SHALL stop and restart the listener with the resolved trigger, so the new key is live without a manual Restart

_Tier: unit-mocked — listener stop/start asserted with the hotkey adapter mocked._

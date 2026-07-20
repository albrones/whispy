## MODIFIED Requirements

### Requirement: Configuration Loading
The engine SHALL load and maintain the application configuration, providing access to model settings and language preferences. The default language SHALL be English (`"en"`) and clipboard copy SHALL be disabled by default (`False`). The engine SHALL also apply text cleaning to strip Whisper watermark credits from transcription output before text injection. The engine SHALL validate configuration keys against `DEFAULT_CONFIG` before persisting to disk. When a configuration update changes the `trigger` key, the engine SHALL restart the key listener so the new trigger takes effect without a manual Restart. Existing installs with a persisted `language` value SHALL keep that value — the default only applies when the key (or the config file) is absent. `save_config` SHALL create the `~/.config/whispy` directory with `0700` permissions and SHALL persist `config.json` with `0600` permissions on every save, including the first save after upgrading from a version that wrote the file without restricting permissions; a failure to set these permissions SHALL be logged but SHALL NOT prevent the config from being saved.

#### Scenario: Configuration Update
- **WHEN** a configuration change (e.g. model size) is detected
- **THEN** the engine SHALL trigger a reload of the transcription model to reflect the new settings

_Tier: unit-mocked — `test_e2e.py` (model reload flag asserted; WhisperModel mocked)._

#### Scenario: Default language is English
- **WHEN** the application starts with no saved config
- **THEN** the engine SHALL use English (`"en"`) as the default language

_Tier: unit-pure — `test_config_validation.py`, `test_engine.py::TestLoadConfig::test_default_language_is_english`._

#### Scenario: Existing persisted language is not overridden
- **WHEN** a config file already exists on disk with a `language` value (e.g. `"fr"`, set before this change)
- **THEN** loading the config SHALL return that persisted value, not the new default

_Tier: unit-pure — `test_engine.py::TestLoadConfig`._

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

#### Scenario: Config file is owner-only readable
- **WHEN** `save_config` writes `config.json`
- **THEN** the resulting file on disk SHALL have `0600` permissions

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Pre-existing world-readable config is tightened on next save
- **WHEN** `config.json` already exists with `0644` permissions from a prior version and `save_config` is called
- **THEN** the resulting file SHALL have `0600` permissions (no separate migration step required)

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Config directory is owner-only
- **WHEN** `save_config` runs and `~/.config/whispy` does not yet have `0700` permissions
- **THEN** the directory SHALL be set to `0700` as part of the save

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Permission failure does not block the save
- **WHEN** setting `0600`/`0700` permissions raises `OSError` (e.g. an unusual filesystem)
- **THEN** `save_config` SHALL log the failure and still complete the write to `config.json`

_Tier: unit-pure — `test_config_validation.py`._

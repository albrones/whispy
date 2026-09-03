## MODIFIED Requirements

### Requirement: Configuration Loading
The engine SHALL load and maintain the application configuration. Clipboard copy SHALL be disabled by default (`False`). The engine SHALL validate configuration keys against `DEFAULT_CONFIG` before persisting to disk; keys absent from `DEFAULT_CONFIG` — including `model_size`, `language`, `beam_size`, `best_of`, and `auto_detect_min_duration` left behind by an earlier version — SHALL be dropped without raising, so an existing config file keeps loading after the upgrade. When a configuration update changes the `trigger` key, the engine SHALL restart the key listener so the new trigger takes effect without a manual Restart. The engine SHALL apply text cleaning to transcription output before text injection. `save_config` SHALL create the `~/.config/whispy` directory with `0700` permissions and SHALL persist `config.json` with `0600` permissions on every save, including the first save after upgrading from a version that wrote the file without restricting permissions; a failure to set these permissions SHALL be logged but SHALL NOT prevent the config from being saved.

#### Scenario: Legacy keys are dropped, not fatal
- **WHEN** a config file written by a pre-Parakeet version is loaded, carrying `model_size` and `language`
- **THEN** loading SHALL succeed, those keys SHALL NOT appear in the validated config, and the next save SHALL persist the file without them

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Default copy to clipboard is disabled
- **WHEN** the application starts with no saved config
- **THEN** the engine SHALL use `False` for `copy_to_clipboard`

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Trigger change restarts the listener
- **WHEN** a configuration update changes the `trigger` key
- **THEN** the engine SHALL restart the key listener without requiring a manual Restart

_Tier: unit-mocked — `test_engine.py`._

### Requirement: Custom vocabulary biases transcription
The engine SHALL support an optional `custom_vocabulary` configuration value (a list of words or phrases). Because the transducer backend exposes no decoder-biasing channel, the vocabulary SHALL be applied **after** transcription as near-miss correction during text cleaning, not passed to the transcription call. The engine SHALL NOT pass any prompt, hotword, or vocabulary argument to the transcription call. When the list is empty or absent, cleaning SHALL leave transcription output unchanged.

#### Scenario: Vocabulary reaches cleaning, not the model
- **WHEN** `custom_vocabulary` contains one or more terms and a recording is transcribed
- **THEN** the transcription call SHALL receive no vocabulary argument, and the configured terms SHALL be supplied to the text-cleaning step

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Empty vocabulary changes nothing
- **WHEN** `custom_vocabulary` is empty or absent
- **THEN** cleaning SHALL return the transcription output with only normal whitespace normalization applied

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Invalid vocabulary falls back safely
- **WHEN** `custom_vocabulary` is loaded with a non-list value or with non-string entries
- **THEN** config validation SHALL coerce it to a list containing only the valid string entries (an entirely invalid value becomes an empty list) and SHALL NOT raise

_Tier: unit-pure — `test_config_validation.py`._

### Requirement: Model-load failure is surfaced
When the transcription model fails to load, the engine SHALL report the failure through the status/notifier callback rather than leaving the model silently unloaded, and the failure SHALL reach an actual UI consumer rather than only being logged. The loader's own contract — one retry, then report — is specified in `asr-backend`.

#### Scenario: Model fails to load
- **WHEN** asynchronous model loading raises (download, SSL, or onnxruntime session error)
- **THEN** the engine SHALL invoke the status/notifier callback with a failure signal so the user is informed, instead of silently returning no text on every subsequent dictation

#### Scenario: Menu bar consumes the model-load-failure callback
- **WHEN** the menu bar application initializes
- **THEN** it SHALL register a handler for `on_model_load_failed` and, when it fires, SHALL post a user-visible notification with actionable guidance (check connectivity, then Restart) — the hook SHALL NOT exist without a UI consumer

_Tier: unit-pure — `test_menu_bar.py::TestAlertWiring::test_init_registers_alert_callbacks`._

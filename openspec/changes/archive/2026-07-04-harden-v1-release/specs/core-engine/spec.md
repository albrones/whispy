## MODIFIED Requirements

### Requirement: Configuration Loading
The engine SHALL load and maintain the application configuration, providing access to model settings and language preferences. The default language SHALL be English (`"en"`) and clipboard copy SHALL be disabled by default (`False`). The engine SHALL also apply text cleaning to strip Whisper watermark credits from transcription output before text injection. The engine SHALL validate configuration keys against `DEFAULT_CONFIG` before persisting to disk. When a configuration update changes the `trigger` key, the engine SHALL restart the key listener so the new trigger takes effect without a manual Restart. Existing installs with a persisted `language` value SHALL keep that value — the default only applies when the key (or the config file) is absent.

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

### Requirement: Model-load failure is surfaced
When the transcription model fails to load, the engine SHALL report the failure through the status/notifier callback rather than leaving the model silently unloaded, and the failure SHALL reach an actual UI consumer rather than only being logged.

#### Scenario: Model fails to load
- **WHEN** asynchronous model loading raises (download, SSL, or backend error)
- **THEN** the engine SHALL invoke the status/notifier callback with a failure signal so the user is informed, instead of silently returning no text on every subsequent dictation

#### Scenario: Menu bar consumes the model-load-failure callback
- **WHEN** the menu bar application initializes
- **THEN** it SHALL register a handler for `on_model_load_failed` and, when it fires, SHALL post a user-visible notification with actionable guidance (check connectivity, then Restart) — the hook SHALL NOT exist without a UI consumer

_Tier: unit-pure — `test_menu_bar.py::TestAlertWiring::test_init_registers_alert_callbacks` (asserts the registration call is present in `__init__`)._

## ADDED Requirements

### Requirement: Explicitly denied startup permissions are surfaced
`Engine.start()` SHALL probe Microphone, Input Monitoring, Accessibility, and Automation access at startup. Each probe reports one of three states — granted, explicitly denied, or undetermined (the system permission prompt is pending or the probe is unavailable). The engine SHALL fire `on_permission_missing(kind, message)` only for explicit denials; a granted or undetermined result SHALL stay silent, since warning on an undetermined state would be redundant with the OS's own prompt.

#### Scenario: Explicit denial fires with actionable guidance
- **WHEN** a startup permission probe reports an explicit denial (e.g. Microphone or Input Monitoring)
- **THEN** the engine SHALL invoke `on_permission_missing` with the permission's kind and a message naming the System Settings pane to fix it

_Tier: unit-mocked — `test_engine.py::TestPermissionMissingSurfaced::test_explicit_denials_fire_with_kind_and_guidance`._

#### Scenario: Granted or undetermined permissions stay silent
- **WHEN** every startup probe reports either granted or undetermined (no explicit denial)
- **THEN** the engine SHALL NOT invoke `on_permission_missing` for any of them

_Tier: unit-mocked — `test_engine.py::TestPermissionMissingSurfaced::test_granted_and_undetermined_stay_silent`._

### Requirement: Recorded audio is always cleaned up after a transcription attempt
`run_transcription` SHALL delete the recorded WAV file after the transcription attempt completes, regardless of the outcome — successful transcription, an empty/`None` result, the model not being loaded, or a raised exception — so recorded voice audio never outlives the attempt that produced it. The only exception is when there was no recording file to begin with (nothing to clean up).

#### Scenario: WAV is deleted when transcription returns no text
- **WHEN** `run_transcription` completes and the transcription result is `None` or an empty string
- **THEN** the recorded WAV SHALL be deleted

_Tier: unit-mocked — `test_engine.py::TestRunTranscriptionCleanup`._

#### Scenario: WAV is deleted when the model is not loaded
- **WHEN** `run_transcription` runs while `state.model` is `None`
- **THEN** the recorded WAV SHALL be deleted even though no transcription was attempted

_Tier: unit-mocked — `test_engine.py::TestRunTranscriptionCleanup::test_deletes_wav_when_model_not_loaded`._

#### Scenario: WAV is deleted when transcription raises
- **WHEN** the underlying transcription call raises an exception
- **THEN** the recorded WAV SHALL still be deleted, and the exception SHALL propagate to the caller

_Tier: unit-mocked — `test_engine.py::TestRunTranscriptionCleanup::test_deletes_wav_when_transcribe_raises`._

### Requirement: Dictating while the model is still loading is surfaced
When the trigger key is released to end a dictation attempt and the transcription model has not finished loading, the menu bar SHALL raise a "model still loading" notification rather than silently producing no transcription output.

#### Scenario: Trigger release while the model is loading
- **WHEN** the trigger key is released and `state.model is None` while `state.model_loading` is true
- **THEN** the menu bar SHALL queue a "Model still loading" alert notification

_Tier: unit-pure — `test_menu_bar.py::TestFnReleasedModelLoadingAlert::test_queues_alert_while_model_still_loading`._

#### Scenario: No alert once the model is ready
- **WHEN** the trigger key is released and the model has finished loading
- **THEN** no "model still loading" alert SHALL be queued

_Tier: unit-pure — `test_menu_bar.py::TestFnReleasedModelLoadingAlert::test_no_alert_once_model_is_loaded`._

### Requirement: Daemon log file rotates instead of growing unbounded
`whispy_daemon.py` SHALL configure `~/.whispy.log` with size-based rotation (1 MB per file, 3 backups retained) rather than a single unbounded log file.

#### Scenario: Log file reaches the size limit
- **WHEN** `~/.whispy.log` reaches the configured 1 MB size limit
- **THEN** it SHALL be rotated to a backup and a fresh log file SHALL be started, up to 3 retained backups

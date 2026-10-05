## MODIFIED Requirements

### Requirement: Configuration Loading
The engine SHALL load and maintain the application configuration. Clipboard copy SHALL be enabled by default (`True`), because the alternative delivery path resolves each character against the active keyboard layout and silently corrupts accented characters and punctuation on any non-US layout (see the text-injection capability).

Because every saved config already carries a value for every known key — `save_config` writes the whole key set, so a changed default reaches no existing install — the engine SHALL additionally perform a one-time, version-gated migration that sets `copy_to_clipboard` to `True` and lowers a `max_chunk_s` still equal to the previous default of 12 s down to the new default. The migration SHALL run once per install, tracked by the config version, and SHALL NOT re-apply on later loads: after it has run, an explicit `copy_to_clipboard: false` SHALL be preserved. The migration SHALL be unconditional for `copy_to_clipboard` even though it cannot distinguish a user's deliberate `false` from the old default, because the two are indistinguishable on disk and the mode it leaves behind corrupts text on any non-US layout; the setting stays reachable and a user who wants it back SHALL be able to set it again.

Because a migration is the one moment the engine rewrites a file it did not
write, it SHALL copy the existing `config.json` to `config.json.v<previous>.bak`
before persisting the migrated result, and SHALL log which keys the migration
changed. The backup SHALL be named for the version it came from, so repeated
loads cannot clobber it and a user whose settings change unexpectedly has the
previous file to compare against. A failure to write the backup SHALL be logged
but SHALL NOT prevent the migration from completing — refusing to start because
a backup could not be written would be worse than the loss it guards against.

The engine SHALL validate configuration keys against `DEFAULT_CONFIG` before persisting to disk; keys absent from `DEFAULT_CONFIG` — including `model_size`, `language`, `beam_size`, `best_of`, and `auto_detect_min_duration` left behind by an earlier version — SHALL be dropped without raising, so an existing config file keeps loading after the upgrade. When a configuration update changes the `trigger` key, the engine SHALL restart the key listener so the new trigger takes effect without a manual Restart. The engine SHALL apply text cleaning to transcription output before text injection. `save_config` SHALL create the `~/.config/whispy` directory with `0700` permissions and SHALL persist `config.json` with `0600` permissions on every save, including the first save after upgrading from a version that wrote the file without restricting permissions; a failure to set these permissions SHALL be logged but SHALL NOT prevent the config from being saved.

#### Scenario: Legacy keys are dropped, not fatal
- **WHEN** a config file written by a pre-Parakeet version is loaded, carrying `model_size` and `language`
- **THEN** loading SHALL succeed, those keys SHALL NOT appear in the validated config, and the next save SHALL persist the file without them

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Copy to clipboard is enabled by default
- **WHEN** the application starts with no saved config
- **THEN** the engine SHALL use `True` for `copy_to_clipboard`

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Default copy to clipboard is disabled
- **WHEN** a saved config that has already been migrated explicitly carries `copy_to_clipboard: false`
- **THEN** that value SHALL be preserved and the engine SHALL use the keystroke path

_Tier: unit-pure — `test_config_validation.py`. This scenario keeps its original name from when `False` was the default; it now covers the explicit opt-out that survives migration._

#### Scenario: An existing install is migrated to clipboard delivery
- **WHEN** a config saved by a previous version is loaded, carrying `copy_to_clipboard: false` and `max_chunk_s: 12.0`
- **THEN** the migration SHALL set `copy_to_clipboard` to `true`, SHALL set `max_chunk_s` to the new default, SHALL persist both, and SHALL record the new config version

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Migration does not re-apply
- **WHEN** a config already at the new version is loaded with `copy_to_clipboard: false`
- **THEN** the value SHALL be left untouched

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: A deliberately tuned chunk ceiling survives migration
- **WHEN** a config saved by a previous version carries a `max_chunk_s` different from the previous default of 12 s
- **THEN** the migration SHALL leave that value unchanged

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: A migration backs up the file it replaces
- **WHEN** a config at a previous version is loaded and migrated
- **THEN** the pre-migration file SHALL be copied to `config.json.v<previous>.bak` beside it, and the keys the migration changed SHALL be logged

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: A config that needs no migration is not rewritten
- **WHEN** a config already at the current version and carrying every known key is loaded
- **THEN** the loader SHALL NOT write the config file and SHALL NOT write a backup, so the backup taken by the migration keeps the pre-migration contents across every later launch

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: A failed backup does not block the migration
- **WHEN** the backup copy cannot be written
- **THEN** the failure SHALL be logged and the migration SHALL still persist the migrated config

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Trigger change restarts the listener
- **WHEN** a configuration update changes the `trigger` key
- **THEN** the engine SHALL restart the key listener without requiring a manual Restart

_Tier: unit-mocked — `test_engine.py`._

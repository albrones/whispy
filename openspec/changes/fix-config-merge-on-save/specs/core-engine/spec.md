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

A configuration update SHALL be persisted as a **merge onto the current
on-disk configuration**, not as a rewrite from the engine's in-memory copy.
A key the update does not name SHALL be preserved with the value the file
holds at the time of the update.

The file is authoritative for untouched keys because the engine reads it only
once, at startup. Persisting the whole in-memory snapshot therefore replays a
boot-time state over every later edit, silently discarding any change made to
the file while the application was running. Most configuration keys have no
user interface, so editing the file is the only way to set them — and it is
precisely the path a snapshot rewrite destroys.

The values a merge takes from the file SHALL be validated on the same terms as
any other load, so a malformed hand-edit degrades to its default rather than
entering the configuration unchecked.

When the file cannot be read or parsed at all, the merge SHALL fall back to the
configuration the engine is currently running with, not to the defaults, and
the update SHALL still be applied and persisted. Falling back to the defaults
would have the next unrelated change — a menu toggle the user does not connect
to the file — persist them over every setting the user holds, turning an
unreadable file into a silent reset of the whole configuration.

The engine SHALL update its in-memory configuration **in place** rather than
replacing the object, because that object is shared by reference with the
audio, injection, and UI layers; replacing it would leave those layers reading
a detached copy.

Side effects of a configuration update — restarting the key listener,
re-wiring streaming, reconfiguring the text injector — SHALL be applied for
every key whose effective value changed as a result of the update, not only
for the keys the caller named. A merged-in value that reaches the
configuration but not the running component would leave the engine disagreeing
with its own persisted settings.

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

#### Scenario: An update preserves a key edited on disk since startup

- **WHEN** the config file is changed on disk after startup for a key the engine has not been asked to update, and a configuration update is then applied for a different key
- **THEN** the persisted config SHALL contain the updated key's new value **and** the on-disk value of the edited key, and SHALL NOT restore the edited key's startup value

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: An update still overrides the file for the keys it names

- **WHEN** a configuration update names a key that was also changed on disk since startup
- **THEN** the update's value SHALL win for that key

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: A malformed on-disk value is not merged in unchecked

- **WHEN** the config file holds an invalid value for a key the update does not name, and a configuration update is applied
- **THEN** that key SHALL be persisted with its default value rather than the invalid one, and the update SHALL NOT raise

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: An unreadable file does not reset the running configuration

- **WHEN** the config file becomes unparseable while the application is running, and a configuration update is then applied for a single key
- **THEN** the update SHALL NOT raise, the named key SHALL be persisted with its new value, and every other key SHALL be persisted with the value the engine is running with rather than its default

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: The shared config object is mutated, not replaced

- **WHEN** a configuration update is applied
- **THEN** the engine's configuration object SHALL be the same object as before the update, carrying the merged values

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: A merged-in streaming value reaches the audio engine

- **WHEN** a streaming parameter is changed on disk after startup and a configuration update is applied that names only a non-streaming key
- **THEN** the engine SHALL re-wire streaming so the running audio engine uses the merged value

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: An update that changes nothing performs no side effects

- **WHEN** a configuration update is applied whose values all match the current effective configuration
- **THEN** the engine SHALL NOT restart the key listener and SHALL NOT re-wire streaming

_Tier: unit-mocked — `test_engine.py`._

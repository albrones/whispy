# correction-store Specification

## Purpose
TBD - created by archiving change adaptive-transcription-memory. Update Purpose after archive.
## Requirements
### Requirement: Persistent correction storage
The system SHALL persist correction mappings in `~/.config/whispy/corrections.json`. The store SHALL be loaded on startup and saved atomically (write to temp file, then `os.replace`) after each new correction is recorded. The `~/.config/whispy` directory SHALL be created (or, if it already exists, tightened) with `0700` permissions on every save, and `corrections.json` SHALL end up with `0600` permissions after every save, including the first save after upgrading from a version that wrote the file without restricting permissions. A failure during the atomic save SHALL propagate the underlying I/O error without being masked by cleanup logic, and SHALL NOT intercept `KeyboardInterrupt` or `SystemExit`.

#### Scenario: Correction stored after detection
- **WHEN** a correction "wispy" → "Whispy" is detected
- **THEN** the store creates or updates an entry with the lowercase key "wispy", replacement "Whispy", increments `corrections_count`, and saves to disk

#### Scenario: Occurrence tracking
- **WHEN** the word "wispy" appears in a transcription output (regardless of whether the user corrects it)
- **THEN** the store increments the `occurrences` count for that entry (if it exists)

#### Scenario: Store loaded on startup
- **WHEN** the application starts and `corrections.json` exists
- **THEN** the store is loaded into memory and available for hotwords and post-processing

#### Scenario: Missing store file
- **WHEN** the application starts and `corrections.json` does not exist
- **THEN** the system operates with an empty correction store and creates the file on first correction

#### Scenario: Corrupt store file
- **WHEN** `corrections.json` exists but contains invalid JSON
- **THEN** the system logs a warning, starts with an empty store, and overwrites the corrupt file on next save

#### Scenario: Corrections file is owner-only readable
- **WHEN** a correction is saved (new correction, occurrence bump, or removal)
- **THEN** `corrections.json` on disk SHALL have `0600` permissions

#### Scenario: Pre-existing world-readable file is tightened on next save
- **WHEN** `corrections.json` already exists with `0644` permissions from a prior version and a new correction triggers a save
- **THEN** the resulting file SHALL have `0600` permissions (no separate migration step required)

#### Scenario: Config directory is owner-only
- **WHEN** any save occurs and `~/.config/whispy` does not yet have `0700` permissions
- **THEN** the directory SHALL be set to `0700` as part of the save

#### Scenario: Save error path does not mask the original exception
- **WHEN** the atomic save's `os.replace` step raises an `OSError`
- **THEN** the temp file SHALL be unlinked and the original `OSError` SHALL propagate unchanged, without a secondary error from cleanup logic obscuring it

#### Scenario: Control-flow exceptions propagate immediately
- **WHEN** a `KeyboardInterrupt` or `SystemExit` is raised while `_save` is writing
- **THEN** the store SHALL NOT catch it as a save failure and SHALL let it propagate immediately

### Requirement: Correction removal via menu bar
The system SHALL allow users to remove individual correction entries from the menu bar UI. Removal SHALL delete the entry from the store and save immediately.

#### Scenario: User removes a correction
- **WHEN** the user clicks a correction entry in the "Learned Words" submenu
- **THEN** the entry is removed from the store and the file is saved

#### Scenario: Empty store after last removal
- **WHEN** the user removes the last correction entry
- **THEN** the store file contains an empty corrections object

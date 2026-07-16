# correction-store Specification

## Purpose
TBD - created by archiving change adaptive-transcription-memory. Update Purpose after archive.
## Requirements
### Requirement: Persistent correction storage
The system SHALL persist correction mappings in `~/.config/whispy/corrections.json`. The store SHALL be loaded on startup and saved atomically (write to temp file, then `os.replace`) after each new correction is recorded.

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

### Requirement: Correction removal via menu bar
The system SHALL allow users to remove individual correction entries from the menu bar UI. Removal SHALL delete the entry from the store and save immediately.

#### Scenario: User removes a correction
- **WHEN** the user clicks a correction entry in the "Learned Words" submenu
- **THEN** the entry is removed from the store and the file is saved

#### Scenario: Empty store after last removal
- **WHEN** the user removes the last correction entry
- **THEN** the store file contains an empty corrections object


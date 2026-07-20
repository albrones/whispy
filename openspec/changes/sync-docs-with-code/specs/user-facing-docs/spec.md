## ADDED Requirements

### Requirement: Documented defaults match code
User-facing documentation SHALL state configuration default values that match
`DEFAULT_CONFIG` in `src/whispy/core/config.py`.

#### Scenario: Language default documented correctly
- **WHEN** README.md documents the `language` configuration key
- **THEN** it states the default as `en`, matching `DEFAULT_CONFIG["language"]`

#### Scenario: Default-value guard test passes
- **WHEN** `tests/test_docs.py` checks the README-documented `language` default against
  `DEFAULT_CONFIG["language"]`
- **THEN** the two values are equal and the test passes

### Requirement: Complete config key reference
README.md's Configuration section SHALL document every key present in `DEFAULT_CONFIG`.

#### Scenario: Every DEFAULT_CONFIG key has a doc row
- **WHEN** a reader compares the keys in `DEFAULT_CONFIG` to the rows in README.md's
  Configuration table
- **THEN** every key (`model_size`, `language`, `beam_size`, `best_of`,
  `copy_to_clipboard`, `start_at_login`, `auto_detect_min_duration`,
  `min_recording_duration`, `custom_vocabulary`, `trigger`, `streaming_enabled`,
  `pause_ms`, `min_chunk_s`, `max_chunk_s`, `vad_aggressiveness`) has a corresponding
  row with a human-readable description

#### Scenario: Config completeness guard test passes
- **WHEN** `tests/test_docs.py` parses the README Configuration table and diffs its keys
  against `DEFAULT_CONFIG.keys()`
- **THEN** no `DEFAULT_CONFIG` key is missing from the table and the test passes

### Requirement: API examples are authenticated and correctly attributed
Documentation that shows HTTP API usage SHALL include the bearer-token authentication
the server requires, and SHALL correctly attribute where server constants are defined.

#### Scenario: AGENTS.md curl examples include the auth header
- **WHEN** AGENTS.md shows a `curl` example against the local API
  (`/status`, `/start`, `/stop`)
- **THEN** each example includes an `-H "Authorization: Bearer <token>"` header (or
  equivalent placeholder), matching the `401` the server returns without it
  (`src/whispy/api/server.py`)

#### Scenario: install.sh smoke-test curl includes the auth header
- **WHEN** `install.sh` prints the post-install smoke-test `curl` command
- **THEN** the printed command includes the bearer-token header (or explicitly notes
  where to find the token), rather than an example that returns `401` if copy-pasted

#### Scenario: PORT attribution is correct
- **WHEN** README.md states where the HTTP `PORT` constant is defined
- **THEN** it names `src/whispy/api/server.py`, not `whispy_daemon.py`

### Requirement: Platform description reflects cross-platform support
AGENTS.md SHALL describe Whispy as supporting both macOS and Linux/X11, not macOS-only,
in its platform statement, tech-stack list, and architecture section.

#### Scenario: Platform line states both operating systems
- **WHEN** AGENTS.md's "Core Tech Stack & Environment" section states the supported
  platform(s)
- **THEN** it states macOS and Linux/X11, not "macOS ... only"

#### Scenario: Tech stack list includes the Linux-path dependencies
- **WHEN** AGENTS.md's "Key Dependencies" list is read
- **THEN** it includes `pynput`, `pystray`, and `Pillow` alongside the macOS-only
  dependencies (`rumps`, `pyobjc-framework-Quartz`)

#### Scenario: Architecture section covers both platforms
- **WHEN** AGENTS.md's "Architecture & Workflow" section describes the daemon, listener,
  and text-injection mechanisms
- **THEN** it describes the Linux/X11 equivalents (systemd --user service, `pynput`
  listener) alongside the macOS mechanisms, rather than presenting macOS as the only
  supported path

### Requirement: Test suite documentation matches the tests/ directory
README.md's test-file table SHALL only reference files that exist in `tests/`, and
SHALL describe each file's actual coverage.

#### Scenario: No reference to a nonexistent test file
- **WHEN** README.md's test-file table is compared against the contents of `tests/`
- **THEN** every listed file (e.g. `tests/test_stress.py`) exists on disk

#### Scenario: test_error_handling.py description matches its content
- **WHEN** README.md describes `tests/test_error_handling.py`
- **THEN** the description does not claim `sox` coverage, matching the file's actual
  scope (capture-backend and microphone-unavailability failures)

#### Scenario: Test inventory guard test passes
- **WHEN** `tests/test_docs.py` checks every file path referenced in README.md's test
  table against `Path("tests").glob(...)`
- **THEN** every referenced path resolves to an existing file and the test passes

### Requirement: Feature documentation parity
FEATURE_MATRIX.md and README.md SHALL each have an entry for every capability that is
promoted on `website/index.html` and has a corresponding OpenSpec capability spec.

#### Scenario: Adaptive vocabulary has a FEATURE_MATRIX row
- **WHEN** a reader consults `FEATURE_MATRIX.md` for the adaptive vocabulary /
  correction-learning feature (backed by `src/whispy/core/corrections.py` and specced by
  the `adaptive-vocabulary`, `correction-detection`, and `correction-store` OpenSpec
  capabilities)
- **THEN** a row exists naming the feature, its tier, and a "Verified by" target that
  points at existing coverage (`tests/test_corrections.py`)

#### Scenario: README mentions the adaptive vocabulary feature
- **WHEN** a reader consults README.md's feature list
- **THEN** the "learns your words" / adaptive-correction behavior is described,
  consistent with `website/index.html`

### Requirement: CHANGELOG is English-only with a single open section
CHANGELOG.md SHALL be written entirely in English and SHALL contain exactly one open
("unreleased") section.

#### Scenario: No French section headers
- **WHEN** CHANGELOG.md's section headers and prose are read
- **THEN** none are in French (no `Non publié`, `Ajoutés`, `Changés`, `Corrigés`, or
  similar French headings)

#### Scenario: Exactly one unreleased section
- **WHEN** CHANGELOG.md is scanned for open-release section headers
- **THEN** exactly one `## [Unreleased]` section exists, and no stale top-level release
  date precedes it

#### Scenario: CHANGELOG guard test passes
- **WHEN** `tests/test_docs.py` scans CHANGELOG.md for French-language markers and counts
  `## [Unreleased]` occurrences
- **THEN** zero French markers are found, exactly one `## [Unreleased]` section exists,
  and the test passes

### Requirement: Build and install tooling comments match actual behavior
Comments and help text in `Makefile` and `install.sh` SHALL match the behavior
implemented in the scripts they describe.

#### Scenario: Makefile app target help matches signing behavior
- **WHEN** a contributor runs `make help` (or reads the `app` target's inline help
  comment in `Makefile`)
- **THEN** the help text reflects that the build prefers the self-signed "Whispy Local
  Signing" identity and falls back to ad-hoc signing only if that identity is absent,
  matching `packaging/macos/build_app.sh`

#### Scenario: install.sh comments do not claim a macOS LaunchAgent
- **WHEN** a contributor reads the comments in `install.sh` referencing how the daemon
  autostarts or runs detached on macOS
- **THEN** no comment claims a LaunchAgent is created on macOS, consistent with the
  SMAppService-based design already documented later in the same file

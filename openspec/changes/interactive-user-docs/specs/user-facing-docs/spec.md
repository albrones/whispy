## MODIFIED Requirements

### Requirement: Documented defaults match code
User-facing documentation SHALL state configuration default values that match the configuration schema in `src/whispy/core/config.py` (from which `DEFAULT_CONFIG` is derived). The generated documentation SHALL take every default from the schema rather than restate it by hand, and README.md SHALL NOT restate configuration defaults.

#### Scenario: Default-value guard test passes
- **WHEN** `tests/test_docs.py` checks each default shown in the generated configuration reference against the corresponding `DEFAULT_CONFIG` entry
- **THEN** the two values are equal and the test passes

#### Scenario: README carries no config defaults
- **WHEN** README.md is read
- **THEN** it contains no configuration table and links to the docs' configuration page instead

### Requirement: Complete config key reference
The generated documentation's configuration reference SHALL document every key present in `DEFAULT_CONFIG`, and SHALL NOT document keys that no longer exist.

#### Scenario: Every DEFAULT_CONFIG key has a doc row
- **WHEN** a reader compares the keys in `DEFAULT_CONFIG` to the rows in the docs' configuration reference
- **THEN** every key has a corresponding row with a human-readable description

#### Scenario: Removed keys are absent from the table
- **WHEN** the configuration reference is read
- **THEN** it SHALL contain no row for `model_size`, `language`, `beam_size`, `best_of`, or `auto_detect_min_duration`

#### Scenario: Config completeness guard test passes
- **WHEN** `tests/test_docs.py` parses the generated configuration reference and diffs its keys against `DEFAULT_CONFIG.keys()`
- **THEN** the two sets match exactly and the test passes

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
- **WHEN** the generated documentation's usage page states where the HTTP `PORT` constant is defined
- **THEN** it names `src/whispy/api/server.py`, not `whispy_daemon.py`

### Requirement: Test suite documentation matches the tests/ directory
CONTRIBUTING.md's test-file table SHALL only reference files that exist in `tests/`, and
SHALL describe each file's actual coverage. README.md SHALL NOT carry a test-file table.

#### Scenario: No reference to a nonexistent test file
- **WHEN** CONTRIBUTING.md's test-file table is compared against the contents of `tests/`
- **THEN** every listed file exists on disk, and `tests/test_stress.py` is not listed

#### Scenario: test_error_handling.py description matches its content
- **WHEN** CONTRIBUTING.md describes `tests/test_error_handling.py`
- **THEN** the description does not claim `sox` coverage, matching the file's actual
  scope (capture-backend and microphone-unavailability failures)

#### Scenario: Test inventory guard test passes
- **WHEN** `tests/test_docs.py` checks every file path referenced in CONTRIBUTING.md's test
  table against `Path("tests").glob(...)`
- **THEN** every referenced path resolves to an existing file and the test passes

## ADDED Requirements

### Requirement: README is a short entry point to the docs
README.md SHALL contain a short pitch, the one-line installer, a prominent link to the documentation site, the supported platforms, the model's download size and supported languages, and the licence. Detailed install, permissions, troubleshooting, configuration and FAQ content SHALL live in the documentation site, not in README.md.

#### Scenario: Install line is near the top
- **WHEN** README.md is rendered on GitHub
- **THEN** the one-line installer appears before any section other than the pitch

#### Scenario: Docs are linked
- **WHEN** README.md is read
- **THEN** it links to the documentation site's install, troubleshooting and configuration pages

#### Scenario: README stays short
- **WHEN** `tests/test_docs.py` counts README.md's lines
- **THEN** there are at most 120

# release-validation Specification

## Purpose
One easy-to-trigger, easy-to-maintain system that verifies Whispy's real
behavior — not just its wiring — on both macOS and Linux/X11. It provides a
single `make validate` entrypoint (source of truth) plus a `/validate` Claude
Code skill that wraps and triages it, runs three honest layers (preflight,
live-drive over the real HTTP API, operator), enforces a loud three-state
reporting contract where unexercisable seams report UNVERIFIED rather than
silent PASS, anchors coverage in a `FEATURE_MATRIX.md`, and binds a maintenance
discipline so coverage provably grows with every fix and feature.

## Requirements
### Requirement: Single validation entrypoint
The system SHALL provide one easy-to-trigger entrypoint, `make validate`, that runs the full release-validation flow for the current operating system (macOS or Linux/X11) and prints a single structured summary. A `/validate` Claude Code skill SHALL wrap `make validate`, invoke it, and interpret its output (which layer failed, which feature, likely cause). The skill SHALL NOT reimplement the checks — `make validate` is the source of truth and SHALL run with no dependency on Claude Code.

#### Scenario: make validate runs all applicable layers for the host OS
- **WHEN** a developer runs `make validate` on macOS or Linux/X11
- **THEN** the system SHALL run preflight, live-drive, and operator layers applicable to that OS and print one summary with per-feature outcomes

#### Scenario: the skill wraps the make target
- **WHEN** the `/validate` skill is invoked
- **THEN** it SHALL call `make validate`, and SHALL report the parsed results (layer, feature, cause) without performing the verification itself

_Tier: unit-mocked — orchestrator selection/parsing verified with mocked layer outputs; the layers themselves carry their own tiers._

### Requirement: Three-state reporting contract
Every validation check SHALL resolve to exactly one of three outcomes: PASS, FAIL, or UNVERIFIED. UNVERIFIED SHALL mean the seam could not be exercised (no input device, permission not granted, required binary absent, daemon would not boot) and SHALL NOT be reported as PASS. The run summary SHALL print counts per outcome and SHALL signal a non-zero, distinct result when any check is UNVERIFIED, so that a green result can never mean "nothing ran."

#### Scenario: an unexercisable seam reports UNVERIFIED, not PASS
- **WHEN** a check cannot run because its device, permission, or binary is absent
- **THEN** the check SHALL be reported as UNVERIFIED and the summary SHALL include it in a distinct UNVERIFIED count separate from PASS

#### Scenario: all-unverified run is distinguishable from all-pass
- **WHEN** every check resolves to UNVERIFIED
- **THEN** the summary and exit signal SHALL differ from a run where every check PASSed

_Tier: unit-pure — outcome classification and summary/exit logic are pure functions over per-check results._

### Requirement: Preflight layer
The validation flow SHALL run an environment preflight (reusing `doctor`) before behavioral layers, reporting permissions, model cache, microphone availability, `xdotool` presence on Linux, and daemon state, and explaining for each seam whether it is expected to be exercisable. A FAIL in a hard prerequisite SHALL stop the flow with an actionable message.

#### Scenario: preflight explains why a seam will be unverified
- **WHEN** preflight detects a missing permission or device
- **THEN** it SHALL report which downstream checks will be UNVERIFIED and how to remediate

_Tier: unit-mocked — preflight aggregation verified with injected check results (mirrors existing `doctor` tests)._

### Requirement: Live-drive layer drives the real daemon
The validation flow SHALL include a live-drive layer that boots the real daemon and drives it over its HTTP API without mocks, asserting real behavior. It SHALL NOT import the test suite's global Quartz/rumps/audio mocks.

#### Scenario: a real record/transcribe cycle is driven over HTTP
- **WHEN** the live-drive layer boots the real daemon, waits for readiness via `GET /status`, drives `POST /start` then `POST /stop` (or `/stop-async`), and reads `GET /last-transcription`
- **THEN** it SHALL assert the status transitions are valid and the last transcription is non-empty and well-formed, or report UNVERIFIED when mic/model are unavailable

_Tier: live-driven — real daemon driven over HTTP against real mic + model; unattended; skips surface as UNVERIFIED._

### Requirement: Deterministic transcription content via known fixtures
The live-drive layer SHALL verify transcription *content* deterministically, without a microphone or a human, by transcribing committed speech fixtures through the real model with the current config. The daemon SHALL expose a `POST /transcribe-file` control endpoint that transcribes a given WAV with the current config and returns the cleaned text WITHOUT injecting keystrokes or deleting the source; it SHALL return the empty string for audio that produced no speech (e.g. silence) and an error status only when the model is not loaded or the file is missing. The harness SHALL assert: silence yields no speech tokens; a known French fixture decoded with `language=fr` contains its expected tokens; a known English fixture decoded with `language=en` contains its expected tokens; and a config change applied over `POST /config` is reflected by `GET /config`. Driving config SHALL NOT mutate the user's real config file. Fixtures SHALL be regenerable from a committed script. UNVERIFIED is reported when the model cannot load (e.g. not cached / offline).

#### Scenario: known speech decodes to the expected text in the selected language
- **WHEN** the harness sets `language=fr` and transcribes the French fixture, then sets `language=en` and transcribes the English fixture, via `POST /transcribe-file`
- **THEN** each transcription SHALL contain its expected tokens, proving transcription content and language selection

#### Scenario: silence yields an empty transcription
- **WHEN** the harness transcribes the silence fixture via `POST /transcribe-file`
- **THEN** the result SHALL contain no speech tokens (a 200 empty string), not an error

#### Scenario: driving config does not mutate the user's config file
- **WHEN** the harness changes language/model over `POST /config` during a run
- **THEN** the daemon SHALL operate on a throwaway config (via `WHISPY_CONFIG`) and the user's real config file SHALL be unchanged

_Tier: live-driven — real model on committed fixtures over HTTP; unattended and deterministic._

### Requirement: Operator layer for the human-only residue
The validation flow SHALL include an operator layer that guides a human through the checks that cannot be automated — the physical trigger keypress and visual confirmation that injected text appears in the focused application. The harness SHALL pre-arm what it can (boot the daemon, clear `/last-transcription`) and SHALL auto-detect the result by polling the API where possible, so the human's only actions are the physical act and a confirmation. Results SHALL be recorded to a timestamped run report.

#### Scenario: operator confirms text injection into a focused field
- **WHEN** the operator layer instructs the human to focus a field, hold the trigger, speak, and release
- **THEN** the harness SHALL poll `GET /last-transcription`, present the detected result for a PASS/FAIL confirmation, and record the outcome to the run report

_Tier: manual-ui — requires a human keypress and visual confirmation; harness-assisted but not unattended._

### Requirement: Feature matrix as the single source of truth
The repository SHALL contain a `FEATURE_MATRIX.md` mapping every user-facing feature to its platform(s), its coverage tier, what verifies it, and notes. It SHALL cover macOS and Linux/X11 in parity and SHALL be the index from which the operator checklist and live-drive plan are derived.

#### Scenario: every user-facing feature has a matrix row
- **WHEN** the feature matrix is reviewed
- **THEN** each user-facing feature SHALL have a row naming its platform(s), tier, and how it is verified

_Tier: unit-pure — the matrix can be parsed and checked for required columns and for rows whose "verified by" target is missing._

### Requirement: Validation evolves with every fix and feature
The capability SHALL define a maintenance discipline rule: any bug fix or feature change MUST (a) update or add the corresponding `FEATURE_MATRIX.md` row and (b) add a regression case at the lowest tier that can catch the issue — a pure-logic defect at `unit-pure`, a real-seam defect at `live-driven`, a human-only defect as a `manual-ui` operator checklist line. The rule SHALL be stated in the matrix header and surfaced by the `/validate` skill.

#### Scenario: a fix adds coverage at the lowest catching tier
- **WHEN** a defect is fixed
- **THEN** the change SHALL add a regression case at the lowest tier capable of catching it and update the matrix row accordingly

#### Scenario: a feature ships with matrix coverage
- **WHEN** a new user-facing feature is added
- **THEN** a matrix row and at least one verifying check at the appropriate tier SHALL be added in the same change

_Tier: unit-pure — the matrix linter can flag rows whose "verified by" points at a nonexistent test/checklist entry._

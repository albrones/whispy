# correction-detection Specification

## Purpose
TBD - created by archiving change adaptive-transcription-memory. Update Purpose after archive.
## Requirements
### Requirement: Snapshot focused field after injection
The system SHALL capture a snapshot of the focused text field via the macOS Accessibility API immediately after injecting transcribed text. The snapshot SHALL include the field's full text value, the injected text, and the injection offset. If the focused element does not expose an `AXValue` attribute, the snapshot SHALL be silently skipped.

#### Scenario: Snapshot captured after successful injection
- **WHEN** transcribed text is injected into a text field that exposes AXValue
- **THEN** the system stores a snapshot containing the field value, injected text, injection offset, and a reference to the focused element

#### Scenario: Snapshot skipped for inaccessible fields
- **WHEN** transcribed text is injected into a field that does not expose AXValue (e.g., Terminal, game UI)
- **THEN** no snapshot is stored and no error is raised

#### Scenario: Streaming mode snapshots final aggregation only
- **WHEN** transcription runs in streaming mode with multiple chunks
- **THEN** the snapshot SHALL be taken only after the final chunk is injected, covering the full aggregated text

### Requirement: Detect corrections on next Fn press
The system SHALL read the focused text field on the next Fn key press (before recording starts) and compare the injected region against the stored snapshot. Word-level differences within the injected region SHALL be extracted as corrections. When a correction is extracted, the system SHALL record it at `DEBUG` log level (not `INFO` or higher), so the wrong→right word pair — a fragment of the user's dictated text — is not written into the default-verbosity, world-readable `~/.whispy.log`.

#### Scenario: Single word correction detected
- **WHEN** the snapshot contains injected text "wispy is great" and the field now reads "Whispy is great" in the same region
- **THEN** the system extracts a correction mapping "wispy" → "Whispy"

#### Scenario: No correction when text unchanged
- **WHEN** the snapshot contains injected text "hello world" and the field still reads "hello world" in the same region
- **THEN** no correction is extracted

#### Scenario: Detection skipped when field changed
- **WHEN** the user has switched to a different text field or application since the last injection
- **THEN** the system SHALL skip correction detection and proceed directly to recording

#### Scenario: Offset drift fallback
- **WHEN** the stored offset does not match the injected text (user typed before the region)
- **THEN** the system SHALL search for the injected text within a ±50 character window around the stored offset before giving up

#### Scenario: Learned correction is logged at DEBUG, not INFO
- **WHEN** a correction is detected and passed to the correction store
- **THEN** the `"[corrections] learned: %s → %s"` log line SHALL be emitted at `DEBUG` level, so it does not appear in the daemon's log file at the default `INFO` verbosity

_Tier: unit-mocked — log level asserted via `caplog`/mocked logger in `test_engine.py`._

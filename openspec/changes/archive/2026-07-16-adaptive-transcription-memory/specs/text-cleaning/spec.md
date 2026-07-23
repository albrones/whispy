## ADDED Requirements

### Requirement: Apply learned corrections after cleaning
The system SHALL apply corrections from the correction store as a post-processing step after existing text cleaning (credit stripping) and before text injection. Only entries with `corrections_count >= 3` SHALL be applied.

#### Scenario: Correction applied after credit stripping
- **WHEN** transcription output is "Sous-titres réalisés par Whisper wispy is great"
- **THEN** credit stripping removes the prefix, then correction replacement changes "wispy" to "Whispy", yielding "Whispy is great"

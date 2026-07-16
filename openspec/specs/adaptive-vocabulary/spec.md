# adaptive-vocabulary Specification

## Purpose
TBD - created by archiving change adaptive-transcription-memory. Update Purpose after archive.
## Requirements
### Requirement: Hotwords from correction store
The system SHALL pass learned vocabulary to faster-whisper's `hotwords` parameter on every transcription call. All correction entries with `corrections_count >= 1` SHALL be included, sorted by `corrections_count` descending, truncated to fit within the ~224 token budget.

#### Scenario: Learned word biases transcription
- **WHEN** the correction store contains "Whispy" with corrections_count >= 1
- **THEN** "Whispy" is included in the `hotwords` parameter passed to `model.transcribe()`

#### Scenario: Token budget respected
- **WHEN** the correction store contains more entries than fit in ~224 tokens
- **THEN** entries are sorted by corrections_count descending and only the top entries that fit are included

#### Scenario: Hotwords coexist with initial_prompt
- **WHEN** both `custom_vocabulary` (config) and correction store entries exist
- **THEN** `custom_vocabulary` feeds `initial_prompt` and corrections feed `hotwords` — both are passed independently

### Requirement: Post-transcription replacement for high-confidence corrections
The system SHALL apply case-insensitive whole-word replacement for correction entries with `corrections_count >= 3` after transcription and text cleaning, before injection. Replacement SHALL use word boundary matching to avoid replacing substrings within larger words.

#### Scenario: High-confidence correction auto-replaced
- **WHEN** transcription output contains "wispy" and the correction store has "wispy" → "Whispy" with corrections_count >= 3
- **THEN** "wispy" is replaced with "Whispy" before injection

#### Scenario: Low-confidence correction not replaced
- **WHEN** transcription output contains "wispy" and the correction store has "wispy" → "Whispy" with corrections_count = 1
- **THEN** the transcription output is not modified (hotwords bias is applied but no post-processing replacement)

#### Scenario: Word boundary respected
- **WHEN** transcription output contains "wispython" and the correction store has "wispy" → "Whispy"
- **THEN** "wispython" is NOT replaced (word boundary prevents partial match)

#### Scenario: Case-insensitive matching
- **WHEN** transcription output contains "WISPY" and the correction store has "wispy" → "Whispy"
- **THEN** "WISPY" is replaced with "Whispy"


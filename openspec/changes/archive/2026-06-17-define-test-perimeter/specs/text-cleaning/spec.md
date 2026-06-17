## ADDED Requirements

### Requirement: Strip Whisper hallucination phrases
The system SHALL remove known Whisper hallucination phrases from transcribed text wherever they occur (not only as a prefix), because Whisper emits training-corpus artifacts on silence or near-empty audio. After removal the system SHALL collapse leftover whitespace, and SHALL return an empty string when nothing meaningful remains. This is distinct from credit-prefix stripping, which only removes phrases at the start of the text.

#### Scenario: Hallucination phrase removed mid-text
- **WHEN** transcribed text contains a known hallucination phrase (e.g. "la communauté d'Amara.org") anywhere in the string
- **THEN** the phrase SHALL be removed and surrounding whitespace collapsed, leaving the remaining meaningful text

#### Scenario: Hallucination-only output becomes empty
- **WHEN** transcribed text consists solely of one or more known hallucination phrases
- **THEN** the result SHALL be an empty string

#### Scenario: Longest phrase wins over substring
- **WHEN** a hallucination phrase is a superstring of another listed phrase (e.g. "Sous-titres réalisés par la communauté d'Amara.org" vs "la communauté d'Amara.org")
- **THEN** the longest matching phrase SHALL be removed rather than leaving a partial fragment

#### Scenario: Clean text is left intact
- **WHEN** transcribed text contains no known hallucination phrase
- **THEN** the text SHALL be returned with only normal whitespace normalization

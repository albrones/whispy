## MODIFIED Requirements

### Requirement: Custom vocabulary improves recognition
The system SHALL bias recognition toward a configured custom vocabulary: when an unusual term is supplied via `initial_prompt`, the real model SHALL produce that term in the output.

#### Scenario: Biased term recognized when provided
- **WHEN** a clip naming an unusual term is transcribed with that term supplied as `initial_prompt`
- **THEN** the cleaned output SHALL contain the term

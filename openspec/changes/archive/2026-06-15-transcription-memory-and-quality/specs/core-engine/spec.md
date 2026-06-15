## ADDED Requirements

### Requirement: Custom vocabulary biases transcription
The engine SHALL support an optional `custom_vocabulary` configuration value (a list of words or phrases). When the list is non-empty, the engine SHALL pass it to the transcription call as an `initial_prompt` so that recognition is biased toward the user's habitual terms. When the list is empty or absent, transcription SHALL behave exactly as before (no prompt passed).

#### Scenario: Vocabulary present biases the decoder
- **WHEN** `custom_vocabulary` contains one or more terms and a recording is transcribed
- **THEN** the engine SHALL pass an `initial_prompt` built from those terms to the Whisper transcription call

#### Scenario: Empty vocabulary changes nothing
- **WHEN** `custom_vocabulary` is empty or absent
- **THEN** the engine SHALL NOT pass an `initial_prompt` (transcription behaves as before)

#### Scenario: Invalid vocabulary falls back safely
- **WHEN** `custom_vocabulary` is loaded with a non-list value or with non-string entries
- **THEN** config validation SHALL coerce it to a list containing only the valid string entries (an entirely invalid value becomes an empty list) and SHALL NOT raise

# transcription-quality Specification

## Purpose
Real-model semantic verification: synthesized speech in a supported language
transcribes to the expected words through the actual `tiny` Whisper model,
custom vocabulary biases recognition, and non-speech produces no output. All
scenarios are tier `macos-real` (convention in `../TESTING-TIERS.md`) and run
only under the `macos` marker.

## Requirements
### Requirement: Real-model semantic transcription
The system SHALL be verifiable end-to-end through the real Whisper model: synthesized speech in a supported language SHALL transcribe to non-empty text containing at least one expected keyword (case-insensitive). Verification SHALL synthesize audio with the macOS `say` command, pad and convert it to 16 kHz mono WAV, and run the real `tiny` model with an explicit language. Because the `tiny` model on synthetic speech is lossy, the bar is meaningful overlap with intent (≥1 expected keyword), not exact recall of every word.

#### Scenario: French phrase transcribes to expected keywords
- **WHEN** a French phrase is synthesized, converted, and transcribed with `language="fr"`
- **THEN** the cleaned output SHALL be non-empty and contain at least one expected keyword (case-insensitive)

_Tier: macos-real — `@pytest.mark.macos`, requires `say`/`sox` and the `tiny` model._

#### Scenario: English phrase transcribes to expected keywords
- **WHEN** an English phrase is synthesized, converted, and transcribed with `language="en"`
- **THEN** the cleaned output SHALL be non-empty and contain at least one expected keyword (case-insensitive)

_Tier: macos-real — `@pytest.mark.macos`._

### Requirement: Custom vocabulary improves recognition
The system SHALL bias recognition toward a configured custom vocabulary: when an unusual term is supplied via `initial_prompt`, the real model SHALL produce that term in the output.

#### Scenario: Biased term recognized when provided
- **WHEN** a clip naming an unusual term is transcribed with that term supplied as `initial_prompt`
- **THEN** the cleaned output SHALL contain the term

_Tier: macos-real — `@pytest.mark.macos`._

### Requirement: Silence and artifacts produce no output
The system SHALL inject nothing for non-speech input at the real-model level: a sub-`min_recording_duration` clip SHALL yield no transcription, and known credit/hallucination phrases SHALL not survive in the cleaned output of silence.

#### Scenario: Sub-threshold clip yields nothing
- **WHEN** a clip is run through the transcribe path with a duration below `min_recording_duration`
- **THEN** the path SHALL return no text (discarded before the model)

_Tier: macos-real — `@pytest.mark.macos`._

#### Scenario: Silence yields no hallucination
- **WHEN** a silent clip is transcribed and cleaned
- **THEN** the cleaned output SHALL not contain any known credit/hallucination phrase

_Tier: macos-real — `@pytest.mark.macos`._

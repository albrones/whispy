## ADDED Requirements

### Requirement: Real-model semantic transcription
The system SHALL be verifiable end-to-end through the real Whisper model: synthesized speech in a supported language SHALL transcribe to text containing the expected keywords. Verification SHALL synthesize audio with the macOS `say` command, convert it to 16 kHz mono WAV, run the real `tiny` model with an explicit language, and assert keyword presence case-insensitively. These checks are tier `macos-real` and run only under the `macos` marker.

#### Scenario: French phrase transcribes to expected keywords
- **WHEN** a French phrase is synthesized, converted, and transcribed with `language="fr"`
- **THEN** the cleaned output SHALL contain the phrase's expected keywords (case-insensitive)

_Tier: macos-real — `@pytest.mark.macos`, requires `say`/`sox` and the `tiny` model._

#### Scenario: English phrase transcribes to expected keywords
- **WHEN** an English phrase is synthesized, converted, and transcribed with `language="en"`
- **THEN** the cleaned output SHALL contain the phrase's expected keywords (case-insensitive)

_Tier: macos-real — `@pytest.mark.macos`._

### Requirement: Custom vocabulary improves recognition
The system SHALL bias recognition toward a configured custom vocabulary: when an unusual term is supplied via `initial_prompt`, the real model SHALL be more likely to produce that term than without it.

#### Scenario: Biased term recognized when provided
- **WHEN** a clip naming an unusual term is transcribed with that term supplied as `initial_prompt`
- **THEN** the cleaned output SHALL contain the term

_Tier: macos-real — `@pytest.mark.macos`._

### Requirement: Silence and artifacts produce no output
The system SHALL inject nothing for non-speech input at the real-model level: a near-silent or sub-threshold clip SHALL yield no usable transcription, and known credit/hallucination phrases SHALL be stripped from real output.

#### Scenario: Sub-threshold clip yields nothing
- **WHEN** a clip shorter than `min_recording_duration` is run through the transcription path
- **THEN** the path SHALL return no text (discarded before the model)

_Tier: macos-real — `@pytest.mark.macos`._

#### Scenario: Credit/hallucination stripped from real output
- **WHEN** the real model emits a known credit or hallucination phrase
- **THEN** the cleaned output SHALL not contain that phrase

_Tier: macos-real — `@pytest.mark.macos`._

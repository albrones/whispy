## MODIFIED Requirements

### Requirement: A second engine answers when the first hears nothing
When a fallback engine is configured and the primary engine returns empty text for a prepared piece, the fallback engine SHALL transcribe the same prepared piece and its text SHALL be used. An answer that holds no letter and no digit SHALL count as empty. In the default pipeline the fallback engine SHALL NOT be in memory until the primary first returns nothing, and SHALL be freed after 30 seconds without a call; its model file SHALL still be checked when the pipeline is created, so a missing one fails at startup.

#### Scenario: Whisper recovers what Parakeet drops
- **WHEN** the primary engine returns nothing for a gated clip and the fallback returns « à améliorer, je pense »
- **THEN** the transcript SHALL be « à améliorer, je pense » and name the fallback engine

_Tier: unit — `whispy-core` `pipeline`._

#### Scenario: Punctuation alone is no answer
- **WHEN** the primary engine returns « ... » for a gated clip
- **THEN** the fallback SHALL be called, and without a fallback the transcript SHALL be empty

_Tier: unit — `whispy-core` `pipeline`._

#### Scenario: The fallback loads on demand and is freed when idle
- **WHEN** a lazy engine is created, called twice, then left without a call for longer than its idle time, then called again
- **THEN** nothing SHALL be loaded before the first call, the two calls SHALL share one load, the engine SHALL be freed after the idle time, and the next call SHALL load it again

_Tier: unit — `whispy-core` `lazy`._

## ADDED Requirements

### Requirement: Parakeet hears every input framed by silence
The Parakeet engine SHALL put 0.25 s of digital silence before and after every input it transcribes: cut tight to its speech, a clip makes Parakeet drop phrases or answer French in English (measured in V1, fcf7861, and again on the user's labelled clips).

#### Scenario: Criterion 3 holds on the user's labelled clips
- **WHEN** `banc --labelled` replays the user's labelled clips through the default pipeline
- **THEN** at least 70 % of the lost chunk clips SHALL come back with text, no lost noise clip SHALL, and V2's WER SHALL not be above V1's

_Tier: bench — `banc --labelled`._

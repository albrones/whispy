## ADDED Requirements

### Requirement: Chunk boundaries are gated on voiced speech

A pause SHALL close a chunk only when the chunk carries at least `min_speech_s`
of **voiced** audio, measured from the same frame classification the segmenter
already uses to detect silence. A chunk holding less SHALL NOT be emitted at a
pause: the segmenter SHALL keep accumulating, so the speech is carried into the
following chunk rather than reaching the model alone.

The guard SHALL measure voiced duration rather than elapsed buffered duration.
Measurement is why: through the production transcription gates, an isolated
`oui` chunk of 1.11 s total but 0.39 s voiced was recognized as English in 5 of 5
realizations, while the same word with 0.5 s of preceding speech — 1.61 s total,
0.72 s voiced — was correct in 5 of 5. Elapsed duration does not separate the two
outcomes; voiced duration does. An elapsed-time guard is additionally unreachable
in this rule, since the pause condition already implies more elapsed time than
any sensible minimum.

The system SHALL NOT discard audio to satisfy this guard.

#### Scenario: A chunk with too little speech does not close at a pause

- **WHEN** a qualifying pause occurs and the current chunk holds less than `min_speech_s` of voiced audio
- **THEN** the segmenter SHALL NOT signal a boundary, and the buffered speech SHALL remain in the current chunk

_Tier: unit-pure — `test_segmentation.py`._

#### Scenario: A chunk with enough speech closes at a pause

- **WHEN** a qualifying pause occurs and the current chunk holds at least `min_speech_s` of voiced audio
- **THEN** the segmenter SHALL signal a boundary and begin a new empty chunk

_Tier: unit-pure — `test_segmentation.py`._

#### Scenario: Short speech is carried into the next chunk

- **WHEN** a short utterance is followed by a pause and then further speech
- **THEN** both SHALL be emitted as one chunk, so the short utterance reaches the model with surrounding context

_Tier: unit-pure — `test_segmentation.py`._

#### Scenario: The guard cannot become unreachable

- **WHEN** the minimum-size guard is evaluated at a pause boundary
- **THEN** it SHALL be capable of blocking that boundary — a guard that the pause condition already implies (as an elapsed-time guard does) SHALL NOT be relied on

_Tier: unit-pure — `test_segmentation.py` (regression: the previous rule compared total buffered seconds against a value smaller than `pause_ms`, so it could never block)._

### Requirement: The voiced-speech threshold is configurable

The threshold SHALL be exposed as the `min_speech_s` configuration key, validated
as a non-negative number, and SHALL be applied at runtime like the other
streaming parameters — a change SHALL re-wire segmentation without a restart.

It SHALL be configuration rather than a constant because its default is derived
from synthesized speech with a single voice, so a real microphone, speaker or
room may move where voice-activity detection counts a frame as voiced. The
mechanism it guards is established; the value is provisional.

#### Scenario: Invalid value falls back

- **WHEN** `min_speech_s` is absent, negative, or not a number
- **THEN** the system SHALL use the default and report the substitution, as it does for the other streaming parameters

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Change applies without a restart

- **WHEN** `min_speech_s` changes while the engine is running
- **THEN** the engine SHALL re-wire audio segmentation to the new value with no restart

_Tier: unit-mocked — `test_engine.py`._

## MODIFIED Requirements

### Requirement: Silence- and length-bounded chunk emission
While streaming is enabled and recording is active, the system SHALL emit a
transcription chunk when accumulated speech carrying at least `min_speech_s` of
voiced audio is followed by a pause of at least `pause_ms`, OR when the current
chunk's audio reaches `max_chunk_s`, whichever occurs first. The system SHALL NOT
emit a chunk that never contained speech.

The `max_chunk_s` branch SHALL remain independent of the voiced-speech threshold,
so a chunk withheld for want of speech still force-flushes and audio can never be
held indefinitely. The final tail flush SHALL likewise remain independent of it,
so a dictation consisting entirely of one short utterance is still transcribed.

#### Scenario: Pause triggers a chunk
- **WHEN** the input level stays below the silence threshold for at least `pause_ms` after speech was detected, and the chunk holds at least `min_speech_s` of voiced audio
- **THEN** the system SHALL emit the accumulated speech as a chunk and begin a new (empty) chunk

#### Scenario: Run-on speech is force-flushed at max length
- **WHEN** the current chunk reaches `max_chunk_s` of audio without any qualifying pause
- **THEN** the system SHALL emit the chunk anyway so streaming continues to make progress

#### Scenario: A chunk below the speech threshold is force-flushed at max length
- **WHEN** a chunk has not reached `min_speech_s` of voiced audio but its audio reaches `max_chunk_s`
- **THEN** the system SHALL emit it, so withholding a boundary can never strand audio

#### Scenario: Pure silence emits nothing
- **WHEN** a span of audio between two emitted chunks contains no detected speech
- **THEN** the system SHALL NOT emit a chunk for that span

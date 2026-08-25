## MODIFIED Requirements

### Requirement: Per-chunk transcription guards
Each chunk SHALL be transcribed with the same safeguards as the whole-recording path: chunks shorter than the minimum duration (`min_chunk_s` / `min_recording_duration`) SHALL be discarded, and each chunk SHALL be transcribed independently of the others. Independence is now a property of the backend — the transducer carries no cross-call decoder context — rather than a flag the caller must pass, so the system SHALL NOT pass `condition_on_previous_text`, `temperature`, `vad_filter`, or any vocabulary prompt. Custom vocabulary is applied once during text cleaning, not per chunk.

#### Scenario: Sub-minimum chunk discarded
- **WHEN** an emitted chunk's duration is below the minimum duration
- **THEN** the system SHALL discard it without injecting any text

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Chunks carry no decoder context between them
- **WHEN** consecutive chunks are transcribed
- **THEN** no chunk's recognized text SHALL influence another's transcription, and no conditioning argument SHALL be passed to achieve this

_Tier: unit-mocked — `test_engine.py`._

#### Scenario: Vocabulary is not applied per chunk
- **WHEN** a custom vocabulary is configured and chunks are transcribed
- **THEN** the transcription call for each chunk SHALL receive no vocabulary argument; correction SHALL happen once on the assembled text during cleaning

_Tier: unit-mocked — `test_engine.py`._

## ADDED Requirements

### Requirement: Per-chunk latency is proportional to chunk length
Chunk transcription SHALL cost time proportional to the chunk's audio duration rather than paying a fixed per-call floor. The previous backend padded every input to a 30-second window, so a 0.5-second chunk cost the same ~0.5 s as a 2-second one and streaming assembly was bounded by the decoder instead of by the speaker.

#### Scenario: A short chunk is cheaper than a long one
- **WHEN** a 0.5-second chunk and a 2.5-second chunk are transcribed through the real model
- **THEN** the shorter chunk SHALL complete measurably faster, and neither SHALL take longer than its own audio duration

_Tier: macos-real — `@pytest.mark.macos`._

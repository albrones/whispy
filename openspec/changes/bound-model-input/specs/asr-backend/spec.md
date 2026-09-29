## ADDED Requirements

### Requirement: Model input length is bounded
The system SHALL NOT pass more than `MODEL_INPUT_MAX_S` (30 s) of audio to a single model call, whatever path produced the clip. A longer clip SHALL be split into pieces — cut on the segmenter's boundaries, then sliced at fixed offsets where a piece still exceeds the bound — each transcribed through the same gates and trim as any clip, and the piece texts joined in order. Splitting SHALL NOT drop audio. The bound SHALL carry a source comment recording the peak-RSS measurement behind it: one 180 s call peaked at 3503 MB on the pinned CPU provider and at 25 GB under CoreML, which panicked the machine.

#### Scenario: A long recording reaches the model in bounded pieces
- **WHEN** a 100 s recording is transcribed
- **THEN** the model SHALL be called more than once, no call SHALL receive more than `MODEL_INPUT_MAX_S` of audio, and the returned text SHALL be the piece texts joined in order

_Tier: unit-mocked — `test_audio.py` (`TestModelInputCeiling`)._

#### Scenario: Splitting is lossless even before the first word
- **WHEN** PCM with 75 s of silence before any speech is split
- **THEN** every piece SHALL be at most `MODEL_INPUT_MAX_S` long and the pieces concatenated SHALL equal the input

_Tier: unit-pure — `test_segmentation.py` (`TestSplitPcm`)._

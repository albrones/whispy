## ADDED Requirements

### Requirement: Live PCM buffering and segmentation hook
When streaming is enabled, the audio engine SHALL buffer captured int16 frames in
memory for the current chunk and run a silence/length segmentation detector over
the frames inside the capture callback, reusing the per-block RMS level already
computed for the waveform. On a chunk boundary the engine SHALL make the
accumulated audio available for transcription as a self-contained 16 kHz mono WAV
at a unique path, leaving the existing single-file capture path in place for the
non-streaming mode. The segmentation work SHALL run within the existing capture
callback's exception containment so a detector error is logged and never raised
into the PortAudio backend.

#### Scenario: Frames are buffered and segmented during capture
- **WHEN** streaming is enabled and the capture callback receives audio frames
- **THEN** the engine SHALL accumulate the frames for the current chunk and evaluate the silence/length segmentation detector on them

#### Scenario: Chunk boundary produces a transcribable WAV
- **WHEN** the segmentation detector signals a chunk boundary
- **THEN** the engine SHALL write the accumulated audio as a unique 16 kHz mono WAV and make it available to the chunk pipeline

#### Scenario: Detector error is contained
- **WHEN** the segmentation detector raises inside the capture callback
- **THEN** the error SHALL be logged and contained, and SHALL NOT propagate into the audio backend

#### Scenario: Non-streaming capture is unchanged
- **WHEN** streaming is disabled
- **THEN** capture SHALL write a single WAV at the established recording path exactly as before, with no per-chunk emission

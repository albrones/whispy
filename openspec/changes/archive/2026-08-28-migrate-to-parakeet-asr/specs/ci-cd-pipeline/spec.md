## MODIFIED Requirements

### Requirement: macOS real-seam tests execute in CI
The macOS real-seam tier SHALL run against the real transcription model in CI, loading `nemo-parakeet-tdt-0.6b-v3` int8 through `onnx-asr` on `CPUExecutionProvider`. The job SHALL allow enough wall-clock for the first-run model download (639 MB) and SHALL override the default per-test timeout for real model load and inference.

#### Scenario: Real model tier runs with an adequate timeout
- **WHEN** the macOS real-seam job executes
- **THEN** it SHALL run the `macos`-marked tests with a timeout longer than the default, covering model download, load, and inference

#### Scenario: No Whisper model is fetched in CI
- **WHEN** the CI workflows are inspected
- **THEN** no job SHALL download or cache a faster-whisper model

## REMOVED Requirements

### Requirement: Chosen Whisper model takes effect
**Reason**: There is one model. `WHISPER_MODEL` selected among Whisper's five size presets; with a single-size backend the variable selects nothing, so it is removed from `install.sh` and `scripts/bootstrap.sh` rather than kept as dead surface.
**Migration**: None. Installs that previously set `WHISPER_MODEL` simply ignore it; the key is dropped from config on the next save (see `core-engine`).

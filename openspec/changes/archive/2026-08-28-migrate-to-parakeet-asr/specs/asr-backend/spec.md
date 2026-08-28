## ADDED Requirements

### Requirement: Parakeet is the sole transcription backend
The system SHALL transcribe speech using `nvidia/parakeet-tdt-0.6b-v3` loaded through the `onnx-asr` package, and SHALL NOT ship a second transcription backend or a configuration key that selects one. Weights SHALL be the int8-quantized ONNX conversion (`istupakov/parakeet-tdt-0.6b-v3-onnx`), obtained through the HuggingFace hub cache. The loader SHALL accept a local model directory as an alternative source so a vendored copy remains viable if the upstream conversion becomes unavailable.

#### Scenario: Model is loaded with int8 weights
- **WHEN** the engine loads the transcription model
- **THEN** it SHALL request the `nemo-parakeet-tdt-0.6b-v3` model with `quantization="int8"`, and SHALL NOT construct any Whisper model

_Tier: unit-mocked — `test_engine.py` (loader arguments asserted; `onnx_asr` mocked)._

#### Scenario: No backend selection is exposed
- **WHEN** the configuration is loaded
- **THEN** `DEFAULT_CONFIG` SHALL contain no key that selects a transcription engine, model size, or model variant

_Tier: unit-pure — `test_config_validation.py`._

### Requirement: Execution provider is pinned to CPU
The system SHALL construct the ONNX session with `providers=["CPUExecutionProvider"]` rather than inheriting onnxruntime's platform default. The default provider list on macOS enrols CoreML, which on Apple M1 Pro measured roughly twice the per-chunk latency and a 6070 MB peak RSS against 1366 MB for CPU-only. The pin SHALL carry a source comment recording this measurement, so that a future change arguing for a different provider has to beat a number rather than a guess.

#### Scenario: Provider list is explicit
- **WHEN** the transcription model is loaded
- **THEN** the loader SHALL pass an explicit provider list containing only `CPUExecutionProvider`

_Tier: unit-mocked — `test_engine.py`._

### Requirement: Language is detected by the model
The system SHALL NOT pass a language argument to the transcription call, and SHALL rely on the model's per-utterance language detection across its 25 supported languages. The system SHALL NOT expose a user-facing language setting, because forcing a language measurably degraded output: with a forced French decode, English speech was transcribed into French rather than recognized.

#### Scenario: No language argument reaches the model
- **WHEN** a recording or a chunk is transcribed
- **THEN** the transcription call SHALL be made without any language parameter

_Tier: unit-mocked — `test_audio.py`._

#### Scenario: French and English transcribe without configuration
- **WHEN** a French clip and an English clip are transcribed through the real model with no language configured
- **THEN** each SHALL produce non-empty text containing at least one expected keyword in its own language

_Tier: macos-real — `@pytest.mark.macos`._

### Requirement: Model-load failure is surfaced, not swallowed
When the transcription model fails to load — missing weights, download failure, SSL error, or an onnxruntime session error — the engine SHALL retry once and then report the failure through the model-load-failure callback, leaving the model unset rather than silently returning no text on every subsequent dictation.

#### Scenario: Load failure reaches the UI
- **WHEN** model loading raises on both the initial attempt and the retry
- **THEN** the engine SHALL invoke the model-load-failure callback with the error text and SHALL leave the model unset

_Tier: unit-mocked — `test_engine.py`._

### Requirement: Model presence is verifiable
`doctor` SHALL report whether the Parakeet ONNX weights are present in the HuggingFace hub cache, and SHALL report a warning rather than a failure when they are absent, because the first run downloads them automatically.

#### Scenario: Cached model reported as present
- **WHEN** the Parakeet ONNX snapshot exists in the hub cache
- **THEN** `doctor` SHALL report the model check as OK

_Tier: unit-pure — `test_doctor.py` (cache path faked)._

#### Scenario: Missing model reported as a warning
- **WHEN** no Parakeet snapshot is present in the hub cache
- **THEN** `doctor` SHALL report a warning stating the model downloads automatically on first use, not a failure

_Tier: unit-pure — `test_doctor.py`._

# audio-capture Specification

## Purpose
Recording lifecycle and pre-transcription guards in `core/audio.py`: recording
readiness, audio duration detection, short-clip discard, auto-detect-language
warning, temporary-file cleanup, audio-layer Whisper credit stripping, and
transcription failure isolation. Created by change `define-test-perimeter`.

Scenario test tiers follow the convention in `../TESTING-TIERS.md`.

## Requirements
### Requirement: Recording readiness wait
The audio engine SHALL wait for the recording process (`sox`) to begin writing audio before returning from start, so that the audio device's cold-start delay does not produce an empty first recording. The wait SHALL terminate when the output file exceeds a minimum size, when the recording process exits early, or when a readiness timeout elapses — and SHALL never block indefinitely.

#### Scenario: Recording becomes ready
- **WHEN** `sox` starts and the output file grows past the minimum recording size
- **THEN** the start call SHALL return with recording active

_Tier: macos-real — no test yet (deferred to step A; needs a real audio device)._

#### Scenario: Readiness times out
- **WHEN** the output file never reaches the minimum size within the readiness timeout
- **THEN** the start call SHALL return anyway and SHALL log a warning that the first recording may be empty

_Tier: macos-real — no test yet (deferred to step A)._

#### Scenario: Recording process exits early
- **WHEN** the `sox` process exits before writing any audio
- **THEN** the readiness wait SHALL stop and SHALL log a warning rather than block

_Tier: macos-real — no test yet (deferred to step A)._

### Requirement: Audio duration detection
The audio engine SHALL determine the duration of a recorded WAV file using frame count and sample rate. When the file cannot be read as WAV, duration detection SHALL return no value rather than raise.

#### Scenario: Valid WAV duration
- **WHEN** a readable WAV file is measured
- **THEN** the engine SHALL return its duration in seconds computed from frames divided by sample rate

_Tier: unit-pure — `test_language_detection.py::test_detects_duration_of_wav_file`._

#### Scenario: Unreadable file
- **WHEN** the file cannot be opened or parsed as WAV
- **THEN** the engine SHALL return no duration value and SHALL NOT raise

_Tier: unit-pure — `test_language_detection.py::test_returns_none_for_non_wav_file`._

### Requirement: Short-clip discard guard
The audio engine SHALL discard a recording whose duration is below the configured `min_recording_duration` before transcription, because near-silent misclick-length clips cause Whisper to hallucinate training-corpus artifacts. A discarded clip SHALL yield no transcription output.

#### Scenario: Misclick-length recording discarded
- **WHEN** a recording's measured duration is below `min_recording_duration`
- **THEN** the engine SHALL skip transcription and return no text

_Tier: unit-mocked — `test_audio.py::test_short_recording_discarded_without_transcribing`._

#### Scenario: Sufficient-length recording proceeds
- **WHEN** a recording's measured duration is at or above `min_recording_duration`
- **THEN** the engine SHALL proceed to transcription

_Tier: unit-mocked — `test_audio.py::test_long_enough_recording_passes_vad_filter`._

### Requirement: Auto-detect language warning
When language is set to auto-detect and the recording is shorter than `auto_detect_min_duration`, the audio engine SHALL log a warning that language auto-detection may be unreliable, then proceed on a best-effort basis without aborting transcription.

#### Scenario: Audio too short for reliable auto-detect
- **WHEN** language is `auto` and the recording duration is below `auto_detect_min_duration` but at or above `min_recording_duration`
- **THEN** the engine SHALL log a warning and still attempt transcription

_Tier: unit-mocked — `test_language_detection.py::test_transcribe_short_audio_with_auto_does_not_crash`. NOTE: `language="auto"` is currently unreachable through validated config (only `fr`/`en` accepted) — see `define-test-perimeter` design finding M1._

### Requirement: Temporary audio file cleanup
The audio engine SHALL remove the temporary recording file after it is no longer needed, and SHALL tolerate the file already being absent without raising.

#### Scenario: Cleanup removes the file
- **WHEN** cleanup is invoked for an existing temporary recording file
- **THEN** the file SHALL be removed

_Tier: unit-pure — `test_audio.py::test_removes_existing_file`._

#### Scenario: Cleanup on missing file is safe
- **WHEN** cleanup is invoked and the file does not exist
- **THEN** the engine SHALL do nothing and SHALL NOT raise

_Tier: unit-pure — `test_audio.py::test_does_not_error_on_missing_file`._

### Requirement: Credit stripping at the audio layer
The audio engine SHALL strip Whisper credit/watermark prefixes (French and English variants) from the joined transcription text before returning it, and SHALL return no value when the entire output was a credit phrase.

#### Scenario: Credit prefix removed from transcription
- **WHEN** the joined transcription text begins with a known Whisper credit phrase
- **THEN** the engine SHALL remove the prefix and return the remaining text

_Tier: unit-pure — covered via `strip_whisper_credit` tests in `test_audio.py`/`test_text_cleaning.py`._

#### Scenario: Credit-only output yields nothing
- **WHEN** the transcription text consists solely of a credit phrase
- **THEN** the engine SHALL return no text

_Tier: unit-mocked — `test_audio.py::test_empty_result_returns_none`._

### Requirement: Transcription failure isolation
The audio engine SHALL catch errors raised by the underlying transcription model and return no value, so that a transcription failure does not propagate as an exception to callers.

#### Scenario: Model raises during transcription
- **WHEN** the transcription model raises an exception
- **THEN** the engine SHALL log the error and return no text rather than propagate the exception

_Tier: unit-mocked — `test_audio.py::test_exception_returns_none`._

# audio-capture Specification

## Purpose
Recording lifecycle and pre-transcription guards in `core/audio.py`: recording
readiness, audio duration detection, short-clip discard, auto-detect-language
warning, temporary-file cleanup, audio-layer Whisper credit stripping, and
transcription failure isolation. Capture is performed through the cross-platform
`sounddevice` (PortAudio) backend, writing a 16 kHz mono WAV at the established
recording path. Created by change `define-test-perimeter`.

Scenario test tiers follow the convention in `../TESTING-TIERS.md`.
## Requirements
### Requirement: Recording readiness wait
The audio engine SHALL capture audio via the cross-platform `sounddevice` (PortAudio) backend rather than a `sox` subprocess, writing the same 16 kHz mono WAV at the established recording path so transcription is unaffected. The engine SHALL wait for the capture stream to begin delivering audio before returning from start, so that the audio device's cold-start delay does not produce an empty first recording. The wait SHALL terminate when capture has started, when the stream fails to open (after the single refresh-and-retry attempt), or when a readiness timeout elapses — and SHALL never block indefinitely.

#### Scenario: Recording becomes ready
- **WHEN** the `sounddevice` capture stream starts and begins delivering audio frames
- **THEN** the start call SHALL return with recording active

_Tier: platform-real — needs a real audio device; deferred to the per-OS smoke tier._

#### Scenario: Readiness times out
- **WHEN** capture never begins delivering audio within the readiness timeout
- **THEN** the start call SHALL return anyway and SHALL log a warning that the first recording may be empty

_Tier: platform-real — deferred to the per-OS smoke tier._

#### Scenario: Capture stream fails to open
- **WHEN** the `sounddevice` stream cannot be opened (no device / busy) even after the refresh-and-retry sequence
- **THEN** the readiness wait SHALL stop, the engine SHALL log a warning rather than block, and the capture failure SHALL be reported for user notification

_Tier: unit-mocked — was platform-real; the refresh/retry/notify path is mockable._

### Requirement: Follow system default input device
The audio engine SHALL re-enumerate the audio backend's device list before opening each capture stream, so that capture targets the system default input device current at the moment recording starts — including after a Bluetooth device connects or disconnects, or the machine wakes from sleep. When the device-list refresh itself fails, the engine SHALL proceed to open the stream anyway (degrading to prior behavior) rather than abort the recording.

#### Scenario: Default input changed since daemon start
- **WHEN** the system default input device has changed since the audio backend was initialized (e.g. a Bluetooth headset disconnected) and a recording starts
- **THEN** the engine SHALL refresh the device list before opening the stream, and the stream SHALL capture from the current system default input device

_Tier: unit-mocked — refresh call pinned and ordered before stream open._

#### Scenario: Device refresh fails
- **WHEN** the device-list refresh raises an error
- **THEN** the engine SHALL log the error and still attempt to open the capture stream

_Tier: unit-mocked._

### Requirement: Retry stream open after refresh
When opening the capture stream fails, the audio engine SHALL refresh the device list once more and retry the open exactly once. Only after the retry also fails SHALL the engine give up on capturing for this recording.

#### Scenario: First open fails, retry succeeds
- **WHEN** the first stream-open attempt raises and the retry after a second refresh succeeds
- **THEN** recording SHALL proceed normally with the retried stream and no capture failure SHALL be reported

_Tier: unit-mocked._

#### Scenario: Retry also fails
- **WHEN** both the initial open and the single retry raise
- **THEN** the engine SHALL stop retrying, record the capture failure for reporting, and the readiness wait SHALL stop rather than block

_Tier: unit-mocked._

### Requirement: Capture failure reported to user
When the capture stream cannot be opened (after the retry), the failure SHALL be surfaced to the user through the engine's callback mechanism — mirroring the existing model-load-failure pattern — so the UI can post a notification, instead of the recording silently capturing nothing.

#### Scenario: Stream open fails after retry
- **WHEN** the capture stream fails to open after the refresh-and-retry sequence and a recording start was requested
- **THEN** the engine SHALL fire the capture-failed callbacks with a human-readable message identifying that no audio is being captured

_Tier: unit-mocked — `engine.py` fan-out mirrors `on_model_load_failed`._

#### Scenario: Stream opens normally
- **WHEN** the capture stream opens successfully
- **THEN** no capture-failed callback SHALL fire

_Tier: unit-mocked._

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

### Requirement: Capture is thread-safe under concurrent stop
Audio capture SHALL synchronize access to the WAV handle so the capture callback thread and the stop thread cannot race, and the capture callback SHALL never propagate an exception into the audio backend.

#### Scenario: Stop during an in-flight callback
- **WHEN** `stop()` closes the recording while the PortAudio callback is mid-write
- **THEN** access to the WAV handle SHALL be serialized so neither thread writes to a closed handle, and any callback error SHALL be logged and contained (never raised into PortAudio)

### Requirement: Each recording is isolated to its own file
Each recording SHALL write to a unique path captured at recording start, so a recording started while a previous transcription is still reading does not corrupt or delete the in-use file.

#### Scenario: Trigger fires during transcription
- **WHEN** a new recording starts while the transcription worker is still reading the prior recording
- **THEN** the new recording SHALL write to a different file and the worker's file SHALL remain intact until cleanup

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

### Requirement: Recording files are created owner-only
Every recording WAV (the main recording and each streaming chunk) SHALL be created with `0o600` permissions (owner read/write only), regardless of the process umask, so recorded voice audio is never world-readable in a shared temporary directory.

#### Scenario: Recording WAV is owner-only under a permissive umask
- **WHEN** a recording starts under a permissive process umask (e.g. `0o022`)
- **THEN** the resulting recording WAV SHALL have file mode `0o600`

_Tier: unit-pure — `test_audio.py::TestRecordingFilePermissions` (POSIX only)._

#### Scenario: Streaming chunk WAV is owner-only
- **WHEN** a streaming chunk WAV is emitted under a permissive process umask
- **THEN** the resulting chunk WAV SHALL have file mode `0o600`

_Tier: unit-pure — `test_audio.py::TestRecordingFilePermissions` (POSIX only)._

### Requirement: Stale recording files are swept at startup
`AudioEngine` initialization SHALL best-effort remove leftover `whispy-*.wav` files (from a prior crash or an incomplete cleanup) from the temporary directory, and a failure during the sweep SHALL NOT prevent `AudioEngine` from starting.

#### Scenario: Startup removes a leftover recording
- **WHEN** a stale `whispy-<uuid>.wav` file exists in the temp directory when `AudioEngine` is constructed
- **THEN** the file SHALL be removed as part of construction

_Tier: unit-pure — `test_audio.py::TestStaleRecordingSweep`._

#### Scenario: Sweep failure does not break startup
- **WHEN** listing or removing stale recordings raises an OS-level error
- **THEN** `AudioEngine` construction SHALL still succeed

_Tier: unit-mocked — `test_audio.py::TestStaleRecordingSweep::test_sweep_failure_does_not_break_startup`._


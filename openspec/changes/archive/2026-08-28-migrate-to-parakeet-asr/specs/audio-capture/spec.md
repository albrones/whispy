## MODIFIED Requirements

### Requirement: Audio duration detection
The audio engine SHALL determine the duration of a recorded WAV file using frame count and sample rate. When the file cannot be read as WAV, duration detection SHALL return no value rather than raise.

#### Scenario: Valid WAV duration
- **WHEN** a readable WAV file is measured
- **THEN** the engine SHALL return its duration in seconds computed from frames divided by sample rate

_Tier: unit-pure — `test_audio.py::TestAudioDurationDetection`. Relocated from the deleted `test_language_detection.py`, which existed for the auto-detect-language feature; duration measurement outlived it as the short-clip discard guard._

#### Scenario: Unreadable file
- **WHEN** the file cannot be opened or parsed as WAV
- **THEN** the engine SHALL return no duration value and SHALL NOT raise

_Tier: unit-pure — `test_audio.py::TestAudioDurationDetection`._

### Requirement: Short-clip discard guard
The audio engine SHALL discard a recording whose duration is below the configured `min_recording_duration` before transcription. The guard now exists to avoid spending a decoder pass on a misclick-length clip; suppressing non-speech output is the job of the RMS and speech gates, not this one. A discarded clip SHALL yield no transcription output.

#### Scenario: Misclick-length recording discarded
- **WHEN** a recording's measured duration is below `min_recording_duration`
- **THEN** the engine SHALL skip transcription and return no text

_Tier: unit-mocked — `test_audio.py`._

#### Scenario: Sufficient-length recording proceeds
- **WHEN** a recording's measured duration is at or above `min_recording_duration`
- **THEN** the engine SHALL proceed to transcription

_Tier: unit-mocked — `test_audio.py`._

### Requirement: Transcription failure isolation
The audio engine SHALL catch errors raised by the underlying transcription model and return no value, so that a transcription failure does not propagate as an exception to callers. The engine SHALL also return no value when the model returns empty text.

#### Scenario: Model raises
- **WHEN** the transcription call raises
- **THEN** the engine SHALL return no text and SHALL NOT propagate the exception

_Tier: unit-mocked — `test_audio.py`._

#### Scenario: Model returns empty text
- **WHEN** the transcription call returns an empty or whitespace-only string
- **THEN** the engine SHALL return no text

_Tier: unit-mocked — `test_audio.py`._

## ADDED Requirements

### Requirement: Near-silent audio is gated before the model
The audio engine SHALL measure the normalized RMS amplitude of a clip and SHALL NOT call the model when it falls below `SILENCE_RMS_THRESHOLD`. When RMS cannot be measured the engine SHALL transcribe the clip anyway — the gate fails open, so an unmeasurable recording is never silently dropped.

This guard is not inherited from the Whisper era; it replaces the phrase blocklist that was. Parakeet does not hallucinate training-corpus artifacts or loop, but it invents short conversational fillers on near-silence, and those would be typed into the user's active field.

#### Scenario: Near-silent clip is discarded without calling the model
- **WHEN** a clip's measured RMS is below the threshold
- **THEN** the engine SHALL return no text and SHALL NOT call the model

_Tier: unit-mocked — `test_audio.py::TestTranscribe`._

#### Scenario: Audible clip passes the gate
- **WHEN** a clip's measured RMS is at or above the threshold
- **THEN** the engine SHALL transcribe it normally

_Tier: unit-mocked — `test_audio.py::TestTranscribe`._

#### Scenario: Unmeasurable clip is transcribed
- **WHEN** RMS cannot be computed (unreadable file, unsupported sample width)
- **THEN** the engine SHALL proceed to transcription rather than discard the clip

_Tier: unit-mocked — `test_audio.py::TestTranscribe`._

### Requirement: Non-speech above the silence threshold is gated before the model
The audio engine SHALL measure the duration of voiced audio in a clip and SHALL NOT call the model when it falls below `MIN_SPEECH_DURATION_S`. When that duration cannot be measured the engine SHALL transcribe the clip anyway — this gate fails open exactly as the RMS gate does, because losing real dictation is worse than injecting an occasional filler.

This gate exists because the RMS gate only catches *near-silence*. Non-speech that is merely loud — a noisy room, a fan, 50 Hz mains hum — measures 0.010–0.035 normalized RMS against a 0.005 threshold, so it clears that gate and reaches the model, which answered 3 of 100 such realizations with a filler (`Yeah.`, `Ha ha ha.`). With this gate, 0 of 100.

The metric SHALL be an absolute duration and SHALL NOT be a voiced/silent ratio. A ratio cannot separate the two populations: one word inside a 10 s trigger-hold is ~6% voiced, and steady noise is ~5% — while in absolute terms they are 0.66 s and 0.09 s. Holding the trigger while thinking is ordinary use, so a ratio gate would discard real dictation.

The threshold SHALL be chosen from the measured separation: across 125 noise realizations above the RMS gate the worst carried 0.12 s of voiced audio, and the shortest real one-word dictation carried 0.33 s.

The gate's ceiling SHALL be documented rather than papered over: voice-activity detection has an energy floor, so past roughly 0.04 normalized RMS it labels steady noise fully voiced and this gate stops discriminating. That band is left to the model, which returned empty text for every such clip measured. Raising the threshold SHALL NOT be used to cover it — that would discard real speech before it caught the noise.

#### Scenario: Loud non-speech is discarded without calling the model
- **WHEN** a clip clears the RMS gate but carries less than `MIN_SPEECH_DURATION_S` of voiced audio
- **THEN** the engine SHALL return no text and SHALL NOT call the model

_Tier: unit-pure — `test_audio.py::TestSpeechGate`._

#### Scenario: Voiced audio passes the gate
- **WHEN** a clip carries at least `MIN_SPEECH_DURATION_S` of voiced audio
- **THEN** the engine SHALL transcribe it normally

_Tier: unit-pure — `test_audio.py::TestSpeechGate`._

#### Scenario: Unmeasurable clip is transcribed
- **WHEN** voiced duration cannot be measured (unreadable file, unsupported sample width, voice-activity detection unavailable)
- **THEN** the engine SHALL proceed to transcription rather than discard the clip

_Tier: unit-pure — `test_audio.py::TestSpeechGate`, one scenario per cause._

### Requirement: Voiced-duration measurement
The segmentation module SHALL expose the total duration of voiced audio in a PCM buffer, computed with the same voice-activity detector the streaming segmenter uses, and SHALL return no value rather than raise when the detector is unavailable, the sample rate is unsupported, or the buffer is shorter than one frame.

#### Scenario: Voiced audio measures its own length
- **WHEN** a buffer of continuously voiced audio is measured
- **THEN** the module SHALL return approximately that buffer's duration

_Tier: unit-pure — `test_segmentation.py::TestSpeechDuration`._

#### Scenario: Silence measures zero
- **WHEN** an all-zero buffer is measured
- **THEN** the module SHALL return 0.0

_Tier: unit-pure — `test_segmentation.py::TestSpeechDuration`._

#### Scenario: Padding does not reduce the measurement
- **WHEN** the same voiced audio is measured tightly cropped and again surrounded by seconds of silence
- **THEN** the padded measurement SHALL be at least the cropped one

_Tier: unit-pure — `test_segmentation.py::TestSpeechDuration`. Pins the property that makes a duration usable where a ratio is not._

#### Scenario: No detector available
- **WHEN** the voice-activity detector cannot be imported or initialized
- **THEN** the module SHALL return no value, so callers fail open

_Tier: unit-pure — `test_segmentation.py::TestSpeechDuration`._

### Requirement: RMS measurement
The audio engine SHALL compute normalized (0.0–1.0) RMS amplitude from a WAV's samples, handling 8-, 16-, and 32-bit PCM, and SHALL return no value rather than raise when the file cannot be measured.

#### Scenario: Digital silence measures zero
- **WHEN** an all-zero 16-bit WAV is measured
- **THEN** the engine SHALL return 0.0

_Tier: unit-pure — `test_audio.py::TestAudioRms`._

#### Scenario: Quiet noise stays below the gate
- **WHEN** a WAV at roughly 0.002 of full scale is measured — the noise floor that made the model emit fillers in the real-model tier
- **THEN** the measured RMS SHALL be below `SILENCE_RMS_THRESHOLD`

_Tier: unit-pure — `test_audio.py::TestAudioRms`._

#### Scenario: Unreadable file yields no value
- **WHEN** the file cannot be opened or parsed as WAV
- **THEN** the engine SHALL return no value and SHALL NOT raise

_Tier: unit-pure — `test_audio.py::TestAudioRms`._

### Requirement: Transcription call carries no decoder parameters
The audio engine's transcription entry point SHALL accept only the audio path, the loaded model, and `min_recording_duration`. It SHALL NOT accept or forward a language, beam size, best-of count, temperature, VAD filter flag, previous-text conditioning flag, or vocabulary prompt. These were Whisper decoder controls with no counterpart in the transducer backend, and two of them were actively harmful: a forced language translated rather than recognized, and disabling previous-text conditioning without VAD truncated long recordings.

#### Scenario: No decoder arguments are forwarded
- **WHEN** a recording or a chunk is transcribed
- **THEN** the call to the model SHALL pass the audio only, with no decoder-tuning keyword arguments

_Tier: unit-mocked — `test_audio.py`._

## REMOVED Requirements

### Requirement: Auto-detect language warning
**Reason**: There is no language setting and no `auto_detect_min_duration` threshold — the backend detects language per utterance regardless of clip length. The requirement also documented a code path that could not run: `language="auto"` raised `ValueError` in faster-whisper and was unreachable only because config validation restricted the value to `fr`/`en`.
**Migration**: None. The WAV duration-measurement scenarios that lived alongside this requirement stay under "Audio duration detection".

### Requirement: Credit stripping at the audio layer
**Reason**: Whisper credit/watermark prefixes were an artifact of the previous model. Parakeet does not emit them, so stripping them at the audio layer protects nothing while retaining logic that silently rewrites user text.
**Migration**: `text-cleaning` drops the corresponding phrase lists. Returning no text for empty model output is preserved under "Transcription failure isolation".

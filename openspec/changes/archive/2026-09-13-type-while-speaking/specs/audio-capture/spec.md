## MODIFIED Requirements

### Requirement: Near-silent audio is gated before the model
The audio engine SHALL measure the normalized RMS amplitude of the **loudest
window** of a clip (about half a second) and SHALL NOT call the model when it
falls below `SILENCE_RMS_THRESHOLD`. The metric SHALL NOT be the whole-clip mean:
the mean scales a single word by the square root of its share of the clip, so
one word held by the segmenter and flushed inside ten seconds of silence
measured under the threshold and was discarded, although the word itself was
five times over it. When RMS cannot be measured the engine SHALL transcribe the
clip anyway — the gate fails open, so an unmeasurable recording is never
silently dropped.

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

#### Scenario: One word inside a long silence passes the gate
- **WHEN** a clip holds one audible word and otherwise silence, such that its whole-clip mean RMS is below the threshold
- **THEN** the loudest-window RMS SHALL be at or above the threshold and the engine SHALL transcribe the clip

_Tier: unit-pure — `test_audio.py::TestPeakRms`._

#### Scenario: Quiet noise has no loud window
- **WHEN** a clip is uniform noise at the quiet-room floor (about 0.002 of full scale)
- **THEN** the loudest-window RMS SHALL be below the threshold and the clip SHALL be discarded

_Tier: unit-pure — `test_audio.py::TestPeakRms`._

## ADDED Requirements

### Requirement: The model receives the clip trimmed to its voiced span
Before calling the model, the audio engine SHALL cut the clip down to the span
between its first and last voice-detected frames, widened by a fixed margin of
about 0.3 s on each side, and SHALL hand the model that trimmed copy. Silence
inside the span SHALL be preserved; only the leading and trailing silence is
removed. The trimmed copy SHALL be deleted after the call and the original clip
SHALL NOT be modified. When the voiced span cannot be measured, or when trimming
would remove less than about a quarter of a second, the engine SHALL send the
original clip unchanged.

This exists because silence around an utterance is not neutral to the model:
measured on synthesized isolated words, recognition fell from 12/15 with 0.6 s of
trailing silence to 3–5/15 with 10 s, and returned to 10–12/15 once trimmed. A
word the segmenter held for the lone-word pause, or that reached the length cut,
always arrives with seconds of silence attached.

#### Scenario: Silence around speech is removed before the model
- **WHEN** a clip holds an utterance preceded and followed by several seconds of silence
- **THEN** the model SHALL receive a copy whose duration is close to the utterance plus the margins, the copy SHALL be removed afterwards, and the original file SHALL still exist

_Tier: unit-mocked — `test_audio.py::TestTrimToSpeech`._

#### Scenario: Internal silence is kept
- **WHEN** a clip holds two utterances separated by a pause
- **THEN** the model SHALL receive both utterances and the pause between them

_Tier: unit-mocked — `test_audio.py::TestTrimToSpeech`._

#### Scenario: A tight clip is sent as is
- **WHEN** a clip already starts and ends on speech
- **THEN** the model SHALL receive the original file

_Tier: unit-mocked — `test_audio.py::TestTrimToSpeech`._

#### Scenario: Trimming fails open
- **WHEN** the voiced span cannot be measured or the trimmed copy cannot be written
- **THEN** the model SHALL receive the original clip rather than nothing

_Tier: unit-mocked — `test_audio.py::TestTrimToSpeech`._

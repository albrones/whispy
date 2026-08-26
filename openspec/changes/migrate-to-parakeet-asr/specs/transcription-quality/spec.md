## MODIFIED Requirements

### Requirement: Real-model semantic transcription
The system SHALL be verifiable end-to-end through the real Parakeet model: synthesized speech in a supported language SHALL transcribe to non-empty text containing at least one expected keyword (case-insensitive). Verification SHALL synthesize audio with the macOS `say` command, convert it to 16 kHz mono WAV, and run the real model **with no language argument**, since language detection is the model's own responsibility. The bar is meaningful overlap with intent (≥1 expected keyword), not exact recall of every word.

#### Scenario: French phrase transcribes to expected keywords
- **WHEN** a French phrase is synthesized, converted, and transcribed with no language configured
- **THEN** the cleaned output SHALL be non-empty and contain at least one expected keyword (case-insensitive)

_Tier: macos-real — `@pytest.mark.macos`, requires `say` and the Parakeet model._

#### Scenario: English phrase transcribes to expected keywords
- **WHEN** an English phrase is synthesized, converted, and transcribed with no language configured
- **THEN** the cleaned output SHALL be non-empty and contain at least one expected keyword (case-insensitive)

_Tier: macos-real — `@pytest.mark.macos`._

#### Scenario: A single clip containing both languages is not forced into one
- **WHEN** a clip whose first half is French and second half is English is transcribed
- **THEN** the output SHALL contain at least one expected keyword from each language, rather than rendering the English half as French words

_Tier: macos-real — `@pytest.mark.macos`. This scenario exists because the previous backend, given a forced language, translated the other language instead of recognizing it._

### Requirement: Custom vocabulary improves recognition
The system SHALL improve rendering of configured vocabulary terms by correcting near misses in transcription output, since the transducer backend offers no decoder-biasing channel. A transcribed token whose similarity to a configured term exceeds the cleaning step's cutoff SHALL be replaced by that term. The system SHALL NOT claim to recover terms the model rendered far from the target — near-miss correction is explicitly weaker than decoder biasing, and documentation SHALL say so.

#### Scenario: Near-miss term corrected
- **WHEN** a clip naming a configured term is transcribed and the model renders it as a close variant (e.g. "wispy" for "Whispy")
- **THEN** the cleaned output SHALL contain the configured term

_Tier: macos-real — `@pytest.mark.macos`._

#### Scenario: Unrelated text is never rewritten into a vocabulary term
- **WHEN** a clip containing none of the configured terms is transcribed with a non-empty `custom_vocabulary`
- **THEN** no configured term SHALL appear in the cleaned output

_Tier: unit-pure — `test_text_cleaning.py`. This scenario exists because the previous decoder-prompt mechanism leaked vocabulary terms into transcriptions verbatim._

### Requirement: Silence and artifacts produce no output
The system SHALL inject nothing for non-speech input. A sub-`min_recording_duration` clip SHALL be discarded before the model, a clip whose normalized RMS amplitude is below the silence threshold SHALL also be discarded before the model, and a clip carrying less than `MIN_SPEECH_DURATION_S` of voiced audio SHALL be discarded before the model.

The system SHALL NOT rely on the model returning empty text for silence, and SHALL NOT use a phrase blocklist. Measurement disproved the first: Parakeet emits short conversational fillers on near-silent audio — `Yeah.` on pure digital silence at 0.6 s / 1.0 s / 1.5 s, `Thank you.` at 2.0 s, and `Okay.` / `Mm-hmm.` / `No.` on a realistic quiet-room noise floor — non-monotonically in duration. The second is excluded because such a list would have to contain `Okay.` and `No.`, which are legitimate one-word dictations, so filtering by text would delete real speech.

The threshold SHALL be chosen from the measured separation: every observed false positive sat at or below 0.00065 normalized RMS, every real utterance at or above 0.147.

Energy alone SHALL NOT be relied on for non-speech that is merely loud. Measurement disproved that too: room noise, a fan and mains hum measure 0.010–0.035 normalized RMS, clear the silence threshold, and reach the model, which answered 3 of 100 such realizations with a filler. The system SHALL therefore also require a minimum *duration* of voiced audio, measured with voice-activity detection (see the audio-capture spec for the metric and its ceiling).

#### Scenario: Sub-threshold clip yields nothing
- **WHEN** a clip is run through the transcribe path with a duration below `min_recording_duration`
- **THEN** the path SHALL return no text (discarded before the model)

_Tier: macos-real — `@pytest.mark.macos`._

#### Scenario: Pure silence is never transcribed
- **WHEN** a silent clip at or above `min_recording_duration` is run through the transcribe path, at any duration
- **THEN** the path SHALL return no text, and the model SHALL NOT be called

_Tier: macos-real — `@pytest.mark.macos::TestSilenceGate`, parameterized over 0.6 / 1.0 / 1.5 / 2.0 s because the model's invented output varies non-monotonically with duration._

#### Scenario: Quiet room noise is never transcribed
- **WHEN** a clip containing only a low-amplitude noise floor is run through the transcribe path
- **THEN** the path SHALL return no text, and the model SHALL NOT be called

_Tier: macos-real — `@pytest.mark.macos::TestSilenceGate`. This is the live case: a real microphone never reaches digital zero._

#### Scenario: Real speech clears the gate by a wide margin
- **WHEN** an ordinary dictation clip is measured
- **THEN** its RMS SHALL exceed the silence threshold several times over, and it SHALL be transcribed

_Tier: macos-real — `@pytest.mark.macos::TestSilenceGate`. Guards against a future threshold change creeping up into real speech._

#### Scenario: Loud non-speech is never transcribed
- **WHEN** a clip of noise loud enough to clear the silence threshold — white, brown or pink noise, mains hum, or a lowpassed fan-like spectrum — is run through the transcribe path
- **THEN** the path SHALL return no text, and the model SHALL NOT be called

_Tier: macos-real — `@pytest.mark.macos::TestSilenceGate::test_loud_non_speech_above_the_rms_gate_is_discarded`. Noise is synthesized with a fixed seed: `sox` draws a fresh realization per call, and the model answers only a small fraction of them, so an unseeded draw makes this a coin flip rather than a test._

#### Scenario: A sub-second word is still transcribed
- **WHEN** a one-word dictation of roughly half a second is run through the transcribe path
- **THEN** the path SHALL return that word

_Tier: macos-real — `@pytest.mark.macos::TestShortDictation`. This is the counterweight to every non-speech guard: `oui` and `non` measure 0.40–0.50 s of audio, so no guard may be tightened past them._

#### Scenario: A word held inside a long silence is still transcribed
- **WHEN** a clip containing one word surrounded by several seconds of silence — the user holding the trigger while thinking — is run through the transcribe path
- **THEN** the path SHALL return that word

_Tier: macos-real — `@pytest.mark.macos::TestShortDictation`. This is why the voiced measurement is a duration and not a voiced/silent ratio: such a clip is ~6% voiced, the same as steady noise._

#### Scenario: An unmeasurable clip is transcribed, not dropped
- **WHEN** RMS cannot be computed for a clip
- **THEN** the system SHALL transcribe it rather than discard it — the gate fails open

_Tier: unit-mocked — `test_audio.py`._

## ADDED Requirements

### Requirement: Short chunks do not degenerate
The system SHALL produce bounded output for short chunks: transcribing a chunk SHALL NOT emit a token or phrase repeated beyond what the audio contains. This is a property of the transducer backend rather than a guard the system implements, and it is specified because the previous backend emitted runaway repetition on sub-2-second chunks — text that was injected into the user's active field.

#### Scenario: A short chunk yields proportionate output
- **WHEN** a chunk of at most 1.5 seconds is transcribed
- **THEN** the output SHALL contain no phrase repeated more than a small bounded number of times

_Tier: macos-real — `@pytest.mark.macos`._

### Requirement: Long recordings are transcribed completely
The system SHALL transcribe the whole of a recording in the non-streaming path. Output SHALL NOT be silently truncated to the first utterance.

#### Scenario: A multi-sentence recording is not truncated
- **WHEN** a recording of at least 20 seconds containing several distinct utterances is transcribed in the non-streaming path
- **THEN** the output SHALL reflect utterances from beyond the first few seconds

_Tier: macos-real — `@pytest.mark.macos`. This scenario exists because the previous backend truncated a 22-second recording to a single sentence with no error._

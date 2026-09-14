# streaming-transcription Specification

## Purpose
TBD - created by archiving change streaming-incremental-transcription. Update Purpose after archive.
## Requirements
### Requirement: Streaming is config-gated and backward compatible
The system SHALL provide a `streaming_enabled` configuration flag (default true,
also toggleable from the menu). When enabled, the system SHALL transcribe the
recording in chunks during recording. When disabled, the system SHALL use the
legacy record-then-transcribe path with identical behaviour to before this
change. The streaming configuration keys (`streaming_enabled`, `pause_ms`,
`min_speech_s`, `min_chunk_s`, `max_chunk_s`, `vad_aggressiveness`,
`type_while_speaking`) SHALL be validated against `DEFAULT_CONFIG` and SHALL be
added with defaults by config migration so existing configs keep working.

#### Scenario: Streaming disabled uses legacy path
- **WHEN** `streaming_enabled` is false and a recording completes
- **THEN** the system SHALL transcribe the whole recording in one block and inject the result, exactly as before this change

#### Scenario: Missing streaming keys are migrated with defaults
- **WHEN** a config without the streaming keys is loaded
- **THEN** the system SHALL add the streaming keys with their default values and SHALL NOT fail

#### Scenario: Invalid streaming values fall back to defaults
- **WHEN** a streaming config value is of the wrong type or out of range
- **THEN** the system SHALL log a warning and use the default for that key

### Requirement: Silence- and length-bounded chunk emission
While streaming is enabled and recording is active, the system SHALL emit a
transcription chunk when accumulated speech is followed by a pause of at least
`pause_ms`, OR when the current chunk's audio has reached `max_chunk_s` and a
short gap in speech (about 200 ms of detected silence) occurs, OR unconditionally
when the chunk reaches one and a half times `max_chunk_s`, whichever occurs
first. Past `max_chunk_s` the system SHALL NOT cut at an arbitrary frame while
speech is detected, because a mid-word cut makes the halves come back duplicated
or empty. A chunk holding less than `min_speech_s` of voiced audio SHALL be held
through an ordinary pause so a short word rides along with the next utterance,
but SHALL be emitted once the silence reaches about 2 s, so a word that nothing
follows is typed rather than held. The system SHALL NOT emit a chunk that never
contained speech.

The length cut SHALL remain independent of the voiced-speech threshold, so a
chunk withheld for want of speech still flushes once it is long, and audio can
never be held indefinitely. The final tail flush SHALL likewise remain
independent of it, so a dictation consisting entirely of one short utterance is
still transcribed.

#### Scenario: Pause triggers a chunk
- **WHEN** the input level stays below the silence threshold for at least `pause_ms` after speech was detected, and the chunk holds at least `min_speech_s` of voiced audio
- **THEN** the system SHALL emit the accumulated speech as a chunk and begin a new (empty) chunk

#### Scenario: Run-on speech is force-flushed at max length
- **WHEN** the current chunk reaches `max_chunk_s` of audio without any qualifying pause
- **THEN** the system SHALL emit the chunk at the first short gap in speech that follows, so streaming continues to make progress without cutting a word in two

#### Scenario: Speech with no gap at all is cut at the hard cap
- **WHEN** the current chunk has passed `max_chunk_s` and speech continues with no short gap
- **THEN** the system SHALL emit the chunk unconditionally once it reaches one and a half times `max_chunk_s`

#### Scenario: A short gap before max length is not a boundary
- **WHEN** a gap of about 200 ms occurs in a chunk that has not yet reached `max_chunk_s`
- **THEN** the system SHALL NOT emit a chunk on that gap alone

#### Scenario: A chunk below the speech threshold is force-flushed at max length
- **WHEN** a chunk has not reached `min_speech_s` of voiced audio but its audio reaches `max_chunk_s`
- **THEN** the system SHALL emit it at the next short gap, or unconditionally at the hard cap, so withholding a boundary can never strand audio

#### Scenario: A lone short word is emitted once the speaker has clearly stopped
- **WHEN** a chunk holds less than `min_speech_s` of voiced audio and the silence after it reaches about 2 s
- **THEN** the system SHALL emit that chunk on its own rather than hold it for a next utterance

#### Scenario: A short word followed by more speech still rides along
- **WHEN** a chunk holds less than `min_speech_s` of voiced audio and speech resumes within 2 s
- **THEN** the system SHALL NOT emit a boundary at that pause, and the short word SHALL be carried into the chunk with the following speech

#### Scenario: Pure silence emits nothing
- **WHEN** a span of audio between two emitted chunks contains no detected speech
- **THEN** the system SHALL NOT emit a chunk for that span

### Requirement: VAD-based, gain-independent speech detection
Speech-vs-silence classification SHALL use a voice-activity detector (WebRTC VAD)
on fixed-size frames, configurable via `vad_aggressiveness` (0–3), rather than a
raw energy threshold — so segmentation does not mis-cut mid-word and does not
require per-microphone gain tuning. When the VAD library is unavailable the
system SHALL fall back to an energy gate so the app still runs. Audio SHALL never
be dropped by the segmenter; it only chooses cut points, and the onset of speech
at recording start SHALL NOT be clipped.

#### Scenario: Speech at recording start is not clipped
- **WHEN** a recording begins with speech (no silent lead-in)
- **THEN** the segmenter SHALL detect that speech and retain it (no onset loss)

#### Scenario: Energy fallback when VAD is absent
- **WHEN** the VAD library cannot be imported
- **THEN** the segmenter SHALL classify frames with an energy gate and continue to function

### Requirement: Text is typed once on release
When the trigger is in **hold** (push-to-talk) mode, or when `type_while_speaking`
is false, chunks transcribed during recording SHALL be buffered and the
assembled text SHALL be injected once when the recording stops — synthetic
keystrokes SHALL NOT fire mid-recording. This is required in hold mode because
the trigger key is physically held for the whole recording, and typing under a
held modifier alters every character. Streaming SHALL be enabled by default.

#### Scenario: No mid-recording injection
- **WHEN** the trigger mode is hold and several chunks are recognized during recording
- **THEN** the system SHALL NOT inject any text until trigger release

#### Scenario: Assembled text typed once on release
- **WHEN** the trigger is released in hold mode after one or more chunks were recognized
- **THEN** the system SHALL inject the chunks' assembled text exactly once

#### Scenario: Live typing disabled by configuration
- **WHEN** the trigger mode is toggle and `type_while_speaking` is false
- **THEN** the system SHALL behave as in hold mode: no mid-recording injection, assembled text typed once at stop

### Requirement: Ordered chunk assembly
The system SHALL transcribe emitted chunks through a single ordered (FIFO)
pipeline, accumulating their recognized text in emission order, and assemble it
space-separated so words from adjacent chunks are not concatenated.

#### Scenario: Chunks assembled in order
- **WHEN** multiple chunks are emitted during one recording
- **THEN** their recognized text SHALL be assembled in the order the chunks were emitted, space-separated

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

### Requirement: Streaming is always on; no menu toggle
Streaming is enabled by default and SHALL NOT have a menu toggle (it is always
active). The menu-bar Settings section SHALL NOT show a "Streaming transcription"
item. A `streaming_enabled=false` config value MAY still select the legacy path
(for diagnostics), but no UI exposes it.

#### Scenario: No streaming toggle in the menu
- **WHEN** the menu is shown
- **THEN** there SHALL be no "Streaming transcription" item

### Requirement: Streaming config changes apply at runtime
The engine SHALL apply streaming configuration changes at runtime without a
restart: when the config changes while the engine is running (e.g. via the
config API or the menu), it SHALL re-wire the audio segmentation and start or
stop the chunk worker to match, and a change to `type_while_speaking` SHALL take
effect on the next recording.

#### Scenario: Enabling at runtime starts the worker
- **WHEN** `streaming_enabled` flips to true while the engine is running
- **THEN** the engine SHALL re-wire the audio engine for streaming and start the chunk worker

#### Scenario: Disabling at runtime stops the worker
- **WHEN** `streaming_enabled` flips to false while the engine is running
- **THEN** the engine SHALL stop the chunk worker and use the whole-recording path on the next recording

#### Scenario: Live typing toggled at runtime
- **WHEN** `type_while_speaking` changes while the engine is running
- **THEN** the next recording SHALL follow the new value, and the recording in progress (if any) SHALL keep the behaviour it started with

### Requirement: Settings toggles render with a trailing check
Boolean settings rows (e.g. "Copy to clipboard") SHALL render their selection
mark trailing the title (right side), so all settings titles stay left-aligned
with the submenu rows (Model, Language). The website menu mockup SHALL match.

#### Scenario: Checked toggle keeps the title left-aligned
- **WHEN** a boolean settings row is checked
- **THEN** its title SHALL start at the left and the check mark SHALL trail it (not indent the title)

### Requirement: Final tail flush on release
When the trigger key is released while streaming, the system SHALL flush and
transcribe the final (in-progress) chunk so no trailing speech is lost, and SHALL
return to the idle state after the tail chunk is handled.

#### Scenario: Trailing speech after the last pause is transcribed
- **WHEN** the user releases the trigger key with un-emitted speech in the current chunk
- **THEN** the system SHALL transcribe and inject that final chunk before returning to idle

### Requirement: Per-chunk latency is proportional to chunk length
Chunk transcription SHALL cost time proportional to the chunk's audio duration rather than paying a fixed per-call floor. The previous backend padded every input to a 30-second window, so a 0.5-second chunk cost the same ~0.5 s as a 2-second one and streaming assembly was bounded by the decoder instead of by the speaker.

#### Scenario: A short chunk is cheaper than a long one
- **WHEN** a 0.5-second chunk and a 2.5-second chunk are transcribed through the real model
- **THEN** the shorter chunk SHALL complete measurably faster, and neither SHALL take longer than its own audio duration

_Tier: macos-real — `@pytest.mark.macos`._

### Requirement: Text is typed per chunk in toggle mode
When the trigger mode is **toggle** and `type_while_speaking` is true (the
default), the system SHALL inject each chunk's cleaned text as soon as that
chunk is transcribed, while recording continues, in chunk emission order. A
chunk typed after an earlier chunk of the same recording produced text SHALL be
prefixed with a single space, so words from adjacent chunks are not
concatenated; the first typed chunk SHALL NOT be prefixed. A chunk that yields
no text SHALL type nothing and SHALL NOT affect the spacing of later chunks.
When the recording stops, the tail chunk SHALL be typed the same way and the
system SHALL NOT inject the assembled text a second time. The decision to type
live SHALL be taken once per recording, at recording start, and the system
SHALL wait for the trigger key to be physically released before each injection,
as it does for the stop-time injection.

#### Scenario: Chunk text appears before the recording stops
- **WHEN** the trigger mode is toggle, `type_while_speaking` is true, and a chunk is transcribed to non-empty text while recording is still active
- **THEN** the system SHALL inject that text immediately, without waiting for the recording to stop

#### Scenario: Adjacent chunks are separated by one space
- **WHEN** two consecutive chunks of one recording both yield text
- **THEN** the second SHALL be injected with exactly one leading space and the first with none

#### Scenario: Empty chunk does not add a space
- **WHEN** a chunk yields no text and the following chunk yields text
- **THEN** the following chunk's leading space SHALL depend only on whether an earlier chunk of the recording was typed

#### Scenario: Stop types the tail and nothing else
- **WHEN** the recording stops after chunks were typed live and the tail chunk yields text
- **THEN** the tail text SHALL be injected once (with its leading space) and the previously typed text SHALL NOT be injected again

#### Scenario: Whole transcript still tracked for the recording limit
- **WHEN** a live-typed toggle recording is stopped by the recording-duration limit
- **THEN** the system SHALL still place the whole recording's assembled text on the clipboard, as the limit stop does today, and `last_transcription` SHALL hold the whole assembled text

### Requirement: Live typing is exposed as a settings toggle
The menu-bar Settings section SHALL show a "Type while speaking" boolean row,
rendered like the other boolean settings rows (trailing check), reflecting
`type_while_speaking` and applying the change through the engine's runtime
config update. The website menu mockup SHALL show the same row.

#### Scenario: Toggling the row updates the config
- **WHEN** the user selects "Type while speaking" in the menu
- **THEN** `type_while_speaking` SHALL flip and be persisted, and the row's check SHALL reflect the new value

#### Scenario: Website mockup matches the menu
- **WHEN** the website menu mockup is rendered
- **THEN** it SHALL list a "Type while speaking" row alongside "Toggle mode"

### Requirement: Chunk boundaries are gated on voiced speech

A pause SHALL close a chunk only when the chunk carries at least `min_speech_s`
of **voiced** audio, measured from the same frame classification the segmenter
already uses to detect silence. A chunk holding less SHALL NOT be emitted at a
pause: the segmenter SHALL keep accumulating, so the speech is carried into the
following chunk rather than reaching the model alone.

The guard SHALL measure voiced duration rather than elapsed buffered duration.
Measurement is why: through the production transcription gates, an isolated
`oui` chunk of 1.11 s total but 0.39 s voiced was recognized as English in 5 of 5
realizations, while the same word with 0.5 s of preceding speech — 1.61 s total,
0.72 s voiced — was correct in 5 of 5. Elapsed duration does not separate the two
outcomes; voiced duration does. An elapsed-time guard is additionally unreachable
in this rule, since the pause condition already implies more elapsed time than
any sensible minimum.

The system SHALL NOT discard audio to satisfy this guard.

#### Scenario: A chunk with too little speech does not close at a pause

- **WHEN** a qualifying pause occurs and the current chunk holds less than `min_speech_s` of voiced audio
- **THEN** the segmenter SHALL NOT signal a boundary, and the buffered speech SHALL remain in the current chunk

_Tier: unit-pure — `test_segmentation.py`._

#### Scenario: A chunk with enough speech closes at a pause

- **WHEN** a qualifying pause occurs and the current chunk holds at least `min_speech_s` of voiced audio
- **THEN** the segmenter SHALL signal a boundary and begin a new empty chunk

_Tier: unit-pure — `test_segmentation.py`._

#### Scenario: Short speech is carried into the next chunk

- **WHEN** a short utterance is followed by a pause and then further speech
- **THEN** both SHALL be emitted as one chunk, so the short utterance reaches the model with surrounding context

_Tier: unit-pure — `test_segmentation.py`._

#### Scenario: The guard cannot become unreachable

- **WHEN** the minimum-size guard is evaluated at a pause boundary
- **THEN** it SHALL be capable of blocking that boundary — a guard that the pause condition already implies (as an elapsed-time guard does) SHALL NOT be relied on

_Tier: unit-pure — `test_segmentation.py` (regression: the previous rule compared total buffered seconds against a value smaller than `pause_ms`, so it could never block)._

### Requirement: The voiced-speech threshold is configurable

The threshold SHALL be exposed as the `min_speech_s` configuration key, validated
as a non-negative number, and SHALL be applied at runtime like the other
streaming parameters — a change SHALL re-wire segmentation without a restart.

It SHALL be configuration rather than a constant because its default is derived
from synthesized speech with a single voice, so a real microphone, speaker or
room may move where voice-activity detection counts a frame as voiced. The
mechanism it guards is established; the value is provisional.

#### Scenario: Invalid value falls back

- **WHEN** `min_speech_s` is absent, negative, or not a number
- **THEN** the system SHALL use the default and report the substitution, as it does for the other streaming parameters

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: Change applies without a restart

- **WHEN** `min_speech_s` changes while the engine is running
- **THEN** the engine SHALL re-wire audio segmentation to the new value with no restart

_Tier: unit-mocked — `test_engine.py`._

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
short gap in speech (`soft_gap_ms` of detected silence) occurs, OR unconditionally
when the chunk reaches one and a half times `max_chunk_s`, whichever occurs
first. Past `max_chunk_s` the system SHALL NOT cut at an arbitrary frame while
speech is detected, because a mid-word cut makes the halves come back duplicated
or empty. A chunk holding less than `min_speech_s` of voiced audio SHALL be held
through an ordinary pause so a short word rides along with the next utterance,
but SHALL be emitted once the silence reaches about 2 s, so a word that nothing
follows is typed rather than held. The system SHALL NOT emit a chunk that never
contained speech.

`max_chunk_s` SHALL default to **8 seconds**, not 12. The backend resolves
language once per call, so the ceiling bounds how much audio a single wrong
language decision can carry away, and long chunks are where those decisions go
wrong. Measured over one daemon log of 610 chunks from a French dictation, the
chunks that came back in English had a median duration of 12.03 s against 7.0 s
for all chunks, and six of the seven were at least 8.5 s; the chunks the model
answered with nothing skewed the same way (16.7 s, 12.5 s, 12.0 s, 10.1 s).
Chunks closed by a genuine pause were almost always correct. The ceiling SHALL
remain configurable, because the value is derived from one speaker's cadence on
one machine while the mechanism it bounds is general.

The gap that releases the length cut SHALL be configurable as `soft_gap_ms`
and SHALL default to **350 ms**, not 200. The gap is the only thing standing
between the ceiling and a cut placed mid-word, and 200 ms is short enough to
occur inside ordinary speech: measured on a live French dictation at
`vad_aggressiveness: 3`, the ceiling cut the word *Régie* in half — the chunk
ended `...je suis dans Rég.` and the next began `la version app`, with the final
syllable lost outright. Lowering `max_chunk_s` from 12 s to 8 s made the cut fire
roughly half again as often, which is what turned a rare defect into a visible
one. The value SHALL remain configurable, because it is derived from one
speaker's cadence at one VAD aggressiveness while the mechanism it guards is
general.

Raising the gap threshold necessarily routes more run-on speech to the
unconditional hard cap, which cuts at an arbitrary frame. That trade is
deliberate: the hard cap is reached only by speech with no qualifying gap for
half again the ceiling, whereas the soft gap was firing on every long sentence.

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
- **WHEN** a gap shorter than `soft_gap_ms` occurs in a chunk that has not yet reached `max_chunk_s`
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

#### Scenario: A gap below the soft-gap threshold does not release the length cut

- **WHEN** a chunk has passed `max_chunk_s` and a gap shorter than `soft_gap_ms` occurs
- **THEN** the system SHALL NOT emit a chunk on that gap, and SHALL keep buffering until a qualifying gap or the hard cap

_Tier: unit-pure — `test_segmentation.py`._

#### Scenario: The default soft gap is 350 milliseconds

- **WHEN** the configuration is loaded with no `soft_gap_ms` value
- **THEN** the system SHALL use 350 milliseconds

_Tier: unit-pure — `test_config_validation.py`._

#### Scenario: The default ceiling is eight seconds
- **WHEN** the configuration is loaded with no `max_chunk_s` value
- **THEN** the system SHALL use 8 seconds

_Tier: unit-pure — `test_config_validation.py`._

### Requirement: A chunk boundary reports why it occurred

The segmenter SHALL report, for every boundary it emits, whether the chunk was closed by a **sentence-length pause** (silence long enough that the speaker plausibly finished a thought) or by a **continuation cut** (the length ceiling, the hard cap, or a pause too short to be a sentence break). The tail flush at the end of a recording SHALL count as a sentence-length pause.

The threshold separating the two SHALL be configurable and SHALL default to a value at or above `pause_ms`, so that raising `pause_ms` can never produce boundaries classified as sentence breaks that the previous setting treated as continuations.

This exists because the reason is the only signal available for joining chunk texts correctly: each chunk is an independent model call that punctuates and capitalizes its output as a standalone sentence, and nothing in the text itself distinguishes a chunk that ended a sentence from one the length ceiling cut in half.

#### Scenario: A length-ceiling flush is a continuation

- **WHEN** a chunk is emitted because its audio reached `max_chunk_s` and a short gap followed, or because it reached the hard cap
- **THEN** the boundary SHALL be reported as a continuation cut

_Tier: unit-pure — `test_segmentation.py`._

#### Scenario: A long pause is a sentence break

- **WHEN** a chunk is emitted because the silence following it reached the sentence-break threshold and the chunk held enough voiced audio
- **THEN** the boundary SHALL be reported as a sentence-length pause

_Tier: unit-pure — `test_segmentation.py`._

#### Scenario: A short qualifying pause is a continuation

- **WHEN** a chunk is emitted at a pause that satisfies `pause_ms` but falls below the sentence-break threshold
- **THEN** the boundary SHALL be reported as a continuation cut

_Tier: unit-pure — `test_segmentation.py`._

#### Scenario: The final flush is a sentence break

- **WHEN** the recording stops and the in-progress chunk is flushed as the tail
- **THEN** that boundary SHALL be reported as a sentence-length pause, so the last chunk keeps its final punctuation

_Tier: unit-pure — `test_segmentation.py`._

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
so that words from adjacent chunks are never concatenated.

Assembly SHALL follow the boundary reason reported by the segmenter rather than
always inserting a bare space. When a chunk was closed by a sentence-length
pause, the following chunk SHALL be joined as a new sentence: a single space,
and the previous chunk's own punctuation and the following chunk's own
capitalization both left alone. When a chunk was closed by a continuation cut,
the following chunk SHALL be joined as a continuation: the previous chunk's
trailing sentence-final period SHALL be dropped, the two SHALL be separated by a
comma and a space, and the following chunk's leading capital SHALL be lowered.

The system SHALL NOT lower a leading capital that is not an ordinary sentence
capital: an all-caps token and a token matching the configured custom vocabulary
SHALL be left as the model produced it. The system SHALL NOT drop a trailing `?`
or `!` — only a period — because a wrongly kept question mark is repairable by
eye while a wrongly dropped one is not.

This exists because each chunk is an independent model call that punctuates and
capitalizes its output as a standalone sentence. Joined with a bare space, a
sentence cut by the length ceiling reads as two: measured on a live dictation,
`...des tickets.` `Des tickets qui se baladent...` was one spoken sentence.

#### Scenario: Chunks assembled in order
- **WHEN** multiple chunks are emitted during one recording
- **THEN** their recognized text SHALL be assembled in the order the chunks were emitted, with no two chunks' words run together

#### Scenario: A continuation boundary joins without a false sentence break
- **WHEN** a chunk closed by a continuation cut ends with `.` and the next chunk begins with a capitalized ordinary word
- **THEN** the assembled text SHALL carry a comma and a space between them, and the second chunk's first letter SHALL be lower case

_Tier: unit-pure — join rule tested without the model._

#### Scenario: A sentence boundary is left intact
- **WHEN** a chunk closed by a sentence-length pause ends with `.` and the next chunk begins with a capital
- **THEN** the assembled text SHALL keep both, separated by a single space

_Tier: unit-pure._

#### Scenario: A proper noun is not lowered at a continuation boundary
- **WHEN** the chunk following a continuation cut begins with an all-caps token or with a configured custom-vocabulary term
- **THEN** that token SHALL be left exactly as the model produced it

_Tier: unit-pure._

#### Scenario: Question and exclamation marks survive a continuation boundary
- **WHEN** a chunk closed by a continuation cut ends with `?` or `!`
- **THEN** that mark SHALL be kept and the join SHALL fall back to a single space

_Tier: unit-pure._

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

### Requirement: Type-while-speaking check reflects effective state
The "Type while speaking" menu item SHALL be checked only when live typing is
effectively active, i.e. `type_while_speaking` AND `streaming_enabled` are both
true (live typing needs streaming chunks). Enabling it from the menu SHALL also
set `streaming_enabled` to true.

#### Scenario: Streaming disabled shows the item unchecked
- **WHEN** `type_while_speaking` is true and `streaming_enabled` is false
- **THEN** the "Type while speaking" item SHALL be unchecked

#### Scenario: Enabling repairs streaming
- **WHEN** the user clicks the unchecked "Type while speaking" item
- **THEN** both `type_while_speaking` and `streaming_enabled` SHALL be set to true

### Requirement: A leftover streaming_enabled=false is repaired once
Config migration to version 3 SHALL set `streaming_enabled` to true when the
on-disk config is older than version 3, has `type_while_speaking` true and
`streaming_enabled` false, keeping the previous file as `config.json.v<n>.bak`.
A `streaming_enabled: false` written after that migration SHALL be left alone.

#### Scenario: Stale flag from an older build
- **WHEN** Whispy starts on a version-2 config with `type_while_speaking: true` and `streaming_enabled: false`
- **THEN** `config.json` SHALL contain `streaming_enabled: true` and `config.json.v2.bak` the previous file

#### Scenario: Diagnostics value set by hand
- **WHEN** a version-3 config has `streaming_enabled: false`
- **THEN** the value SHALL be kept

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
chunk is transcribed, while recording continues, in chunk emission order.

Because typing is append-only — text already delivered cannot be taken back —
the system SHALL withhold a chunk's trailing sentence-final period until the
*next* boundary reveals whether it was real, and SHALL deliver the separator
with the following chunk. A chunk typed after an earlier chunk of the same
recording produced text SHALL therefore be prefixed with the separator its
boundary reason calls for: a single space after a sentence-length pause, or `, `
after a continuation cut, with its leading capital lowered under the same
exceptions as the assembly rule. The first typed chunk SHALL NOT be prefixed.
The final chunk of a recording SHALL be delivered with its trailing period
restored, since no further boundary follows.

A chunk that yields no text SHALL type nothing and SHALL NOT affect the spacing
or the withheld punctuation of later chunks. When the recording stops, the tail
chunk SHALL be typed the same way and the system SHALL NOT inject the assembled
text a second time. The decision to type live SHALL be taken once per recording,
at recording start, and the system SHALL wait for the trigger key to be
physically released before each injection, as it does for the stop-time
injection.

#### Scenario: Chunk text appears before the recording stops
- **WHEN** the trigger mode is toggle, `type_while_speaking` is true, and a chunk is transcribed to non-empty text while recording is still active
- **THEN** the system SHALL inject that text immediately, without waiting for the recording to stop

#### Scenario: Adjacent chunks are separated by one space
- **WHEN** two consecutive chunks of one recording both yield text and the first was closed by a sentence-length pause
- **THEN** the second SHALL be injected with exactly one leading space and the first with none

#### Scenario: A live-typed continuation does not show a false sentence break
- **WHEN** a chunk closed by a continuation cut is typed live and the next chunk yields text
- **THEN** the first chunk SHALL have been typed without its trailing period, and the second SHALL be injected with a leading `, ` and a lowered first letter

_Tier: unit-mocked — `test_engine.py` (injector calls recorded)._

#### Scenario: Empty chunk does not add a space
- **WHEN** a chunk yields no text and the following chunk yields text
- **THEN** the following chunk's separator SHALL depend only on the last boundary that produced typed text

#### Scenario: Stop types the tail and nothing else
- **WHEN** the recording stops after chunks were typed live and the tail chunk yields text
- **THEN** the tail text SHALL be injected once (with its separator and its final period) and the previously typed text SHALL NOT be injected again

#### Scenario: A withheld period is restored at the end of a recording
- **WHEN** the last chunk of a recording is typed and its own text ended with a period
- **THEN** the injected text SHALL end with that period

_Tier: unit-mocked — `test_engine.py`._

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

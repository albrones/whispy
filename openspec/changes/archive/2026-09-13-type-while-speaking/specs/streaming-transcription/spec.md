## MODIFIED Requirements

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

#### Scenario: Pause triggers a chunk
- **WHEN** the input level stays below the silence threshold for at least `pause_ms` after speech was detected
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

#### Scenario: A lone short word is emitted once the speaker has clearly stopped
- **WHEN** a chunk holds less than `min_speech_s` of voiced audio and the silence after it reaches about 2 s
- **THEN** the system SHALL emit that chunk on its own rather than hold it for a next utterance

#### Scenario: A short word followed by more speech still rides along
- **WHEN** a chunk holds less than `min_speech_s` of voiced audio and speech resumes within 2 s
- **THEN** the system SHALL NOT emit a boundary at that pause, and the short word SHALL be carried into the chunk with the following speech

#### Scenario: Pure silence emits nothing
- **WHEN** a span of audio between two emitted chunks contains no detected speech
- **THEN** the system SHALL NOT emit a chunk for that span

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

## ADDED Requirements

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

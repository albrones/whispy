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
`min_chunk_s`, `max_chunk_s`, `vad_aggressiveness`) SHALL be validated against
`DEFAULT_CONFIG` and SHALL be added with defaults by config migration so existing
configs keep working.

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
`pause_ms`, OR when the current chunk's audio reaches `max_chunk_s`, whichever
occurs first. The system SHALL NOT emit a chunk that never contained speech.

#### Scenario: Pause triggers a chunk
- **WHEN** the input level stays below the silence threshold for at least `pause_ms` after speech was detected
- **THEN** the system SHALL emit the accumulated speech as a chunk and begin a new (empty) chunk

#### Scenario: Run-on speech is force-flushed at max length
- **WHEN** the current chunk reaches `max_chunk_s` of audio without any qualifying pause
- **THEN** the system SHALL emit the chunk anyway so streaming continues to make progress

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
Chunks transcribed during recording SHALL be buffered and the assembled text
SHALL be injected once on trigger release — synthetic keystrokes SHALL NOT fire
mid-recording (which disrupts focus in full-screen apps). Streaming SHALL be
enabled by default.

#### Scenario: No mid-recording injection
- **WHEN** several chunks are recognized during recording
- **THEN** the system SHALL NOT inject any text until trigger release

#### Scenario: Assembled text typed once on release
- **WHEN** the trigger is released after one or more chunks were recognized
- **THEN** the system SHALL inject the chunks' assembled text exactly once

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
config API), it SHALL re-wire the audio segmentation and start or stop the chunk
worker to match.

#### Scenario: Enabling at runtime starts the worker
- **WHEN** `streaming_enabled` flips to true while the engine is running
- **THEN** the engine SHALL re-wire the audio engine for streaming and start the chunk worker

#### Scenario: Disabling at runtime stops the worker
- **WHEN** `streaming_enabled` flips to false while the engine is running
- **THEN** the engine SHALL stop the chunk worker and use the whole-recording path on the next recording

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

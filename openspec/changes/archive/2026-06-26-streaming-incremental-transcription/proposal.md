## Why

Today transcription is record-then-transcribe: nothing happens until the trigger
key is released, and then the **entire** recording is transcribed in one block.
Transcription time scales with audio length, so a long dictation produces a long
post-release wait (measured RTF ≈ 0.15 on the default `small` model → ~9 s of
wait after 60 s of speech) and the whole text lands as one paste. The wait is
inherent to the design, not a tuning problem.

Whisper transcribes ~7× faster than real time on `small` int8, so we can
transcribe **while the user is still speaking** instead of after. Streaming the
audio in silence-bounded chunks moves that work off the post-release critical
path (last-chunk-only wait → ~1–2 s) and surfaces text incrementally as it is
recognized.

## What Changes

- Capture buffers live PCM and runs an **energy-based silence detector** on the
  frames already producing the waveform level, emitting a chunk boundary when
  speech is followed by a pause (`pause_ms`) **or** when a chunk reaches a
  maximum length (`max_chunk_s`) — the latter bounds latency for run-on speech
  with no pauses.
- A **chunk pipeline** transcribes each emitted chunk and injects its text
  incrementally (append-only, with inter-chunk spacing), in FIFO order, **while
  recording continues**. On trigger release the final tail chunk is flushed.
- **FSM-1**: chunk transcription runs outside the state machine; `RECORDING`
  stays the single owner of the recording lifecycle. `is_transcribing` continues
  to denote only the final tail flush, so existing UI/status consumers are
  unaffected.
- The existing short-clip / hallucination guards (`min_recording_duration`,
  VAD filter, `temperature=0`, credit stripping) apply **per chunk**. Chunks
  stay independent (`condition_on_previous_text=False` retained) — the previous
  chunk's text is **not** fed back as context, preserving the existing
  anti-snowball-hallucination stance.
- New config keys (all defaulted, behaviour unchanged when streaming is off):
  `streaming_enabled`, `pause_ms`, `min_chunk_s`, `max_chunk_s`,
  `vad_aggressiveness`, `streaming_inject_mode`. When `streaming_enabled` is
  false, the legacy record-then-transcribe path is used verbatim.
- Segmentation uses **WebRTC VAD** (`webrtcvad-wheels`) for gain-independent
  pause detection (energy fallback if absent). Injection timing is configurable:
  `on_release` (default — assemble chunks transcribed during recording, type once
  on release; no focus disruption) or `live` (type each chunk as recognized).

## Capabilities

### New Capabilities
- `streaming-transcription`: live silence/length-bounded segmentation of the
  capture stream, an ordered chunk-transcription pipeline, and incremental
  append-only injection of recognized text while recording continues.

### Modified Capabilities
- `audio-capture`: capture additionally buffers live PCM and exposes
  energy-based silence/length segmentation that emits chunk boundaries during
  recording, in addition to the existing single-file capture path.
- `core-engine`: the single-shot transcription worker becomes an ordered chunk
  consumer that can transcribe and inject during `RECORDING` (FSM-1); the
  trigger-release path flushes the final tail chunk rather than transcribing the
  whole recording.

## Impact

- Code: `src/whispy/core/audio.py` (PCM buffering + segmentation), `core/engine.py`
  (chunk queue + ordered injection + FSM-1 wiring), `core/config.py` (new keys +
  validation/migration), `core/state_machine.py` (confirm `RECORDING` stays sole
  owner; no composite state needed).
- UI: a "Streaming transcription" toggle in the menu-bar Settings section
  (mirrors the clipboard toggle); applied live via `update_config`. The status
  chain is unaffected — it checks `is_recording` before `is_transcribing`, and
  the waveform is gated on recording start/stop only.
- Dependencies: `webrtcvad-wheels` (binary-wheel WebRTC VAD fork; no
  pkg_resources/setuptools runtime dep). The segmenter falls back to an energy
  gate when it is absent.
- Risk: `large-v3` (RTF approaching 1.0 under concurrent capture) could let the
  chunk queue grow; bounded by `max_chunk_s` and surfaced, not silently dropped.
- Backward compatible: `streaming_enabled` defaults preserve current behaviour;
  the legacy path remains intact.

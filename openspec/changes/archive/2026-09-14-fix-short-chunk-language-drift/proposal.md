## Why

Dictating in French, part of the transcript comes back in English. Measured, the
cause is not language detection and not a missing language setting — it is where
streaming cuts the audio.

`SpeechSegmenter.feed` decides a chunk boundary with:

```python
(self._silence_s >= self._pause_s and self._buffered_s >= self._min_chunk_s)
```

`_buffered_s` counts **total** buffered seconds, silence included. The same
condition already requires `_silence_s >= pause_s` (0.6 s), so `_buffered_s` is
always at least 0.6 s by the time it is compared against `min_chunk_s` (0.4 s).
**The term can never bind.** The guard meant to stop over-short chunks measures
the wrong quantity, and a single short word followed by a pause becomes a chunk
of its own — one model call, with nothing around it.

Isolated like that, the multilingual transducer resolves the word into another
language. Measured with `scripts/asr-bench/probe_chunk_language.py`, 5-6
realizations per case, through the production `AudioEngine.transcribe` gates:

| clip | total | voiced | result |
| --- | --- | --- | --- |
| `bref`, isolated | 0.51 s | 0.51 s | `Dress.` 6/6 |
| `oui`, isolated, as the segmenter emits it | 1.11 s | 0.39 s | `We` 5/5 |
| the same speech inside the whole dictation | 19.45 s | — | correct, every word |

`probe_chunk_merge.py` then confirms context is what fixes it, and how little is
needed — prepending preceding speech to the failing chunk:

| prepended | total | voiced | result |
| --- | --- | --- | --- |
| 0.0 s | 1.11 s | **0.39 s** | `We` 5/5 ✗ |
| 0.5 s | 1.61 s | **0.72 s** | `Oui.` 5/5 ✓ |
| 1.0 s / 2.0 s / 3.4 s | — | 1.17–3.27 s | correct 5/5 ✓ |

Total duration is not the discriminator: 1.11 s fails and 1.61 s succeeds. Voiced
duration is, and the two regimes separate cleanly at 0.39 s against 0.72 s.

## What Changes

- The segmenter accumulates **voiced** seconds for the current chunk and requires
  a minimum of them before a pause may close it. A chunk carrying too little
  speech is simply not emitted: it keeps buffering, so the short word rides along
  with its neighbour. Not emitting *is* the merge — the audio is already in the
  caller's buffer.
- The dead `min_chunk_s` term is removed from the boundary rule, and the
  parameter is dropped from `SpeechSegmenter` rather than left in the signature
  asserting a guard it never provided. `min_chunk_s` keeps its other, real
  meaning: the engine's per-chunk discard duration.
- A new `min_speech_s` config key (default **0.7**, between the two measured
  regimes) with runtime re-wiring, like the other streaming parameters.
- `max_chunk_s` still force-flushes, so a chunk cannot grow without bound, and
  `flush_tail()` is untouched, so a dictation that is entirely one short word is
  still emitted at stop.

## Capabilities

### New Capabilities
<!-- none: this corrects an existing boundary rule -->

### Modified Capabilities

- `streaming-transcription`: chunk emission gains a voiced-speech condition. The
  boundary rule stops measuring elapsed time for its minimum-size guard and
  measures speech instead; the threshold is configurable.

## Non-Goals

- **Forcing a language.** Still impossible on this backend: `onnx-asr` documents
  `language` as "only for Whisper and Canary models", and the `<|lang|>` token
  injection lives in the encoder-decoder class, never on the TDT transducer path.
  This change removes the need — the observed symptom is fixed without any
  language setting.
- **Priming the TDT decoder** with `<|fr|>` / `<|nopredict_lang|>` (hypothesis
  H2). Still unproven, still a separate spike, and no longer on the critical path.
- **Retuning `pause_ms` or `max_chunk_s`.** Both are left at their current
  defaults; this change adds one condition rather than shifting existing ones.
- **Calibrating the threshold on real speech.** 0.7 s comes from two measurement
  points on macOS `say` with one voice. The mechanism is solid (5/5 and 6/6, no
  marginal cases); the *number* is a starting point, which is precisely why it is
  a config key and not a constant. Real-voice calibration is separate work.

## Impact

- **Code**: `core/segmentation.py` (voiced accumulation, boundary rule, dropped
  parameter), `core/config.py` (new key + validation), `core/audio.py` (pass the
  new parameter through `segment_pcm` and the live segmenter), `core/engine.py`
  (include it in the runtime re-wire set).
- **Behavior**: fewer, slightly longer chunks. No user-visible latency change:
  chunk texts accumulate and are injected once when recording stops, so deferring
  a chunk moves work earlier or later within the recording, never past the stop.
- **Tests**: `test_segmentation.py` for the boundary rule (including a regression
  case that the old rule could never block), `test_config_validation.py` for the
  key, `test_engine.py` for the runtime re-wire.
- **Bench**: `scripts/asr-bench/probe_chunk_language.py` and `probe_chunk_merge.py`
  are the scripts behind the tables above and are added alongside the change.
- **Docs**: README config table (guarded by `tests/test_docs.py`),
  `docs/SPECIFICATION.md`, `CHANGELOG.md`. No website change: the site does not
  enumerate streaming parameters.
- No new dependencies. No API change.

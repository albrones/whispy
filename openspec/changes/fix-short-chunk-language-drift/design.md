## Context

Streaming cuts the recording into chunks inside the capture callback and
transcribes each one as an independent model call:

```
capture callback ──► SpeechSegmenter.feed(block) ──► boundary?
                          │                              │ yes
              _chunk_buf accumulates                     ▼
                                              AudioEngine._emit_chunk()
                                                    writes a WAV
                                                         ▼
                                              Engine._chunk_queue
                                                         ▼
                                        _transcribe_and_inject_chunk()
                                            one model.recognize() call
                                                         ▼
                                            _chunk_texts.append(...)
                                                         ▼
                                     assembled and injected ONCE on stop
```

Two properties of this pipeline matter for the fix:

- **Each chunk is transcribed with no context from any other.** That is
  deliberate and specified (`streaming-transcription`: "Chunks carry no decoder
  context between them") — the transducer carries none, so there is nothing to
  pass. Whatever a chunk contains is all the model gets.
- **Chunk texts are not injected as they arrive.** They accumulate in
  `_chunk_texts` and are typed once when recording stops, to avoid mid-recording
  focus disruption. Streaming exists so the work is already done at stop, not so
  text appears earlier.

The current boundary rule:

```python
if self._have_speech and (
    (self._silence_s >= self._pause_s and self._buffered_s >= self._min_chunk_s)
    or self._buffered_s >= self._max_chunk_s
):
```

`_buffered_s` is total elapsed buffered seconds; `_silence_s` is the current
silence run. The first branch already requires `_silence_s >= 0.6`, and
`_buffered_s >= _silence_s` always, so `_buffered_s >= 0.4` is satisfied
whenever it is evaluated. The minimum-size guard is unreachable code expressed
as a condition.

## Goals / Non-Goals

**Goals**
- A chunk never reaches the model carrying so little speech that it is resolved
  into the wrong language.
- The minimum-size guard measures the quantity that actually separates the two
  behaviors, and its threshold is tunable without a code change.
- No audio is lost, and no chunk grows without bound.
- No user-visible latency change.

**Non-Goals**
- Forcing or hinting a language; priming the decoder; retuning `pause_ms` or
  `max_chunk_s`; calibrating the threshold on real speech (see proposal
  Non-Goals).

## Decisions

### D1 — Gate on voiced seconds, not elapsed seconds

Measured, elapsed time does not separate the regimes and voiced time does:

| case | total | voiced | outcome |
| --- | --- | --- | --- |
| isolated `oui` chunk | 1.11 s | 0.39 s | wrong language, 5/5 |
| same, +0.5 s of preceding speech | 1.61 s | 0.72 s | correct, 5/5 |

A 1.11 s chunk fails and a 1.61 s chunk succeeds, so any threshold on
`_buffered_s` would have to be tuned against how much *silence* happened to be
captured — which varies with the speaker's pauses and says nothing about how
much the model has to work with. `_speech_s` is the quantity under test.

The segmenter already classifies every frame (`_is_speech`) to maintain
`_silence_s`. Accumulating `_speech_s` from the same classification is free.

### D2 — Not emitting *is* the merge

The obvious reading of "merge short chunks" is to hold an emitted chunk and
concatenate it with the next one. That would mean buffering WAV paths in the
chunk worker, concatenating audio outside the capture path, and reasoning about
ordering when a merge straddles a stop.

None of it is necessary. `AudioEngine._feed_segmenter` appends every block to
`_chunk_buf` and only writes a WAV when the segmenter says "boundary". Declining
to signal a boundary leaves the audio exactly where it already is, and the short
word is carried into the next chunk by construction. The fix is one condition,
not a merging stage.

### D3 — The latency cost is near zero, and the architecture is why

Deferring a chunk delays *transcription work*, not text. Because `_chunk_texts`
are injected once at stop, a chunk transcribed later still lands before the user
sees anything, as long as it lands before the stop — which it does, since the
next boundary or `max_chunk_s` will flush it.

The one case where a short chunk waits until stop is when it is the last thing
said. That is already how the tail behaves today (`flush_tail`), so it is not a
regression.

### D4 — `max_chunk_s` and `flush_tail` are the two escape hatches, unchanged

Withholding a boundary must not be able to strand audio:

- Run-on or fragmented speech still force-flushes at `max_chunk_s` (12 s), so a
  chunk cannot grow indefinitely while waiting for enough voiced audio.
- `flush_tail()` returns on `_have_speech`, not on the new threshold, so a
  dictation consisting entirely of one short word is still emitted at stop. The
  threshold suppresses *intermediate* boundaries only; it never discards.

Both are load-bearing and both are deliberately left alone.

### D5 — The dead parameter is removed, not left in place

`min_chunk_s` stays a real config key: the engine passes it as the per-chunk
`min_recording_duration`, which does discard sub-threshold chunks. But
`SpeechSegmenter` will no longer accept it, because it never used it for
anything reachable. Leaving it in the signature would keep asserting a guard the
class does not provide — the exact misreading that hid this bug.

### D6 — The threshold is configuration, not a constant

0.7 s sits between the two measured regimes (0.39 s fails, 0.72 s passes). But
both points come from macOS `say`, one voice, one word. The *mechanism* is
solid — 5/5 and 6/6, nothing marginal — while the *number* is provisional.

A real microphone, a different speaker, or a noisier room will move where VAD
counts a frame as voiced. Shipping this as a constant would mean a code change
to recalibrate; shipping it as `min_speech_s` means the same probe scripts can
re-derive it and a user can adjust it.

## Risks / Trade-offs

- **A pathological input holds a chunk to `max_chunk_s`.** Someone speaking in
  isolated monosyllables with long pauses accumulates 12 s before flushing, so
  more work lands near the stop. Bounded, and the failure mode it replaces
  (wrong-language text injected into the user's document) is worse.
- **`max_chunk_s` can still deliver a low-speech chunk.** Withholding a boundary
  does not stop the clock: a chunk holding one short word followed by ~11.6 s of
  *unbroken* silence force-flushes at `max_chunk_s` and reaches the model with
  0.39 s voiced, which clears the per-chunk `MIN_SPEECH_DURATION_S` (0.20) gate —
  exactly the failing case. Accepted, and D4 stands: today *every* short word
  followed by a pause does this, so the fix is strictly better, and closing the
  remaining hole would mean either discarding audio (the spec forbids it) or
  making chunk length unbounded. Toggle mode makes long mid-recording silences
  somewhat more likely, not likely.
- **The threshold is TTS-derived.** Named in the proposal's Non-Goals and
  mitigated by D6. If real speech shows 0.7 s is too aggressive, the fix is a
  config value, not a release.
- **VAD absence changes the measurement.** With `webrtcvad` missing the segmenter
  falls back to an energy gate, so `_speech_s` becomes energy-derived and the
  threshold means something slightly different. This is the pre-existing fallback
  contract (the spec already allows it); the new condition degrades with it
  rather than failing closed.

## Verified after the fix

`probe_chunk_language.py` re-run through the same corpus and the same production
gates. Pass B (the engine's own `SpeechSegmenter` replayed over the dictation,
i.e. what the daemon does) now emits **5 chunks, every one correct French**:

```
chunk 0   3.78s  'Bonjour tout le monde, je vais vous expliquer le problème.'
chunk 1   5.82s  'Donc, il faut que je vérifie le rapport avant la réunion de demain.'
chunk 2   3.39s  'En fait, oui.'
chunk 3   4.42s  'Je pense que la transcription fonctionne plutôt bien maintenant.'
chunk 4   2.04s  'Voilà.'
```

Chunk 2 is the evidence: the short `oui` is carried into its neighbour rather
than emitted alone. Pass C, which transcribes each phrase in isolation and so
bypasses segmentation, still returns `"We're going to be able to do it"` for that
same `oui` phrase — the model is unchanged; what changed is that the segmenter no
longer hands it over on its own.

`probe_chunk_merge.py` re-run reproduces its original table unchanged (0.0 s
prepended → wrong 5/5, 0.5 s → correct 5/5), as expected: it feeds clips straight
to `AudioEngine.transcribe` and measures the model, not the boundary rule. It
remains the calibration instrument for `min_speech_s`, not a regression test.

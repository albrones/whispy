## Context

See proposal.md — Why. The pipeline this builds on:

```
capture callback -> SpeechSegmenter.feed() -> boundary -> chunk WAV
                                                            |
                                              Engine._chunk_queue (FIFO)
                                                            |
                                          _transcribe_and_inject_chunk()
                                             model.recognize -> clean_text
                                                            |
                                          _chunk_texts.append(cleaned)      <- today: only this
                                                            |
                              STOP -> drain queue -> " ".join -> _deliver()  <- typed once
```

Facts that shape the design:

- **The chunk worker is already a single ordered thread**, and the FSM already
  allows injection during `RECORDING` (spec `core-engine`: "transcribe and
  inject them while the state machine remains in RECORDING"). Nothing in the
  state machine has to move.
- **`inject()` is fire-and-forget**: each call spawns a thread running the
  subprocess steps. Two calls a second apart can interleave keystrokes. This is
  latent today (one inject per dictation) and becomes live with one inject per
  chunk.
- **The trigger key state matters.** In hold mode the key is down for the whole
  recording. In toggle mode `_fn_pressed` is set on the press and cleared by the
  release a few hundred milliseconds later, and `_wait_trigger_released()` spins
  on it before every injection.
- **Two stop paths consume `_chunk_texts`**: the normal stop types the assembled
  text; the recording-limit stop copies it to the clipboard (`_deliver_to_clipboard`)
  because the focused field may be long gone.
- Measured chunk cadence (daemon log, real dictation): chunks of 2.6–12 s,
  transcribed in well under a second each on Parakeet.

## Goals / Non-Goals

**Goals:**
- Text visible about one second after each pause in toggle mode, in order, with
  correct inter-chunk spacing, and no duplicate at stop.
- Hold mode byte-for-byte unchanged.
- Ordering of injections guaranteed by the injector, for every caller, on both
  platforms.
- `_chunk_texts`, `last_transcription`, the limit-stop clipboard copy, and the
  API `/status` payload keep their meaning.

**Non-Goals:**
- Any FSM change. `is_transcribing` still denotes only the stop-time tail flush.
- Sentence-final-punctuation gating ("logical blocks") — additive later, see
  proposal.
- Revising already-typed text (backspacing). Injection stays append-only.
- Making `inject()` synchronous or adding a `blocking` parameter to the port.

## Decisions

### D1 — Live typing is decided once per recording, from trigger mode and config

At recording start (where `_chunk_texts` is reset) the engine snapshots
`live = trigger_mode == "toggle" and config["type_while_speaking"]` into a
per-recording flag. The chunk worker and the stop path both read that flag,
never the live config.

Why a snapshot: a config flip mid-recording must not leave half the chunks typed
and the other half accumulated *and then* typed again at stop. The spec scenario
"Live typing toggled at runtime" pins this.

Why gate on trigger mode rather than expose the choice: in hold mode the key is
held during typing; the Right Option trigger turns every character into its
Option-layer glyph. That is physics, not preference. `type_while_speaking` only
means something in toggle mode, so the menu row is shown regardless but is
inert in hold mode (documented in the row's tooltip-free world by the README).

### D2 — The chunk worker types *and* still appends

In live mode `_transcribe_and_inject_chunk` calls `_wait_trigger_released()`
then `_text_injector.inject(prefix + cleaned)`, and still appends `cleaned` to
`_chunk_texts` exactly as today. The stop path then:

- normal stop, live cycle: drains the queue (so the tail chunk is typed by the
  worker), consumes `_chunk_texts` for `last_transcription`, and **skips**
  `_deliver()`;
- limit stop (`_deliver_to_clipboard`), live cycle: drains, then `copy_only()`
  the full assembled text — so the clipboard holds the whole dictation, not just
  the untyped tail, and the "copied to the clipboard" notification stays true;
- any stop, non-live cycle: unchanged.

Alternative considered — stop appending in live mode and make the stop path a
pure no-op: smaller, but breaks the limit-stop copy and `last_transcription`,
and the `_chunk_any_text` success-sound logic would need its own path. Keeping
the accumulation makes live typing purely additive.

### D3 — Spacing is a per-recording "typed anything yet" flag

`prefix = " " if self._live_typed_any else ""`, set to true after a non-empty
chunk is typed, reset with `_chunk_texts` at recording start and on
`_force_recover`. Mirrors `" ".join(chunk_texts)`: empty chunks contribute
nothing and do not change spacing. Parakeet does not force-capitalize chunk
starts (log: `"... permettre de"` / `"pour vocation de ..."`), so no
punctuation repair is needed at the join.

### D4 — Ordering lives inside the injector: one FIFO worker per adapter

Both adapters replace `threading.Thread(target=_run).start()` with
`self._jobs.put(_run)`, consumed by one lazily started daemon thread. `inject()`
and `copy_only()` stay non-blocking; delivery order equals call order; a failing
job is classified exactly as today and the worker moves on.

Alternatives considered:

- **`blocking=True` on the port** (June's fix). Couples chunk transcription to
  typing time (the worker cannot recognize chunk N+1 while N is being typed),
  leaks a scheduling concern into the `TextInjector` protocol, and only protects
  callers who remember to pass it. It was reverted once already.
- **A lock around `_run`**. Serializes but does not order: thread start order is
  not guaranteed, so B can take the lock before A. Not good enough for text.
- **Serialize in the engine**. Would have to be re-done for every caller
  (`run_transcription`, the stop path, the chunk worker); the adapter is the one
  place all of them meet.

Typing throughput is the only thing the queue can hide: if System Events types
slower than the user speaks, text lags but never reorders or interleaves.
Measured cadence (one chunk every 3–12 s, chunk text ≤ ~200 characters) leaves
ample margin.

### D5 — No FSM change; the FSM may reach IDLE while the last keystrokes land

With injection asynchronous (D4), the stop path's drain wait covers chunk
*transcription*, not typing. The FSM can return to `IDLE` and the success sound
can play while the tail's keystrokes are still in flight. Accepted: it is
cosmetic, it is bounded by the tail's length, and the alternative (waiting on
the injection queue inside the FSM worker) reintroduces the June coupling.
`# ponytail:` comment at the site.

### D6 — Config, menu, docs follow the existing streaming-key pattern

`type_while_speaking: True` in `DEFAULT_CONFIG`, bool validation with warning +
default fallback like `streaming_enabled`, included in the `streaming_keys`
re-wire set (harmless: `_apply_streaming_config` re-reads config; the snapshot
in D1 is what makes it take effect on the next recording). Menu row "Type while
speaking" built like "Toggle mode" (`menu_theme.toggle_title`, trailing check),
refreshed in the same place. Website: menu mockup row + the "Text lands as you
release the key" card gains the toggle-mode sentence; README config table;
`docs/SPECIFICATION.md` data-flow paragraph; `CHANGELOG.md`.

### D7 — Past `max_chunk_s`, cut on the next short gap, not the next frame

Added after the first live drive. Two 12 s force-flushes landed mid-word:
`"...quel est le problème actuel mais" / "Mais si je lui dis..."` (both halves
of one "mais" transcribed), and `"...ou en mode..." → None → None` (the
half-word onset of the next chunk and its neighbour came back empty — a lost
utterance). With text typed at stop these were rare and blurred into the
block; typed live, they are word losses and duplicates on screen.

Rule: once `_buffered_s >= max_chunk_s`, cut at the first `SOFT_FLUSH_GAP_S`
(0.2 s) of VAD silence — a between-word-groups breath, which continuous speech
offers every few seconds — and unconditionally at `max_chunk_s * HARD_MAX_FACTOR`
(1.5, so 18 s) for speech with no gap at all. Both are module constants, not
config: there is nothing for a user to tune here, and `max_chunk_s` keeps its
meaning as the length past which the segmenter starts looking for a cut.
WebRTC VAD carries ~4 frames of hangover after speech, so the effective gap is
~320 ms of physical silence.

This also covers the "blip clock": a single VAD-positive frame during a silence
opens a chunk and starts the 12 s clock; if the speaker resumes at second 11 the
old rule cut at second 12, in the middle of the new utterance. Now the cut waits
for the next gap in that utterance.

Alternatives: cutting on the *last* VAD speech→silence transition before 12 s
(needs a rewind of the caller's buffer — the segmenter would stop being a pure
"cut here" signal); a second config key for the hard cap (nothing to tune).

### D8 — A model call that returns nothing is logged

`transcribe()` had two silent `None` paths: `model.recognize` returning empty
text, and an exception printed to stderr — which the bundled app does not
route anywhere (`~/.whispy-error.log` did not exist on the test machine). The
live drive's lost words were only attributable by elimination (no gate line).
Both paths now log: `"Model returned no text for a %.2fs clip"` at INFO, and
`logger.exception` for the error. Observability only; no behaviour change.

### D9 — The near-silence gate measures the loudest window, not the clip mean

Second live drive: the user said one word ("test") and nothing else. The
segmenter held it (below `min_speech_s`, D2 of `fix-short-chunk-language-drift`),
the soft cut flushed it 10 s later inside its own silence, and the RMS gate
measured the whole clip: 0.00496, under 0.005 by 1%. Discarded. Two more
"near-silent" discards in the same session were the same shape.

The mean scales a word by `sqrt(voiced / total)` — the gate was measuring how
long the user stayed quiet afterwards, not how loud they spoke. `_get_peak_rms`
takes the highest RMS over any 0.5 s window (`PEAK_RMS_WINDOW_S`): for one word
that *is* the word; for a near-silent clip there is no loud window, so the
threshold keeps its calibration (noise floor ≤ 0.00065 vs 0.005). `_get_audio_rms`
stays for the fixture margin checks. Same pattern as the `min_chunk_s` fix:
the guard measured the wrong quantity.

Alternative considered: RMS over VAD-voiced frames only. Also correct, but it
couples the gate to `webrtcvad`'s availability (energy fallback would change the
metric) and the peak window is one line of numpy.

### D10 — A lone word is emitted after `LONE_WORD_PAUSE_S` of silence

D9 keeps the word; it still appears 12 s late, because `min_speech_s` withholds
the pause boundary until more speech arrives. That rule exists for a short word
*inside* a dictation. When nothing follows for `LONE_WORD_PAUSE_S` (2.0 s) there
is no neighbour to ride with, so the segmenter emits the word alone. Trade-off,
accepted with the user: that word reaches the model without context and can
come back in the wrong language ("oui" → "We", measured). The alternative is
the word appearing 12 s late or, in hold mode, only at release. Constant, not
config: 2 s is well past any within-sentence pause and the behaviour is not
something to tune.

### D11 — The clip is trimmed to its voiced span before the model

Third live drive, with D9/D10 in place: the lone "test" cleared every gate and
the log finally said why it vanished — `Model returned no text` on 7 of 9
clips of 1.9 to 16.7 s. Parakeet was being handed one word inside seconds of
silence, and silence is not neutral to it. Measured with
`scripts/asr-bench/probe_lone_word.py` (test / oui / bonjour × 6 `say` voices ×
full and 0.15 volume):

| trailing silence | raw clip | trimmed to voiced span |
| --- | --- | --- |
| 0.6 s | 12/15 | 10–11/15 |
| 2 s | 9–11/15 | 10/15 |
| 5 s | 4–6/15 | 10–12/15 |
| 10 s | 3–5/15 | 10/15 |

The residual misses are the known wrong-language cases on "oui". A lone word
always arrives with silence attached: `LONE_WORD_PAUSE_S` of it by construction,
or the whole soft-cut window. So `transcribe()` now cuts the clip to its
outermost VAD-speech frames plus `TRIM_MARGIN_S` (0.3 s) on each side and hands
the model that copy; internal silences are kept, the copy is deleted after the
call, and the caller's file is untouched. The VAD pass already existed for the
speech gate — `speech_span_s` returns the span alongside the voiced total, one
pass instead of two. Trimming is skipped when it would save less than
`TRIM_MIN_GAIN_S` or when the span is unmeasurable (fail open, as every gate).

Alternative considered: handing the model a numpy slice instead of a file.
`onnx-asr`'s `recognize` accepts arrays, but the whole pipeline and every seam
(`/transcribe-file`, the bench scripts) is path-based; a temp copy keeps one
contract.

## Risks / Trade-offs

- **Focus change mid-dictation scatters text** → same class as today, wider
  window. Documented in README next to the setting; `type_while_speaking=false`
  is the opt-out. No behavioural guard (would need focused-app tracking).
- **Wrong-language chunk typed at the pause** → equally irreversible at stop
  today; `min_speech_s` already covers the measured cause. The remaining hole
  (`max_chunk_s` force-flush of a near-silent chunk) is unchanged.
- **Stopping press lands mid-typing** → the toggle stop press briefly holds the
  trigger while keystrokes may be in flight; the existing check-then-inject gap
  (`_wait_trigger_released` docstring) is now hit more often. Mitigation: the
  wait runs before each chunk, so only keystrokes already handed to
  `osascript` are exposed — a sub-second window per chunk. Closing it fully
  needs modifier-clearing CGEvent injection; out of scope, noted.
- **Clipboard mode per chunk** → snapshot / `pbcopy` / `Cmd+V` / restore every
  few seconds. Works, but a copy the user makes *during* dictation can be
  overwritten by the restore of the previous chunk. Accepted for v1: clipboard
  mode is off by default and the user here types via keystrokes; documented.
- **Typing lags speech** (slow System Events, very long chunks) → queue grows,
  order preserved, everything lands; bounded by `max_chunk_s`. Observable via
  `[inject]` log lines.
- **Push-to-talk users see no change** → intended; README states the setting
  applies to toggle mode. The user has asked for parity; that needs an injector
  that posts keystrokes with modifier flags cleared (CGEvent), which a code
  comment records as previously dropped for a self-signed app. Separate spike,
  not this change.
- **A lone word after 2 s of silence may be typed in the wrong language** →
  the measured failure of `fix-short-chunk-language-drift` reappears for this
  one case; it is the price of the word appearing at all, and the user chose
  it. Words followed by more speech within 2 s still ride along as before.
- **Trimming cuts a quiet onset the VAD missed** → the 0.3 s margin covers
  VAD's few frames of lag; a whispered first syllable under VAD's energy floor
  was already lost to the speech gate before this change.
- **Soft cut waits up to 6 s on gap-free speech** → text past 12 s lags until a
  gap or the 18 s cap. Bounded; a word boundary is worth more than 6 s of
  latency on a chunk that long.

## Migration Plan

- Ship `type_while_speaking` default **true**. Config migration adds the key;
  toggle-mode users get live typing on next launch, hold-mode users see nothing.
- Rollback: menu row or `type_while_speaking: false` restores type-once-at-stop.
  No code revert needed. The injector FIFO stays either way (strictly safer).

# Transcription Quality & Memory

Two questions: does Whispy produce irrelevant transcriptions, and can a "memory"
system make it better the more it is used?

> **Rewritten for the Parakeet backend.** The original version of this document
> catalogued defences against Whisper's failure modes and planned a memory
> system built on decoder prompting. Both premises are gone: the model that
> hallucinated on silence has been replaced, and the transducer that replaced it
> has no prompt channel to bias. What follows describes what actually runs.

## Part 1 — Irrelevant transcription

Most of the old safeguard list existed because Whisper invented text on
near-silent audio and looped on short chunks. Parakeet is a Token-and-Duration
Transducer: it emits tokens tied to encoder frames rather than decoding freely,
so it produces no training-corpus artifacts and cannot run away into repetition.

But it is **not** silent on silence. This was discovered by running the
real-model tier, after an earlier draft of this document claimed otherwise on
the strength of a single 1.0-second fixture:

| input | RMS | output |
| --- | --- | --- |
| pure digital silence, 0.6 / 1.0 / 1.5 s | ≤0.000015 | `Yeah.` |
| pure digital silence, 2.0 s | 0.0 | `Thank you.` |
| quiet-room white noise, 0.6 / 1.0 / 2.0 s | ~0.00065 | `Okay.` / `Mm-hmm.` / `No.` |
| real speech (fr / en fixtures) | ≥0.147 | correct transcription |

Note the failure is non-monotonic in duration, and note the third row: a real
microphone never reaches digital zero, so this is the live case rather than a
synthetic-test curiosity. Left unguarded, releasing the key on a pause would
type `Okay.` into whatever you had focused.

What ships:

| Safeguard | Where | What it prevents |
| --------- | ----- | ---------------- |
| **RMS silence gate** | `audio.py` — `SILENCE_RMS_THRESHOLD = 0.005`, checked before the model | The fillers above. Every observed false positive measured ≤0.00065 and every real utterance ≥0.147, a 220× gap, so the threshold is robust rather than fiddly. Fails **open**: an unmeasurable clip is transcribed, not dropped. |
| **Voiced-duration speech gate** | `audio.py` — `MIN_SPEECH_DURATION_S = 0.20`, `_carries_speech` via `segmentation.speech_duration_s` | Non-speech that is *loud enough to clear the RMS gate*: a noisy room, a fan, mains hum, all 0.010–0.035 RMS. Those reached the model and 3 of 100 realizations came back as a filler; with the gate, 0 of 100. Reuses the `webrtcvad` the streaming segmenter already needs. Fails **open** like the RMS gate. |
| **Short-clip discard** | `audio.py` — `duration < min_recording_duration` (default 0.3 s) returns `None` | Spends no decoder pass on a misclick. Purely an optimisation now; suppressing non-speech is the RMS gate's job. |
| **Empty output is not injected** | `AudioEngine.transcribe` returns `None` for empty/whitespace output; `engine.run_transcription` injects only truthy text | Whatever the model returns, nothing empty reaches the injector. |
| **Failure isolation** | `except Exception → return None` around the model call | An onnxruntime error surfaces as "no text", never as a crash in the trigger path. |

**Why a duration and not a ratio.** The natural reading of "is this speech?" is
*what fraction of the clip was voiced*, and that metric is wrong here. Holding
the trigger while you think is normal use, and one word inside a 10-second hold
is ~6% voiced — indistinguishable from steady noise at ~5%. The same two clips in
absolute terms are 0.66 s and 0.09 s. Measured across 125 noise realizations
above the RMS gate the worst carried 0.12 s of voiced frames, against 0.33 s for
the shortest real one-word dictation ("non", 0.40 s of audio), so 0.20 s sits
between them with room on both sides. The ratio metric, on the same corpus,
ordered the two populations by 1.4× on one draw and not at all on another.

**Where the speech gate stops working.** `webrtcvad` has an energy floor, so it
only tells noise from speech while the noise is quiet. Past roughly 0.04
normalized RMS it labels steady noise 100% voiced and the gate is inert — every
noise level from `sox vol=0.2` up reads as fully voiced. That band is the model's
problem, and the model handled it: an empty string for all 15 such clips. A real
fix for loud rooms needs a speech-vs-noise classifier, not a higher threshold.

**Why energy and not a phrase list.** The obvious fix is to blocklist `Yeah.`,
`Okay.`, `Mm-hmm.`, `No.`. It is the wrong fix: `Okay.` and `No.` are legitimate
one-word dictations, so filtering by text would delete speech the user actually
produced — exactly the liability that made Whisper's list worth deleting. Energy
never looks at what was said.

What was **deleted** with the backend, and why keeping it would have been worse:

- `strip_whisper_credit` and the watermark prefix list — nothing emits those
  phrases now, so the code only retained the ability to silently rewrite text a
  user genuinely said.
- The hallucination phrase blocklist (`la communauté d'Amara.org`, subtitle
  credits, …) — those specific phrases are gone with their emitter, and the
  replacement failure mode is handled by energy instead of by text (above).
- `vad_filter`, `condition_on_previous_text=False`, `temperature=0` — Whisper
  decoder controls with no counterpart. Chunk independence is now a property of
  the architecture rather than a flag the caller must remember to pass.
- The degenerate-output scrubber (long same-character runs, box-drawing tokens).

Three bugs disappeared with the backend rather than being fixed:

- **Forced-language mistranslation.** With `language="fr"` — a supported config
  value — Whisper transcribed English speech *into French*: "the test is done"
  came back as "le test est fait". Parakeet detects language per utterance and
  handles switching inside a single clip.
- **Silent truncation of long audio.** In the non-streaming path a 22-second
  recording transcribed to a single sentence, dropping ~90% of the audio with no
  error. Parakeet returns the whole thing.

- **Hallucination on room noise.** This one was measured *after* the swap, on
  100 noise realizations per backend over identical files: `faster-whisper small`
  answered 52–100% of them with text (`you`, `Thank you.`, depending on noise
  type), Parakeet 3%. The remaining 3% is what the speech gate above closes.

### The measured comparison

Numbers from `scripts/asr-bench/` on an Apple M1 Pro — that directory holds the
scripts, so this is re-runnable rather than folklore.

| | faster-whisper `small` int8 | parakeet int8 |
| --- | --- | --- |
| WER, pre-migration defaults (forced `en`) | 17.2% | **5.2%** |
| WER, language detection on | 3.4% | **5.2%** |
| Latency, 0.5 s clip | 0.575 s | **0.035 s** |
| Latency, 2.2 s clip | 0.615 s | **0.075 s** |
| 16.6 s clip | 1 sentence of 8 (~87% dropped) | **all 8** |
| Noise answered with text | 52–100% | **3%**, 0% with the speech gate |

The WER rows are the honest shape of it: Parakeet beats the *configuration that
shipped*, and Whisper with language detection left on is a hair better on clean
TTS phrases. What Parakeet wins on is not per-phrase accuracy — it is the failure
modes, and a latency proportional to real audio instead of flat at ~0.6 s.

### Two limits that remain

- **A clip cut mid-word** produces a plausible wrong word rather than a truncated
  one: 0.5 s of "hello" becomes `Help me.` rather than `Hell`. Not a regression
  (Whisper returned garbage too) and not fixable at this layer — the two
  candidate levers both fail. Token logprobs, exposed via `with_timestamps()`,
  score the invented `Hello` at −0.040 mean against −0.399 for a correctly
  recognized `Oui.`, so a confidence threshold discards real dictation before it
  catches the invention. Raising `min_recording_duration` past 0.5 s would
  discard `oui` and `non`, which measure 0.49 s.
- **Loud rooms**, per the speech-gate ceiling above.

## Part 2 — Memory: custom vocabulary

The words a generic model gets wrong most often are the user's: names, product
terms, acronyms, jargon. Whispy still targets that, by a different mechanism.

### What ships

`custom_vocabulary` (a list of words, validated to a clean list of strings) is
applied **after** transcription, in `text_cleaner.clean_text`. Each output token
is compared to the configured terms two ways — by spelling and by sound — and
replaced when either matches.

```json
{ "custom_vocabulary": ["Whispy", "Parakeet", "Zenika", "OpenSpec"] }
```

Wiring: `engine.run_transcription` → `clean_text(text, vocabulary)`. The
transcription call itself receives no vocabulary argument, and a test asserts
that it never will.

### Why post-hoc, and what it costs

The transducer has no `initial_prompt` or `hotwords` channel — post-hoc
correction is the only lever available, not a preference. It is genuinely weaker:
it fixes terms the model rendered *close* to the target and leaves distant ones
alone.

Spelling alone is not enough, and this was learned from use: users reported
proper nouns and brand names surviving badly, `parakite` for `Parakeet` being the
canonical case. Against a vocabulary of {Whispy, Parakeet, OpenSpec, onnx,
Zenika}:

| token | closest term | spelling | sound | |
| --- | --- | --- | --- | --- |
| `wispy` | Whispy | 0.909 | 0.857 | corrected on spelling |
| `pense` | OpenSpec | 0.769 | 0.667 | **false match** — rejected on sound |
| `parakite` | Parakeet | 0.750 | **1.000** | corrected on sound |
| `paraquet` | Parakeet | 0.750 | **1.000** | corrected on sound |
| `onyx` | onnx | 0.750 | **1.000** | corrected on sound |
| `on` | onnx | 0.667 | — | excluded by length |

On spelling, a false match outscores true ones — the classes are not separable.
On sound they are, which is why `phonetic_key` exists: strip accents, fold
interchangeable consonants (c/k/q, s/z/x, v/f), drop vowels after the first
letter, collapse doubles. Fifteen lines of stdlib, no Metaphone dependency.

The bars are `VOCABULARY_CUTOFF = 0.80`, `PHONETIC_CUTOFF = 0.90`,
`MIN_TOKEN_LENGTH = 4`. The phonetic bar is deliberately the stricter one,
because sound is the looser signal. False corrections over
`/usr/share/dict/words` (234 335 entries of 4+ letters), eight-term vocabulary:

| rule | false positives |
| --- | --- |
| spelling ≥0.80 alone | 31 (0.013%) |
| sound ≥0.80 alone | 1763 (0.752%) — would mangle "appreciate" |
| sound ≥0.90 alone | 112 (0.048%) |
| **spelling ≥0.80 or sound ≥0.90** | **139 (0.059%)** |

4.5× the false-correction rate of spelling alone, in exchange for the cases the
feature exists to fix. What still slips through is a misrendering that is neither
spelt nor pronounced close to the target — "parasite" for "Parakeet" — and that
is the ceiling, not a bug to tune away.

That direction is not arbitrary. The previous mechanism failed the other way —
`initial_prompt` leaked vocabulary terms verbatim into transcriptions ("… sur la
boitée. Orange principal, `int8, OpenSpec` Il faudra penser à …"), and the
adaptive-correction feature built on the same channel was deleted for a
self-reinforcing version of it (issue #8). A vocabulary feature that can invent
text is worse than one that misses.

### Where it could go

- **Editable vocabulary in the UI** — a "Vocabulary…" menu item instead of
  hand-editing JSON. `POST /config` already accepts `custom_vocabulary`.
- **Learning from corrections** — the genuine habit-learning step, needing a
  signal Whispy does not capture: what the user changed after injection. Tracked
  in issue #8, and blocked on alignment that does not mislearn from ordinary
  continued dictation.
- **Multi-word terms** — currently skipped, since spanning tokens makes false
  rewrites likelier. This is the biggest remaining gap: `faster-whisper`,
  `onnx runtime` and `int8` are all multi-word, and they are exactly the terms
  that survive worst in technical dictation.
- **A larger model is not the answer** — measured, not assumed. `canary-1b-v2`
  (1B params, same 25 languages) scored 62% of expected technical terms against
  Parakeet's 72%, at 2.7× the time and 1.75× the memory, and it translates to
  English unless handed an explicit language.

Principles that survive unchanged: everything stays on-device, and the feature
is framed as "better by habit", never as a guarantee.

## Part 3 — Streaming / incremental transcription

The legacy path was record-then-transcribe: nothing happened until the trigger
key was released, then the whole recording was transcribed in one block.

Streaming segments the live capture on **silence** (and a **max length**) and
transcribes + injects each chunk while recording continues, in order.

This matters far more with Parakeet than it did with Whisper, because the two
have opposite cost curves. Whisper padded every input to a 30-second window, so a
0.5-second chunk cost the same ~0.5 s as a 2-second one — chunking bought
responsiveness but paid a fixed toll per chunk. Parakeet's cost is proportional
to real audio. Measured on an Apple M1 Pro:

| chunk | faster-whisper `small` int8 | parakeet int8, CPU |
| --- | --- | --- |
| 0.5 s | 0.529 s | **0.037 s** |
| 1.0 s | 0.562 s | **0.046 s** |
| 2.2 s | 0.628 s | **0.075 s** |

Over a 6–8 second dictation split into 1.5-second chunks, end-to-end goes from
2.5–7.9 s to 0.26–0.36 s. Streaming assembly is now bounded by how fast the user
speaks, not by the decoder.

Each chunk keeps the short-clip discard guard, and chunks stay independent — by
construction now, with no conditioning flag to pass. Segmentation uses **WebRTC
VAD** (`webrtcvad-wheels`) to find pauses: a gain-independent voice detector, so
it does not mis-cut mid-word the way a raw energy threshold does. If the
dependency is missing, the segmenter degrades to a simple energy gate.

One caveat, unchanged by the backend swap: cutting on a fixed interval rather
than on silence degrades output for any model — a chunk boundary mid-word is
mid-word regardless of architecture. The VAD thresholds (`pause_ms`,
`min_chunk_s`, `max_chunk_s`) have not been retuned against the new latency
budget, and there is now far more headroom to spend on shorter, cleaner chunks.

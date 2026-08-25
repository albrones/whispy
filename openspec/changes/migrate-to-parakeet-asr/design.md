## Context

`faster-whisper` is reached through exactly two places:

- `src/whispy/core/engine.py:83` — `_load_model()`, the only `WhisperModel(...)`
  construction, plus `load_model_async()` and its retry/failure reporting.
- `src/whispy/core/audio.py:508` — the only `model.transcribe(...)` call, inside
  `AudioEngine.transcribe()` (`audio.py:460`).

Everything above them — the FSM, the chunk queue, VAD segmentation, ordered
assembly, injection, the tray/menu bar, the HTTP API — is backend-agnostic. Four
engine call sites (`engine.py:517`, `:584`, `:678`, `:730`) pass the same
Whisper-shaped keyword arguments into `AudioEngine.transcribe`; they collapse
once those arguments disappear.

### Measurements

Recorded on an M1 Pro against `tests/fixtures/audio/*` and five longer
synthesized sentences (FR technical, franglais, hesitations, EN technical),
each clip run whole and re-run split into 1.5 s chunks to emulate the streaming
path. Best of three passes.

| | faster-whisper `small` int8 | parakeet-tdt-0.6b-v3 int8, CPU EP |
|---|---|---|
| chunk 0.5 s | 0.529 s | **0.037 s** |
| chunk 1.0 s | 0.562 s | **0.046 s** |
| clip 2.2 s | 0.628 s | **0.075 s** |
| clip 2.68 s | 0.621 s | **0.087 s** |
| clip 22 s | 0.628 s (output truncated to one sentence) | 0.601 s (complete) |
| 6–8 s dictation, 1.5 s chunks | 2.5–7.9 s | **0.26–0.36 s** |
| warm load | 0.69 s | 1.10 s |
| RSS after load / peak | 839 MB / 923 MB | 1188 MB / **1366 MB** |
| disk | 466 MB | 639 MB |

Execution provider matters more than expected. onnxruntime's default provider
list on macOS enrols CoreML:

| | default (CoreML enrolled) | `["CPUExecutionProvider"]` |
|---|---|---|
| warm load | 5.01 s | 1.10 s |
| chunk 2.2 s | 0.145 s | 0.075 s |
| chunk 0.5 s | 0.081 s | 0.037 s |
| peak RSS | 6070 MB | 1366 MB |

Correctness observations that drive several decisions below:

- Silence (1 s) → Parakeet returns `""`. **This does not generalize** — see
  decision 7: on other durations and on a realistic quiet-room noise floor it
  returns short fillers instead, which is why an RMS gate ships.
- `language="fr"` on English audio → Whisper outputs French. Parakeet, given no
  language at all, transcribes FR→EN code-switching correctly inside one clip.
- 1.5 s chunks → Whisper produces degenerate repetition (`"grand"` ×100,
  `"de la vidéo"` ×60, `"Macintosh"` ×55). Never observed with Parakeet.
- `initial_prompt` built from `custom_vocabulary` leaks verbatim into Whisper's
  output. It also *suppresses* some repetition loops, which is why the loops are
  worse in the no-vocabulary run — the prompt was accidentally load-bearing.
- fp32 weights (2.3 GB) were measured and rejected: quality gain over int8 is
  marginal, cost is 3.6× the download.

## Goals / Non-Goals

**Goals:**

- One backend, no runtime engine switch, no dual dependency tree.
- Per-chunk latency low enough that streaming assembly is bounded by the user's
  speech, not by the decoder.
- No configuration key that does not change behaviour.
- Every claim in README, FEATURE_MATRIX, and the website matches what runs, with
  the CC-BY-4.0 attribution the model licence requires.
- The two latent Whisper bugs found while measuring (`language="auto"` raising
  `ValueError`, long-audio truncation) are gone rather than carried over.

**Non-Goals:**

- No CoreML / ANE execution provider, and no `parakeet-mlx` or CoreML backend.
  Measured worse here on both latency and memory; the CPU path clears the
  latency budget by an order of magnitude, so there is no headroom to buy.
- No Whisper fallback for the 74 languages Parakeet lacks. `SUPPORTED_LANGUAGES`
  has only ever offered `fr` and `en`.
- No change to VAD segmentation thresholds. Chunking at 1.5 s degraded both
  engines; tuning `pause_ms`/`min_chunk_s`/`max_chunk_s` against the new latency
  budget is separate work.
- No switch from WAV paths to in-memory numpy arrays in the chunk path.
  `onnx_asr.recognize()` accepts both; keeping paths keeps the diff small.
- No re-implementation of decoder-level vocabulary biasing.

## Decisions

1. **Hard swap, not a backend abstraction.** Alternative: a `core/asr/` package
   with `WhisperBackend`/`ParakeetBackend` and an `engine` config key. Rejected:
   an interface with two implementations is only worth it if both ship, and
   shipping both means two dependency trees, two CI matrices, a bigger `.app`,
   and a config key whose wrong value silently reintroduces the repetition loops.
   The measurements do not show a workload where Whisper wins. Rollback is
   `git revert`, not a config toggle.

2. **`onnx-asr` + int8 ONNX weights, not NeMo.** `nemo_toolkit[asr]` pulls
   PyTorch (~2.5 GB) for a menu-bar daemon. `onnx-asr` (MIT, 0.12.0, requires
   Python ≥3.10 — matches the CI floor) depends only on `numpy` and
   `onnxruntime`, both already bundled. Weights come from
   `istupakov/parakeet-tdt-0.6b-v3-onnx`, an ONNX conversion of the NVIDIA
   model. Verified: `onnxruntime-1.29.0-cp314-cp314-macosx_14_0_arm64.whl`
   exists, so the Python 3.14 `.app` bundle is unaffected.

3. **Pin `providers=["CPUExecutionProvider"]` explicitly.** Not a default worth
   inheriting: onnxruntime's macOS default enrols CoreML, which costs 4.5× the
   memory and 2× the latency here. The pin is a deliberate, commented choice,
   not an omission. It is settled on the M1 Pro numbers and is not conditional
   on re-measurement: the CPU provider already clears the latency budget by an
   order of magnitude, so a faster provider would buy headroom nobody is asking
   for. Anyone revisiting this needs a workload that the CPU path fails, not a
   newer machine.

4. **Delete `model_size`, `beam_size`, `best_of`, `language`,
   `auto_detect_min_duration`.** Alternative: keep them as accepted-but-ignored
   keys for compatibility. Rejected — a setting that does nothing is worse than
   a missing one, and `MODEL_PRESETS` drives a visible menu whose every entry
   would become a lie. Existing config files are already validated against
   `DEFAULT_CONFIG`, so stale keys drop silently on the next save; no migration
   code is needed. `min_recording_duration` stays: it still saves a decoder pass
   on a misclick.

5. **`language` goes away rather than becoming "auto".** This is the decision
   most likely to read as a regression, so it is stated plainly: forcing a
   language was measurably *harmful* (English audio transcribed into French),
   and Parakeet's per-utterance detection handled everything in the fixture set,
   including code-switching mid-clip. If per-user language pinning is ever
   wanted back, it needs a different mechanism than a decoder argument.

6. **`custom_vocabulary` becomes post-hoc near-miss correction.** Alternative A:
   drop the feature and file a tracking issue, as adaptive correction was
   handled. Alternative B: keep decoder biasing — impossible, TDT has no
   `initial_prompt`/`hotwords` channel. Chosen: `difflib.get_close_matches`
   against the configured terms, per output token, above a similarity cutoff, in
   `text_cleaner.py`. Stdlib, no new dependency. Crucially it cannot leak
   vocabulary into output the way `initial_prompt` did.

   **Extended after user testing.** Character similarity alone missed the cases
   users actually hit: `parakite` for `Parakeet` scores 0.750, under the cutoff,
   and lowering the cutoff to catch it also catches `pense` → `OpenSpec`
   (0.769). The classes are not separable on spelling. They are separable on
   *sound*: reduced to a consonant skeleton, `parakite` and `parakeet` are
   identical (1.000) while `pense` and `openspec` fall to 0.667. The shipped rule
   is therefore a union — character ≥0.80 **or** phonetic ≥0.90 — with the
   phonetic bar set high because phonetics alone is far too loose.

   Measured over `/usr/share/dict/words` (234 335 entries ≥4 letters) against an
   eight-term vocabulary:

   | rule | false positives |
   |---|---|
   | char ≥0.80 alone | 31 (0.013%) |
   | phon ≥0.80 alone | 1763 (0.752%) — rejected, mangles "appreciate" |
   | phon ≥0.90 alone | 112 (0.048%) |
   | **char ≥0.80 OR phon ≥0.90** | **139 (0.059%)** |

   4.5× the false-positive rate of spelling alone, in exchange for the phonetic
   misrenderings that are the whole point of the feature. Distant misses
   ("parasite" for "Parakeet") stay uncorrected: that is the honest ceiling.
   `phonetic_key` is ~15 lines of stdlib, no Metaphone dependency.

7. **Delete Whisper-specific text cleaning, and replace it with an energy gate.**
   `strip_whisper_credit` and the hallucination phrase list exist because
   Whisper emits training-corpus artifacts on silence. Those specific phrases
   are gone with their emitter.

   **Corrected during implementation.** This decision originally claimed
   Parakeet "returns an empty string for silence", generalized from a single
   1.0 s fixture. Running the real-model tier disproved it: Parakeet does not
   hallucinate the way Whisper did — no corpus artifacts, no repetition loops —
   but it invents short conversational fillers on near-silence, and the failure
   is non-monotonic in duration:

   | input | RMS | output |
   |---|---|---|
   | pure digital silence, 0.6 s / 1.0 s / 1.5 s | ≤0.000015 | `Yeah.` |
   | pure digital silence, 2.0 s | 0.0 | `Thank you.` |
   | quiet-room white noise, 0.6 / 1.0 / 2.0 s | ~0.00065 | `Okay.` / `Mm-hmm.` / `No.` |
   | real speech (fr / en fixtures) | ≥0.147 | correct transcription |

   The quiet-noise row is the one that matters: a real microphone never reaches
   digital zero, so this is the live case, not a synthetic-test artifact.

   The replacement is an **RMS gate before the model**
   (`SILENCE_RMS_THRESHOLD = 0.005` in `audio.py`), not a Parakeet-flavoured
   phrase list. Two reasons. The measured separation is 220× — every false
   positive sits at or below 0.00065, every real utterance at or above 0.147 —
   so a threshold is robust rather than fiddly. And a blocklist would have to
   contain `Okay.` and `No.`, which are legitimate one-word dictations: filtering
   by text would delete real speech, which is precisely the liability this
   decision cites against Whisper's list. Energy never looks at what was said.

   `clean_text` keeps whitespace normalization and gains the vocabulary
   correction from decision 6.

8. **`WHISPER_MODEL` is removed, not renamed.** There is one model. Keeping an
   env var that selects among one option is dead surface in `install.sh`,
   `scripts/bootstrap.sh`, the `ci-cd-pipeline` spec, and
   `tests/test_install_scripts.py`.

9. **Ship a `NOTICE` file.** The model is CC-BY-4.0 and Whispy is GPL-3.0. The
   weights are downloaded at runtime and never redistributed, so there is no
   licence conflict, but attribution is owed. `NOTICE` is the conventional place
   and keeps `LICENSE` untouched.

10. **Fix the two latent bugs by deletion, and say so in CHANGELOG.**
    `audio.py`'s `language: str = "auto"` default raises `ValueError` in
    faster-whisper (unreachable today only because config validation restricts
    the value to `fr`/`en`); the long-audio truncation comes from
    `condition_on_previous_text=False` without VAD. Both parameters disappear
    with the backend. They are worth naming in the changelog because users who
    hit the truncation never saw an error.

11. **One model size, and it is the small one.** Asked whether a larger model
    would handle proper nouns and anglicisms better, `nemo-canary-1b-v2` (1B
    params, same 25 languages, also available through `onnx-asr`) was measured
    against the jargon fixtures, scoring how many expected technical terms
    survived:

    | | terms | time | peak RSS | disk |
    |---|---|---|---|---|
    | **parakeet-tdt-0.6b-v3** | **23/32 (72%)** | 0.89 s | 1307 MB | 639 MB |
    | canary-1b-v2, auto | 19/32 (59%) | 2.29 s | 2290 MB | 982 MB |
    | canary-1b-v2, `language` forced | 20/32 (62%) | 2.37 s | 2290 MB | 982 MB |

    The larger model is worse on this workload while costing 2.7× the time and
    1.75× the memory. It also **translates by default**: Canary is an ASR+AST
    model, so without an explicit `language` every French clip came back in
    English — reintroducing the very setting decision 5 removes, with a silent
    mistranslation as its default. Rejected.

    Side result worth recording: passing `language` to **Parakeet** changes the
    output not at all — byte-identical across all four clips. Decision 5 is
    therefore confirmed on Parakeet itself, not merely inherited from the Whisper
    measurement.

## Risks / Trade-offs

- [+440 MB resident for a background daemon] → accepted, and the measurement is
  in this document so a future change can argue against it with numbers. The
  CoreML default would have made it +5 GB; pinning the CPU provider is what
  makes the trade acceptable. Not revisited on newer hardware: a faster machine
  changes the latency, not the resident footprint.
- [639 MB download on first run after upgrade, with no visible tie to the old
  466 MB cache] → the release notes and README SHALL state the new download and
  name `~/.cache/huggingface/hub/models--Systran--faster-whisper-*` as safe to
  delete manually. Automating deletion of a shared cache directory is out of
  scope and was already rejected in `macos-install`.
- [Unusual proper nouns recognized worse than with `initial_prompt`] → real and
  acknowledged in decision 6. Mitigated by near-miss correction on both spelling
  and sound, which covers the reported cases; distant misrenderings remain
  uncorrected and the docs say so rather than papering over it.
- [The phonetic path raises false corrections 4.5×] → measured, not estimated:
  139 of 234 335 dictionary words (0.059%). Accepted because the alternative is a
  feature that misses the cases users actually report. The phonetic bar (0.90) is
  deliberately far above the character bar (0.80) because phonetics is the looser
  signal — at 0.80 it would corrupt 1763 words.
- [25 languages instead of 99] → `SUPPORTED_LANGUAGES` only ever exposed `fr`
  and `en`, both covered. A user dictating outside the 25 loses everything, so
  README SHALL list the supported set rather than implying universality.
- [`istupakov/parakeet-tdt-0.6b-v3-onnx` is a third-party conversion of an
  NVIDIA model] → single point of supply for the weights. `onnx_asr` also
  accepts a local model directory, so a vendored or self-converted copy is a
  viable fallback if that repo disappears; note it in the loader comment.
- [The silence gate is a fixed threshold on a machine-dependent quantity] →
  the 220× measured margin makes 0.005 safe by a wide factor, and the gate fails
  *open*: an unmeasurable clip is transcribed rather than dropped. A user
  dictating at genuinely inaudible levels would be silently ignored, which is
  the same outcome they would get from the model anyway.
- [The `.app` bundle loses four packages at once] → `py2app`'s static scan
  already misses lazily imported natives, which is why packages are listed
  verbatim. After editing `setup_app.py`, `make app` and a real launch of the
  built bundle are required, not just a green test suite.
- [Global `rumps`/AppKit mocks in `conftest.py` hide launch-time breakage] →
  known repository hazard; the macOS real-seam tier is the check that matters
  for the loader change.

## Migration Plan

Branch `feat/parakeet-asr-backend` off `main`, after `remove-adaptive-correction`
has landed — it deletes `corrections.py` and the `hotwords` channel, which
neighbours every `custom_vocabulary` site this change rewrites. Doing it in the
other order guarantees conflicts in `engine.py` and `text_cleaner.py`.

One PR, ordered as in tasks.md: backend first with the old tests still asserting
Whisper behaviour (they fail, which proves coverage), then config and UI, then
tests, then docs and site, then packaging. `make app` and a real launch of
`dist/Whispy.app` gate the merge alongside the suite. Version goes to `2.0.0`.

Rollback is a revert of the PR. Users who reverted keep a 639 MB orphaned cache;
harmless, and named in the release notes.

## Open Questions

- Resolved: **`difflib` cutoff = 0.80, plus a 4-character minimum token
  length.** Measurement showed the classes are not separable by ratio alone —
  the false match "pense"~"OpenSpec" (0.769) outscores the true match
  "paraquet"~"Parakeet" (0.750) — so the tie is broken toward never rewriting
  what the user said, and distant misrenderings stay uncorrected by design. The
  short-token rule kills "on"~"onnx" (0.667) structurally. Recorded in the
  `text-cleaning` spec.
- Not blocking: whether to also expose Parakeet's word-level timestamps. Nothing
  in Whispy consumes them today.

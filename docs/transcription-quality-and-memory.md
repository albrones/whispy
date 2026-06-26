# Transcription Quality & Memory

Two questions: does Whispy produce irrelevant transcriptions, and can a "memory"
system make it better the more it is used? This documents the existing
safeguards and lays out a phased plan — Phase 1 of which ships alongside this
document.

## Part 1 — Irrelevant transcription: confirmation

Whispy already has layered defenses against irrelevant / hallucinated output.
All live in `src/whispy/core/audio.py` (`AudioEngine.transcribe`) and
`src/whispy/core/text_cleaner.py`:

| Safeguard | Where | What it prevents |
| --------- | ----- | ---------------- |
| **Short-clip discard** | `audio.py` — `duration < min_recording_duration` (default 0.3s) returns `None` | A quick Fn misclick records near-silence, on which Whisper hallucinates training-corpus artifacts (e.g. "…la communauté d'Amara.org"). Discarded before anything is injected. |
| **VAD filter** | `model.transcribe(..., vad_filter=True)` | Voice-activity detection drops non-speech segments. |
| **No cross-segment priming** | `condition_on_previous_text=False` | Prevents the decoder from snowballing a hallucination across segments. |
| **Greedy, deterministic decode** | `temperature=0` | Avoids the temperature-fallback path that invents text on low-confidence audio. |
| **Credit / hallucination stripping** | `strip_whisper_credit` (in `transcribe`) + `clean_text` (in `engine.run_transcription`) | Removes known watermark/credit phrases (Amara.org, subtitle-author credits, FR/EN variants) from the output. |
| **Empty-after-clean is not injected** | `engine.run_transcription` only injects when `clean_text(...)` is truthy | A transcription that is *only* a credit/hallucination cleans to `""` and is never typed into the active field. |

These were verified by reading the code and are covered by tests in
`tests/test_audio.py`, `tests/test_text_cleaning.py`, and the e2e suite.

**Conclusion:** the irrelevant-transcription risk is actively mitigated. The
remaining gap is not *bad* output but *imperfect* output on the user's own
vocabulary — which is what the memory system targets. (One related robustness
fix — the worker no longer wedges on empty transcriptions — landed in the
`code-health-audit-and-fixes` change; see `docs/code-audit.md`.)

## Part 2 — Memory system: make it better by habit

The words a generic model gets wrong most often are the user's: names,
project/product terms, acronyms, domain jargon. A "memory" system biases the
decoder toward those, and over time can learn them automatically.

### Phase 1 — Custom vocabulary (shipped with this document)

- New config key `custom_vocabulary` (a list of words/phrases), validated to a
  clean list of strings.
- When non-empty, the engine joins the terms into a Whisper `initial_prompt`,
  which conditions the decoder toward them. Empty/absent → no prompt, behavior
  unchanged.
- Wiring: `engine.run_transcription` → `AudioEngine.transcribe(initial_prompt=...)`
  → `model.transcribe(initial_prompt=...)`.
- Tests: `tests/test_config_validation.py::TestCustomVocabulary`,
  `tests/test_audio.py` (initial_prompt pass-through),
  `tests/test_engine.py::TestCustomVocabularyWiring`.

This is the highest-leverage, lowest-risk step: user-curated, immediate effect,
zero impact when unused.

**Try it:** add terms to `~/.config/whispy/config.json`:

```json
{ "custom_vocabulary": ["Whispy", "ctranslate2", "Zenika", "OpenSpec"] }
```

### Phase 2 — Editable vocabulary in the UI

- A "Vocabulary…" menu-bar item / small editor to add and remove terms without
  hand-editing JSON. Persists through the same `update_config` path.
- A POST `/config` route already accepts `custom_vocabulary` (it is now a known
  key), so external tooling can manage it too.

### Phase 3 — Learn from corrections (the actual "memory")

The genuine habit-learning step. Requires a signal Whispy does not capture
today: what the user *changed* after text was injected.

- **Capture:** after injection, observe the user's edits to the dictated text
  (e.g. an optional clipboard/selection diff, or an explicit "fix last
  transcription" affordance). This is privacy-sensitive and must be local-only
  and opt-in.
- **Learn:** when a correction recurs (model says X, user fixes to Y, N times),
  promote Y into `custom_vocabulary`, and optionally record an X→Y
  post-transcription substitution applied in `clean_text`.
- **Store:** a local `memory.json` next to the config (per-user, `0600`),
  holding term frequencies and confirmed substitutions.
- **Decay/cap:** bound the vocabulary size and decay stale terms so the prompt
  stays short (long prompts consume decoder context).

### Phase 4 — Context-aware vocabulary (optional)

- Per-frontmost-app or per-language vocabularies (coding terms in the editor,
  contact names in chat). Selected by the active app at transcription time.
- Possible upgrade from `initial_prompt` to faster-whisper `hotwords` once its
  cross-backend behavior is validated.

### Risks / principles

- **Local & private:** all memory stays on-device; correction-learning is
  opt-in. Whispy's value proposition is local processing — the memory system
  must not weaken it.
- **Bias, not guarantee:** `initial_prompt`/`hotwords` nudge the decoder; they
  do not force output. Frame the feature as "better by habit", not perfect.
- **Prompt budget:** keep the effective vocabulary short; cap and decay in
  Phase 3.

## Part 3 — Streaming / incremental transcription

The legacy path was record-then-transcribe: nothing happened until the trigger
key was released, then the **whole** recording was transcribed in one block.
Transcription time scales with audio length (measured RTF ≈ 0.15 on `small`
int8), so long dictations produced a long post-release wait (~9 s after 60 s of
speech) and the text landed as one paste.

Streaming segments the live capture on **silence** (and a **max length**) and
transcribes + injects each chunk while recording continues, in order. The
post-release wait shrinks to the last chunk only (~1–2 s) and text appears
incrementally. Each chunk keeps the same per-chunk guards as the whole-recording
path (short-clip discard, VAD filter, `temperature=0`, credit stripping) and
chunks stay independent (`condition_on_previous_text=False`, no previous-text
feedback) — preserving the anti-snowball-hallucination stance.

Segmentation uses **WebRTC VAD** (`webrtcvad-wheels`) to find pauses — a
gain-independent voice detector, so it does not mis-cut mid-word the way a raw
energy threshold does. If the dependency is missing, the segmenter degrades to a
simple energy gate.

Chunks are transcribed *during* recording but the assembled text is typed **once
on release** — so the result appears near-instantly instead of after a multi-
second whole-file pass, and synthetic keystrokes never fire mid-recording (which
stole focus from full-screen apps). Streaming is **on by default**; toggle it in
the menu (Settings → Streaming transcription).

### Config keys (in `~/.config/whispy/config.json`)

| Key | Default | Meaning |
| --- | ------- | ------- |
| `streaming_enabled` | `true` | Master switch (also in the menu). Off → legacy whole-recording path. |
| `pause_ms` | `600` | Trailing silence (ms) that closes a chunk at a natural pause. |
| `min_chunk_s` | `0.4` | Chunks shorter than this are discarded (per-chunk hallucination guard). |
| `max_chunk_s` | `12.0` | Hard cap: force-flush run-on speech with no pause so no single packet grows huge. |
| `vad_aggressiveness` | `2` | WebRTC VAD aggressiveness (0–3); higher = more eager to call audio non-speech. |

### Caveat: model speed vs. real time

Streaming keeps pace only while the model transcribes faster than real time
(RTF < 1). Measured: `small` ≈ 0.15, `medium` ≈ 0.18–0.37. **`large-v3`** can
approach RTF 1.0 under concurrent capture — the chunk queue may then lag (text is
delayed, never lost; `max_chunk_s` still bounds chunk size). Streaming is tuned
for `small`/`medium`; treat `large-v3` + streaming as best-effort.

## Status

- ✅ Part 1 confirmed and documented.
- ✅ Phase 1 (custom vocabulary) implemented and tested.
- ⏳ Phases 2–4 planned here; each warrants its own OpenSpec change.
- ✅ Part 3 (streaming) implemented and tested; **on by default** (WebRTC VAD
  segmentation, types the assembled text once on release).

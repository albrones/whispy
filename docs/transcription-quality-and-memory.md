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

## Status

- ✅ Part 1 confirmed and documented.
- ✅ Phase 1 (custom vocabulary) implemented and tested.
- ⏳ Phases 2–4 planned here; each warrants its own OpenSpec change.

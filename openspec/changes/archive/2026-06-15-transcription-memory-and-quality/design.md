## Context

Whispy transcribes with faster-whisper 1.2.1. Its `WhisperModel.transcribe`
supports both `initial_prompt` (a text prefix that conditions the decoder) and
`hotwords`. The current call (`audio.py:203`) passes neither. Hallucination on
silence is already handled (short-clip discard + credit/hallucination stripping
+ `condition_on_previous_text=False` + `temperature=0` + `vad_filter=True`).

The TODO asks to (1) confirm there are no irrelevant transcriptions and (2)
consider a "memory" system to improve quality by habit. The highest-leverage,
lowest-risk first step is a **custom vocabulary**: the words a generic model
most often misrecognizes are the user's proper nouns and jargon, and biasing the
decoder toward a user-supplied list directly addresses that.

## Goals / Non-Goals

**Goals:**
- Document the existing anti-irrelevant-transcription safeguards.
- Ship Phase 1 (custom vocabulary → `initial_prompt`) with tests.
- Write a phased plan for the larger memory system.

**Non-Goals (deferred to the plan):**
- Auto-learning from user corrections (requires capturing edits — no signal today).
- Per-app or per-context vocabularies.
- Fine-tuning / model adaptation.

## Decisions

### `initial_prompt` over `hotwords`
`initial_prompt` is the broadly-supported, well-understood lever and degrades
gracefully (a phrase the model ignores costs nothing). `hotwords` is newer and
its effect varies by backend. Phase 1 uses `initial_prompt`; the plan notes
`hotwords` as a possible enhancement. The prompt is built by joining the
vocabulary terms (e.g. `", ".join(terms)`), which is the conventional way to
seed domain terms.

### Config shape and validation
Add `custom_vocabulary: []` to `DEFAULT_CONFIG`. Validation coerces:
- non-list → `[]`
- list → keep only `str` entries, stripped, dropping empties
This keeps a malformed config from ever reaching the decoder and matches the
existing "validate-and-fall-back" pattern in `_validate_config`.

### Threading the value through
`Engine.run_transcription` reads `state.config["custom_vocabulary"]`, builds the
prompt (or `None` if empty), and passes `initial_prompt=` to
`AudioEngine.transcribe`, which forwards it to `model.transcribe`. Passing
`None` reproduces today's behavior exactly, so the empty case is a no-op.

## Risks / Trade-offs

- A very long prompt eats decoder context; mitigated by this being user-curated
  and short in practice. The plan notes a soft cap as future work.
- `initial_prompt` biases, it does not guarantee; framed as "increase good
  transcription by habit", not perfect recognition.

## Migration Plan

`custom_vocabulary` is additive with an empty default; `_migrate_config`'s
"add any missing default keys" loop back-fills it for existing configs on next
load. No breaking change.

## Open Questions

- Auto-learning from corrections needs a way to observe user edits to injected
  text — captured as a phase in the plan, not built here.

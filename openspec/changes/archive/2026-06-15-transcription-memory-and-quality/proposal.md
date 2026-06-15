## Why

Two open questions from the TODO: (1) confirm Whispy does not emit irrelevant/hallucinated transcriptions, and (2) decide whether a "memory" system could raise transcription quality by adapting to how the user habitually speaks. The anti-hallucination measures already exist but are undocumented, and there is no mechanism to bias recognition toward the user's recurring vocabulary (names, jargon, product terms) — exactly the words a generic model gets wrong most often. We want a written confirmation + plan, and a concrete, low-risk first step that delivers the "better by habit" benefit immediately.

## What Changes

- Add `docs/transcription-quality-and-memory.md`: a report that (a) confirms and documents the existing anti-irrelevant-transcription safeguards (short-clip discard, Whisper-credit/hallucination stripping, `condition_on_previous_text=False`, `temperature=0`, VAD filter), and (b) lays out a phased plan for a transcription "memory" system.
- Implement **Phase 1** of that plan — a user **custom vocabulary**:
  - Add a `custom_vocabulary` config key (a list of words/phrases).
  - When non-empty, feed it to the Whisper decoder as an `initial_prompt` so recognition is biased toward the user's habitual terms.
  - Validate the key (list of strings; bad input falls back to an empty list) and persist it like other config.
- Add unit tests for the new validation and for the transcription wiring (vocabulary present → `initial_prompt` passed; absent → not passed).

## Capabilities

### Modified Capabilities
- `core-engine`: configuration includes an optional `custom_vocabulary`; when set, the engine SHALL pass it to the transcription call as an `initial_prompt` to bias recognition toward the user's habitual vocabulary. The engine's existing anti-hallucination behavior is documented (no behavior change there).

## Impact

- `docs/transcription-quality-and-memory.md` — new report + phased plan.
- `src/whispy/core/config.py` — add `custom_vocabulary` to `DEFAULT_CONFIG` and validate it.
- `src/whispy/core/audio.py` — `transcribe()` accepts an `initial_prompt` and passes it to `model.transcribe`.
- `src/whispy/core/engine.py` — `run_transcription` builds the prompt from `custom_vocabulary` and passes it through.
- `tests/` — validation + transcription-wiring tests.

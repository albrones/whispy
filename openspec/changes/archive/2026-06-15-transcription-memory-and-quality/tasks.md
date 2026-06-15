## 1. Write the report + plan

- [x] 1.1 Create `docs/transcription-quality-and-memory.md` documenting the existing anti-irrelevant-transcription safeguards (short-clip discard, credit/hallucination stripping, condition_on_previous_text=False, temperature=0, VAD)
- [x] 1.2 Add the phased memory-system plan (Phase 1 custom vocabulary shipped here; later phases: correction-learning, per-context vocab, hotwords)

## 2. Config: custom_vocabulary

- [x] 2.1 Add `custom_vocabulary: []` to `DEFAULT_CONFIG`
- [x] 2.2 Validate it in `_validate_config`: non-list → `[]`; list → keep stripped non-empty string entries only

## 3. Wire vocabulary into transcription

- [x] 3.1 `AudioEngine.transcribe` accepts `initial_prompt: str | None = None` and passes it to `model.transcribe`
- [x] 3.2 `Engine.run_transcription` builds the prompt from `custom_vocabulary` (None if empty) and passes it through

## 4. Tests

- [x] 4.1 Test `_validate_config` coerces a non-list `custom_vocabulary` to `[]` and filters non-string entries
- [x] 4.2 Test `transcribe` passes `initial_prompt` to `model.transcribe` when given, and None when not
- [x] 4.3 Test `run_transcription` builds a prompt from a non-empty `custom_vocabulary` and passes None when empty

## 5. Verification

- [x] 5.1 Run the full test suite; confirm no regression
- [x] 5.2 `ruff check` / `ruff format --check` on changed files
- [x] 5.3 `openspec validate transcription-memory-and-quality --strict`

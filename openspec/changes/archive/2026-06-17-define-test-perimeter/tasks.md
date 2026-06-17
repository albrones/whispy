## 1. Verify new specs against existing code & tests

- [x] 1.1 Confirm each `audio-capture` scenario maps to a real behavior in `src/whispy/core/audio.py` (readiness wait, duration, discard guard, auto-detect warning, cleanup, credit strip, failure isolation)
- [x] 1.2 Confirm each `text-cleaning` hallucination scenario matches `_HALLUCINATION_PHRASES` behavior in `src/whispy/core/text_cleaner.py`
- [x] 1.3 Map every `unit-pure`/`unit-mocked` scenario in the matrix to its existing test in `tests/`; flag any tagged ✅ that has no actual assertion
- [x] 1.4 Record any mismatch (spec says X, code does Y) as a follow-up note — do NOT change code in this change

## 2. Annotate test tiers on canonical specs

- [x] 2.1 Add the four-tier vocabulary (`unit-pure` / `unit-mocked` / `macos-real` / `manual-ui`) as a short note in the relevant specs or a shared conventions location
- [x] 2.2 Tag each scenario in `core-engine`, `event-listener`, `text-injection`, `text-cleaning`, `audio-capture`, `api-interface` with its tier per the design matrix
- [x] 2.3 Mark the `macos-real` and `manual-ui` scenarios that currently pass only via mocks (event-listener, text-injection) so green is not mistaken for real-seam proof

## 3. Promote specs (apply)

- [x] 3.1 Apply the `audio-capture` ADDED requirements into `openspec/specs/audio-capture/spec.md`
- [x] 3.2 Apply the `text-cleaning` hallucination requirement into `openspec/specs/text-cleaning/spec.md` (alongside existing credit requirement)
- [x] 3.3 Run `pytest` to confirm no test regressed (this change touches no `src/` code)

## 4. Scope the follow-up work (C → B → A)

- [x] 4.1 From the matrix, list the `macos-real` rows whose logic can be extracted to `unit-pure` → seed the **C** proposal (event-tap/UI coverage)
- [x] 4.2 Define the **B** proposal scope: semantic transcription tests (real `tiny` model over FR/EN fixture `.wav`, assert cleaned output)
- [x] 4.3 Define the **A** proposal scope: single `@pytest.mark.macos` end-to-end smoke (real device → real model → real injection)
- [x] 4.4 Confirm whether step B gets its own capability (`transcription-quality`) or lives under `audio-capture`

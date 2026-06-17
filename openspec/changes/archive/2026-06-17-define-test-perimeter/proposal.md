## Why

The test suite is green (351 tests, 84% core coverage) but its perimeter is undefined: we cannot tell, from the specs, which behaviors are genuinely verified, which only pass because their macOS boundary is mocked, and which behaviors exist in code with no spec at all. Before adding more tests (event-tap/UI coverage, semantic transcription tests, a real macOS smoke test) we must first formalize *what* the app is supposed to do and *at which level each behavior can be trusted*. The spec is the test perimeter — so we complete the spec first.

This is step **D** in an agreed sequence (D → C → B → A): define the perimeter, then cover event-tap/UI (C), add semantic transcription tests (B), and finally a real end-to-end smoke test (A). The hypothesis being tested: completing the spec may be enough to scope all later test work.

## What Changes

- **New capability `audio-capture`**: formalize the behaviors already living in `core/audio.py` that have no spec home — short-recording discard (`min_recording_duration`), too-short auto-detect warning, sox recording-readiness wait, WAV duration detection, temp-file cleanup, and Whisper credit stripping at the audio layer.
- **Modified capability `text-cleaning`**: add a requirement for **hallucination-phrase stripping** (`_HALLUCINATION_PHRASES`: Amara.org, SousTitreur.com, Radio-Canada, "Merci d'avoir regardé…") — implemented and tested today, but described by no spec. The existing credit-prefix requirement stays.
- **Test-tier annotation convention**: introduce a lightweight convention to tag every scenario with the level at which it can be verified — `unit-pure`, `unit-mocked`, `macos-real`, or `manual-ui`. Captured in this change's `design.md` as the convention plus the full scenario→tier matrix; the matrix becomes the direct work-list for steps C, B, and A.
- **No application code changes. No new tests.** Writing the tests is steps C/B/A; touching `audio.py`/`text_cleaner.py` behavior is out of scope. This change only records reality and classifies it.

## Capabilities

### New Capabilities
- `audio-capture`: recording lifecycle and pre-transcription guards in `core/audio.py` — recording readiness, duration detection, short-clip discard, auto-detect warning, temp-file cleanup, and audio-layer credit stripping.

### Modified Capabilities
- `text-cleaning`: add a requirement covering removal of known Whisper hallucination phrases anywhere in the output (distinct from the existing credit-prefix stripping).

## Impact

- **Specs**: new `openspec/specs/audio-capture/spec.md`; delta to `openspec/specs/text-cleaning/spec.md`. The scenario→tier matrix in `design.md` annotates `core-engine`, `event-listener`, `text-injection`, `text-cleaning`, `audio-capture`, and `api-interface`.
- **No source impact**: `src/` and `tests/` are untouched by this change.
- **Downstream**: the tier matrix scopes the follow-up changes for C (event-tap/UI coverage), B (semantic transcription tests), and A (real macOS smoke test).

## Why

The whole suite mocks `WhisperModel`, so nothing proves that real audio in French or English actually produces the right words out. This is the gap `define-test-perimeter` isolated as "the semantic layer" — and it is the literal answer to the original question: *are the features faithful to what was asked?* This is step **B** of the D→C→B→A sequence: verify transcription quality end-to-end through the real model, not its mock.

## What Changes

- **New capability `transcription-quality`**: a real-model test layer that synthesizes speech with the macOS `say` command, converts it to the 16 kHz mono WAV the pipeline expects, runs the real `tiny` Whisper model, and asserts that expected keywords appear in the cleaned output (case-insensitive, punctuation-tolerant).
- Cover both supported languages (FR + EN) with explicit `language=` (not auto, per finding M1 — auto is unreachable through validated config).
- Cover the **custom-vocabulary** effect: transcribe a clip naming an unusual term with and without `initial_prompt`, asserting the biased term is recognized when provided.
- Cover the **short-clip discard** and **credit/hallucination cleaning** at the real-model level (a near-silent `say` clip yields no injected text).
- All tests marked `@pytest.mark.macos` and tier `macos-real`: they require `say`/`sox`, download the `tiny` model on first run, and are **excluded from default CI** (local / opt-in only).

## Capabilities

### New Capabilities
- `transcription-quality`: real-model semantic verification — synthesized FR/EN speech transcribes to the expected keywords, custom vocabulary biases recognition, and silence/credit/hallucination produces no output.

### Modified Capabilities
<!-- none — additive test layer, no behavior change -->

## Impact

- **Tests**: new `tests/test_transcription_quality.py`, marked `@pytest.mark.macos`; a fixture/helper that runs `say … -o x.aiff` then `sox x.aiff -r 16000 -c 1 x.wav`.
- **pytest config**: register/confirm the `macos` marker (already declared in `pyproject.toml`) and document how to run/skip these slow tests (e.g. `-m macos` to run, default run excludes them).
- **Dependencies**: no new Python deps. Runtime tools `say` (built-in) and `sox` (already required) used at test time. First run downloads the `tiny` model via `faster-whisper`.
- **No source impact**: `src/` unchanged.
- **Downstream**: leaves step **A** (live event tap, real audio device, real osascript injection) as the only remaining `macos-real` gap.

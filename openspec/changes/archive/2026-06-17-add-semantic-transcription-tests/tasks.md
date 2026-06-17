## 1. Audio synthesis helper

- [x] 1.1 Add a test helper that runs `say "<phrase>" -o <aiff>` then `sox <aiff> -r 16000 -c 1 <wav>`, returning the wav path (tmp-scoped, cleaned up)
- [x] 1.2 Module-level skip when `say` or `sox` is unavailable; ensure the helper raises a clear skip/fixture error rather than a cryptic failure

## 2. Real-model fixture

- [x] 2.1 Add a session-scoped fixture loading the real `tiny` model (CPU int8) via `faster-whisper`, reused across tests to avoid repeated load
- [x] 2.2 Route transcription through the real path (`AudioEngine.transcribe` / `Engine.run_transcription`) so credit-strip, duration-guard, and `initial_prompt` are exercised — not `faster_whisper` directly

## 3. Semantic tests (FR/EN)

- [x] 3.1 `tests/test_transcription_quality.py` — FR phrase → expected keywords present (`language="fr"`, case-insensitive)
- [x] 3.2 EN phrase → expected keywords present (`language="en"`)
- [x] 3.3 Custom vocabulary: unusual term recognized when supplied as `initial_prompt`
- [x] 3.4 Sub-`min_recording_duration` clip → no text returned
- [x] 3.5 Credit/hallucination phrase absent from cleaned real output

## 4. Marker gating

- [x] 4.1 Mark all tests `@pytest.mark.macos`; confirm the `macos` marker is registered in `pyproject.toml`
- [x] 4.2 Make the default `pytest` run exclude them (`addopts = -m "not macos"`) and document `pytest -m macos` to run the real layer
- [x] 4.3 Verify: default run stays green and fast (378 passing, no model download); `pytest -m macos` runs the new layer locally

## 5. Spec sync

- [x] 5.1 Apply the `transcription-quality` spec into `openspec/specs/transcription-quality/spec.md`

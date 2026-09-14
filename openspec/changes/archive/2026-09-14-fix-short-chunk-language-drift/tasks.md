## 1. Segmenter: gate boundaries on voiced speech

- [x] 1.1 Add a `_speech_s` accumulator to `SpeechSegmenter`, incremented by `_frame_s` on every frame `_is_speech` classifies as speech (reusing the existing classification, not a second pass), and reset in `reset_chunk()` alongside `_have_speech` / `_buffered_s` / `_silence_s`
- [x] 1.2 Replace the unreachable `self._buffered_s >= self._min_chunk_s` term in the pause branch of `feed()` with `self._speech_s >= self._min_speech_s`; leave the `max_chunk_s` branch and `flush_tail()` exactly as they are
- [x] 1.3 Replace the `min_chunk_s` constructor parameter with `min_speech_s: float = 0.7`; update the class docstring to explain that the guard measures *voiced* seconds because elapsed seconds cannot separate the two behaviors (cite 0.39 s wrong / 0.72 s correct), and that `min_chunk_s` remains the engine's per-chunk discard duration, a different thing
- [x] 1.4 Unit test: a chunk whose voiced audio is below the threshold does NOT emit a boundary at a qualifying pause, and the following speech ends up in the same chunk
- [x] 1.5 Unit test: a chunk with enough voiced audio emits at the pause exactly as before
- [x] 1.6 Regression test naming the bug: with the *old* rule, a pause boundary was reachable with only ~0.39 s of voiced audio — assert the new rule blocks it, so the guard cannot silently become unreachable again
- [x] 1.7 Unit test: `max_chunk_s` still force-flushes a chunk that never reaches the voiced threshold, so audio cannot be held indefinitely
- [x] 1.8 Unit test: `flush_tail()` still emits a short-but-real chunk at stop, so a dictation of one short word is not lost

## 2. Config: `min_speech_s`

- [x] 2.1 Add `"min_speech_s": 0.7` to `DEFAULT_CONFIG` with a comment stating what it gates and why the value is provisional (measured on synthesized speech; see the change's proposal for the table)
- [x] 2.2 Validate it in `_validate_config` as a non-negative number (reject bool), falling back to the default with the standard stderr line, next to the other streaming parameters
- [x] 2.3 Unit test in `test_config_validation.py`: valid values pass; a negative, a bool, a string and `None` fall back; a config file without the key loads as the default

## 3. Wiring

- [x] 3.1 Pass `min_speech_s` from config through `AudioEngine.configure_streaming` into `_seg_kwargs`, and through the `segment_pcm` replay helper, replacing the `min_chunk_s` the segmenter no longer takes — leaving `min_chunk_s` in place everywhere it feeds the engine's per-chunk `min_recording_duration`
- [x] 3.2 Add `min_speech_s` to the streaming key set in `Engine.update_config` so a change re-wires the segmenter at runtime like the other streaming parameters
- [x] 3.3 Unit test: changing `min_speech_s` at runtime re-wires the audio engine without a restart
- [x] 3.4 Grep for every remaining `SpeechSegmenter(` and `segment_pcm(` call site (source and tests) and update the ones passing `min_chunk_s`

## 4. Bench scripts

- [x] 4.1 Add `scripts/asr-bench/probe_chunk_language.py` (the three-pass whole/chunked/isolated comparison plus the short-word pass) and `probe_chunk_merge.py` (the prepend sweep) — the scripts the proposal's tables come from
- [x] 4.2 Add both to the script table in `scripts/asr-bench/README.md` with the question each answers, matching the existing rows
- [x] 4.3 Re-run `probe_chunk_merge.py` after the fix and record, in the change or the CHANGELOG, that the isolated-chunk case no longer reaches the model

## 5. Documentation

- [x] 5.1 Add a `min_speech_s` row to the README configuration table (required: `tests/test_docs.py` asserts every `DEFAULT_CONFIG` key is documented there)
- [x] 5.2 Document the key and the corrected boundary rule in `docs/SPECIFICATION.md` wherever the streaming parameters are described
- [x] 5.3 Add a `Fixed` entry to `CHANGELOG.md` in the file's existing voice: French dictation could come back partly in English because a short word followed by a pause became a chunk of its own; include the measured numbers, since the entries in this file carry their evidence
- [x] 5.4 No `website/index.html` change — the site does not enumerate streaming parameters; state this explicitly in the PR so the keep-the-website-in-sync convention is visibly considered, not forgotten

## 6. Verification

- [x] 6.1 Run `./.venv/bin/pytest` — existing and new tests green
- [x] 6.2 Run `./.venv/bin/ruff check .` and `ruff format --check .`
- [x] 6.3 Live-drive: dictate in French with a deliberate pause around a single short word ("oui", "bref", "donc") and confirm the transcript stays French. **Confirmed by the operator on 2026-09-07** on the built app.
- [x] 6.4 Live-drive: confirm a dictation consisting of one short word alone still transcribes (the `flush_tail` path). **Confirmed by the operator on 2026-09-07.**
- [x] 6.5 Note in the PR that the threshold is TTS-derived and unvalidated against real speech, so the first real-voice counter-example should retune `min_speech_s` rather than be treated as a new bug

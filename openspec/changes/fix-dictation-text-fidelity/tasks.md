## 1. Delivery path and config migration

- [x] 1.1 Flip `DEFAULT_CONFIG["copy_to_clipboard"]` to `True` and `DEFAULT_CONFIG["max_chunk_s"]` to `8.0` in `src/whispy/core/config.py`; verify `test_config_validation.py` asserts both new defaults on a no-file load.
- [x] 1.2 Bump `CONFIG_VERSION` to `2` and add the v1→v2 step in `_migrate_config`: set `copy_to_clipboard` to `True` unconditionally, and set `max_chunk_s` to the new default only when it still equals `12.0`; verify with a new `test_config_validation.py` case loading a v1 file carrying `{copy_to_clipboard: false, max_chunk_s: 12.0}` and asserting both are rewritten and `_version` becomes 2.
- [x] 1.3 Verify the migration is one-shot and respects deliberate values: a config already at `_version: 2` with `copy_to_clipboard: false` is left untouched, and a v1 config with `max_chunk_s: 20.0` keeps `20.0` — two `test_config_validation.py` cases.
- [x] 1.4 Update the existing `test_config_validation.py` case that asserted `copy_to_clipboard` defaults to `False` so it covers the explicit opt-out instead, matching the scenario of the same name in the core-engine delta.

## 2. Chunk ceiling

- [x] 2.1 Update the `max_chunk_s` comment in `config.py` to carry the measured rationale from the streaming-transcription delta (median 12.03 s for language-drifted chunks vs 7.0 s overall), so a future change to the value has to beat a number; verify by reading the constant block.
- [x] 2.2 Verify no test or fixture hardcodes `12.0` as the chunk ceiling or `18` as the hard cap: `rg -n "12\.0|max_chunk" tests/ src/` and fix any that assert the old default rather than reading it from `DEFAULT_CONFIG`.

## 3. Boundary reason in the segmenter

- [x] 3.1 Add a sentence-break threshold to `SpeechSegmenter.__init__` (default: the `pause_ms` it is constructed with) and change `feed()` to return the boundary reason — `"sentence"`, `"continuation"`, or `None` — instead of a bool; verify `test_segmentation.py` covers each of the four emission paths (long pause, short qualifying pause, `max_chunk_s` soft gap, hard cap).
- [x] 3.2 Classify the lone-word emission (`LONE_WORD_PAUSE_S`) as a sentence break and `flush_tail()` as a sentence break; verify with `test_segmentation.py` cases asserting the returned reason for each.
- [x] 3.3 Keep every existing `test_segmentation.py` assertion passing by treating the returned reason as truthy where a bool was expected; verify `./.venv/bin/pytest tests/test_segmentation.py` is green.
- [x] 3.4 Thread the reason through `AudioEngine`: the chunk sink signature gains the boundary reason alongside the WAV path, and the tail flush on `stop()` passes the sentence reason; verify with `test_audio.py` asserting the sink receives the reason for a forced cut and for a pause cut.

## 4. Continuation-aware join

- [x] 4.1 Add a pure join helper (text + previous boundary reason + `custom_vocabulary` → prefix and possibly-lowered text) next to the existing text cleaning; verify with unit tests covering: sentence boundary keeps `" "` and the capital, continuation emits `", "` and lowers the first letter, all-caps token is not lowered, a vocabulary term is not lowered, `?`/`!` fall back to `" "`.
- [x] 4.2 Strip a chunk's trailing `.` (never `?` or `!`) before delivery, and restore it on the final chunk of a recording; verify with `test_engine.py` asserting the injected strings for a three-chunk recording ending in a period.
- [x] 4.3 Use the helper in `_transcribe_and_inject_chunk` for the live-typing path, replacing the hardcoded `" " if self._live_typed_any else ""`; verify with a `test_engine.py` case recording injector calls across a continuation boundary.
- [x] 4.4 Use the same helper for the stop-time assembly of `_chunk_texts`, so the two paths cannot diverge; verify with a `test_engine.py` case running the same chunk sequence with `type_while_speaking` off and asserting the assembled text matches the live-typed concatenation.
- [x] 4.5 Verify an empty chunk does not consume or shift the pending separator: a chunk yielding no text leaves the next chunk's prefix determined by the last boundary that produced typed text (`test_engine.py`).

## 5. Empty model result is retried and reported

- [x] 5.1 In `AudioEngine.transcribe`, when the model returns empty text for a clip that was trimmed, retry once with the untrimmed original; verify with a `test_audio.py` case where the mocked model returns `""` then text, asserting two calls and the non-empty result.
- [x] 5.2 Skip the retry when the model already saw the untrimmed clip; verify with a `test_audio.py` case asserting exactly one call when trimming was a no-op.
- [x] 5.3 Replace the current INFO discard with a WARNING carrying duration, peak RMS and voiced seconds when both calls come back empty; verify with `caplog` in `test_audio.py` asserting the level and the three fields.
- [x] 5.4 Verify gate-rejected clips are unaffected — the duration, RMS and VAD discards keep their existing level and still never reach the model (`test_audio.py`).

## 6. Documentation and website

- [x] 6.1 Update `docs/SPECIFICATION.md`: the `DEFAULT_CONFIG` listing (lines ~115 and ~126), the config table rows for `copy_to_clipboard` (`False` → `True`) and `max_chunk_s` (`12.0` → `8.0`), and the `SpeechSegmenter` paragraph describing `feed(raw) → bool` and the 18 s hard cap; verify `./.venv/bin/pytest tests/test_docs.py`.
- [x] 6.2 Document in the `copy_to_clipboard` row that disabling it types the transcript key by key and is only correct on a US keyboard layout; verify the row renders in `docs/SPECIFICATION.md` and `tests/test_docs.py` passes.
- [x] 6.3 Check `website/index.html` against the new defaults — the menu mockup already renders "Copy to clipboard" as checked, so confirm it matches and update any prose stating the old default; verify `./.venv/bin/pytest tests/test_website.py`.
- [x] 6.4 Note in `docs/transcription-quality-and-memory.md` that `max_chunk_s` has now been retuned and on what measurement, replacing the standing "have not been retuned" line for that key.

## 7. Verification

- [x] 7.1 Run the full default-tier suite: `./.venv/bin/pytest` is green.
- [x] 7.2 Run `openspec validate fix-dictation-text-fidelity --type change --strict` and confirm it passes.
- [ ] 7.3 Live drive on macOS: dictate a French sentence containing `tâches`, a comma and an accented word in toggle mode with `type_while_speaking` on, and verify the field receives the characters exactly and that `~/.whispy.log` shows the chunk texts matching what was typed.
- [ ] 7.4 Live drive a run-on sentence long enough to hit the 8 s ceiling and verify the typed text carries `, ` and a lower-case continuation rather than `. ` and a capital.

## 8. Mid-word cuts and migration safety (follow-up from the first live drive)

- [x] 8.1 Add a `soft_gap_ms` key to `DEFAULT_CONFIG` (default `350`) with the measured `Régie` rationale in its comment, plus validation (a positive number; falls back to the default otherwise); verify with `test_config_validation.py` cases for the default and for a rejected value.
- [x] 8.2 Replace the `SOFT_FLUSH_GAP_S` constant in `core/segmentation.py` with a `soft_gap_ms` constructor parameter defaulting to 350, keeping the constant only as the default's source; verify `test_segmentation.py` covers a gap below the threshold NOT releasing the length cut and a gap at the threshold releasing it.
- [x] 8.3 Thread `soft_gap_ms` through `AudioEngine.configure_streaming` and `segment_pcm`, and add it to the engine's runtime re-wire set; verify with `test_audio.py` and a `test_engine.py` re-wire case.
- [x] 8.4 In `_migrate_config`, copy the existing config file to `config.json.v<previous>.bak` before `save_config`, and log at INFO the keys the migration changed; verify with a `test_config_validation.py` case asserting the backup file's contents match the pre-migration file and that the log names the changed keys.
- [x] 8.5 Verify a backup failure does not block the migration: with the copy raising `OSError`, the migrated config is still persisted and the failure is logged (`test_config_validation.py`).
- [x] 8.6 Update `docs/SPECIFICATION.md` (config table + `DEFAULT_CONFIG` listing + the `SpeechSegmenter` paragraph's 200 ms mention), the `README.md` config table, and `CHANGELOG.md`; verify `./.venv/bin/pytest tests/test_docs.py`.
- [x] 8.7 Run the full default-tier suite and `openspec validate fix-dictation-text-fidelity --type change --strict`.
- [x] 8.9 Make the migration a no-op when there is nothing to migrate: the daemon log showed `Migrated config v2 -> v2; keys changed: none` and a fresh `.v2.bak` on an ordinary launch, so every start rewrote the file and copied the already-migrated config over the backup taken at 8.4 — erasing the only pre-migration snapshot. Guarded by an equality check in `_migrate_config`; verified by `test_an_already_migrated_config_is_not_rewritten_or_re_backed_up`
- [ ] 8.8 Live drive: dictate a run-on sentence past the 8 s ceiling and confirm in `~/.whispy.log` that the chunk boundary no longer lands mid-word.

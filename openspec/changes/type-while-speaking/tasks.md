## 1. Injector ordering (both adapters)

- [x] 1.1 `hardware/injection.py`: replace the per-call `threading.Thread(target=_run).start()` in `_spawn` with a single lazily-started daemon worker consuming a `queue.Queue` of jobs; `inject()` / `copy_only()` stay non-blocking. Verify existing `tests/test_injection.py` still passes unchanged
- [x] 1.2 `platform/linux/injection.py`: same FIFO worker for `_inject_via_clipboard`, `_inject_via_keystrokes`, `copy_only`. Verify `tests/test_linux_adapters.py` still passes
- [x] 1.3 Tests: in `test_injection.py` and `test_linux_adapters.py`, mock `subprocess` so the first injection's step blocks on an event, call `inject("A")` then `inject("B")`, release, and assert every "A" step ran before any "B" step; assert `inject()` returned before the first step finished; assert a failing first job (rc=1 / timeout) does not prevent the second from running and still logs the `1002` classification

## 2. Config key

- [x] 2.1 `core/config.py`: add `type_while_speaking: True` to `DEFAULT_CONFIG` with a comment (toggle-mode only; hold mode always types at release), bool validation with warning + default fallback like `streaming_enabled`. Verify with new cases in `tests/test_config_validation.py` (missing key migrated, non-bool falls back, false preserved)
- [x] 2.2 `core/engine.py` `update_config`: add `type_while_speaking` to the `streaming_keys` set. Verify with a `test_engine.py` case that an update of that key alone calls `_apply_streaming_config` and does not stop/start the chunk worker spuriously

## 3. Engine live typing

- [x] 3.1 `core/engine.py` `_on_fsm_recording`: snapshot `self._live_typing = trigger_mode == "toggle" and config.get("type_while_speaking", True)` and reset `self._live_typed_any = False` under the same lock as `_chunk_texts`; also reset both in `_force_recover`. Verify with `test_engine.py` cases: toggle+true → flag set, hold+true → clear, toggle+false → clear
- [x] 3.2 `_transcribe_and_inject_chunk`: when `self._live_typing` and `cleaned` is non-empty, call `_wait_trigger_released()` then `_text_injector.inject((" " if self._live_typed_any else "") + cleaned)` and set `_live_typed_any = True`; keep the `_chunk_texts.append(cleaned)` and `_chunk_any_text` update unchanged. Verify with `test_engine.py`: two chunks → injector receives `"A"` then `" B"`; an empty chunk between them adds no extra space; hold mode → injector not called during recording (existing `test_chunks_accumulate_without_mid_recording_injection` stays green)
- [x] 3.3 Stop path in the transcription worker: after the drain, when the cycle was live, set `last_transcription` to the assembled text but do **not** call `_deliver()` unless `_deliver_to_clipboard` is set (limit stop), in which case `copy_only(assembled)` still runs. Add a `# ponytail:` note that the FSM may reach IDLE while the tail's keystrokes are still in flight. Verify with `test_engine.py`: live cycle stop → `inject` called exactly once per non-empty chunk and zero times with the assembled text; limit stop on a live cycle → `copy_only` receives the full assembled text; `test_second_stop_event_does_not_reinject` stays green
- [x] 3.4 Mid-recording config flip: start a live recording, flip `type_while_speaking` to false via `update_config`, emit another chunk → it is still typed live (snapshot holds); next recording accumulates. Verify with a `test_engine.py` case

## 4. Menu

- [x] 4.1 `ui/menu_bar.py`: add a "Type while speaking" `rumps.MenuItem` next to "Toggle mode" using `menu_theme.toggle_title` (trailing check), callback flipping the key through `engine.update_config`, refreshed in `_refresh_accents` like the toggle-mode row. Verify with `tests/test_menu_bar.py` cases mirroring the Toggle mode ones (checked/unchecked rebuild, callback flips the config)

## 5. Docs and website

- [x] 5.1 `website/index.html`: add the "Type while speaking" row to the menu mockup beside "Toggle mode"; extend the "Text lands as you release the key" card (and the Toggle mode lede) with one sentence: in toggle mode text is typed after each pause. Verify `./.venv/bin/pytest tests/test_website.py` passes, adding an assertion that the page mentions typing while speaking
- [x] 5.2 `README.md` config table: add `type_while_speaking` (default `true`, toggle mode only, note on focus changes mid-dictation); `docs/SPECIFICATION.md`: update the streaming data-flow paragraph and the `_chunk_worker_loop` row; `CHANGELOG.md`: Added entry. Verify `./.venv/bin/pytest tests/test_docs.py` passes

## 6. Verification

- [x] 6.1 Full suite: `./.venv/bin/pytest` green; `ruff check` and `ruff format --check` clean
- [x] 6.2 Live drive on macOS: `make app`, relaunch, toggle mode on, dictate 3-4 sentences with pauses into a full-screen app. Verify: text appears after each pause, one space between chunks, no duplicate at stop, no Space switch, `~/.whispy.log` shows one `[inject] (keystrokes) ok` per non-empty chunk. Then flip "Type while speaking" off and verify the next dictation types once at stop
- [x] 6.3 Hold-mode regression: switch Toggle mode off, dictate with the key held. Verify nothing is typed until release and the text lands once
- [x] 6.4 `graphify update .` after code changes

## 7. Live-drive findings: mid-word force cuts and silent model returns

- [x] 7.1 `core/segmentation.py`: past `max_chunk_s`, cut on the first `SOFT_FLUSH_GAP_S` (0.2 s) of detected silence; unconditional cut at `max_chunk_s * HARD_MAX_FACTOR` (1.5). Verified by `tests/test_segmentation.py::TestMaxLengthFlush` (hard cap, gap cut with VAD hangover allowance, no cut on a gap before max length; the below-threshold force-flush test still passes)
- [x] 7.2 `core/audio.py` `transcribe()`: log `Model returned no text for a %.2fs clip` when the model returns empty, and `logger.exception` instead of a stderr print on error. Verified: `tests/test_audio.py` green; the log line shows up in `~/.whispy.log` on the next live drive
- [x] 7.3 Docs: README `max_chunk_s` row, `docs/SPECIFICATION.md` (config comment + segmenter paragraph), `CHANGELOG.md` Fixed entries. Verified `tests/test_docs.py` green
- [x] 7.4 Live drive (macOS, toggle mode): dictate a 20 s run-on sentence with no pause ≥ 800 ms. Verify the cut lands between words (no duplicated or missing word at the join) and that any `-> None` chunk now has a reason line right above it in `~/.whispy.log`

## 8. Live-drive findings: a lone word was lost

- [x] 8.1 `core/audio.py`: near-silence gate measures `_get_peak_rms` (loudest 0.5 s window, `PEAK_RMS_WINDOW_S`) instead of the whole-clip mean; `_get_audio_rms` kept for calibration checks, both share `_load_normalized`. Verified by `tests/test_audio.py::TestPeakRms` (word in 10 s silence: mean fails, peak passes; quiet noise still fails; silence 0.0; short clip measured whole; None on unreadable) and the re-pointed `TestTranscribe` gate tests
- [x] 8.2 `core/segmentation.py`: `LONE_WORD_PAUSE_S` (2.0 s) — a chunk below `min_speech_s` is emitted once the silence reaches it. Verified by `tests/test_segmentation.py::TestVoicedSpeechGate` (held at 1.9 s, emitted past 2 s; carried-over case unchanged)
- [x] 8.3 Docs: README `min_speech_s` row, `docs/SPECIFICATION.md` segmenter + gate paragraphs, `CHANGELOG.md` Fixed. Verified `tests/test_docs.py` green
- [x] 8.4 Live drive (macOS, toggle mode): say one word ("test") and nothing else. Verify it is typed within ~3 s and no `near-silent` discard appears for it in `~/.whispy.log`; then say a short word followed by a sentence within a second and verify they arrive as one chunk

## 9. Live-drive findings: the model returns nothing for a word inside silence

- [x] 9.1 Measure: `scripts/asr-bench/probe_lone_word.py` — isolated word × voices × trailing silence × volume, raw vs trimmed, through the production `transcribe`. Result recorded in design D11 (raw 3–5/15 at 10 s tail, trimmed 10/15)
- [x] 9.2 `core/segmentation.py`: `speech_span_s` returns `(first_s, last_s, voiced_s)`; `speech_duration_s` becomes a view on it. Verified by `tests/test_segmentation.py::TestSpeechSpan`
- [x] 9.3 `core/audio.py`: `_speech_span` / `_span_carries_speech` (one VAD pass for gate and trim), `_trim_to_speech` writes `<path>.trim.wav` cut to the span + `TRIM_MARGIN_S`, skipped under `TRIM_MIN_GAIN_S` or when unmeasurable; the copy is deleted after `recognize`. Verified by `tests/test_audio.py::TestTrimToSpeech` (padding removed, internal gap kept, tight clip as is, fail-open on None span and on write failure)
- [x] 9.4 Docs: `docs/SPECIFICATION.md` transcribe row, `CHANGELOG.md` Fixed, `scripts/asr-bench/README.md` finding. Verified `tests/test_docs.py` green
- [x] 9.5 Live drive (macOS, toggle mode): say "test" alone, five times with a few seconds between. Verify at least 4/5 are typed and any miss shows `Model returned no text` (not a gate) in `~/.whispy.log`

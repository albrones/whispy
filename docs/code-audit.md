# Whispy Code Audit

_Date: 2026-06-15. Scope: `src/whispy` (~2.7k LOC) plus tests._

A multi-dimensional review across bugs, security, dead code, architecture,
performance, and test coverage. Each finding lists a severity, location,
problem, and recommendation. **Status** marks whether it is addressed in the
`code-health-audit-and-fixes` change (✅ fixed) or recorded as follow-up (⏳).

Severity: **HIGH** (user-visible breakage / security), **MED** (latent /
conditional), **LOW** (robustness / cleanliness).

---

## Bugs

| Sev | Location | Problem | Recommendation | Status |
| --- | -------- | ------- | -------------- | ------ |
| HIGH | `api/server.py:52` | `/stop-async` calls `engine.state._stop_event.set()`, but the attribute is `stop_event`. The read of nonexistent `_stop_event` raises `AttributeError` → HTTP 500, and the worker is never signaled. | Use `engine.state.stop_event`. | ✅ fixed |
| HIGH | `core/engine.py:345-347` | Transcription worker only calls `transcription_complete()` when `run_transcription()` returns truthy text, and is not exception-guarded. Empty/hallucination-only output (cleaned to `""`) or a raised exception leaves the FSM stuck in `TRANSCRIBING`; an exception also kills the worker thread (`_transcription_running` stays True). Recovery only via the force-reset in `start_recording`. | Wrap in try/except (log), call `transcription_complete()` in `finally`. | ✅ fixed |
| LOW | `core/engine.py:142` | `TextInjector(copy_to_clipboard=state.config.get("copy_to_clipboard", True))` defaults to `True`, contradicting `DEFAULT_CONFIG` (`False`) and the `core-engine` spec. | Use `False` fallback. | ✅ fixed |
| MED | `api/server.py:80-105` | `_sync_stop_and_transcribe` manually mutates `is_recording`/`is_transcribing` and drives FSM transitions while the background worker may run concurrently; a near-simultaneous `/stop` and Fn-release race on `RECORDING_PATH` and FSM with no lock. | Route `/stop` through the same single-owner worker path, or guard with the engine lock. | ⏳ |
| LOW | `core/engine.py:57` | `cpu_threads = 0` is dead; both branches overwrite it. Logic relies on the `TypeError` path when `os.cpu_count()` is `None`. | Simplify to `(os.cpu_count() or 8) // 2`. | ⏳ |

## Security

| Sev | Location | Problem | Recommendation | Status |
| --- | -------- | ------- | -------------- | ------ |
| HIGH | `hardware/injection.py:33,40-42,54-66` | Transcribed text is interpolated into an AppleScript `-e` string with only `"` escaped. A trailing backslash breaks out of the string literal, and `\n`/`\t`/`\r` are reinterpreted, corrupting injected text. Source is mic audio, so primarily correctness, but malformed text yields unintended AppleScript. | Escape backslashes first (`replace("\\","\\\\")` then `"`), or pass text via `argv` (`on run argv`) / stdin instead of interpolation. | ⏳ |
| MED | `api/server.py` (whole) | The local control API has no authentication. Bound to `127.0.0.1`, but any local process can POST `/start`/`/stop`/`/config` and GET `/last-transcription` (leaks last dictated text). No CORS headers, but JSON endpoints are reachable by local clients; DNS-rebinding is a theoretical concern. | Per-session bearer token written to the config dir with `0600`, validated each request; reject requests carrying an `Origin` header. | ⏳ |
| MED | `api/server.py:57-58` | `Content-Length` is trusted and the full body read with no cap; a negative value is possible. | Reject negative and clamp to a max (e.g. 64 KB) before `read`. | ⏳ |
| LOW | `core/audio.py` (`RECORDING_PATH`) | Recording WAV written to a fixed, predictable path in the shared temp dir. On a multi-user box another user could read it or pre-create/symlink the path. | Write under a per-user dir with `0600` (e.g. `~/.cache/whispy/`) or `mkstemp`. | ⏳ |

## Dead code

| Location | Problem | Recommendation | Status |
| -------- | ------- | -------------- | ------ |
| `ui/indicator_window.py` | `IndicatorWindow.show()` is never called (only `hide()`/`destroy()`); superseded by `WaveformWindow`. Emojis/colors/positioning all unreachable. | Delete `IndicatorWindow` and the `_indicator` field + hide/destroy calls in `menu_bar.py`. | ⏳ |
| `core/audio.py` (`strip_whisper_credit`) | Duplicates `text_cleaner.clean_text`; credit stripping runs twice (in `transcribe` and again via `clean_text` in `run_transcription`). | Consolidate on `clean_text`; drop in-`transcribe` stripping. | ⏳ |
| `core/audio.py` (`AudioEngine.play_sound`) | Never called; sound is played inline via `subprocess.Popen`. | Remove, or route inline `afplay` calls through it. | ⏳ |
| `core/audio.py` (`is_recording`/`is_transcribing` props) | Unused by src (callers read `engine.state.*`). | Remove if not a deliberate public API. | ⏳ |
| `core/engine.py:98,101,108` (`DictationState.recording_process`, `.lock`, `.app`) | Vestigial: `recording_process` moved to `AudioEngine`; `lock` never used; `.app` set by daemon but never read. | Remove (needs test updates). | ⏳ |
| `core/engine.py:294` (`_trigger_keycode_from_config`) | Always returns the constant; leftover from configurable-trigger era. | Inline `DEFAULT_TRIGGER_KEYCODE`. | ⏳ |
| `hardware/event_tap.py:43-149` (`_KEYCODE_TO_NAME`) | 100-entry table used only to print the trigger name once; key is always Fn. Also mislabels keycode 63 as "f5". | Collapse to a hardcoded "Fn". | ⏳ |
| `core/state_machine.py:172` (`transition_history`) | Consumed only by tests. | Keep as debug API or remove. | ⏳ |

## Architecture

| Location | Problem | Recommendation | Status |
| -------- | ------- | -------------- | ------ |
| `api/server.py:80-105` | `_sync_stop_and_transcribe` reimplements the worker's stop→transcribe→complete orchestration by poking engine privates. | Extract `Engine.stop_and_transcribe()` used by both API and worker. | ⏳ |
| `core/engine.py` + `config.py` + `audio.py` | Config handling spread across layers: `update_config` filters, `save_config` filters, `_validate_config` filters, and `run_transcription` re-supplies per-key defaults duplicating `DEFAULT_CONFIG`. | Single-source the defaults. | ⏳ |
| `core/engine.py` (`DictationState`) | Mutated from event-tap, worker, HTTP, and UI threads; the `lock` is unused, so mirror fields (`is_recording`, etc.) are racy while the FSM is locked. | Make the FSM the single source of truth; drop mirror fields or guard them. | ⏳ |
| `core/engine.py:368` (`update_config`) | Persists any known-key value without running `_validate_config`; a bad `model_size`/`language` is saved and crashes the next model load (relies on load-time validation to recover). | Validate in `update_config` before persisting. | ⏳ |

## Performance

| Location | Problem | Recommendation | Status |
| -------- | ------- | -------------- | ------ |
| `core/audio.py:156` | Unconditional `time.sleep(0.15)` in `AudioEngine.stop()` adds fixed 150 ms latency per dictation before transcription. | Poll file-size stability / detect sox flush instead. | ⏳ |
| `core/engine.py:340` | Worker `stop_event.wait(timeout=0.1)` wakes 10×/s forever; `set()` already wakes the waiter. | Drop the timeout (or lengthen) so it blocks until signaled. | ⏳ |
| `ui/menu_bar.py:47,183` | `_anim_timer` fires every 90 ms for the app's life even when idle. | Pause when idle, resume from a state-change callback. | ⏳ |
| `ui/audio_level.py` + `core/audio.py:81` | Mic captured twice concurrently: sox (WAV) + `sounddevice` (level meter). | Tail sox output for levels, or have sox feed both. | ⏳ |

## Missing tests (ranked)

1. **`/stop-async`** — was entirely untested and shipped broken. ✅ regression test added.
2. **Worker FSM completion** on empty / raising transcription. ✅ tests added.
3. **`config._migrate_config`** version migration on load — untested; a regression silently corrupts user configs on upgrade. ⏳
4. **`_validate_config`** branches other than `min_recording_duration` (`model_size`, `language`, `beam_size`, `best_of`, `copy_to_clipboard`, `auto_detect_min_duration`). ⏳
5. **`run_transcription` anti-hallucination path** — that a credit/hallucination-only result is not injected and does not set `last_transcription`. ⏳
6. **`load_model_async`** worker — leaves flags consistent on load failure. ⏳
7. **`start_fn_listener`** press/release wiring — release sets `stop_event`. ⏳
8. **Deprecated-key rejection** (`trigger_key`, `compute_key`) at POST `/config`. ⏳

Well-covered already: `state_machine`, `text_cleaner`/`strip_whisper_credit`,
`AudioEngine` start/stop/transcribe, `config` save/load.

---

## Suggested follow-up changes

Grouped for future OpenSpec proposals:

1. **`harden-control-api`** — bearer token auth, `Origin` rejection, body-size cap.
2. **`fix-applescript-injection-escaping`** — backslash-safe escaping or `argv` passing.
3. **`remove-dead-code`** — `IndicatorWindow`, `play_sound`, vestigial `DictationState` fields, `_KEYCODE_TO_NAME`, duplicated credit stripping.
4. **`unify-stop-transcribe-path`** — single `Engine.stop_and_transcribe()` for API + worker; fixes the stop/transcribe race.
5. **`config-single-source`** — validate in `update_config`; one source of transcription defaults.
6. **`coverage-config-and-engine`** — tests for migration, validation branches, anti-hallucination, model-load failure.
7. **`perf-recording-latency`** — remove the 150 ms sleep; idle-pause UI timer; single mic capture.

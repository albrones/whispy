## 1. Trigger callback handoff (core-engine)

- [x] 1.1 Add `self._trigger_queue: queue.Queue[str]`, `self._trigger_thread`, and
      `self._trigger_worker_running` to `Engine.__init__`
- [x] 1.2 Add `_handle_trigger_press_work()` containing the exact former body of `_on_trigger_press`
      (`_detect_corrections()`, `_notify_fn_pressed()`, `_notifier.recording_started()`,
      `start_recording()`, in that order)
- [x] 1.3 Add `_handle_trigger_release_work()` containing the exact former body of
      `_handle_trigger_release` (`_notify_fn_released()`, `stop_recording()`, set `state.stop_event`
      only if transitioned)
- [x] 1.4 Add `_trigger_worker_loop()` (mirrors `_chunk_worker_loop`: `queue.get(timeout=0.1)` poll on
      `_trigger_worker_running`) dispatching `"press"` → `_handle_trigger_press_work()`, `"release"` →
      `_handle_trigger_release_work()`
- [x] 1.5 Add `start_trigger_worker()` / `stop_trigger_worker()`; call them from `Engine.start()` /
      `Engine.stop()` alongside the other worker lifecycles
- [x] 1.6 Rewrite the closures in `start_fn_listener()` so `_on_trigger_press` only does
      `self._trigger_queue.put("press")` and the release closure only does
      `self._trigger_queue.put("release")`
- [x] 1.7 Unit test: the press callback returns without calling `_detect_corrections`/
      `start_recording` directly (assert via a mock that blocks, confirming the callback itself does
      not block)
- [x] 1.8 Unit test: a press signal followed immediately by a release signal are processed by the
      worker in that order (assert `start_recording` is called before `stop_recording`)
- [x] 1.9 Unit test: the worker preserves the exact prior call order on press and on release
      (correction-detection → notify-pressed → sound → start; notify-released → stop → conditional
      stop_event)

## 2. Chunk state thread-safety (core-engine)

- [x] 2.1 Wrap the `_chunk_texts = []` / `_chunk_any_text = False` reset in `_on_fsm_recording` with
      `with self.state.lock:`
- [x] 2.2 Wrap the `_chunk_texts.append(...)` / `_chunk_any_text = True` writes in
      `_transcribe_and_inject_chunk` with `with self.state.lock:`
- [x] 2.3 In the transcription worker's stop-event handling, take a lock-guarded snapshot of
      `_chunk_texts`/`_chunk_any_text` (copy the list, read the flag) before releasing the lock and
      performing `" ".join(...)`/injection
- [x] 2.4 Wrap the `_chunk_texts = []` / `_chunk_any_text = False` reset in `_force_recover` with
      `with self.state.lock:`
- [x] 2.5 Unit test: chunk-worker append and transcription-worker read each acquire
      `DictationState.lock` (spy/mock the lock and assert `acquire`/`release` calls bracket the
      access)
- [x] 2.6 Unit test: concurrent chunk appends and a read (driven via real threads, not just mocks)
      never raise and always yield a consistent list length (regression guard against the unlocked
      race)

## 3. Synchronous `/stop` via the shared worker (core-engine + api-interface)

- [x] 3.1 Add `self._transcription_done_event = threading.Event()` to `Engine.__init__`, initialized
      set (idle)
- [x] 3.2 Add `SYNC_STOP_TIMEOUT_S` constant near `CHUNK_DRAIN_TIMEOUT_S`/`TRANSCRIBING_MAX_S`
- [x] 3.3 In the transcription worker's stop-event handler, clear `_transcription_done_event`
      immediately after consuming `stop_event`, and set it in the existing `finally` block after
      `transcription_complete()` and the status notification
- [x] 3.4 Also set `_transcription_done_event` inside `_force_recover()` (watchdog forced recovery),
      so a waiter is released even when the watchdog — not the worker — resolves the cycle
- [x] 3.5 Add `Engine.stop_and_wait_for_transcription(timeout=SYNC_STOP_TIMEOUT_S) -> str | None`:
      call `stop_recording()`; if not transitioned, return `None` immediately; otherwise clear
      `_transcription_done_event`, set `state.stop_event`, wait on the done event (bounded by
      `timeout`), and return `state.last_transcription`
- [x] 3.6 Replace `RequestHandler._sync_stop_and_transcribe` in `api/server.py` with a call to
      `engine.stop_and_wait_for_transcription()`; delete the hand-rolled FSM/state mutation and the
      direct `run_transcription()` call
- [x] 3.7 Remove the now-redundant `engine._notifier.transcription_succeeded()` call from the
      `/stop` POST handler (the worker already fires it, gated on `produced_text`)
- [x] 3.8 Unit test (`test_engine.py`): `stop_and_wait_for_transcription` in streaming mode returns
      the same assembled text the worker injected, after one or more chunks were queued
- [x] 3.9 Unit test (`test_engine.py`): `stop_and_wait_for_transcription` called while not recording
      returns `None` immediately and does not set `stop_event`
- [x] 3.10 Unit test (`test_engine.py`): if the done event is never set (simulated stalled worker),
      `stop_and_wait_for_transcription` returns after `timeout` rather than hanging (use a small
      timeout in the test)
- [x] 3.11 Regression test (`test_api/test_server.py`): `POST /stop` in streaming mode (chunk worker
      driven with a mocked transcribe call producing multiple chunks) returns
      `{"status": "done", "text": <assembled text>}`, not `null`
- [x] 3.12 Regression test (`test_api/test_server.py`): `POST /stop` while not recording returns
      `{"status": "done", "text": null}` and triggers no notifier call
- [x] 3.13 Regression test (`test_api/test_server.py`): `POST /stop` on a successful transcription
      fires the success-cue notifier exactly once

## 4. Verification

- [x] 4.1 Run `./.venv/bin/pytest` — all existing + new tests green
- [ ] 4.2 Live-drive on macOS: tap-and-hold the trigger while transcribing a prior recording is still
      in flight, confirm no `kCGEventTapDisabledByTimeout` log line and that the waveform still
      shows/hides promptly
- [ ] 4.3 Live-drive: with streaming enabled, dictate a multi-chunk phrase and call `POST /stop`
      manually (e.g. via `curl`) instead of releasing the trigger; confirm the response `text` matches
      what was typed
- [x] 4.4 Confirm no user-facing surface changed (no `website/index.html` update needed — internal
      correctness fix only, no new/changed/removed setting or feature); note this explicitly in the PR

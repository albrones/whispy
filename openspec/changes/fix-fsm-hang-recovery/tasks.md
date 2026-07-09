## 1. State machine — forced recovery

- [x] 1.1 Add `StateMachine.force_idle()` that sets state to IDLE from any state under the lock, appends a `"<state> -> IDLE (forced)"` history entry, and fires IDLE callbacks (notify outside the lock, matching `transition_to`)
- [x] 1.2 Unit test: `force_idle()` from RECORDING and from TRANSCRIBING both end in IDLE and fire the IDLE state-change callback

## 2. Bounded chunk drain (stuck-in-TRANSCRIBING fix)

- [x] 2.1 Add `CHUNK_DRAIN_TIMEOUT_S` constant (~30s) in `core/engine.py`
- [x] 2.2 Add a `_drain_chunk_queue(timeout)` helper that waits on `self._chunk_queue.all_tasks_done` with a monotonic deadline; returns whether it fully drained; logs on timeout
- [x] 2.3 Replace `self._chunk_queue.join()` in the transcription worker with `_drain_chunk_queue(CHUNK_DRAIN_TIMEOUT_S)`; on timeout still inject the assembled `_chunk_texts` and fall through to the existing `finally` → `transcription_complete()`
- [x] 2.4 Unit test: with a chunk worker that never calls `task_done`, the worker returns to IDLE within the timeout and injects the text produced so far (use a small timeout in the test)

## 3. Event-tap release recovery (stuck-in-RECORDING fix)

- [x] 3.1 Track a `_pressed` flag in `EventTapListener`: set when emitting `press`, clear when emitting `release`
- [x] 3.2 In the disable→re-arm branch, read live modifier flags via `CGEventSourceFlagsState(kCGEventSourceStateHIDSystemState)` (guarded import; fall back to re-arm-only if unavailable) and set `self._prev_flags = _normalize_flags(live)`
- [x] 3.3 After resync, if the trigger is a modifier, `_pressed` is True, and the trigger's flag bit is no longer set → emit the missed `release` and clear `_pressed` (reuse pure `event_decode` helpers for the bit test)
- [x] 3.4 Unit test (pure/off-device): given a stale `_prev_flags` with the modifier bit set and a live-flags value with it cleared, the resync path yields a `release`; and a normal held-modifier value yields no synthetic release

## 4. FSM watchdog backstop (Engine)

- [x] 4.1 Add `RECORDING_MAX_S` (~300s) and `TRANSCRIBING_MAX_S` (~120s) constants and record a monotonic timestamp when the FSM enters RECORDING / TRANSCRIBING (hook the existing FSM state-change callbacks)
- [x] 4.2 In a dedicated `fsm-watchdog` thread (NOT the worker loop — that loop is what wedges), add a watchdog check: if RECORDING exceeds `RECORDING_MAX_S`, stop the audio engine, clear `stop_event` and chunk buffers, then `force_idle()` and re-notify status; if TRANSCRIBING exceeds `TRANSCRIBING_MAX_S`, `force_idle()` and re-notify status; log each recovery with the state recovered from
- [x] 4.3 Ensure a normal record→transcribe cycle within the timeouts triggers no watchdog action (regression guard)
- [x] 4.4 Unit test: simulate dwell past each timeout (inject a tiny timeout) and assert the engine forces IDLE, stops audio for the RECORDING case, and logs the recovery

## 5. Verification

- [x] 5.1 Run `./.venv/bin/pytest` — all existing + new tests green
- [ ] 5.2 Live-drive on macOS: hold trigger and stall a chunk (or kill the tap mid-hold), confirm the menu bar returns to "Ready" without a restart; check `~/.whispy.log` shows the recovery line
- [x] 5.3 Confirm no user-facing surface changed (no `website/index.html` update needed — internal recovery only); note this explicitly in the PR

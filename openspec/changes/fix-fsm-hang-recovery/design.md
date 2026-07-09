## Context

The engine drives a 3-state FSM (IDLE → RECORDING → TRANSCRIBING → IDLE) in
`core/state_machine.py`, fed by the CGEventTap listener (`hardware/event_tap.py`)
and a background transcription worker (`core/engine.py`). Live logs show the FSM
stranded in RECORDING (lost trigger release) and, separately, in TRANSCRIBING
(worker blocked on `self._chunk_queue.join()`). Both leave the app unusable until
a manual restart.

Relevant current behavior:
- `StateMachine.start_recording()` already force-resets a stuck TRANSCRIBING to
  IDLE when the trigger is pressed again — so a TRANSCRIBING wedge is partially
  self-healing *if* a press is delivered. A RECORDING wedge is **not**:
  `start_recording()` returns False when already RECORDING, so re-pressing does
  nothing.
- The transcription worker already runs a continuous 0.1s poll loop
  (`stop_event.wait(timeout=0.1)`), a natural home for a watchdog tick — no new
  thread needed.
- `queue.Queue.join()` takes **no timeout argument**; a bounded drain must be
  built from the queue's own `all_tasks_done` condition variable.

Constraints: macOS-only hot path; the event-tap callback must stay fast and
non-blocking; pure decode logic stays in `event_decode.py` for off-device tests.

## Goals / Non-Goals

**Goals:**
- No state in which releasing the trigger leaves the app permanently stuck.
- A single coarse backstop (watchdog) plus two precise fixes (release recovery,
  bounded drain) so a lost event or stalled chunk always resolves to IDLE.
- Recoveries are logged, not silent, so recurrence is diagnosable.
- Happy path byte-for-byte unchanged; recovery only fires on the fault paths.

**Non-Goals:**
- PortAudio `-9986` capture-open failures (separate change).
- Multi-instance config-corruption race (separate change).
- Exposing watchdog timeouts as user config (internal constants for now).

## Decisions

### 1. Watchdog runs in its own thread (Engine)
Track a monotonic timestamp of when the FSM entered its current non-idle state
(set from the existing FSM state-change callbacks). A dedicated `fsm-watchdog`
thread ticks every ~1s and force-recovers if a timeout is exceeded. Rejected:
reusing the transcription worker's poll loop — the worker is *exactly* what wedges
in the TRANSCRIBING case (a blocked `inject`/`transcribe`), so a watchdog inside
it could never fire for that case. Independence is the whole point, so it must be
a separate thread. The watchdog lives in the Engine (not `StateMachine`) because
recovery from RECORDING must also stop the audio engine and reset chunk state,
which the bare FSM can't do.

Timeouts (internal constants, generous to never clip a legit session):
- RECORDING: `RECORDING_MAX_S` ≈ 300s (no one holds push-to-talk 5 min; the real
  release always arrives far sooner).
- TRANSCRIBING: `TRANSCRIBING_MAX_S` ≈ 120s backstop (the bounded drain below is
  the primary guard; this only catches anything the drain timeout misses).

### 2. `StateMachine.force_idle()` for guard-bypassing recovery
Add a method that sets state to IDLE from any state, appends a
`"<state> -> IDLE (forced)"` history entry, and fires IDLE callbacks like a
normal transition. The existing guarded transitions are untouched; forcing is an
explicit, separate, clearly-logged path used only by recovery.

### 3. Recovery from RECORDING = stop audio + force IDLE
When the watchdog trips in RECORDING it calls `stop_recording()` semantics on the
audio engine (close the stream, flush is irrelevant here), clears
`stop_event`/chunk buffers, then `force_idle()`. This mirrors a normal release
minus injection, so no partial recording lingers.

### 4. Bounded chunk drain via `all_tasks_done`
Replace `self._chunk_queue.join()` in the worker with a helper that waits on the
queue's `all_tasks_done` condition with a deadline:
```
with q.all_tasks_done:
    deadline = monotonic() + CHUNK_DRAIN_TIMEOUT_S
    while q.unfinished_tasks:
        remaining = deadline - monotonic()
        if remaining <= 0:
            log("chunk drain timed out"); break
        q.all_tasks_done.wait(remaining)
```
On timeout the worker proceeds to inject whatever `_chunk_texts` holds and falls
through its existing `finally` → `transcription_complete()`, returning to IDLE.
`CHUNK_DRAIN_TIMEOUT_S` ≈ 30s (a chunk should transcribe in ≪ that). Rejected:
switching the queue type or adding sentinels — the condition-variable wait is
stdlib and leaves FIFO semantics intact.

### 5. Event-tap release recovery on re-arm
The listener gains a `_pressed` flag (set when it emits a press, cleared on
release). In the disable→re-arm branch it:
1. Reads the live modifier state via `CGEventSourceFlagsState(kCGEventSourceStateHIDSystemState)`.
2. Sets `self._prev_flags = _normalize_flags(live)` so the next transition
   decodes correctly (fixes the desync).
3. If the trigger is a modifier, `_pressed` is True, and the trigger's flag bit
   is no longer set → emit the missed `release` (and clear `_pressed`).
The bit test reuses the pure `event_decode` helpers so it stays unit-testable;
only the live-flags read is OS-bound.

## Risks / Trade-offs

- [Watchdog clips a legitimately long recording] → timeouts set far above any
  real push-to-talk hold (300s); TRANSCRIBING backstop (120s) sits above the
  bounded drain (30s) so the drain resolves first in practice.
- [Forced IDLE races a real event arriving at the same instant] → `force_idle`
  and guarded transitions share the FSM lock; worst case is one redundant
  transition, and `transition_to`/`transcription_complete` already no-op when not
  in the expected source state.
- [`CGEventSourceFlagsState` unavailable / returns stale flags] → guard the
  import like the rest of Quartz; if the live read fails, fall back to re-arm-only
  (today's behavior) so we never regress, and the watchdog still backstops.
- [Bounded drain injects partial text on timeout] → acceptable: partial output
  beats a permanent hang, and the event is logged.

## Migration Plan

Pure additive behavior on fault paths; no config or data migration. Ships in the
menu-bar app; validated by the recovery unit tests plus a manual live-drive
(hold trigger, kill the tap / stall a chunk, confirm the app returns to Ready).
Rollback is a straight revert — nothing persists state.

## Open Questions

- Should recoveries also play the error notification sound / flash the menu bar
  so the user knows a hang was auto-recovered? (Leaning yes for RECORDING
  recovery, since no text was produced.) Deferred to implementation.
- Final constant values (300 / 120 / 30s) to confirm against a `large-v3` run on
  a slow machine during live-drive.

## Why

The app intermittently wedges after the user releases the push-to-talk trigger: the transcription never runs and the only remedy is a full restart. Live logs confirm two distinct dead-ends with **no recovery path** — the FSM has no watchdog, so any lost event or blocked worker strands it forever.

Two root causes, both reproduced in `~/.whispy.log`:

1. **Stuck in RECORDING** — for a modifier trigger (e.g. Right Option, keycode 61), the release is decoded from `flags_changed` transitions. When macOS disables the CGEventTap (slow callback under transcription CPU load, or heavy input) the release event fires while the tap is down. `event_tap.py` re-arms the tap but the release is already lost, and `_prev_flags` is left desynced — the FSM never leaves RECORDING. (Log: `IDLE -> RECORDING` followed only by chunk lines, no `-> TRANSCRIBING`.)
2. **Stuck in TRANSCRIBING** — on release the worker calls `self._chunk_queue.join()` with no timeout. If a chunk transcription blocks or the chunk worker stalls, `join()` never returns and the FSM stays in TRANSCRIBING. (Log counters: `RECORDING->TRANSCRIBING = 196` vs `TRANSCRIBING->IDLE = 195`.)

## What Changes

- Add an **FSM watchdog**: a bounded time in RECORDING (no release) or TRANSCRIBING (no completion) force-transitions the FSM back to IDLE, re-notifies the UI, and logs the recovery — a single safety net covering both dead-ends.
- **Release recovery for modifier triggers**: on tap re-arm after an OS disable, re-sync `_prev_flags` from the live modifier state so the next transition decodes correctly; if the FSM is in RECORDING with the trigger modifier no longer held, synthesize the missed release.
- **Bounded chunk drain**: `_chunk_queue.join()` on release gets a timeout; on expiry the worker stops waiting, injects whatever assembled text exists, and returns the FSM to IDLE instead of blocking forever.
- Recovery events are logged so future occurrences are diagnosable rather than silent.

## Capabilities

### New Capabilities
<!-- none: this hardens existing behaviors -->

### Modified Capabilities
- `core-engine`: FSM gains a watchdog requirement — bounded dwell in RECORDING/TRANSCRIBING auto-recovers to IDLE; the release-triggered chunk drain is bounded, not indefinite.
- `event-listener`: after the OS disables and the listener re-arms the tap, it MUST re-sync modifier flag state and recover a release missed while the tap was down, so a modifier trigger cannot strand the engine in RECORDING.
- `streaming-transcription`: the on-release wait for the chunk queue to drain MUST be bounded; a stalled chunk cannot wedge the FSM in TRANSCRIBING.

## Impact

- Code: `src/whispy/core/engine.py` (transcription worker, chunk drain, watchdog), `src/whispy/core/state_machine.py` (forced recovery transition), `src/whispy/hardware/event_tap.py` (re-arm resync + missed-release recovery), possibly `src/whispy/hardware/event_decode.py` (pure resync helper).
- Behavior: no change to the happy path; only adds recovery when an event is lost or a worker stalls.
- Tests: new unit tests for watchdog recovery, tap-re-arm flag resync, and bounded `join`. Pure-logic decode helpers stay testable off-device.
- No new dependencies. No API or config changes (watchdog timeouts are internal constants; may expose as config later, out of scope here).

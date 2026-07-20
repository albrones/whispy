## Context

`Engine.start_fn_listener()` (`core/engine.py:780-797`) wires two closures —
`_on_trigger_press` and `_handle_trigger_release` — as the `on_trigger_press`/`on_trigger_release`
callbacks passed to whichever hotkey adapter the platform detects (`EventTapListener` on macOS,
`PynputHotkeyListener` on Linux). Both adapters invoke these closures **synchronously, on their own
dedicated listener thread** (the `CGEventTap` run-loop thread, or pynput's single listener thread),
inside a `try/except` that only contains exceptions — it does nothing about latency. Today the
closures do real work inline: AX reads (`_detect_corrections`), a fire-and-forget sound
(cheap), and — the expensive parts — `start_recording()`/`stop_recording()`, which reach into
`AudioEngine.start()`/`stop()`: device re-enumeration (`sd._terminate()`/`_initialize()`), stream
open/close, and a bounded-but-real 2.0s readiness wait. On macOS this risks the OS disabling a
slow listen-only tap (`kCGEventTapDisabledByTimeout`, already handled reactively at
`event_tap.py:162`); on Linux a blocking press handler stalls pynput's single thread, so the
matching release is not even *decoded* until the press handler returns.

Separately, `RequestHandler._sync_stop_and_transcribe` (`api/server.py:206-232`) reimplements a
miniature version of the transcription worker's job directly on the (single-threaded) HTTP server's
thread: it calls `AudioEngine.stop()`, hand-mutates `engine.state.is_recording`/`is_transcribing`,
calls `engine.run_transcription()` (which only knows the whole-file path — nothing about
`_chunk_texts`), and force-calls `engine._state_machine.transcription_complete()`. This duplicates
logic that already lives correctly in `Engine.start_transcription_worker()`'s `_worker` loop
(`engine.py:823-865`), which already knows how to drain the chunk queue, assemble `_chunk_texts`,
inject once, and always return the FSM to `IDLE`. Two independent implementations of "what happens
when recording stops" is exactly how the streaming case was missed in one of them.

Constraints: the hardware callback threads (`CGEventTap` run loop, pynput listener) must return
fast — that is the whole bug. `HTTPServer` in `server.py` is the stdlib single-threaded variant (not
`ThreadingHTTPServer`), so `/stop` already blocks the entire API for its duration by design (that's
why `/stop-async` exists); this change does not alter that latency contract, only which code produces
the result. `StateMachine.stop_recording()` has a pre-existing (out-of-scope) TOCTOU: two callers can
both read `current_state == RECORDING` before either transitions, and both can then observe
`transitioned = True` (the second call's `transition_to(TRANSCRIBING)` sees `target == current` and
short-circuits as an idempotent no-op returning `True`). This existed before this change for any two
concurrent stop sources and is not fixed here.

## Goals / Non-Goals

**Goals:**
- No blocking work (AX reads, audio device I/O, WAV flush) ever runs on the `CGEventTap` run-loop
  thread or the pynput listener thread.
- One fix, not two: cover macOS and Linux by fixing the shared `Engine`-level closures rather than
  patching each platform shell.
- `POST /stop` returns the correct assembled text in streaming mode, by reusing the existing
  transcription worker instead of a second, incomplete implementation.
- Eliminate the `/stop` vs. background-worker race by never mutating FSM/state by hand outside the
  worker.
- Close the three unlocked cross-thread accesses to `_chunk_texts`/`_chunk_any_text` using the
  already-present (currently dead) `DictationState.lock`.
- Preserve exact existing call order per event (detect-corrections → notify-pressed → sound →
  start-recording; notify-released → stop-recording → maybe set stop_event) and exact existing
  press/release semantics (stray release is a no-op).

**Non-Goals:**
- Fixing `StateMachine.stop_recording()`'s TOCTOU / idempotent-no-op double-`True` return. It is a
  narrow, pre-existing race between any two concurrent stop sources (not introduced or worsened
  here) and is a separate, deeper change to the FSM's guard semantics.
- Making the HTTP server multi-threaded, or changing `/stop`'s synchronous contract. `/stop` is
  documented/used as the blocking variant; `/stop-async` remains the non-blocking one.
- Reworking the watchdog (`fix-fsm-hang-recovery`) — this change only makes the watchdog's forced
  recovery also release a waiter on the new completion signal (see Decision 3).

## Decisions

### 1. One Engine-level trigger queue + dedicated worker thread, not per-platform fixes

`Engine` gains `self._trigger_queue: queue.Queue[str]` and a `trigger-worker` thread (started/stopped
alongside the other workers in `Engine.start()`/`stop()`). The closures in `start_fn_listener()`
shrink to:

```python
def _on_trigger_press() -> None:
    self._trigger_queue.put("press")

def _handle_trigger_release_signal() -> None:
    self._trigger_queue.put("release")
```

A single consumer loop (mirroring the existing `_chunk_worker_loop` pattern: `queue.get(timeout=0.1)`
so the thread can also observe a running flag for clean shutdown) pops items and dispatches to
`_handle_trigger_press_work()` / `_handle_trigger_release_work()`, which hold the *exact* bodies the
closures used to run inline (same call order, same guards).

**Alternatives considered:**
- *A pair of `threading.Event`s (`press_requested`/`release_requested`) instead of a queue.* Rejected:
  events coalesce — a press followed immediately by a release before the worker wakes would only
  leave the release event set, losing the press entirely (or vice versa, depending on wake timing). A
  `Queue` preserves every event in arrival order with no coalescing risk, which matters because a fast
  tap-and-release is a normal, common usage pattern.
- *Fix `event_tap.py` and `hotkey.py` independently* (e.g. spawn a thread per callback). Rejected: the
  blocking work lives in the `Engine`-level closures, not in either platform shell — both shells
  already just call whatever callable `Engine` handed them inside their own `try/except`. Fixing this
  once in `start_fn_listener()` fixes both platforms and avoids duplicating queue/thread bookkeeping
  in two adapters.
- *Spawn a fresh `threading.Thread` per press/release event* instead of a persistent worker. Rejected:
  unbounded thread creation under rapid tapping, and it reintroduces exactly the kind of ordering
  hazard (two short-lived threads racing to call `start_recording()`/`stop_recording()` out of order)
  the queue avoids for free via FIFO + a single consumer.

### 2. `/stop` reuses the background transcription worker via a stop-event handoff + completion signal

`Engine` gains `stop_and_wait_for_transcription(timeout: float = SYNC_STOP_TIMEOUT_S) -> str | None`:

```python
def stop_and_wait_for_transcription(self, timeout=SYNC_STOP_TIMEOUT_S):
    transitioned = self.stop_recording()
    if not transitioned:
        return None
    self._transcription_done_event.clear()
    self.state.stop_event.set()
    self._transcription_done_event.wait(timeout=timeout)
    return self.state.last_transcription
```

`self._transcription_done_event` is a new `threading.Event`, initialized *set* (idle — nothing
pending). The transcription worker's loop clears it right after consuming `stop_event` and sets it in
the existing `finally` block, after `transcription_complete()` and the status notification. Clearing
happens on the **caller's** side (before setting `stop_event`), not only inside the worker, so that a
stale "done" state left over from a *previous* cycle can never be read as this cycle's completion —
if the clear happened only inside the worker's pickup, a `/stop` call whose `.wait()` runs before the
worker wakes from its 0.1s poll would see the event still `set()` from the last cycle and return
immediately with stale data.

`RequestHandler._sync_stop_and_transcribe` shrinks to a single delegate call:

```python
def _sync_stop_and_transcribe(self, engine):
    return engine.stop_and_wait_for_transcription()
```

This makes streaming mode correct for free — the worker already knows how to drain `_chunk_queue`,
assemble `_chunk_texts`, inject once, and set `state.last_transcription`; `/stop` no longer needs its
own (incomplete) copy of that logic. It also removes the race: the HTTP thread no longer mutates
`is_recording`/`is_transcribing`/calls `transcription_complete()` itself — only the worker does, so
there is exactly one writer of those transitions per cycle (modulo the pre-existing FSM TOCTOU noted
in Context, which this change does not touch). The endpoint handler in `server.py` also drops its own
`engine._notifier.transcription_succeeded()` call — the worker already fires that sound, gated on
`produced_text`, so the handler doing it unconditionally was a latent bug (always played the success
cue, even on empty output); removing the duplicate call fixes it as a side effect.

**Alternatives considered:**
- *Teach `run_transcription()` (or a new streaming-aware variant) to drain chunks itself, called
  directly from the HTTP thread.* Rejected: this duplicates the drain/assemble/inject sequence that
  already exists in the worker loop — literally the kind of duplication that produced bug 2 in the
  first place — and still leaves the HTTP thread mutating FSM state in parallel with whatever the
  worker might independently be doing, rather than there being one code path.
- *Poll `state_machine.current_state` until it returns to `IDLE` instead of a dedicated event.*
  Rejected: `IDLE` is also the state before any recording starts and after a stray/no-op stop, so
  polling for it is ambiguous about *which* cycle finished without additional bookkeeping; a
  purpose-built event scoped to "this transcription attempt finished" is unambiguous and cheap.

### 3. Watchdog forced recovery also releases a waiter on `_transcription_done_event`

`Engine._force_recover()` (the watchdog's TRANSCRIBING-dwell backstop from `fix-fsm-hang-recovery`)
now also calls `self._transcription_done_event.set()` alongside its existing state resets. Without
this, a `/stop` caller waiting on the event during a wedged-then-watchdog-recovered cycle would sit
out its full `SYNC_STOP_TIMEOUT_S` even though the watchdog already resolved the FSM — a small
robustness addition consistent with the watchdog's existing job of unblocking anything waiting on the
stuck cycle.

### 4. `DictationState.lock` becomes the guard for `_chunk_texts` / `_chunk_any_text`

Rather than adding a new lock, the existing-but-unused `DictationState.lock` now wraps every access
identified by the audit:
- `Engine._on_fsm_recording` — resets `_chunk_texts = []` / `_chunk_any_text = False` on entering
  `RECORDING` (now runs on the trigger-worker thread per Decision 1, but still concurrent with an
  in-flight chunk worker from a stale prior cycle in principle).
- `Engine._transcribe_and_inject_chunk` (chunk-worker thread) — appends to `_chunk_texts`, sets
  `_chunk_any_text = True`.
- The transcription worker's stop-event handler (`engine.py:841`) — reads/joins `_chunk_texts` and
  `_chunk_any_text` to assemble and decide `produced_text`.
- `Engine._force_recover` (watchdog thread) — resets both fields during forced recovery.

Reads/writes take the lock only around the list/flag access itself (a snapshot copy under the lock,
then release before the slower `inject()`/`" ".join()` work), so the lock is never held across
blocking calls.

**Alternatives considered:**
- *Remove `DictationState.lock` entirely as dead code and leave the accesses unlocked.* Rejected:
  that resolves the "dead code" half of the audit finding while leaving the real thread-safety gap
  (three unlocked cross-thread accesses) open — the audit calls both out together for a reason.
- *Add a new, engine-private lock instead of reusing `DictationState.lock`.* Rejected: no functional
  difference, but it leaves an unused field sitting in `DictationState` for no reason and adds a
  second lock name to reason about; reusing the existing field is strictly simpler.

## Risks / Trade-offs

- [Trigger-worker thread itself stalls (e.g. a genuinely slow AX read or audio-open retry) and the
  queue backs up under rapid tapping] → Mitigation: this is no worse than today's synchronous
  behavior from the *engine's* point of view — the work still happens, just off the OS-owned callback
  thread, which was the actual bug (a slow *OS* tap callback risks the OS disabling the tap; a slow
  *our-own* worker thread risks nothing at the OS level, at most a delayed press/release). The
  existing FSM watchdog (`RECORDING_MAX_S`/`TRANSCRIBING_MAX_S`) still backstops a truly wedged
  cycle.
- [`/stop` blocks the single-threaded HTTP server for the full transcription duration] → Not a new
  risk: `/stop` was already synchronous-by-contract before this change (that is the documented
  difference from `/stop-async`); this change only fixes *what* produces the result, not the
  blocking contract itself.
- [`_transcription_done_event.wait(timeout=...)` expires before the worker finishes (slow model,
  large recording)] → Mitigation: bounded wait returns `state.last_transcription` best-effort
  (possibly still the previous cycle's value or `None`) rather than hanging the HTTP thread forever,
  matching the existing bounded-wait pattern (`_drain_chunk_queue`); a follow-up `GET /status` or
  `/last-transcription` still reflects the eventual real result once the worker completes.
- [Concurrent hardware trigger release and HTTP `/stop`] → Both call `Engine.stop_recording()`; the
  pre-existing `StateMachine.stop_recording()` TOCTOU (see Context) means both could observe
  `transitioned = True` in a narrow window, each then racing to set/clear `stop_event` and wait on
  `_transcription_done_event`. This is an existing, narrow, pre-existing limitation not introduced or
  worsened by this change (today it already applies to e.g. two rapid consecutive hardware
  releases); flagged here as a known residual risk for a future, FSM-focused change rather than
  blocking this fix.

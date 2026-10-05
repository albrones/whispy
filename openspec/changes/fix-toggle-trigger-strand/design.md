## Context

See `proposal.md` — Why, for the measurements and the failure shape.

Three facts about the current code shape the approach:

**The listener already has a polling loop.** `EventTapListener.start` runs its own thread whose body is:

```python
while not self._stop_event.is_set():
    CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.5, False)
```

It already wakes twice a second and does nothing with the wake. A liveness check costs one call per wake on a thread that exists, on a schedule that exists.

**Recovery is currently reachable only through the channel being recovered.** `_event_callback` handles `kCGEventTapDisabledByTimeout` / `kCGEventTapDisabledByUserInput` by calling `CGEventTapEnable(tap, True)`. That is correct when the notification arrives, and self-defeating as the *only* path: the notification is delivered through the same tap whose health is in question, and it is delivered once. Nothing retries, nothing verifies.

**Press and release are not symmetric under toggle mode.** In hold mode, press starts and release stops — losing either is recoverable from the live modifier flag state, which is what `_resync_after_rearm` does. In toggle mode `_handle_trigger_release_signal` returns immediately and only the press carries meaning. A press is an *edge*, not a state: no amount of reading live flags after the fact reveals whether one occurred while the tap was down. This asymmetry is why the existing recovery is structurally unable to help a toggle user, and why this design does not extend it to presses.

The causal chain from `type_while_speaking` → synthetic keystroke burst → tap disablement is inferred, not observed, because the diagnostics that would confirm it are written to a discarded stream. That is the first thing this change fixes, and it is why the ordering below is not arbitrary.

## Goals / Non-Goals

**Goals:**

- A disabled event tap returns to service within 500 ms regardless of how it was disabled or whether the disablement notification was delivered.
- The next occurrence produces evidence in `~/.whispy.log` and `~/.whispy-error.log` rather than silence.
- Existing `print(..., file=sys.stderr)` diagnostics throughout the codebase become readable without touching their call sites.

**Non-Goals:**

- Eliminating the disablement itself. This design makes disablement survivable, not impossible. Removing the synthetic-event flood belongs to `fix-dictation-text-fidelity`'s `copy_to_clipboard` flip.
- Recovering the specific press that was lost during the outage. One missed press means "press again", which is an acceptable outcome; a restart is not.
- Any change to hold-mode behavior, to `_resync_after_rearm`'s existing release recovery, or to the watchdog's timeouts.

## Decisions

### 1. Poll `CGEventTapIsEnabled` in the run loop rather than only reacting to the disablement event

Add the check to the existing 500 ms wake:

```
while not stop:
    CFRunLoopRunInMode(default_mode, 0.5, False)
    if tap is not None and not CGEventTapIsEnabled(tap):
        CGEventTapEnable(tap, True)
        logger.warning("[event-tap] tap was disabled — re-enabled by liveness check")
```

**Why this over the alternatives:**

- *Keep event-driven recovery only, fix the specific disablement cause.* Rejected: it requires the cause theory to be exactly right, and the theory is currently unverifiable (see Context). The liveness check is correct for every cause, including causes not yet identified.
- *Filter Whispy's own synthetic events out of the tap by event source.* Rejected as the primary fix, though it is the tidier model. It is a strictly larger change (source tagging on the injection side, source inspection on the tap side, and `osascript`/System Events posts events under System Events' identity, not Whispy's — so the tag is not straightforwardly available). It also addresses only the self-inflicted share of disablements and would still leave the tap dead if a disablement notification were ever missed.
- *Unconditionally call `CGEventTapEnable(tap, True)` every pass without checking.* Tempting — it is idempotent and one line shorter. Rejected because the check is what makes the recovery *observable*: an unconditional enable cannot distinguish "healthy" from "recovered 340 times this session", and observability is half the point of this change.

The event-driven handler in `_event_callback` is **kept**, not replaced. When the notification does arrive it recovers in microseconds instead of up to 500 ms, and it carries the disablement *reason* (`ByTimeout` vs `ByUserInput`), which the liveness check cannot recover and which is exactly the evidence needed to confirm or refute the `type_while_speaking` theory. The two paths are belt and braces, and the existing `_resync_after_rearm` runs from whichever fires.

### 2. Capture stderr at the stream, not at the logging handler

The capture point is `sys.stderr` itself, replaced with a small file-like object that funnels raw writes into a `RotatingFileHandler` for `~/.whispy-error.log` and mirrors them to the original stream.

**A logging handler alone cannot do this, and an earlier draft of this design claimed it could.** Verified:

```python
logging.basicConfig(handlers=[RotatingFileHandler("err.log", ...)])
print("RAW STDERR PRINT", file=sys.stderr)   # -> terminal only
logging.warning("LOG RECORD")                 # -> err.log
# err.log contents: 'WARNING:root:THIS IS A LOG RECORD\n'
```

Handlers receive *log records*. `print(..., file=sys.stderr)` never enters the logging system, so it never reaches a handler. There are 35 such call sites across 10 modules, so "no call-site edits" was load-bearing rather than incidental — a handler-only fix would have captured nothing this change exists to capture, while appearing to work.

Wrapping the stream keeps that property: all 35 sites, plus uncaught thread tracebacks routed through `threading.excepthook` (which resolves `sys.stderr` at raise time), are captured with no call-site edits. Rotation stays `RotatingFileHandler`'s job rather than hand-rolled.

**Ordering is load-bearing.** `logging.StreamHandler()` binds `sys.stderr` once, at construction. So `basicConfig` runs *first* — its console handler keeps the real stream — and the swap happens *after*. Reversed, the console handler would bind to the wrapper and every INFO log record would be duplicated into the error log, turning it into a second copy of `~/.whispy.log`. This needs a comment at the call site; it reads like reorderable setup and is not.

Mirroring to the original stream is not only a dev convenience: the validation harness reads the daemon's stderr from its subprocess, and swallowing it would break that.

The tap's own diagnostics *additionally* move from `print` to `logger.warning`, so they appear in `~/.whispy.log` alongside the `[fsm]` and `[audio]` lines they must be correlated against. That correlation is the whole diagnostic value: a re-arm line has to be readable *next to* the `IDLE -> RECORDING` it strands. The two mechanisms are complementary, not redundant — stream capture makes a diagnostic survive, the logger conversion puts it where it can be read in context.

*Alternatives considered:*

- *Convert all 35 `print(file=sys.stderr)` sites to `logger`.* Rejected: the largest diff of the three, it still loses uncaught thread tracebacks, and it touches 10 modules for a change about the event tap. Individual conversions can happen when those files are touched for other reasons.
- *Redirect at the file-descriptor level with `os.dup2`.* Rejected for now, though it is the most faithful: it would additionally capture PortAudio's C-level writes to fd 2, which bypass `sys.stderr` entirely. It makes rotation external or hand-rolled and makes the daemon harder to run in a terminal. Worth revisiting if PortAudio diagnostics ever become the thing being chased.

### 3. Report a mid-recording re-arm; do not synthesize a press

When the tap re-arms while the FSM is in `RECORDING` and `trigger_mode` is `toggle`, log at WARNING and identify it as a possible lost stop-press.

Synthesizing a press was considered and rejected on asymmetry grounds. A synthesized *release* (what the code does today for hold mode) is safe because it is verifiable against live modifier flags and because a spurious release only stops a recording the user had already ended. A synthesized *press* is neither: it cannot be verified after the fact, and a spurious one **ends a dictation the user is still speaking into** — converting a recoverable annoyance ("press again") into data loss. Detection and disclosure only.

Whether the report should also reach the UI (a menu-bar state nudge telling the user to press again) is deferred; the log line is the part this change commits to.

### 4. Ordering: logging lands before the liveness check

The stderr capture and the WARNING conversions ship first, independently verifiable, because they are what turns the next occurrence into evidence. If the liveness check shipped first and the strands stopped, the cause would remain unproven and the `type_while_speaking` interaction undocumented; if the strands *continued*, there would still be nothing to read.

## Risks / Trade-offs

- **The strand is not the tap at all — the trigger-worker thread is blocked inside `sounddevice`'s `stream.stop()`.** `AudioEngine.stop` (`audio.py:476`) calls `self._stream.stop()` / `.close()` on the trigger-worker thread and logs *nothing* before doing so; `capture closed` is only emitted after the close returns. A PortAudio close that blocks is indistinguishable in the current log from a press that never arrived — both produce exactly the observed silence. → This change does not fix that case, but it does make it distinguishable: with the liveness check logging, a strand with no re-arm line and no `capture closed` points at the audio close, not the tap. A confirmed audio-close block is a separate change, not a modification to this one. See Open Questions.
- **A liveness check every 500 ms on the listener thread.** → One `CGEventTapIsEnabled` call per wake on a thread that already wakes at that rate. Negligible, and on the listener's own thread rather than the callback path, so it cannot itself contribute to a `ByTimeout` disablement.
- **A tap disabled and re-enabled in a tight loop would emit a WARNING every 500 ms and flood the log.** → The log is already rotating (`maxBytes=1_000_000, backupCount=3`), so the bound exists. If the flood proves real in practice, rate-limit to one line per disablement episode (log on the healthy→disabled edge, not on every failing check). Not pre-built: the edge-triggered form is the natural implementation of decision 1 anyway.
- **`~/.whispy-error.log` reintroduces a file that can grow.** → Rotating handler with the same bounds as `~/.whispy.log`, satisfying the existing `core-engine` requirement that the daemon log rotate rather than grow unbounded.
- **Recovery within 500 ms still loses the press that landed inside the window.** → Accepted, and stated as a non-goal. The failure mode degrades from "restart the app" to "press again", and decision 3 makes the cause visible when it happens.

## Migration Plan

No migration. No config, API, or data changes; no user action. The `~/.whispy-error.log` file is created on next daemon start.

Rollback is per-decision and independent: reverting the liveness check restores today's event-driven-only recovery, and reverting the logging handler restores today's discarded stderr. Neither depends on the other at runtime.

Validation is a live drive on macOS in the user's own configuration (toggle mode, Right Option, `type_while_speaking: true`, `copy_to_clipboard: false`) — the configuration every existing mitigation missed, and the one `fix-fsm-hang-recovery` task 5.2 still has open. Success is the re-arm WARNING appearing in `~/.whispy.log` under a live-typing dictation with the hotkey still working afterwards.

## Open Questions

- **During a strand, was the menu bar still responsive and the waveform pill still animating?** The user has not yet answered. It does not change this design — decisions 1, 2, and 4 are correct regardless, and decision 3 is scoped to detection — but it predicts what the instrumentation will show: a responsive menu bar with an animating pill means the tap was dead (this change is the fix); a responsive menu bar with a *frozen* pill means the trigger worker is blocked in the audio close (this change surfaces it, and a follow-up fixes it); an unresponsive menu bar means an AppKit/rumps deadlock, which is a third bug and out of scope here.
- **Should a mid-recording re-arm also nudge the UI**, not just the log? Deferred per decision 3 — answerable after the first logged occurrence shows how often it actually happens, and it changes neither the specs nor the task breakdown.

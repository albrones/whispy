## Context

Two intermittent macOS bugs (pill missing over full-screen apps; settings reverting after restart) trace to the same condition: **two daemons running at once**. The `:9090` HTTP bind was the implicit singleton lock, but `start_http_server` (`server.py:257-273`) walks ports 9090→9099 on `OSError`, so a second instance never fails — it drifts to 9091 and keeps running. Restart (`menu_bar.py:412-423`) uses `open -n` (force a *new* instance) + `sleep 1` + quit, which leaves a window where old and new overlap.

Why each symptom follows:
- **Pill**: "fixed by restart" means a fresh process renders it correctly; a stale overlapping instance, or per-show Space resolution against a stale screen, puts it on the wrong Space.
- **Settings**: the on-disk config currently holds custom values, so the load/save path is sound — the reset is conditional on overlap/stale-bundle, not a logic bug in `config.py`.

Constraints: macOS accessory (`LSUIElement`) app; AppKit calls on main thread; the `:9090` bind must stay the lock (no new dependency — ponytail). `HTTPServer` already sets `allow_reuse_address=True`, so `SO_REUSEADDR` lets a *dead* instance's `TIME_WAIT` socket be rebound while a *live* `LISTEN` by another process still rejects the bind — exactly the semantics a singleton lock needs.

## Goals / Non-Goals

**Goals:**
- Exactly one daemon at a time; a second instance fails fast with a clear log and non-zero exit.
- Remove the port fallback — never drift off `:9090`.
- Restart reliably ends with exactly one instance (no overlap, and crucially no *zero*-instance outcome once fallback is gone).
- Pill appears over the active full-screen Space on every recording, without a restart.

**Non-Goals:**
- No PID files, flock, or `NSRunningApplication` singleton framework — the port bind is the lock.
- No rework of `config.py` load/save (it is correct).
- No redesign of the waveform rendering (`WaveformView`) — only its window placement/elevation lifecycle.
- Not reconciling the stale "ferrofluid" wording in the existing `recording-visualization` spec (tracked separately).

## Decisions

### D1 — `:9090` exclusive bind is the lock; drop the fallback loop
`start_http_server` loses the `for port in range(...)` loop and binds `127.0.0.1:9090` exactly once. On `OSError` it raises. **Call it early** in `whispy_daemon` startup — before the event tap, audio capture, and model load — so a second instance dies before doing any expensive or device-grabbing work. `main()` catches the bind failure, logs `another instance is already running`, and exits non-zero.

- *Alternatives:* PID file (stale-PID races, needs cleanup on crash); `flock` on a lockfile (extra file, same race surface); `NSRunningApplication`/`LSMultipleInstancesProhibited` in Info.plist (only covers the `.app` path, not the loose-script/venv daemon). Rejected — the port already is a lock that covers both run modes, with zero new state.

### D2 — Restart hands off the lock instead of racing it
Removing the fallback makes restart *more* fragile if left as-is: if the new instance binds before the old releases, it now **fails** instead of drifting (restart → zero instances). Fix the sequencing:
- The old instance quits first; the detached relaunch helper **polls `127.0.0.1:9090` until it stops accepting connections** (old instance gone), with a timeout (~5 s) fallback, then launches.
- Drop `open -n` → use `open <bundle>` (no force-new); for the source/venv path, the re-exec already starts after quit, but it gains the same "wait for port free" poll.

`allow_reuse_address=True` (already set) means the old socket's `TIME_WAIT` won't block the new bind once the old *process* is gone — so the poll only needs to wait for the process to stop listening, not for `TIME_WAIT` to drain.

- *Alternatives:* fixed `sleep` (current; a guess that's both too long and unreliable); have the new instance retry the bind in a loop (contradicts "fail fast" and hides double-launch bugs). Rejected.

### D3 — Re-apply Space behavior on every pill show
Keep lazy window creation, but move the Space-sensitive setup into `_show_on_main` so it runs every time, not once at init:
- Re-apply `setCollectionBehavior_(CanJoinAllSpaces | FullScreenAuxiliary | Stationary | IgnoresCycle)` and `setLevel_(NSScreenSaverWindowLevel)` per show (idempotent, cheap).
- Resolve the target screen against the **active** screen each show rather than trusting a value cached from first init.
- Order front with `orderFrontRegardless()` so the non-activating panel joins the active Space (including a full-screen one) without stealing focus.

This satisfies the spec's "re-applied and position resolved against the active Space each time it is shown" and is the visualization-side belt to D1's systemic fix.

- *Alternatives:* destroy + recreate the window on every show (heavier, flicker risk). Rejected — re-applying behavior is enough.

## Risks / Trade-offs

- **Restart yields zero instances if the poll mis-times** → mitigated by D2's port-free poll with a bounded timeout that launches anyway; `allow_reuse_address` prevents a `TIME_WAIT` false-block.
- **A genuinely wedged old process never releases `:9090`** → second instance correctly refuses to start; user sees the clear log and can kill the stuck process. This is the intended singleton behavior, not a regression.
- **Per-show re-apply doesn't fully fix a multi-display full-screen edge** → acceptable; D1 removes the dominant cause (overlap). Remaining multi-monitor nuance can be a follow-up.
- **Validation harness / `WHISPY_CONFIG` headless runs** also bind `:9090` → already isolated by env/port in the harness; confirm the harness path still starts (it sets its own port/config).

## Migration Plan

1. Land D1 (server single-bind) + D2 (restart hand-off) together — D1 alone would make restart flaky.
2. Land D3 (pill per-show) independently; it has no dependency on D1/D2.
3. Rollback: revert is clean (restore the fallback loop and `open -n`); no persisted state or schema changes.

## Open Questions

- Should the "already running" second instance surface a user-visible alert (NSAlert) in the `.app` path, or is a log line + exit enough? (Default: log + exit; alert only if users hit it.)
- Confirm the current call order in `whispy_daemon.main()` so the HTTP bind moves ahead of model load without breaking token/auth setup.

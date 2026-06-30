## Why

Two reported macOS bugs share one root cause. Restart (`_on_reload`) relaunches via `open -n` (always a *new* instance) while `start_http_server` falls back across ports 9090→9099 when the port is busy. The `:9090` bind was the de-facto singleton lock; the port fallback defeats it, so a stale daemon and a fresh one can run in parallel. Symptoms: (1) the recording pill sometimes fails to appear over another app's full-screen Space and only "comes back" after a restart; (2) settings occasionally revert to defaults after a restart instead of persisting. Both are intermittent because they depend on whether two instances overlap.

## What Changes

- The daemon binds `:9090` as an **exclusive single-instance lock**: a second instance fails fast (clear log + exit) instead of drifting to 9091+. **BREAKING** for any workflow that relied on a fallback port — none is intended.
- Restart releases `:9090` *before* the replacement instance binds it, so the new instance is guaranteed to be the only one (no `open -n` overlap window leaving two daemons alive).
- The waveform pill is positioned/elevated for the **currently active Space** on every `show()` (not only the first lazy init), so it reliably floats over full-screen apps without requiring a restart.

## Capabilities

### New Capabilities
- `single-instance-lock`: Guarantee at most one Whispy daemon runs at a time — the `:9090` bind is an exclusive lock, a second instance exits fast, and the restart flow hands the port from old to new without overlap.

### Modified Capabilities
- `recording-visualization`: The floating pill SHALL reliably appear above the active Space — including another application's full-screen Space — on every recording start, not only on a freshly launched process.

## Impact

- `src/whispy/api/server.py` — `start_http_server` port-fallback loop removed/replaced with a single exclusive bind.
- `src/whispy/ui/menu_bar.py` — `_on_reload` restart sequencing (release before relaunch).
- `src/whispy/ui/waveform_window.py` — per-show Space targeting / window elevation.
- `whispy_daemon.py` — startup handling when the lock is already held (fail fast with a clear message).
- Tests: `tests/` (server bind, restart, waveform show) — guard the singleton and the over-fullscreen behavior.

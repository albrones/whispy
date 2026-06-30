## 1. Single-instance lock (server)

- [x] 1.1 Remove the port-fallback loop in `start_http_server` (`src/whispy/api/server.py:257-273`); bind `127.0.0.1:9090` exactly once and let `OSError` propagate (keep `allow_reuse_address=True`).
- [x] 1.2 Confirm/adjust `whispy_daemon.py` call order so `start_http_server` runs **before** event-tap, audio capture, and model load.
- [x] 1.3 In `whispy_daemon.main()` (and `run_headless`), catch the bind `OSError`, log `another instance is already running on :9090`, and exit non-zero before any device/model init.
- [x] 1.4 Verify the validation harness path (`WHISPY_CONFIG` / headless) still starts — it must use its own port/config and not trip the lock.

## 2. Restart hand-off (menu)

- [x] 2.1 Rewrite `_on_reload` (`src/whispy/ui/menu_bar.py:412-423`): the relaunch helper polls `127.0.0.1:9090` until it stops accepting connections (old instance gone), with a ~5 s timeout fallback, then launches.
- [x] 2.2 Drop `open -n` → use `open <bundle>` (no force-new) for the `.app` path; apply the same "wait for port free" poll before the source/venv re-exec path.
- [x] 2.3 Quit the current instance only after the relaunch helper is detached, so the helper outlives it.

## 3. Pill over full-screen (visualization)

- [x] 3.1 Move per-Space setup into `_show_on_main` (`src/whispy/ui/waveform_window.py`): re-apply `setCollectionBehavior_(CanJoinAllSpaces | FullScreenAuxiliary | Stationary | IgnoresCycle)` and `setLevel_(NSScreenSaverWindowLevel)` on every show (idempotent).
- [x] 3.2 Resolve the target screen against the active screen on each show instead of a value cached at first init; keep `orderFrontRegardless()`.
- [x] 3.3 Verify click-through (`setIgnoresMouseEvents_(True)`) and non-activating panel behavior are preserved after the per-show re-apply.

## 4. Tests

- [x] 4.1 Test: `start_http_server` raises (no fallback) when `:9090` is already bound; succeeds when free.
- [x] 4.2 Test: a simulated second daemon startup exits non-zero / logs "already running" without initializing audio/model (mock the heavy init).
- [x] 4.3 Test: `_on_reload` waits for the port to free before launching and never forces a parallel instance (mock the launcher + port probe).
- [x] 4.4 Test/guard: `WaveformWindow.show()` re-applies collection behavior + level each call (assert on a fake/spy NSWindow).

## 5. Verify & docs

- [ ] 5.1 Manual: with a full-screen app frontmost, start recording repeatedly — pill appears each time without restart; restart leaves exactly one `Whispy` process (`pgrep -fl Whispy`) and preserves custom settings.
- [x] 5.2 Update `MANUAL_TEST_PLAN.md` with the dual-instance + full-screen-pill checks.

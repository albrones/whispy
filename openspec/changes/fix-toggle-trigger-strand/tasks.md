## 1. Make the diagnostics readable

Ships first and independently. Per `design.md` decision 4, the instrumentation
must land before the fix, or the next occurrence proves nothing either way.

- [x] 1.1 Add a file-like stderr wrapper in `whispy_daemon.py` that funnels raw writes into a `RotatingFileHandler` for `~/.whispy-error.log` (1 MB, 3 backups, UTF-8) and mirrors them to the original stream; buffer by line, since `print` issues separate `write()` calls for the text and the newline. Verify with a unit test that writing a line to the wrapper appends it to the file and passes it through to the mirror
- [x] 1.2 Install the wrapper in `whispy_daemon.py` **after** `logging.basicConfig`, with a comment stating why the order matters (`StreamHandler()` binds `sys.stderr` at construction; swapping first would duplicate every log record into the error log). Verify with a test that a `print(..., file=sys.stderr)` reaches the error log while an INFO log record does **not** — the assertion that pins the ordering, covering the "A stderr diagnostic is readable" and "The error log is bounded" scenarios
- [x] 1.3 Convert the **recovery** `print(..., file=sys.stderr)` diagnostics in `src/whispy/hardware/event_tap.py` to `logger.warning` / `logger.exception` so they land in `~/.whispy.log` next to the `[fsm]` / `[audio]` lines they must be correlated against; verify existing `tests/test_event_tap_e2e.py` still passes and assertions on those messages target the logger. Startup *failure guidance* (Quartz missing, `CGEventTapCreate` failed, run-loop timeout, unparseable trigger) deliberately stays on stderr: it addresses the user at launch rather than an operator reading a session back, it has its own spec requirement and `capsys` tests, and task 1.1's capture now files it in `~/.whispy-error.log` regardless
- [x] 1.5 Convert the **startup confirmation** print to `logger.info` in `src/whispy/hardware/event_tap.py` and `src/whispy/platform/linux/hotkey.py`. Task 1.3 moved the stderr diagnostics but left this one on stdout, which the bundled `.app` discards outright — `grep event-tap ~/.whispy.log` returned nothing on a live daemon whose listener was demonstrably active. The failure guidance stays on stderr as 1.3 decided; `test_startup_log_shows_combination_string` now asserts through `caplog`
- [x] 1.4 Run `./.venv/bin/pytest tests/test_logging_setup.py tests/test_config_validation.py tests/test_event_tap_e2e.py` and confirm green before starting group 2

## 2. Make the event tap self-healing

- [x] 2.1 Import `CGEventTapIsEnabled` in `src/whispy/hardware/event_tap.py` alongside the existing Quartz imports; verify the module still imports cleanly when Quartz is absent (the `QUARTZ_AVAILABLE` fallback path) via the existing import-guard test
- [x] 2.2 Extract the liveness probe as a small method on `EventTapListener` (check `CGEventTapIsEnabled`, re-enable + log on the healthy→disabled edge only) so it can be driven directly from a test without running a CFRunLoop; verify by calling it against a mocked disabled tap and asserting `CGEventTapEnable` was called once with `True`
- [x] 2.3 Call the probe once per pass in the `_run` loop, after the existing `CFRunLoopRunInMode(..., 0.5, False)`; verify the loop still exits promptly on `stop()` (existing listener lifecycle test stays green)
- [x] 2.4 Add the "tap disabled without a disablement event reaching the listener" test to `tests/test_event_tap_e2e.py`: mocked tap reports disabled, no callback invoked, probe re-enables and logs at WARNING
- [x] 2.5 Add the "healthy tap is not repeatedly re-enabled" test: probe against an enabled tap performs no re-enable and emits no log line (this is what keeps the recovery countable rather than a per-tick flood)
- [x] 2.6 Confirm the event-driven handler in `_event_callback` is retained and still logs the disablement *reason*; verify the two existing `test_disabled_by_timeout_rearms_tap` / `test_disabled_by_user_input_rearms_tap` tests pass unchanged apart from asserting on the logger

## 3. Report a lost toggle-mode stop-press

- [x] 3.1 Expose the tap re-arm to the engine (a callback fired by both recovery paths); verify the existing `_resync_after_rearm` release-recovery behavior is untouched by re-running `test_combination_rearm_does_not_synthesize_release`
- [x] 3.2 In `src/whispy/core/engine.py`, log at WARNING when a re-arm lands while the FSM is in `RECORDING` and `trigger_mode` is `toggle`, naming a possibly-lost stop-press; verify with a new `tests/test_engine.py` test that the FSM is left in `RECORDING` and no press is synthesized
- [x] 3.3 Add the "re-arm while idle" test: a re-arm in `IDLE` logs the recovery but does not report a lost stop-press
- [x] 3.4 Add the "hold-mode release recovery is unchanged" test to `tests/test_event_tap_e2e.py`, pinning the asymmetry this change deliberately preserves

## 4. Verification

- [x] 4.1 Run the full suite: `./.venv/bin/pytest` — green, with no new skips
- [x] 4.2 Run `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .` (ruff pinned 0.6.9) — clean
- [x] 4.3 Confirm `README.md`'s five existing references to `~/.whispy-error.log` are now accurate — verified after `make reinstall`: the file exists and holds the `[config] Failed to load ...` stderr diagnostic produced by deliberately corrupting the config during the 5.4 drive of `fix-config-merge-on-save`: `make app`, launch, and verify the file exists and is non-empty after a session that produces at least one stderr diagnostic
- [ ] 4.4 Live-drive on macOS in the configuration every prior mitigation missed — `trigger_mode: toggle`, `trigger: 61` (Right Option), `type_while_speaking: true`, `copy_to_clipboard: false`. Dictate long enough for live typing to fire several chunks, then stop with the trigger key. Success: the trigger still stops the recording without restarting the app, and `capture open` / `capture closed` counts in `~/.whispy.log` stay equal
- [ ] 4.5 From the same live drive, record which branch the instrumentation shows (see `design.md` — Open Questions): a re-arm WARNING present = the tap was the cause and this change fixes it; a strand with **no** re-arm line and no `capture closed` = the trigger worker is blocked in `AudioEngine.stop`'s `stream.stop()`, which is a separate change — file it rather than widening this one
- [ ] 4.6 Re-run the `capture open` vs `capture closed` count over a week of normal use; the two must stay equal. This is the only measurement that confirms the strand is actually gone rather than rarer

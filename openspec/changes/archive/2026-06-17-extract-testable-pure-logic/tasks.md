## 1. Extract event-tap decoding

- [x] 1.1 Create `src/whispy/hardware/event_decode.py` with `decode_trigger_event(event_type, keycode, flags, trigger_keycode)` (handles Fn keycode-63 secondary-flag press/release, unwraps flags tuple, returns press/release/None) and move the keycode→name table + `keycode_to_name`
- [x] 1.2 Re-export the table/`_keycode_to_name` from `event_tap.py` for compatibility; rewrite `_event_callback` to delegate to `decode_trigger_event` (behavior-identical)
- [x] 1.3 Add `tests/test_event_decode.py` — press, release, flags-tuple unwrap, non-trigger keycode ignored, keycode→name known + fallback

## 2. Extract daemon path resolution

- [x] 2.1 Create `src/whispy/core/paths.py` with `resolve_daemon_script() -> Path` and `daemon_script_exists(path) -> bool`
- [x] 2.2 Rewrite `menu_bar._on_reload` to call the helpers (resolution + existence), keeping the alert/relaunch/quit as-is
- [x] 2.3 Add `tests/test_paths.py` — resolves to project-root `whispy_daemon.py`, stable across cwd, existence check true/false

## 3. Extract visualization math

- [x] 3.1 Create `src/whispy/ui/level_math.py` with `rms_to_level(rms, prev_smoothed, smoothing) -> float` (normalize ×10, clamp 1.0, EMA)
- [x] 3.2 Add `select_frame(frame_index, is_active) -> str` to `ui/unicode_anim.py` (WAVEROWS wrap when active, IDLE_FRAME when not)
- [x] 3.3 Rewrite `AudioLevelMonitor._audio_callback` to call `rms_to_level` and `menu_bar._tick_anim` to call `select_frame` (behavior-identical)
- [x] 3.4 Add `tests/test_level_math.py` and `tests/test_anim_frames.py` — clamp, EMA formula, frame wrap, idle frame

## 4. Surface injection pure behaviors

- [x] 4.1 Confirm `injection.py` quote-escape / empty no-op / mode selection are reachable for unit tests without `osascript`; extract a tiny pure helper only if needed (no behavior change)
- [x] 4.2 Ensure `tests/test_injection.py` asserts escaping, empty no-op, and mode selection at `unit-pure` level (add cases if missing)

## 5. Coverage + spec sync

- [x] 5.1 Narrow `pyproject.toml` `coverage.run.omit`: replace `ui/*` with the specific Cocoa/rumps files (`menu_bar.py`, `waveform_window.py`, `indicator_window.py`, `audio_level.py`); keep `event_tap.py` omitted (new pure modules now covered)
- [x] 5.2 Apply spec deltas into canonical specs: `event-listener`, `core-engine`, `recording-visualization`, `text-injection` (with re-tiered scenarios)
- [x] 5.3 Run full suite — must stay green (≥ prior 351) with new pure tests added and zero behavior change

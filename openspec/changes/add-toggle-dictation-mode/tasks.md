## 1. Config: `trigger_mode`

- [x] 1.1 Add `"trigger_mode": "hold"` to `DEFAULT_CONFIG` in `core/config.py`, documented as hold = push-to-talk (current behavior), toggle = press to start / press to stop
- [x] 1.2 Validate in `_validate_config`: must be one of `{"hold", "toggle"}`; anything else falls back to `"hold"` with the standard stderr line
- [x] 1.3 Confirm `_migrate_config`'s missing-default fill covers an existing config with no `trigger_mode` (no version-specific step needed)
- [x] 1.4 Unit test in `tests/test_config_validation.py`: valid values pass through; an invalid value, a non-string, and `None` all fall back to `"hold"`; a config file without the key loads as `"hold"`

## 2. Pure decoding: modifier combinations

- [x] 2.1 Add modifier mask constants to `hardware/event_decode.py` — `MASK_SHIFT = 0x20000`, `MASK_CONTROL = 0x40000`, `MASK_OPTION = 0x80000`, `MASK_COMMAND = 0x100000` — alongside the existing `NX_SECONDARYFNMASK`, and note they mirror the values already used in `_TRIGGER_HELD_MASK`
- [x] 2.2 Add pure `parse_trigger(value) -> (keycode: int, mask: int) | None`: accepts the canonical string form `ctrl+alt+cmd+shift+<key>` (lowercase, fixed modifier order), resolves `<key>` through the name→keycode table, returns `None` for an unparseable value so the caller can fall back to the platform default
- [x] 2.3 Extend `decode_trigger_event` with an optional `required_mask` parameter: a match requires both the keycode and `(flags & required_mask) == required_mask`; `required_mask = 0` preserves today's single-key behavior exactly
- [x] 2.4 Extend `decode_key_match` (Linux path) with a `held_modifiers: frozenset[str]` parameter and the same all-required-modifiers-present rule
- [x] 2.5 Correct the keycode entries the new presets depend on in `_KEYCODE_TO_NAME`: `14 -> "e"` (currently absent) and `8 -> "c"` (currently mislabelled `"e"`); leave the rest of the letter block untouched and add a comment recording that the block is known-suspect and audited separately
- [x] 2.6 Unit tests in `tests/test_event_decode.py`: `parse_trigger("ctrl+alt+cmd+e")` yields keycode 14 and mask `0x1C0000`; an unknown key and a malformed string yield `None`; the combination matches only when every required modifier bit is set; a partial-modifier event does not match; `required_mask = 0` reproduces every existing single-key case unchanged; `keycode_to_name(14) == "e"`

## 3. Engine: toggle semantics

- [x] 3.1 Read `trigger_mode` into the engine and expose it where the trigger worker can see it (re-read on config update, like `trigger`)
- [x] 3.2 In `_trigger_worker_loop`, branch the `press` signal: in toggle mode, dispatch to `_handle_trigger_release_work()` when the FSM is RECORDING and to `_handle_trigger_press_work()` otherwise; in hold mode, dispatch to `_handle_trigger_press_work()` unchanged
- [x] 3.3 In `_trigger_worker_loop`, branch the `release` signal: in toggle mode, call `_notify_fn_released()` **only** (never `stop_recording()`); in hold mode, call `_handle_trigger_release_work()` unchanged
- [x] 3.4 Extend `update_config` so a `trigger_mode` change takes effect without a restart, alongside the existing `trigger` handling (no listener restart is required — the mode is read by the worker, not the listener)
- [x] 3.5 Unit test: in toggle mode, press → RECORDING; a second press → TRANSCRIBING; an interleaved release changes no state
- [x] 3.6 Unit test (regression guard for the `_fn_pressed` trap): in toggle mode, after a press/release pair the `_fn_pressed` flag is False, so `_wait_trigger_released()` returns immediately rather than blocking for `TRIGGER_RELEASE_INJECT_TIMEOUT_S`
- [x] 3.7 Unit test: in hold mode every existing press/release path behaves exactly as before (assert against the current tests, unmodified)

## 4. Engine: graceful recording limit

- [x] 4.1 Add a clipboard-only delivery path to the injectors — `copy_only(text)` on `hardware/injection.py` (macOS `pbcopy`, reusing the existing `_spawn` argument-passing plumbing) and on `platform/linux/injection.py` (`xclip`/`xsel`) — distinct from `inject()`, which also pastes
- [x] 4.2 Add a one-shot "deliver to clipboard instead of injecting" flag on the engine, set by the watchdog and consumed (and cleared) by the transcription worker at the point where it currently calls `_text_injector.inject(assembled)`
- [x] 4.3 Replace the watchdog's RECORDING branch: stop the audio engine, run the normal stop path so chunks drain and assemble, set the clipboard flag, and let the worker deliver; fall back to the existing `_force_recover()` if the graceful stop raises
- [x] 4.4 Add a `recording_limit_reached` engine callback (mirroring `on_capture_failed`) carrying a user-facing message, and wire `ui/menu_bar.py` to post it via the existing `rumps.notification` path and `platform/linux/tray.py` via its notifier
- [x] 4.5 Keep `RECORDING_MAX_S` at 300.0 and update its comment, which currently justifies the value with "no push-to-talk hold lasts minutes" — an assumption toggle mode invalidates
- [x] 4.6 Unit test: with a small injected timeout, a recording that exceeds the limit ends with the FSM in IDLE, the assembled text on the clipboard, `_chunk_texts` **not** discarded before delivery, and the notification callback fired once
- [x] 4.7 Unit test: a recording that completes within the limit triggers no watchdog action and injects normally (regression guard)

## 5. Trigger presets and menu surface

- [x] 5.1 Add `("⌃⌥⌘E", "ctrl+alt+cmd+e")` and `("⌃⌥⌘F", "ctrl+alt+cmd+f")` to `TRIGGER_PRESETS`, labelled by their keys — explicitly not by a language (see proposal Non-Goals)
- [x] 5.2 Verify `_trigger_is_active` and `_trigger_label` in `ui/menu_bar.py` handle a string preset value; extend `_trigger_label`'s fallback so a hand-edited combination string renders as itself rather than through `keycode_to_name`
- [x] 5.3 Add a `Toggle mode` checkbox to the Settings section of `ui/menu_bar.py`, copying the `_on_toggle_copy` / `menu_theme.toggle_title` pattern, and include it in `_refresh_accents` so it re-renders on an appearance flip
- [x] 5.4 Add the equivalent toggle item to `platform/linux/tray.py`
- [x] 5.5 Wire the combination presets through to the listeners: `resolve_trigger()` returns the raw config value, `platform/detect.py` passes it through, and each listener resolves it via `parse_trigger` (macOS: keycode + mask; Linux: key name + modifier set)
- [x] 5.6 Track held modifiers in `PynputHotkeyListener` (add on modifier key-down, discard on key-up, clear on `start()`) and pass the set to `decode_key_match`
- [x] 5.7 Confirm `trigger_held_after_rearm` behaves correctly for a combination trigger and change no logic: a combination's trigger key is a *regular* key absent from `_TRIGGER_HELD_MASK`, so the helper already returns `None` and `_resync_after_rearm` correctly declines to synthesize a release — a regular key's release is a `key_up` that live modifier flags cannot reconstruct. Record that reasoning in a comment; the FSM watchdog remains the backstop. (This task's original wording asked to extend the mask, which would have defeated the invariant the module documents.)
- [x] 5.8 Unit test: selecting a combination preset persists it, moves the checkmark, and updates the submenu title; toggling `Toggle mode` persists `trigger_mode` and updates its title

## 6. Documentation and website

- [x] 6.1 Update `website/index.html`: document toggle mode and the two combination presets in the feature cards and the menu-bar demo, per the project's keep-the-website-in-sync convention
- [x] 6.2 Extend `tests/test_website.py` with a floor assertion that the toggle mode is mentioned
- [x] 6.3 Update `README.md` and `docs/SPECIFICATION.md` where the trigger is described as hold-only
- [x] 6.4 Add a `CHANGELOG.md` entry covering both the toggle mode and the recording-limit behavior change (the latter is user-visible: text is now preserved and announced instead of discarded)

## 7. Verification

- [x] 7.1 Run `./.venv/bin/pytest` — existing and new tests green
- [x] 7.2 Live-drive on macOS: with `⌃⌥⌘E` in toggle mode, one press starts (pill appears, waveform reacts), a second press stops and injects; confirm the injected text carries no modifier-layer mangling. **Confirmed by the operator.** First run exposed two defects (pill hidden on the physical key release; the stopping press clearing the trigger-held flag while the keys were down) — both fixed and guarded by regression tests before re-confirmation.
- [ ] 7.3 Live-drive: confirm hold mode with Fn is unchanged
- [ ] 7.4 Live-drive: exceed the recording limit in toggle mode and confirm the notification appears and the text is on the clipboard
- [x] 7.5 Note in the PR which combination-decode paths were exercised on a real event tap versus only in unit tests (per `openspec/specs/TESTING-TIERS.md`). **Recorded here:** every combination decode path (`parse_trigger`, the `required_mask` gate, `split_trigger_combination`, `canonical_modifier`, the held-modifier tracking) is covered at the unit-pure tier only. No assertion in this change has run against a live `CGEventTap` or a live X11 `pynput` listener; tasks 7.2-7.4 are the platform-real tier and remain outstanding.

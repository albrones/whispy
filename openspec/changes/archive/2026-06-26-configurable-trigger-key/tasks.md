## 1. Trigger presets (config)

- [x] 1.1 Add `TRIGGER_PRESETS` (ordered list of `(label, value)` where value is `None` for Fn or an int keycode) to `src/whispy/core/config.py`.
- [x] 1.2 Confirm each non-`None` preset keycode against `_KEYCODE_TO_NAME` and a real CGEventTap (Right Command / Right Option / F13 decode to a clean press+release); drop or fix any that don't. **Table verified (test 1.3); Caps Lock dropped (toggle key); real-tap confirmed live — all presets fire.**
- [x] 1.3 Add a runnable check asserting every non-`None` preset keycode is present in `_KEYCODE_TO_NAME` (`tests/test_config_validation.py::TestTriggerPresets`).

## 2. Live-apply listener restart (engine)

- [x] 2.1 In `engine.update_config`, when `"trigger"` is in updates and `self.state.fn_listener_active`, call `stop_fn_listener()` then `start_fn_listener()`.
- [x] 2.2 Verify `start_fn_listener` reads the freshly-saved trigger via `resolve_trigger()` (it already does — assert via test).
- [x] 2.3 Unit test (hotkey adapter mocked): updating `trigger` while active stops+starts the listener with the new value; updating while inactive does not start it.

## 3. Trigger submenu (menu bar UI)

- [x] 3.1 Replace `fn_status_item` with a `Trigger` submenu built from `TRIGGER_PRESETS`, mirroring the Model/Language submenu construction; store items in `self._trigger_items` with `item._trigger_value` and `item._label`.
- [x] 3.2 Add `_update_trigger_title` (title = `Trigger: <label or keycode_to_name>` for the active trigger) and call it on build and after selection.
- [x] 3.3 Add `_on_trigger_select`: read `item._trigger_value`, call `engine.update_config({"trigger": value})`, move the checkmark, refresh the title.
- [x] 3.4 Active-trigger match: Fn = `config["trigger"] in (None, "")`; otherwise compare to stored keycode. Unknown configured value → no check, title via `keycode_to_name`.
- [x] 3.5 Register `_trigger_items` in `_refresh_accents` so titles rebuild on appearance flip.
- [x] 3.6 Swap `fn_status_item` for `self.trigger_menu` in the `self.menu` list.

## 4. Verification

- [x] 4.1 Run the unit/pure suite (`test_event_decode.py`, `test_config_validation.py`, engine config tests) green. **Full suite: 529 passed, 1 skipped. ruff clean.**
- [x] 4.2 Manual (macos-real): pick each preset, confirm the title/check update and that hold-to-talk works with the new key without a Restart; confirm Fn still works as default. **Verified from source. Fixed a stale-✓ visual bug in `menu_theme` (unchecked rows must return an attributed string so `setAttributedTitle_` clears the old check — AppKit's attributedTitle outranks .title); fix also covers Model/Language/copy-toggle.**
- [x] 4.3 `openspec validate configurable-trigger-key --strict`.

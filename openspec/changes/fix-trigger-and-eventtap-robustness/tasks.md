## 1. Keycode map (event_decode.py)

- [ ] 1.1 Map keycode 63 → `"fn"`; move `"f5"` to keycode 96
- [ ] 1.2 Confirm the startup banner / any UI reading `keycode_to_name(63)` now shows `"fn"`

## 2. Modifier trigger press/release (event_decode.py)

- [ ] 2.1 Track prior modifier flags; for a non-default `flags_changed` trigger, derive press vs. release from the flag bit
- [ ] 2.2 Ensure a pure-modifier trigger emits a matching release so recording stops

## 3. Event-tap auto-recovery (event_tap.py)

- [ ] 3.1 Detect `kCGEventTapDisabledByTimeout` / `kCGEventTapDisabledByUserInput` and call `CGEventTapEnable(tap, True)`
- [ ] 3.2 Wrap `on_trigger_press` / `on_trigger_release` invocations in `try/except` (log; keep tap alive)

## 4. Linux hotkey robustness (linux/hotkey.py)

- [ ] 4.1 Call `is_wayland_session()` in `start()` and emit the Wayland guidance message
- [ ] 4.2 Reset `_held = False` in `start()`

## 5. Tests

- [ ] 5.1 `keycode_to_name(63)` == `"fn"`; keycode 96 == `"f5"`
- [ ] 5.2 A modifier-key trigger event stream decodes to a press followed by a release
- [ ] 5.3 A tap-disabled event triggers a re-arm call
- [ ] 5.4 An exception in a trigger callback does not propagate out of the tap callback
- [ ] 5.5 Linux `start()` resets `_held` and warns on a simulated Wayland session

## 6. Verification

- [ ] 6.1 Run the full test suite; confirm no regression
- [ ] 6.2 `ruff check` / `ruff format --check` on changed files
- [ ] 6.3 `openspec validate fix-trigger-and-eventtap-robustness --strict`

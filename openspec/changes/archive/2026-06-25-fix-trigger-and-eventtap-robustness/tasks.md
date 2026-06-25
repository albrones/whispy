## 1. Keycode map (event_decode.py)

- [x] 1.1 Map keycode 63 → `"fn"`; move `"f5"` to keycode 96
- [x] 1.2 Confirm the startup banner / any UI reading `keycode_to_name(63)` now shows `"fn"`

## 2. Modifier trigger press/release (event_decode.py)

- [x] 2.1 Track prior modifier flags; for a non-default `flags_changed` trigger, derive press vs. release from the flag bit
- [x] 2.2 Ensure a pure-modifier trigger emits a matching release so recording stops

## 3. Event-tap auto-recovery (event_tap.py)

- [x] 3.1 Detect `kCGEventTapDisabledByTimeout` / `kCGEventTapDisabledByUserInput` and call `CGEventTapEnable(tap, True)`
- [x] 3.2 Wrap `on_trigger_press` / `on_trigger_release` invocations in `try/except` (log; keep tap alive)

## 4. Linux hotkey robustness (linux/hotkey.py)

- [x] 4.1 Call `is_wayland_session()` in `start()` and emit the Wayland guidance message
- [x] 4.2 Reset `_held = False` in `start()`

## 5. Tests

- [x] 5.1 `keycode_to_name(63)` == `"fn"`; keycode 96 == `"f5"`
- [x] 5.2 A modifier-key trigger event stream decodes to a press followed by a release
- [x] 5.3 A tap-disabled event triggers a re-arm call
- [x] 5.4 An exception in a trigger callback does not propagate out of the tap callback
- [x] 5.5 Linux `start()` resets `_held` and warns on a simulated Wayland session

## 6. Verification

- [x] 6.1 Run the full test suite; confirm no regression
- [x] 6.2 `ruff check` / `ruff format --check` on changed files
- [x] 6.3 `openspec validate fix-trigger-and-eventtap-robustness --strict`

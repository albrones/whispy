## Why

The global-hotkey layer has three correctness bugs that break the core "hold to talk" interaction:

- **Fn keycode mislabeled "f5"**: `event_decode.py` maps keycode 63 (the default Fn trigger) to the name `"f5"`. The startup log "Trigger key listener active (key: f5)" and any UI showing the trigger name lie to the user. (F5 is actually keycode 96.)
- **Non-Fn modifier trigger latches "pressed" forever**: for a configurable trigger that emits `flags_changed` (a modifier key), the decode returns `"press"` unconditionally and there is no release path — a pure modifier never emits `key_up`, so the trigger stays "pressed" and recording never stops. The advertised configurable-trigger feature is broken for modifier keys.
- **CGEventTap is never re-armed**: macOS silently disables an event tap whose callback is slow or under heavy input (`kCGEventTapDisabledByTimeout` / `…ByUserInput`). The run loop doesn't handle those events, so the tap dies mid-session and the hotkey stops working with no error.

Plus robustness gaps: the event-tap callback invokes engine callbacks with no `try/except` (an exception can disable the tap / kill the listener thread), and the Linux hotkey listener has no Wayland guard at `start()` and never resets its `_held` debounce on restart (a missed release latches the next press out permanently).

## What Changes

- Fix the keycode→name map: 63 → `"fn"`, move `"f5"` to 96.
- Derive press/release for non-Fn modifier triggers from the modifier's flag bit (track prior flag state) instead of returning `"press"` unconditionally, so they emit a release.
- In the event-tap callback, detect `kCGEventTapDisabledByTimeout` / `…ByUserInput` and re-arm with `CGEventTapEnable(tap, True)`.
- Wrap the engine callback invocations in the tap callback in `try/except` (log, keep the tap alive).
- Linux: check `is_wayland_session()` in `hotkey.start()` and emit the Wayland guidance; reset `_held = False` on `start()`.

## Capabilities

### Added Capabilities
- `event-listener`: the trigger decoder SHALL correctly name the default trigger and SHALL emit a release for modifier-key triggers; the event tap SHALL re-arm after the OS disables it and SHALL isolate callback exceptions.

### Modified Capabilities
- `linux-support`: the Linux hotkey listener SHALL warn on Wayland at startup and SHALL not latch a held state across listener restarts.

## Impact

- `src/whispy/hardware/event_decode.py` — keycode map fix; modifier press/release via flag-bit tracking.
- `src/whispy/hardware/event_tap.py` — re-arm on tap-disabled events; `try/except` around engine callbacks.
- `src/whispy/platform/linux/hotkey.py` — Wayland guard in `start()`; reset `_held` on `start()`.
- `tests/` — decode of keycode 63 → `"fn"`, modifier press→release pairing, tap re-arm on disabled event, callback-exception isolation, Linux `_held` reset.

## Context

On macOS the trigger is captured via a `CGEventTap` on a dedicated background thread; the Fn key arrives as a `flags_changed` event, other keys as `key_down`/`key_up`. The decode logic in `event_decode.py` is pure and unit-tested, but its keycode table and its modifier-trigger handling have bugs. The tap itself (`event_tap.py`) has the well-known macOS failure mode where the OS disables a tap that is too slow or hit by heavy input, and the app must re-enable it.

## Goals / Non-Goals

**Goals:**
- Correct trigger naming; working press/release for any configured trigger including modifiers.
- A hotkey that survives an OS tap-disable and a misbehaving callback.
- Linux hotkey that warns on Wayland and doesn't latch.

**Non-Goals:**
- Changing the default trigger (still Fn / keycode 63).
- Implementing Wayland hotkey support (out of scope; only the warning).

## Decisions

### Keycode map
`63 → "fn"` (the documented default), and `"f5"` moved to its real keycode `96`. Anything reading `keycode_to_name(63)` (startup banner, UI) then tells the truth.

### Modifier press/release
For a non-default trigger that arrives via `flags_changed`, determine press vs. release by comparing the relevant modifier flag bit against the previously-seen flags (the same technique already used for the Fn bit), rather than returning `"press"` unconditionally. Pure-modifier triggers then produce a matching release and recording stops.

### Tap re-arm
In `_event_callback`, if the event type is `kCGEventTapDisabledByTimeout` or `kCGEventTapDisabledByUserInput`, call `CGEventTapEnable(self._tap, True)` and return — re-arming the tap in place. This is the canonical recovery for these events.

### Callback isolation
Wrap `on_trigger_press` / `on_trigger_release` invocations in `try/except Exception` (log once). An engine-side exception then cannot bubble into the pyobjc run loop and disable/kill the tap thread.

### Linux
`hotkey.start()` calls `is_wayland_session()` (already in `session.py`) and emits the existing Wayland message when true, so the user gets guidance even in the common "listener starts but receives nothing" case (not only on exception). Reset `_held = False` in `start()` so a restart after a missed release doesn't swallow the next press.

## Risks / Trade-offs

- Modifier flag-bit tracking needs the prior-flags state kept in the decoder; it is pure given the input event stream, so still unit-testable.
- Re-arming on every disabled event is safe and idempotent.

## Migration Plan

Pure correctness fixes; no config or API change. The default trigger and its keycode are unchanged — only its name label and the modifier/auto-recovery paths change.

## Open Questions

- None blocking. (Whether to also expose the corrected trigger name in the menu/UI is covered by whatever reads `keycode_to_name`.)

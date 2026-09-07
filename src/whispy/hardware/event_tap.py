"""Trigger key listener via macOS CGEventTap.

Monitors hardware-level keyboard events and notifies the core engine
of state changes via callbacks. Always uses the Fn key (keycode 63)
as the trigger key.
"""

import sys
import threading
from collections.abc import Callable
from typing import Any

QUARTZ_AVAILABLE = False

try:
    from Quartz import (
        CFMachPortCreateRunLoopSource,
        CFRunLoopAddSource,
        CFRunLoopGetCurrent,
        CFRunLoopRunInMode,
        CGEventGetFlags,
        CGEventGetIntegerValueField,
        CGEventGetType,
        CGEventMaskBit,
        CGEventSourceFlagsState,
        CGEventTapCreate,
        CGEventTapEnable,
        kCFRunLoopDefaultMode,
        kCGEventFlagsChanged,
        kCGEventKeyDown,
        kCGEventKeyUp,
        kCGEventSourceStateHIDSystemState,
        kCGEventTapDisabledByTimeout,
        kCGEventTapDisabledByUserInput,
        kCGEventTapOptionListenOnly,
        kCGHeadInsertEventTap,
        kCGKeyboardEventKeycode,
        kCGSessionEventTap,
    )

    QUARTZ_AVAILABLE = True
except ImportError:
    pass

# Trigger-event decoding and the keycode table now live in the pure, testable
# event_decode module. Re-exported here for backward compatibility (engine.py
# imports DEFAULT_TRIGGER_KEYCODE from this module, and the keycode table is a
# documented part of this module's surface).
from .event_decode import (  # noqa: E402, F401
    _KEYCODE_TO_NAME,
    DEFAULT_TRIGGER_KEYCODE,
    NX_SECONDARYFNMASK,
    _normalize_flags,
    decode_trigger_event,
    keycode_to_name,
    parse_trigger,
    trigger_held_after_rearm,
)


class EventTapListener:
    """Monitors keyboard events via CGEventTap and emits events for a configurable trigger key."""

    def __init__(
        self,
        trigger_keycode: int = DEFAULT_TRIGGER_KEYCODE,
        on_trigger_press: Callable | None = None,
        on_trigger_release: Callable | None = None,
    ) -> None:
        # ``trigger_keycode`` may arrive as a plain int keycode (unchanged
        # behavior) or as a combination string (e.g. "ctrl+alt+cmd+e") coming
        # straight from config via platform/detect.py. Resolve it once here so
        # the rest of the class only ever deals with (keycode, mask). Keep the
        # parameter name for backward compatibility — callers and tests still
        # pass a bare int.
        self._trigger_label: str | None = None
        if isinstance(trigger_keycode, str):
            parsed = parse_trigger(trigger_keycode)
            if parsed is None:
                print(
                    f"[event-tap] Unrecognized trigger '{trigger_keycode}' — "
                    "falling back to the default trigger key (Fn).",
                    file=sys.stderr,
                )
                self._trigger_keycode = DEFAULT_TRIGGER_KEYCODE
                self._required_mask = 0
            else:
                self._trigger_keycode, self._required_mask = parsed
                self._trigger_label = trigger_keycode
        else:
            self._trigger_keycode = trigger_keycode
            self._required_mask = 0
        self._on_trigger_press = on_trigger_press
        self._on_trigger_release = on_trigger_release
        self._tap = None
        self._run_loop_thread: threading.Thread | None = None
        self._run_loop_source: Any = None
        # Last-seen modifier flags, so a flags_changed for a modifier trigger can
        # be decoded as press vs release from the bit transition.
        self._prev_flags = 0
        # Whether we last emitted a press with no matching release yet. Lets the
        # re-arm path recover a modifier release that fired while the tap was down.
        self._pressed = False
        self.active = False

    def start(self) -> None:
        """Start the event tap listener in a dedicated thread."""
        if not QUARTZ_AVAILABLE:
            print(
                "[event-tap] pyobjc-framework-Quartz not installed — trigger key detection disabled.\n"
                "  Install with: pip install pyobjc-framework-Quartz",
                file=sys.stderr,
            )
            return

        # Listen for BOTH flags changed AND key down/up events
        event_mask = (
            CGEventMaskBit(kCGEventFlagsChanged) | CGEventMaskBit(kCGEventKeyDown) | CGEventMaskBit(kCGEventKeyUp)
        )

        # Listen-only: Whispy only observes the trigger key, never modifies
        # events. A listen-only session tap needs just Input Monitoring; an
        # active (modifying) tap would additionally require Accessibility.
        tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            event_mask,
            self._event_callback,
            None,
        )
        if tap is None:
            print(
                "[event-tap] CGEventTapCreate failed — grant Input Monitoring to Whispy:\n"
                "  System Settings → Privacy & Security → Input Monitoring → add Whispy\n"
                "  Then restart Whispy: menu → Restart, or `open -a Whispy`",
                file=sys.stderr,
            )
            return

        self._tap = tap
        self._run_loop_source = CFMachPortCreateRunLoopSource(None, tap, 0)
        self._ready_event = threading.Event()
        self._stop_event = threading.Event()

        def _run():
            CFRunLoopAddSource(CFRunLoopGetCurrent(), self._run_loop_source, kCFRunLoopDefaultMode)
            CGEventTapEnable(tap, True)
            self.active = True
            # A combination trigger's keycode is the plain letter/key, which
            # would print misleadingly on its own (e.g. "e" instead of
            # "ctrl+alt+cmd+e") — show the configured combination string when
            # there is one.
            key_name = self._trigger_label or _keycode_to_name(self._trigger_keycode)
            print(f"[event-tap] Trigger key listener active (key: {key_name})")
            self._ready_event.set()
            while not self._stop_event.is_set():
                CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.5, False)

        self._run_loop_thread = threading.Thread(target=_run, name="trigger-event-tap", daemon=True)
        self._run_loop_thread.start()
        if self._ready_event.wait(timeout=5.0):
            return
        else:
            print(
                "[event-tap] Timed out waiting for CFRunLoop to start — Input Monitoring may not be granted to Whispy",
                file=sys.stderr,
            )

    def stop(self) -> None:
        """Stop the event tap listener."""
        self.active = False
        self._stop_event.set()
        if self._run_loop_thread and self._run_loop_thread.is_alive():
            self._run_loop_thread.join(timeout=2)

    def _event_callback(self, _proxy: Any, _type: Any, event: Any, _refcon: Any) -> Any:
        """Callback invoked for each relevant CGEvent (pyobjc legacy signature).

        Reads the raw CGEvent fields and delegates the press/release decision to
        the pure ``decode_trigger_event`` so the OS shell holds no logic. Re-arms
        the tap if macOS disabled it, and contains exceptions from the engine
        callbacks so neither can kill the listener thread.
        """
        event_type = CGEventGetType(event)

        # macOS silently disables a tap whose callback is slow or hit by heavy
        # input. Re-enable it in place so the hotkey survives the whole session.
        if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
            if self._tap is not None:
                CGEventTapEnable(self._tap, True)
                self._resync_after_rearm()
                print("[event-tap] tap was disabled by the OS — re-armed", file=sys.stderr)
            return event

        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

        if event_type == kCGEventKeyDown:
            kind = "key_down"
        elif event_type == kCGEventKeyUp:
            kind = "key_up"
        elif event_type == kCGEventFlagsChanged:
            kind = "flags_changed"
        else:
            kind = "other"

        flags = CGEventGetFlags(event)
        action = decode_trigger_event(
            kind, keycode, flags, self._trigger_keycode, self._prev_flags, self._required_mask
        )
        # Track the latest flags so the next modifier transition decodes correctly.
        if kind == "flags_changed":
            self._prev_flags = _normalize_flags(flags)

        try:
            if action == "press":
                self._pressed = True
                if self._on_trigger_press:
                    self._on_trigger_press()
            elif action == "release":
                self._pressed = False
                if self._on_trigger_release:
                    self._on_trigger_release()
        except Exception:
            # An engine-side error must not propagate into the pyobjc run loop
            # (which can disable the tap or kill this thread).
            import traceback

            print("[event-tap] trigger callback raised:", file=sys.stderr)
            traceback.print_exc()

        return event

    def _resync_after_rearm(self) -> None:
        """Re-sync modifier flag state after the OS disabled and we re-armed the tap.

        A modifier trigger's press/release is decoded from ``flags_changed``
        transitions, so a release that fires while the tap is down is lost and
        ``_prev_flags`` is left stale (the next transition would decode inverted).
        Read the live modifier state, reset ``_prev_flags`` to it, and — if the
        trigger was held but is no longer down — emit the missed release so the
        engine cannot stay stuck in RECORDING. Degrades to re-arm-only if the
        live-flags read is unavailable.
        """
        try:
            live = CGEventSourceFlagsState(kCGEventSourceStateHIDSystemState)
        except Exception:
            return
        self._prev_flags = _normalize_flags(live)
        if not self._pressed:
            return
        # For a combination trigger (e.g. "ctrl+alt+cmd+e"), self._trigger_keycode
        # is the regular key ("e"), not a modifier — it is absent from
        # _TRIGGER_HELD_MASK, so trigger_held_after_rearm deliberately returns
        # None here. A regular key's release is a key_up event, and live
        # modifier flags cannot reconstruct whether a key_up was missed while
        # the tap was disabled. That's fine: _prev_flags is still resynced
        # above (so the next flags_changed for the *modifiers* decodes
        # correctly), and the FSM watchdog is the backstop that recovers a
        # stuck RECORDING state if the missed release is never recovered here.
        held = trigger_held_after_rearm(self._trigger_keycode, live)
        if held is False:
            # The trigger was released while the tap was disabled.
            self._pressed = False
            print("[event-tap] recovered a trigger release missed during tap outage", file=sys.stderr)
            if self._on_trigger_release:
                try:
                    self._on_trigger_release()
                except Exception:
                    import traceback

                    print("[event-tap] trigger release callback raised:", file=sys.stderr)
                    traceback.print_exc()


# Backward-compatible alias: the human-readable name lookup now lives in
# event_decode.keycode_to_name.
_keycode_to_name = keycode_to_name

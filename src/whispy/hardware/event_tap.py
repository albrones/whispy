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
        CGEventTapCreate,
        CGEventTapEnable,
        kCFRunLoopDefaultMode,
        kCGEventFlagsChanged,
        kCGEventKeyDown,
        kCGEventKeyUp,
        kCGEventTapOptionDefault,
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
    decode_trigger_event,
    keycode_to_name,
)


class EventTapListener:
    """Monitors keyboard events via CGEventTap and emits events for a configurable trigger key."""

    def __init__(
        self,
        trigger_keycode: int = DEFAULT_TRIGGER_KEYCODE,
        on_trigger_press: Callable | None = None,
        on_trigger_release: Callable | None = None,
    ) -> None:
        self._trigger_keycode = trigger_keycode
        self._on_trigger_press = on_trigger_press
        self._on_trigger_release = on_trigger_release
        self._tap = None
        self._run_loop_thread: threading.Thread | None = None
        self._run_loop_source: Any = None
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

        tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            event_mask,
            self._event_callback,
            None,
        )
        if tap is None:
            print(
                "[event-tap] CGEventTapCreate failed — grant Input Monitoring to python3:\n"
                "  System Settings → Privacy & Security → Input Monitoring → add python3\n"
                "  Then restart: launchctl kickstart -k gui/$(id -u)/com.whispy",
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
            key_name = _keycode_to_name(self._trigger_keycode)
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
                "[event-tap] Timed out waiting for CFRunLoop to start — Input Monitoring may not be granted to python3",
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
        the pure ``decode_trigger_event`` so the OS shell holds no logic.
        """
        event_type = CGEventGetType(event)
        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

        if event_type == kCGEventKeyDown:
            kind = "key_down"
        elif event_type == kCGEventKeyUp:
            kind = "key_up"
        elif event_type == kCGEventFlagsChanged:
            kind = "flags_changed"
        else:
            kind = "other"

        action = decode_trigger_event(kind, keycode, CGEventGetFlags(event), self._trigger_keycode)
        if action == "press":
            if self._on_trigger_press:
                self._on_trigger_press()
        elif action == "release":
            if self._on_trigger_release:
                self._on_trigger_release()

        return event


# Backward-compatible alias: the human-readable name lookup now lives in
# event_decode.keycode_to_name.
_keycode_to_name = keycode_to_name

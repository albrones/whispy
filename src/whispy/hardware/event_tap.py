"""Fn key listener via macOS CGEventTap.

Monitors hardware-level events (specifically the Fn key) and notifies
the core engine of state changes via callbacks.
"""

import threading
from typing import Any, Callable, Optional

QUARTZ_AVAILABLE = False

try:
    from Quartz import (
        CFMachPortCreateRunLoopSource,
        CFRunLoopAddSource,
        CFRunLoopGetCurrent,
        CFRunLoopRun,
        CGEventGetFlags,
        CGEventGetIntegerValueField,
        CGEventMaskBit,
        CGEventTapCreate,
        CGEventTapEnable,
        kCFRunLoopDefaultMode,
        kCGEventFlagsChanged,
        kCGEventTapOptionDefault,
        kCGHeadInsertEventTap,
        kCGKeyboardEventKeycode,
        kCGSessionEventTap,
    )

    QUARTZ_AVAILABLE = True
except ImportError:
    pass

FN_KEYCODE = 63
NX_SECONDARYFNMASK = 0x800000


class EventTapListener:
    """Monitors the Fn key via CGEventTap and emits events to the core engine."""

    def __init__(
        self,
        on_fn_press: Optional[Callable] = None,
        on_fn_release: Optional[Callable] = None,
    ) -> None:
        self._on_fn_press = on_fn_press
        self._on_fn_release = on_fn_release
        self._tap = None
        self._run_loop_thread: Optional[threading.Thread] = None
        self._run_loop_source: Any = None
        self.active = False

    def start(self) -> None:
        """Start the event tap listener in a dedicated thread."""
        if not QUARTZ_AVAILABLE:
            print(
                "[event-tap] pyobjc-framework-Quartz not installed — Fn key detection disabled.\n"
                "  Install with: pip install pyobjc-framework-Quartz",
                file=__import__("sys").stderr,
            )
            return

        tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            CGEventMaskBit(kCGEventFlagsChanged),
            self._event_callback,
            None,
        )
        if tap is None:
            print(
                "[event-tap] CGEventTapCreate failed — grant Input Monitoring to python3:\n"
                "  System Settings → Privacy & Security → Input Monitoring → add python3\n"
                "  Then restart: launchctl kickstart -k gui/$(id -u)/com.whispy",
                file=__import__("sys").stderr,
            )
            return

        self._tap = tap
        self._run_loop_source = CFMachPortCreateRunLoopSource(None, tap, 0)

        def _run():
            CFRunLoopAddSource(
                CFRunLoopGetCurrent(), self._run_loop_source, kCFRunLoopDefaultMode
            )
            CGEventTapEnable(tap, True)
            self.active = True
            print("[event-tap] Fn key listener active (CGEventTap)")
            CFRunLoopRun()

        self._run_loop_thread = threading.Thread(
            target=_run, name="fn-event-tap", daemon=True
        )
        self._run_loop_thread.start()

    def stop(self) -> None:
        """Stop the event tap listener."""
        self.active = False
        if self._run_loop_thread and self._run_loop_thread.is_alive():
            # CFRunLoopRun has no stop API; the thread will be daemonized.
            pass

    def _event_callback(
        self, _proxy: Any, event_type: int, event: Any, _refcon: Any
    ) -> Any:
        """Callback invoked for each relevant CGEvent."""
        if event_type != kCGEventFlagsChanged:
            return event

        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
        if keycode != FN_KEYCODE:
            return event

        flags = CGEventGetFlags(event)
        if flags & NX_SECONDARYFNMASK:
            # Fn key pressed
            if self._on_fn_press:
                self._on_fn_press()
        else:
            # Fn key released
            if self._on_fn_release:
                self._on_fn_release()

        return event

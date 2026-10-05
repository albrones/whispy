"""Trigger key listener via macOS CGEventTap.

Monitors hardware-level keyboard events and notifies the core engine
of state changes via callbacks. Always uses the Fn key (keycode 63)
as the trigger key.
"""

import logging
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

# Recovery diagnostics go to the daemon log, not stderr: a re-arm line is only
# useful read *next to* the [fsm] and [audio] lines around it. Startup failure
# guidance stays on stderr — it addresses the user at launch, not an operator
# reading back a session.
logger = logging.getLogger(__name__)

# Minimum seconds between two undecodable-trigger warnings. A held modifier
# repeats flags_changed, so the condition this reports can fire continuously;
# 5 s keeps a genuinely dead trigger visible without burying the [fsm] and
# [audio] lines a strand is diagnosed against.
UNDECODABLE_LOG_INTERVAL_S = 5.0

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
        CGEventTapIsEnabled,
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
        # Last observed tap health, so check_tap_liveness can log the
        # healthy -> disabled edge rather than every failing poll.
        self._tap_was_enabled = True
        # Rate-limit state for the undecodable-trigger warning. flags_changed
        # repeats while a key is held, so an unbounded warning would be the
        # loudest line in the log exactly when the log matters most.
        self._undecodable_last_log = 0.0
        self._undecodable_suppressed = 0
        # Optional engine-side hook fired once per tap outage, by whichever
        # recovery path ran. Set by the engine after construction so the
        # platform adapter signature (shared with Linux's pynput listener,
        # which has no tap) stays unchanged.
        self.on_rearm: Callable | None = None
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
            # logger, not print: a bundled .app has no stdout, so a bare print
            # is discarded and the one line that proves the listener came up
            # never reaches ~/.whispy.log.
            logger.info("[event-tap] Trigger key listener active (key: %s)", key_name)
            self._ready_event.set()
            while not self._stop_event.is_set():
                CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.5, False)
                # This wake already existed and did nothing with itself; the
                # probe rides it, so a disabled tap is back within 500 ms
                # whether or not the OS notification ever arrived.
                self.check_tap_liveness()

        self._run_loop_thread = threading.Thread(target=_run, name="trigger-event-tap", daemon=True)
        self._run_loop_thread.start()
        if self._ready_event.wait(timeout=5.0):
            return
        else:
            print(
                "[event-tap] Timed out waiting for CFRunLoop to start — Input Monitoring may not be granted to Whispy",
                file=sys.stderr,
            )

    def _notify_rearm(self) -> None:
        """Fire the engine-side re-arm hook, containing any error it raises."""
        if self.on_rearm is None:
            return
        try:
            self.on_rearm()
        except Exception:
            logger.exception("[event-tap] re-arm callback raised")

    def check_tap_liveness(self) -> bool:
        """Re-enable the tap if the OS has disabled it. Returns True if it recovered.

        The event-driven recovery in ``_event_callback`` only fires if the
        disablement notification is actually delivered — through the very tap
        whose health is in question, and exactly once. Nothing retries it and
        nothing verifies the result, so a missed notification leaves the trigger
        key dead for the rest of the session with no way back. This probe is the
        path that does not depend on the failing channel: it runs on the
        listener's own run-loop thread, so it costs one call per existing wake
        and cannot itself make a callback slow enough to be disabled.

        Deliberately edge-triggered. An unconditional ``CGEventTapEnable`` every
        pass would recover just as well and log nothing useful — the point is to
        be able to *count* recoveries, which means distinguishing "healthy" from
        "recovered 340 times this session". Logging only the healthy -> disabled
        transition also bounds the log line rate if the tap ever flaps.
        """
        if self._tap is None or not QUARTZ_AVAILABLE:
            return False
        try:
            enabled = bool(CGEventTapIsEnabled(self._tap))
        except Exception:  # pragma: no cover - defensive; a probe must never kill the loop
            return False

        if enabled:
            # Only an observed healthy tap clears the edge. Clearing it right
            # after a re-enable instead would assume the re-enable took.
            self._tap_was_enabled = True
            return False

        # Disabled. Retry the re-enable on EVERY poll — a re-enable that did not
        # take must not leave the tap dead for the session, which is the whole
        # failure this probe exists to break. Only the healthy -> disabled edge
        # is reported, so a tap that stays down cannot flood the log.
        first_seen = self._tap_was_enabled
        self._tap_was_enabled = False
        CGEventTapEnable(self._tap, True)
        if first_seen:
            logger.warning("[event-tap] tap was disabled (no notification received) — re-enabled by liveness check")
            # Edge only: resync can synthesize a missed release, and that must
            # happen once per outage, not once per poll.
            self._resync_after_rearm()
            self._notify_rearm()
        return first_seen

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
                # The reason is the whole value of this path over the liveness
                # probe: only the notification says *why* the OS cut the tap,
                # which is what attributes recurring outages to a cause.
                reason = "timeout" if event_type == kCGEventTapDisabledByTimeout else "user input"
                logger.warning("[event-tap] tap disabled by the OS (%s) — re-armed", reason)
                self._resync_after_rearm()
                self._notify_rearm()
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
        # Track the latest flags so the next modifier transition decodes
        # correctly. Every CGEvent carries the live modifier state, not just
        # flags_changed, so key_down/key_up are taken too: a flags_changed the
        # tap never received leaves _prev_flags stale until the next one, and
        # any keystroke in between is a free chance to catch up. This bounds
        # the staleness of the flag-diff decode path; it does not remove the
        # dependency on history (see decode_trigger_event's device-bit path).
        if kind in ("flags_changed", "key_down", "key_up"):
            self._prev_flags = _normalize_flags(flags)

        if action is None and keycode == self._trigger_keycode and not self._required_mask:
            # An event on the trigger's own keycode that resolves to neither
            # press nor release means the decode lost track, which is exactly
            # how the trigger goes dead with the tap still healthy. Without
            # this line that failure is visible only as the *absence* of
            # later lines. Combination triggers are excluded: there, a
            # rejected key_down is the modifier gate doing its job on an
            # ordinary keystroke, not an anomaly.
            self._report_undecodable_trigger(kind, flags)

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
            logger.exception("[event-tap] trigger callback raised")

        return event

    def _report_undecodable_trigger(self, kind: str, flags: Any) -> None:
        """Log a trigger-keycode event that decoded to neither press nor release.

        Rate-limited to one line per ``UNDECODABLE_LOG_INTERVAL_S``, carrying the
        count suppressed since the last one so a burst is still quantified. The
        count is what distinguishes "this fired once" from "the trigger has been
        dead for a minute", which is the question the next strand has to answer.
        """
        now = time.monotonic()
        if self._undecodable_last_log and now - self._undecodable_last_log < UNDECODABLE_LOG_INTERVAL_S:
            self._undecodable_suppressed += 1
            return
        suppressed = self._undecodable_suppressed
        self._undecodable_suppressed = 0
        self._undecodable_last_log = now
        logger.warning(
            "[event-tap] trigger event decoded to neither press nor release (kind=%s, keycode=%s, flags=0x%x)%s",
            kind,
            self._trigger_keycode,
            _normalize_flags(flags),
            f" — {suppressed} more suppressed since the last line" if suppressed else "",
        )

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
            logger.warning("[event-tap] recovered a trigger release missed during tap outage")
            if self._on_trigger_release:
                try:
                    self._on_trigger_release()
                except Exception:
                    logger.exception("[event-tap] trigger release callback raised")


# Backward-compatible alias: the human-readable name lookup now lives in
# event_decode.keycode_to_name.
_keycode_to_name = keycode_to_name

"""Trigger key listener via macOS CGEventTap.

Monitors hardware-level keyboard events and notifies the core engine
of state changes via callbacks. Supports both preset keys and learned
(custom) trigger keys.
"""

import sys
import threading
from typing import Any, Callable, Dict, Optional, Tuple

QUARTZ_AVAILABLE = False

try:
    from Quartz import (
        CFMachPortCreateRunLoopSource,
        CFRunLoopAddSource,
        CFRunLoopGetCurrent,
        CFRunLoopRun,
        CFRunLoopRunInMode,
        CFRunLoopStop,
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
        kCGEventTapOptionListenOnly,
        kCGHeadInsertEventTap,
        kCGKeyboardEventKeycode,
        kCGSessionEventTap,
    )

    QUARTZ_AVAILABLE = True
except ImportError:
    pass

# macOS keycodes for common keys (physical key position)
# See: https://developer.apple.com/documentation/coregraphics/kcgkeycode
_KEYCODE_TO_NAME: Dict[int, str] = {
    0: "a",
    1: "s",
    2: "d",
    3: "f",
    4: "h",
    5: "g",
    6: "z",
    7: "x",
    8: "e",
    9: "w",
    10: "r",
    11: "y",
    12: "t",
    16: "q",
    17: "1",
    18: "2",
    19: "3",
    20: "4",
    21: "6",
    22: "5",
    24: "=",
    26: "9",
    27: "7",
    28: "-",
    29: "8",
    30: "0",
    33: "]",
    34: "o",
    35: "u",
    36: "[",
    37: "i",
    38: "&",
    39: "p",
    40: "enter",
    41: "l",
    42: "j",
    43: "'",
    44: "k",
    46: ";",
    47: "\\",
    48: ",",
    49: "/",
    50: "n",
    51: "m",
    52: ".",
    53: "escape",
    57: "space",
    59: "f1",
    60: "f2",
    61: "f3",
    62: "f4",
    63: "f5",
    64: "f6",
    65: "f7",
    66: "f8",
    67: "f9",
    68: "f10",
    69: "f11",
    70: "f12",
    105: "f13",
    106: "f14",
    107: "f15",
    108: "f16",
    109: "f17",
    110: "f18",
    111: "f19",
    112: "f20",
    # Navigation keys
    123: "left",
    124: "right",
    125: "down",
    126: "up",
    116: "page_up",
    121: "page_down",
    115: "home",
    114: "end",
    118: "insert",
    # Function keys (extended - Apple keyboards)
    105: "f13",
    106: "f14",
    107: "f15",
    108: "f16",
    109: "f17",
    110: "f18",
    111: "f19",
    112: "f20",
    # Other keys
    45: "tab",
    55: "delete",
    51: "backspace",
    56: "caps_lock",
    117: "help",
    54: "decimal",
    # International keys
    85: "international4",
    83: "international5",
    82: "international6",
    84: "international7",
    87: "international8",
    88: "international9",
    # Language-specific keys
    90: "lang1",
    91: "lang2",
    92: "lang3",
    93: "lang4",
    94: "lang5",
    95: "lang6",
    96: "lang7",
    97: "lang8",
    98: "lang9",
    # Modifier keys (virtual/physical)
    252: "shift",
    253: "control",
    254: "option",
    255: "command",
}

# Preset trigger keys: name -> (keycode, label)
PRESET_TRIGGERS: Dict[str, Tuple[int, str]] = {
    "fn": (63, "Fn"),
    "ampersand": (38, "&"),
    "shift": (252, "Shift"),
    "control": (253, "Control"),
    "option": (254, "Option"),
    "command": (255, "Command"),
}

# Default trigger key (Fn)
DEFAULT_TRIGGER_KEYCODE = 63
NX_SECONDARYFNMASK = 0x800000


class EventTapListener:
    """Monitors keyboard events via CGEventTap and emits events for a configurable trigger key."""

    def __init__(
        self,
        trigger_keycode: int = DEFAULT_TRIGGER_KEYCODE,
        on_trigger_press: Optional[Callable] = None,
        on_trigger_release: Optional[Callable] = None,
    ) -> None:
        self._trigger_keycode = trigger_keycode
        self._on_trigger_press = on_trigger_press
        self._on_trigger_release = on_trigger_release
        self._tap = None
        self._run_loop_thread: Optional[threading.Thread] = None
        self._run_loop_source: Any = None
        self.active = False
        # Learning mode state
        self._learning = False
        self._learned_keycode: Optional[int] = None
        self._learn_ready_event = threading.Event()

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
            CGEventMaskBit(kCGEventFlagsChanged)
            | CGEventMaskBit(kCGEventKeyDown)
            | CGEventMaskBit(kCGEventKeyUp)
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
            CFRunLoopAddSource(
                CFRunLoopGetCurrent(), self._run_loop_source, kCFRunLoopDefaultMode
            )
            CGEventTapEnable(tap, True)
            self.active = True
            key_name = _keycode_to_name(self._trigger_keycode)
            print(f"[event-tap] Trigger key listener active (key: {key_name})")
            self._ready_event.set()
            while not self._stop_event.is_set():
                CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.5, False)

        self._run_loop_thread = threading.Thread(
            target=_run, name="trigger-event-tap", daemon=True
        )
        self._run_loop_thread.start()
        if self._ready_event.wait(timeout=5.0):
            return
        else:
            print(
                "[event-tap] Timed out waiting for CFRunLoop to start — "
                "Input Monitoring may not be granted to python3",
                file=sys.stderr,
            )

    def start_learning(self) -> None:
        """Enable learning mode — captures the next key press keycode."""
        self._learning = True
        self._learned_keycode = None
        self._learn_ready_event.clear()

    def stop_learning(self) -> Optional[int]:
        """Disable learning mode and return the learned keycode (if any)."""
        learned = self._learned_keycode
        self._learning = False
        self._learned_keycode = None
        return learned

    @property
    def is_learning(self) -> bool:
        return self._learning

    def stop(self) -> None:
        """Stop the event tap listener."""
        self.active = False
        self._learning = False
        self._stop_event.set()
        if self._run_loop_thread and self._run_loop_thread.is_alive():
            self._run_loop_thread.join(timeout=2)

    def _event_callback(
        self, _proxy: Any, event_type: int, event: Any, _refcon: Any
    ) -> Any:
        """Callback invoked for each relevant CGEvent."""
        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

        # Learning mode: capture the first keydown event
        if self._learning:
            if event_type == kCGEventKeyDown:
                # Ignore the current trigger key during learning
                if keycode == self._trigger_keycode:
                    return event
                self._learned_keycode = keycode
                self._learning = False
                self._learn_ready_event.set()
            return event

        # Normal mode: check against configured trigger keycode
        if keycode != self._trigger_keycode:
            return event

        # Detect press vs release based on event type
        if event_type == kCGEventKeyDown or event_type == kCGEventFlagsChanged:
            # For Fn key (keycode 63), check secondary flag to distinguish press/release
            if self._trigger_keycode == 63:
                flags = CGEventGetFlags(event)
                if flags & NX_SECONDARYFNMASK:
                    if self._on_trigger_press:
                        self._on_trigger_press()
                else:
                    if self._on_trigger_release:
                        self._on_trigger_release()
            else:
                # Regular keydown = press
                if self._on_trigger_press:
                    self._on_trigger_press()
        elif event_type == kCGEventKeyUp:
            if self._on_trigger_release:
                self._on_trigger_release()

        return event


def _keycode_to_name(keycode: int) -> str:
    """Convert a macOS keycode to a human-readable name."""
    if keycode in _KEYCODE_TO_NAME:
        return _KEYCODE_TO_NAME[keycode]
    return f"key{keycode}"


def keycode_to_label(keycode: int) -> str:
    """Convert a macOS keycode to a display label for the UI."""
    name = _keycode_to_name(keycode)
    # Map common names to pretty labels
    labels = {
        "escape": "Esc",
        "enter": "Enter",
        "shift": "Shift",
        "control": "Control",
        "option": "Option",
        "command": "Command",
    }
    if name in labels:
        return labels[name]
    # For F-keys, keep the name
    if name.startswith("f"):
        return name.upper()
    # For numbers and symbols, return as-is
    return name.upper() if len(name) == 1 else name

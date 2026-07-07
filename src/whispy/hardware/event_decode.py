"""Pure, platform-independent decoding for trigger-key events.

Extracted from ``event_tap.py`` so the press/release decision and the
keycode→name mapping can be unit-tested without importing Quartz or running a
live CGEventTap. ``event_tap.py`` imports from here and stays the thin OS shell.
"""

# Default trigger key (Fn) and the secondary-Fn flag bit used to tell a press
# (flag set) from a release (flag clear) on keycode 63.
DEFAULT_TRIGGER_KEYCODE = 63
NX_SECONDARYFNMASK = 0x800000

# macOS keycodes for common keys (physical key position).
# See: https://developer.apple.com/documentation/coregraphics/kcgkeycode
_KEYCODE_TO_NAME: dict[int, str] = {
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
    52: ".",
    53: "escape",
    57: "space",
    59: "f1",
    60: "f2",
    61: "f3",
    62: "f4",
    63: "fn",  # the default trigger (Fn / Globe); NOT F5 (which is keycode 96)
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
    96: "f5",  # real macOS hardware keycode for F5
    97: "lang8",
    98: "lang9",
    # Modifier keys (virtual/physical)
    252: "shift",
    253: "control",
    254: "option",
    255: "command",
}


def keycode_to_name(keycode: int) -> str:
    """Convert a macOS keycode to a human-readable name (or ``keyNN`` fallback)."""
    if keycode in _KEYCODE_TO_NAME:
        return _KEYCODE_TO_NAME[keycode]
    return f"key{keycode}"


def _normalize_flags(flags: object) -> int:
    """Coerce a pyobjc flags value (which may arrive as a tuple) to an int."""
    if isinstance(flags, tuple):
        flags = flags[0] if flags else 0
    return int(flags or 0)


def decode_trigger_event(
    kind: str,
    keycode: int,
    flags: object,
    trigger_keycode: int,
    prev_flags: object = 0,
) -> str | None:
    """Decide whether an event is a trigger press, release, or irrelevant.

    Pure function of the event's classified ``kind`` (one of ``"key_down"``,
    ``"key_up"``, ``"flags_changed"``; anything else is ignored), its
    ``keycode``, the modifier ``flags`` value, the configured ``trigger_keycode``,
    and ``prev_flags`` (the flags value from the previous event).

    - Fn (keycode 63): press vs release is the secondary-Fn flag bit.
    - A non-default *modifier* trigger arrives as ``flags_changed`` with no
      matching ``key_up``; press vs release is derived from which flag bit
      transitioned between ``prev_flags`` and ``flags`` (set → press, cleared →
      release). This prevents the trigger latching "pressed" forever.
    - A non-default *regular* key arrives as ``key_down``/``key_up``.

    Returns ``"press"``, ``"release"``, or ``None``.
    """
    if keycode != trigger_keycode:
        return None

    if kind == "flags_changed":
        if trigger_keycode == DEFAULT_TRIGGER_KEYCODE:
            return "press" if (_normalize_flags(flags) & NX_SECONDARYFNMASK) else "release"
        # Generic modifier: the key's mask bit toggles between events.
        now = _normalize_flags(flags)
        prev = _normalize_flags(prev_flags)
        changed = now ^ prev
        if changed & now:
            return "press"  # a bit went 0 -> 1
        if changed & prev:
            return "release"  # a bit went 1 -> 0
        return None

    if kind == "key_down":
        if trigger_keycode == DEFAULT_TRIGGER_KEYCODE:
            return "press" if (_normalize_flags(flags) & NX_SECONDARYFNMASK) else "release"
        return "press"

    if kind == "key_up":
        return "release"

    return None


# Modifier trigger keycode -> the CGEventFlags mask bit that is set while the key
# is physically held. Used only to tell whether a modifier trigger is still held
# after the OS disabled and we re-armed the tap (so a release that fired during
# the outage can be recovered). Regular (non-modifier) keys are absent — their
# release is a key_up event that flags state cannot reconstruct.
_TRIGGER_HELD_MASK: dict[int, int] = {
    DEFAULT_TRIGGER_KEYCODE: NX_SECONDARYFNMASK,  # Fn
    54: 0x100000,  # Right Command (kCGEventFlagMaskCommand)
    61: 0x80000,  # Right Option (kCGEventFlagMaskAlternate)
}


def trigger_held_after_rearm(trigger_keycode: int, live_flags: object) -> bool | None:
    """Is the modifier trigger still physically held, given the live modifier flags?

    Pure helper for recovering a release missed while the event tap was disabled.
    Returns True/False for a known modifier trigger, or None when the trigger is
    not a modifier we can test from flags (caller cannot recover its release this
    way and must rely on the FSM watchdog backstop).
    """
    mask = _TRIGGER_HELD_MASK.get(trigger_keycode)
    if mask is None:
        return None
    return bool(_normalize_flags(live_flags) & mask)


def decode_key_match(kind: str, key_name: str | None, trigger_key: str) -> str | None:
    """Platform-neutral key-match decode (used by the Linux/pynput listener).

    A configured trigger key/name maps a key-down to ``"press"`` and a key-up to
    ``"release"``; any other key or event kind is ignored. Pure function of the
    classified ``kind`` (``"key_down"``/``"key_up"``), the event's ``key_name``,
    and the configured ``trigger_key`` — no live event source involved.

    Returns ``"press"``, ``"release"``, or ``None``.
    """
    if not trigger_key or key_name != trigger_key:
        return None
    if kind == "key_down":
        return "press"
    if kind == "key_up":
        return "release"
    return None

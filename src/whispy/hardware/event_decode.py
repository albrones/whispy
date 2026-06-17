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


def keycode_to_name(keycode: int) -> str:
    """Convert a macOS keycode to a human-readable name (or ``keyNN`` fallback)."""
    if keycode in _KEYCODE_TO_NAME:
        return _KEYCODE_TO_NAME[keycode]
    return f"key{keycode}"


def decode_trigger_event(
    kind: str,
    keycode: int,
    flags: object,
    trigger_keycode: int,
) -> str | None:
    """Decide whether an event is a trigger press, release, or irrelevant.

    Pure function of the event's classified ``kind`` (one of ``"key_down"``,
    ``"key_up"``, ``"flags_changed"``; anything else is ignored), its
    ``keycode``, the modifier ``flags`` value, and the configured
    ``trigger_keycode``.

    For the Fn key (keycode 63) press vs release is distinguished by the
    secondary-Fn flag; the ``flags`` value may arrive as a tuple on some pyobjc
    versions, in which case the first element is used.

    Returns ``"press"``, ``"release"``, or ``None``.
    """
    if keycode != trigger_keycode:
        return None

    if kind in ("key_down", "flags_changed"):
        if trigger_keycode == DEFAULT_TRIGGER_KEYCODE:
            if isinstance(flags, tuple):
                flags = flags[0] if flags else 0
            flags = flags or 0
            return "press" if (flags & NX_SECONDARYFNMASK) else "release"
        return "press"

    if kind == "key_up":
        return "release"

    return None


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

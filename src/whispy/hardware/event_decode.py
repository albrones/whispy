"""Pure, platform-independent decoding for trigger-key events.

Extracted from ``event_tap.py`` so the press/release decision and the
keycode→name mapping can be unit-tested without importing Quartz or running a
live CGEventTap. ``event_tap.py`` imports from here and stays the thin OS shell.
"""

# Default trigger key (Fn) and the secondary-Fn flag bit used to tell a press
# (flag set) from a release (flag clear) on keycode 63.
DEFAULT_TRIGGER_KEYCODE = 63
NX_SECONDARYFNMASK = 0x800000

# CGEventFlags modifier mask bits, named so callers (parse_trigger below, and
# anyone building a combination-trigger required_mask) don't have to hardcode
# hex. These mirror the values already baked into _TRIGGER_HELD_MASK further
# down (Right Command = 0x100000, Right Option = 0x80000) — that table has
# been rewritten to reference these constants so each bit has one definition.
MASK_SHIFT = 0x20000
MASK_CONTROL = 0x40000
MASK_OPTION = 0x80000
MASK_COMMAND = 0x100000

# macOS keycodes for common keys (physical key position).
# See: https://developer.apple.com/documentation/coregraphics/kcgkeycode
#
# NOTE: the letter entries in this table are known to be unreliable — several
# do not match Apple's Events.h kVK_ANSI_* values (it was assembled from an
# unverified community source, not audited against the header). Only the
# entries that shipped trigger presets actually depend on (currently "e" and
# "c", corrected below) have been checked and fixed. Auditing the rest is
# deliberately out of scope for this change; treat other letters with
# suspicion until someone does that pass.
_KEYCODE_TO_NAME: dict[int, str] = {
    0: "a",
    1: "s",
    2: "d",
    3: "f",
    4: "h",
    5: "g",
    6: "z",
    7: "x",
    8: "c",
    9: "w",
    10: "r",
    11: "y",
    12: "t",
    14: "e",
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


# Built once from _KEYCODE_TO_NAME so parse_trigger doesn't scan the table on
# every call. Safe because the table currently has no two keycodes sharing a
# name (verified for the letters trigger presets use); if that ever changes,
# whichever keycode is inserted last in _KEYCODE_TO_NAME wins here.
_NAME_TO_KEYCODE: dict[str, int] = {name: code for code, name in _KEYCODE_TO_NAME.items()}

# Canonical modifier order for the string trigger form "ctrl+alt+cmd+shift+<key>".
# Any subset of these may be present, but the ones that are present must appear
# in this relative order — this keeps the string form a single canonical
# spelling per trigger instead of accepting every permutation.
_MODIFIER_ORDER: tuple[str, ...] = ("ctrl", "alt", "cmd", "shift")

_MODIFIER_MASKS: dict[str, int] = {
    "ctrl": MASK_CONTROL,
    "alt": MASK_OPTION,
    "cmd": MASK_COMMAND,
    "shift": MASK_SHIFT,
}


def parse_trigger(value: object) -> tuple[int, int] | None:
    """Parse the canonical string trigger form into ``(keycode, mask)``.

    The canonical form is lowercase, "+"-separated: any subset of the
    modifiers ``ctrl``, ``alt``, ``cmd``, ``shift`` — in that fixed relative
    order when more than one is present — followed by a key name as the final
    segment (e.g. ``"ctrl+alt+cmd+e"`` or a bare ``"space"`` with no
    modifiers). The key name is resolved against ``_KEYCODE_TO_NAME`` (via its
    reverse map, ``_NAME_TO_KEYCODE``) — the same table ``keycode_to_name``
    uses — so a valid key name here is exactly a name that table produces.

    Returns ``(keycode, mask)`` on success, where ``mask`` is the OR of the
    CGEventFlags bits for the modifiers present (0 for a bare key name).

    Returns ``None`` — rather than raising — for anything that doesn't fit
    the contract: a non-string ``value``, an empty or whitespace-only string,
    a string with no key segment (e.g. a trailing "+"), an unknown key name,
    an unknown modifier token, a repeated modifier token, or modifiers given
    out of the canonical order. This is deliberate: a malformed config value
    should degrade to "no custom trigger" rather than crash the daemon at
    startup, so every caller of this function is expected to fall back to the
    platform default trigger when it gets ``None`` back.
    """
    if not isinstance(value, str) or not value.strip():
        return None

    parts = value.split("+")
    key_name = parts[-1]
    modifier_tokens = parts[:-1]

    if len(modifier_tokens) != len(set(modifier_tokens)):
        return None  # a modifier repeated (e.g. "ctrl+ctrl+e")

    order_indices = []
    for token in modifier_tokens:
        if token not in _MODIFIER_MASKS:
            return None  # unknown modifier token (e.g. "meta")
        order_indices.append(_MODIFIER_ORDER.index(token))
    if order_indices != sorted(order_indices):
        return None  # present but out of canonical ctrl/alt/cmd/shift order

    keycode = _NAME_TO_KEYCODE.get(key_name)
    if keycode is None:
        return None  # unknown key name, or no key segment at all (empty string)

    mask = 0
    for token in modifier_tokens:
        mask |= _MODIFIER_MASKS[token]
    return (keycode, mask)


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
    required_mask: int = 0,
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

    ``required_mask`` supports a combination trigger (e.g. "ctrl+alt+cmd+e"):
    when non-zero, the configured ``trigger_keycode`` is the *regular* key
    (arriving as key_down/key_up) and ``required_mask`` is the OR of the
    modifier bits that must also be held for a press. When ``required_mask``
    is 0 (the default), this function behaves exactly as it did before this
    parameter existed — every existing caller and test is unaffected.

    The modifier check is asymmetric on purpose: it gates ``key_down`` (and
    ``flags_changed``) but never ``key_up``. A key_up on the matching keycode
    is always a release, even if the modifiers were let go first — a user
    finishing "ctrl+alt+cmd+e" naturally releases Command/Option/Control
    before lifting the letter, and requiring them still-held at that moment
    would make the release undetectable, latching the trigger "pressed".

    Returns ``"press"``, ``"release"``, or ``None``.
    """
    if keycode != trigger_keycode:
        return None

    if required_mask and kind != "key_up":
        if (_normalize_flags(flags) & required_mask) != required_mask:
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
    54: MASK_COMMAND,  # Right Command (kCGEventFlagMaskCommand)
    61: MASK_OPTION,  # Right Option (kCGEventFlagMaskAlternate)
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


def decode_key_match(
    kind: str,
    key_name: str | None,
    trigger_key: str,
    held_modifiers: frozenset[str] | None = None,
    required_modifiers: frozenset[str] | None = None,
) -> str | None:
    """Platform-neutral key-match decode (used by the Linux/pynput listener).

    A configured trigger key/name maps a key-down to ``"press"`` and a key-up to
    ``"release"``; any other key or event kind is ignored. Pure function of the
    classified ``kind`` (``"key_down"``/``"key_up"``), the event's ``key_name``,
    and the configured ``trigger_key`` — no live event source involved.

    ``held_modifiers``/``required_modifiers`` support a combination trigger on
    Linux (e.g. ctrl+alt+cmd+e): ``required_modifiers`` is the set of canonical
    modifier names (see ``canonical_modifier``) that must be a subset of the
    caller-maintained ``held_modifiers`` set for a key-down to count as a
    press. Both default to ``None``, in which case this function behaves
    exactly as it did before these parameters existed — every existing caller
    and test is unaffected.

    Same asymmetry as ``decode_trigger_event``, and for the same reason: the
    modifier check only gates ``key_down``. A key_up on the matching key is
    always a release, even if the modifiers were released first (a user
    naturally lets go of Ctrl/Alt/Cmd before the letter) — requiring them
    still-held at release time would make the release undetectable and latch
    the trigger "pressed".

    Returns ``"press"``, ``"release"``, or ``None``.
    """
    if not trigger_key or key_name != trigger_key:
        return None
    if kind == "key_down":
        if required_modifiers and not (required_modifiers <= (held_modifiers or frozenset())):
            return None
        return "press"
    if kind == "key_up":
        return "release"
    return None


# pynput reports left/right variants (and macOS's alt_gr) for the same logical
# modifier; this collapses them to the canonical names parse_trigger/
# decode_key_match use ("ctrl", "alt", "cmd", "shift"), so the Linux listener
# can maintain a held-modifiers set without caring which physical side was
# pressed.
_PYNPUT_MODIFIER_NAMES: dict[str, str] = {
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
    "cmd": "cmd",
    "cmd_l": "cmd",
    "cmd_r": "cmd",
    "shift": "shift",
    "shift_r": "shift",
}


def canonical_modifier(key_name: str) -> str | None:
    """Map a pynput key name to its canonical modifier name, or ``None``.

    ``None`` means ``key_name`` isn't a modifier at all (e.g. a letter key) —
    the Linux listener uses that to decide whether an event should update its
    held-modifiers set or be treated as an ordinary key.
    """
    return _PYNPUT_MODIFIER_NAMES.get(key_name)

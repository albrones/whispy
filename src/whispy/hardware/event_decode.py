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

# Device-dependent modifier bits (IOKit's IOLLEvent.h, not exported by pyobjc —
# hardcoded here exactly as NX_SECONDARYFNMASK above is). macOS sets one bit per
# *physical* key, where the MASK_* constants above are shared by the left and
# right key of the same modifier. That sharing is the bug this table exists to
# kill: a Left Option press sets MASK_OPTION just like Right Option, so a
# decode that diffs MASK_OPTION against the previous event cannot tell the two
# apart, and a Right Option press arriving while Left Option is held produces
# no observable change at all.
#
# Values confirmed on real hardware (see the change's design.md for the capture):
#   Right Option  keycode 61 -> 0x00080140 pressed, 0x00000100 released
#   Left  Option  keycode 58 -> 0x00080120 pressed  (never touches 0x40)
#   Right Command keycode 54 -> 0x00100110 pressed
NX_DEVICELCTLKEYMASK = 0x00000001
NX_DEVICELSHIFTKEYMASK = 0x00000002
NX_DEVICERSHIFTKEYMASK = 0x00000004
NX_DEVICELCMDKEYMASK = 0x00000008
NX_DEVICERCMDKEYMASK = 0x00000010
NX_DEVICELALTKEYMASK = 0x00000020
NX_DEVICERALTKEYMASK = 0x00000040
NX_DEVICERCTLKEYMASK = 0x00002000

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
    # macOS virtual keycodes, as published in Carbon's <HIToolbox/Events.h>
    # (kVK_* constants). This table was previously written from memory and was
    # wrong from keycode 9 onward -- Right Option (61) printed as "f3" in the
    # menu bar and in the daemon log, and a hand-written string trigger such as
    # "ctrl+alt+cmd+p" bound the quote key. Values below are the kVK_ ones; do
    # not "tidy" them into numeric order without checking against that header.
    # Letters
    0: "a",
    11: "b",
    8: "c",
    2: "d",
    14: "e",
    3: "f",
    5: "g",
    4: "h",
    34: "i",
    38: "j",
    40: "k",
    37: "l",
    46: "m",
    45: "n",
    31: "o",
    35: "p",
    12: "q",
    15: "r",
    1: "s",
    17: "t",
    32: "u",
    9: "v",
    13: "w",
    7: "x",
    16: "y",
    6: "z",
    # Digits
    29: "0",
    18: "1",
    19: "2",
    20: "3",
    21: "4",
    23: "5",
    22: "6",
    26: "7",
    28: "8",
    25: "9",
    # Punctuation
    27: "-",
    24: "=",
    33: "[",
    30: "]",
    42: "\\",
    41: ";",
    39: "'",
    43: ",",
    47: ".",
    44: "/",
    50: "`",
    # Editing and whitespace
    36: "enter",
    48: "tab",
    49: "space",
    51: "backspace",
    53: "escape",
    117: "delete",
    114: "help",
    # Modifiers. These are the keys the trigger presets use, so a wrong value
    # here mislabels the trigger the user actually configured.
    55: "command",
    54: "right_command",
    56: "shift",
    60: "right_shift",
    58: "option",
    61: "right_option",
    59: "control",
    62: "right_control",
    57: "caps_lock",
    63: "fn",  # the default trigger (Fn / Globe); NOT F5 (which is keycode 96)
    # Function keys. Not contiguous and not in order -- this is the real layout.
    122: "f1",
    120: "f2",
    99: "f3",
    118: "f4",
    96: "f5",
    97: "f6",
    98: "f7",
    100: "f8",
    101: "f9",
    109: "f10",
    103: "f11",
    111: "f12",
    105: "f13",
    107: "f14",
    113: "f15",
    106: "f16",
    64: "f17",
    79: "f18",
    80: "f19",
    90: "f20",
    # Navigation
    123: "left",
    124: "right",
    125: "down",
    126: "up",
    115: "home",
    119: "end",
    116: "page_up",
    121: "page_down",
    # Media
    72: "volume_up",
    73: "volume_down",
    74: "mute",
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
      matching ``key_up``. When the keycode has a verified device-dependent bit
      (``_TRIGGER_DEVICE_MASK``), press vs release is read off **that bit on
      this event alone** — set → press, cleared → release — so the decode
      carries no history and cannot desynchronise. Otherwise it falls back to
      which flag bit transitioned between ``prev_flags`` and ``flags``. Both
      paths prevent the trigger latching "pressed" forever; only the first also
      survives a missed event or the opposite-side key of the same modifier,
      which share the side-agnostic ``MASK_*`` bit.
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
        now = _normalize_flags(flags)
        device_bit = _TRIGGER_DEVICE_MASK.get(trigger_keycode)
        if device_bit is not None:
            if now & device_bit:
                return "press"
            # The bit is clear, which is a release *if* this event stream sets
            # device bits at all. Some remappers and external keyboards do not,
            # and there reading every event as a release would mean a press
            # never starts a recording — strictly worse than the diff. Two
            # checks settle it without guessing:
            held_mask = _TRIGGER_HELD_MASK.get(trigger_keycode, 0)
            if not (now & held_mask):
                # The modifier is fully let go. Unambiguous.
                return "release"
            # The modifier is still held by *something*. If any device bit of
            # this modifier's family is set, the stream does carry them, so our
            # key's bit being clear means our key is the one that came up (the
            # opposite-side key is what still holds the shared mask).
            if now & _DEVICE_FAMILY.get(held_mask, 0):
                return "release"
            # Held, and not one device bit in sight: this keyboard does not
            # emit them. Fall through to the diff, which is what it uses today.
        # Generic modifier: the key's mask bit toggles between events. Reached
        # for a trigger with no verified device bit, and as the fallback above.
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

# Modifier trigger keycode -> the DEVICE-DEPENDENT bit set while that exact
# physical key is held. Unlike _TRIGGER_HELD_MASK above (which answers "is this
# modifier held by either side?"), this identifies the one key, which is what
# makes press/release decodable from a single event with no history.
#
# Only keycodes verified on hardware belong here. A keycode absent from this
# table decodes through the flag-diff path exactly as before, so an unverified
# key degrades to today's behaviour rather than to a new failure mode. The two
# entries are the modifier presets that ship in config.TRIGGER_PRESETS.
_TRIGGER_DEVICE_MASK: dict[int, int] = {
    54: NX_DEVICERCMDKEYMASK,  # Right Command
    61: NX_DEVICERALTKEYMASK,  # Right Option
}

# Side-agnostic modifier mask -> both device bits of that modifier family.
# Used to answer "does this event stream carry device bits at all?", which is
# what separates "our key is up while the other side is still down" from "this
# keyboard or remapper never sets device bits". Without that distinction a
# cleared device bit is ambiguous and neither reading is safe.
_DEVICE_FAMILY: dict[int, int] = {
    MASK_SHIFT: NX_DEVICELSHIFTKEYMASK | NX_DEVICERSHIFTKEYMASK,
    MASK_CONTROL: NX_DEVICELCTLKEYMASK | NX_DEVICERCTLKEYMASK,
    MASK_OPTION: NX_DEVICELALTKEYMASK | NX_DEVICERALTKEYMASK,
    MASK_COMMAND: NX_DEVICELCMDKEYMASK | NX_DEVICERCMDKEYMASK,
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

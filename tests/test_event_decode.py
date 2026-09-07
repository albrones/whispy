"""Unit tests for the pure trigger-event decoding (no Quartz, no event tap)."""

import sys
from pathlib import Path

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.hardware.event_decode import (
    DEFAULT_TRIGGER_KEYCODE,
    NX_SECONDARYFNMASK,
    canonical_modifier,
    decode_key_match,
    decode_trigger_event,
    keycode_to_name,
    parse_trigger,
    trigger_held_after_rearm,
)
from whispy.platform.detect import LINUX_DEFAULT_TRIGGER, detect

FN = DEFAULT_TRIGGER_KEYCODE  # 63


class TestDecodeFnTrigger:
    def test_fn_press_when_secondary_flag_set(self):
        assert decode_trigger_event("flags_changed", FN, NX_SECONDARYFNMASK, FN) == "press"

    def test_fn_release_when_secondary_flag_clear(self):
        assert decode_trigger_event("flags_changed", FN, 0, FN) == "release"

    def test_fn_key_down_with_flag_is_press(self):
        assert decode_trigger_event("key_down", FN, NX_SECONDARYFNMASK, FN) == "press"

    def test_flags_tuple_form_is_unwrapped(self):
        # pyobjc legacy form: flags arrive as a tuple
        assert decode_trigger_event("flags_changed", FN, (NX_SECONDARYFNMASK,), FN) == "press"
        assert decode_trigger_event("flags_changed", FN, (0,), FN) == "release"
        assert decode_trigger_event("flags_changed", FN, (), FN) == "release"

    def test_none_flags_treated_as_release(self):
        assert decode_trigger_event("flags_changed", FN, None, FN) == "release"


class TestDecodeNonFnTrigger:
    def test_regular_keydown_is_press(self):
        assert decode_trigger_event("key_down", 49, 0, 49) == "press"

    def test_regular_keyup_is_release(self):
        assert decode_trigger_event("key_up", 49, 0, 49) == "release"

    def test_modifier_flags_changed_decodes_press_then_release(self):
        # A non-Fn modifier trigger arrives only as flags_changed (no key_up).
        # Press = its mask bit goes 0->1; release = 1->0, derived from prev_flags.
        BIT = 0x40000  # arbitrary modifier mask
        TRIG = 54  # a modifier keycode
        press = decode_trigger_event("flags_changed", TRIG, BIT, TRIG, prev_flags=0)
        release = decode_trigger_event("flags_changed", TRIG, 0, TRIG, prev_flags=BIT)
        assert press == "press"
        assert release == "release"

    def test_modifier_flags_changed_no_transition_is_none(self):
        # No bit changed for the trigger → neither press nor release (avoids the
        # old behavior of latching "press" forever).
        BIT = 0x40000
        assert decode_trigger_event("flags_changed", 54, BIT, 54, prev_flags=BIT) is None


class TestDecodeIgnored:
    def test_non_trigger_keycode_ignored(self):
        assert decode_trigger_event("key_down", 10, NX_SECONDARYFNMASK, FN) is None

    def test_other_kind_ignored(self):
        assert decode_trigger_event("other", FN, NX_SECONDARYFNMASK, FN) is None

    def test_fn_keyup_ignored_branch(self):
        # Fn uses flags_changed, not key_up; a key_up on the Fn keycode is release
        assert decode_trigger_event("key_up", FN, 0, FN) == "release"


class TestKeycodeToName:
    def test_known_keycode(self):
        # keycode 63 is the Fn trigger (not F5); F5 is keycode 96.
        assert keycode_to_name(63) == "fn"
        assert keycode_to_name(96) == "f5"
        assert keycode_to_name(0) == "a"

    def test_unknown_keycode_fallback(self):
        assert keycode_to_name(9999) == "key9999"

    def test_corrected_letters(self):
        # kVK_ANSI_E = 0x0E = 14, kVK_ANSI_C = 0x08 = 8 (Apple's Events.h).
        # The table previously had these swapped/missing; see 2.5.
        assert keycode_to_name(14) == "e"
        assert keycode_to_name(8) == "c"


class TestParseTrigger:
    def test_full_combo(self):
        assert parse_trigger("ctrl+alt+cmd+e") == (14, 0x1C0000)

    def test_full_combo_other_key(self):
        assert parse_trigger("ctrl+alt+cmd+f") == (3, 0x1C0000)

    def test_bare_key_no_modifiers(self):
        # Read straight from the table rather than guessing the keycode.
        from whispy.hardware.event_decode import _KEYCODE_TO_NAME

        space_keycode = next(k for k, v in _KEYCODE_TO_NAME.items() if v == "space")
        assert parse_trigger("space") == (space_keycode, 0)

    def test_none_is_none(self):
        assert parse_trigger(None) is None

    def test_empty_string_is_none(self):
        assert parse_trigger("") is None

    def test_whitespace_only_is_none(self):
        assert parse_trigger("   ") is None

    def test_non_string_is_none(self):
        assert parse_trigger(123) is None

    def test_unknown_key_is_none(self):
        assert parse_trigger("ctrl+alt+cmd+zzz") is None

    def test_unknown_modifier_is_none(self):
        assert parse_trigger("meta+e") is None

    def test_wrong_modifier_order_is_none(self):
        assert parse_trigger("alt+ctrl+e") is None

    def test_no_key_segment_is_none(self):
        assert parse_trigger("ctrl+alt+cmd+") is None


class TestDecodeTriggerEventCombination:
    """decode_trigger_event's required_mask gate for a combination trigger."""

    E_KEYCODE = 14
    FULL_MASK = 0x1C0000  # ctrl+alt+cmd

    def test_key_down_with_all_modifiers_held_is_press(self):
        result = decode_trigger_event(
            "key_down", self.E_KEYCODE, self.FULL_MASK, self.E_KEYCODE, required_mask=self.FULL_MASK
        )
        assert result == "press"

    def test_key_down_with_partial_modifiers_is_none(self):
        partial = 0x40000 | 0x80000  # ctrl+alt only, missing cmd
        result = decode_trigger_event("key_down", self.E_KEYCODE, partial, self.E_KEYCODE, required_mask=self.FULL_MASK)
        assert result is None

    def test_key_down_with_no_modifiers_is_none(self):
        result = decode_trigger_event("key_down", self.E_KEYCODE, 0, self.E_KEYCODE, required_mask=self.FULL_MASK)
        assert result is None

    def test_key_up_ignores_required_mask(self):
        # The user may release Command/Option/Control before the letter.
        result = decode_trigger_event("key_up", self.E_KEYCODE, 0, self.E_KEYCODE, required_mask=self.FULL_MASK)
        assert result == "release"

    def test_required_mask_zero_reproduces_existing_behavior(self):
        assert decode_trigger_event("key_down", 49, 0, 49, required_mask=0) == "press"
        assert decode_trigger_event("key_up", 49, 0, 49, required_mask=0) == "release"


class TestCanonicalModifier:
    def test_known_pynput_modifiers(self):
        assert canonical_modifier("ctrl_r") == "ctrl"
        assert canonical_modifier("ctrl_l") == "ctrl"
        assert canonical_modifier("alt_gr") == "alt"
        assert canonical_modifier("cmd") == "cmd"
        assert canonical_modifier("shift") == "shift"

    def test_non_modifier_is_none(self):
        assert canonical_modifier("a") is None


class TestDecodeKeyMatchWithModifiers:
    def test_all_required_modifiers_held_is_press(self):
        held = frozenset({"ctrl", "alt", "cmd"})
        required = frozenset({"ctrl", "alt", "cmd"})
        assert decode_key_match("key_down", "e", "e", held, required) == "press"

    def test_partial_modifiers_held_is_none(self):
        held = frozenset({"ctrl", "alt"})
        required = frozenset({"ctrl", "alt", "cmd"})
        assert decode_key_match("key_down", "e", "e", held, required) is None

    def test_key_up_ignores_required_modifiers(self):
        required = frozenset({"ctrl", "alt", "cmd"})
        assert decode_key_match("key_up", "e", "e", frozenset(), required) == "release"


class TestDecodeKeyMatch:
    """Platform-neutral key-match decode path (Linux/pynput)."""

    def test_configured_key_down_is_press(self):
        assert decode_key_match("key_down", "ctrl_r", "ctrl_r") == "press"

    def test_configured_key_up_is_release(self):
        assert decode_key_match("key_up", "ctrl_r", "ctrl_r") == "release"

    def test_non_trigger_key_ignored(self):
        assert decode_key_match("key_down", "a", "ctrl_r") is None

    def test_missing_key_name_ignored(self):
        assert decode_key_match("key_down", None, "ctrl_r") is None

    def test_empty_trigger_ignored(self):
        assert decode_key_match("key_down", "ctrl_r", "") is None

    def test_char_key_match(self):
        assert decode_key_match("key_down", "z", "z") == "press"
        assert decode_key_match("key_up", "z", "z") == "release"


class TestPlatformDefaultTrigger:
    """The platform default trigger resolution (macOS Fn / Linux push-to-talk)."""

    def test_macos_default_is_fn_keycode(self):
        assert detect("darwin").default_trigger == DEFAULT_TRIGGER_KEYCODE == 63

    def test_linux_default_is_documented_key(self):
        assert detect("linux").default_trigger == LINUX_DEFAULT_TRIGGER


class TestTriggerHeldAfterRearm:
    """trigger_held_after_rearm — recover a modifier release missed during a tap outage."""

    def test_fn_held(self):
        assert trigger_held_after_rearm(FN, NX_SECONDARYFNMASK) is True

    def test_fn_released(self):
        assert trigger_held_after_rearm(FN, 0) is False

    def test_right_option_held(self):
        assert trigger_held_after_rearm(61, 0x80000) is True

    def test_right_option_released(self):
        # No alt bit set → the key was released while the tap was down.
        assert trigger_held_after_rearm(61, 0) is False

    def test_right_command_held(self):
        assert trigger_held_after_rearm(54, 0x100000) is True

    def test_regular_key_returns_none(self):
        # F13 (105) is a regular key: its release cannot be told from flags.
        assert trigger_held_after_rearm(105, 0) is None

    def test_tuple_flags_are_normalized(self):
        assert trigger_held_after_rearm(61, (0x80000,)) is True

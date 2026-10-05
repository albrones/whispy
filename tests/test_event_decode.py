"""Unit tests for the pure trigger-event decoding (no Quartz, no event tap)."""

import sys
from pathlib import Path

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.hardware.event_decode import (
    DEFAULT_TRIGGER_KEYCODE,
    MASK_COMMAND,
    MASK_OPTION,
    NX_DEVICELALTKEYMASK,
    NX_DEVICERALTKEYMASK,
    NX_DEVICERCMDKEYMASK,
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
        # Flags are the ones Right Command actually produces (captured live):
        # command mask + its device bit on press, everything clear on release.
        # The earlier version of this test used 0x40000 (the CONTROL mask) for
        # keycode 54, a combination the hardware never emits.
        TRIG = 54  # Right Command
        DOWN = MASK_COMMAND | NX_DEVICERCMDKEYMASK
        press = decode_trigger_event("flags_changed", TRIG, DOWN, TRIG, prev_flags=0)
        release = decode_trigger_event("flags_changed", TRIG, 0, TRIG, prev_flags=DOWN)
        assert press == "press"
        assert release == "release"

    def test_modifier_flags_changed_no_transition_is_none_on_the_fallback_path(self):
        # No bit changed for the trigger → neither press nor release (avoids the
        # old behavior of latching "press" forever). This is the flag-diff
        # path, which now applies only to a keycode with no verified device
        # bit; 55 (Left Command) is deliberately absent from _TRIGGER_DEVICE_MASK.
        BIT = MASK_COMMAND
        assert decode_trigger_event("flags_changed", 55, BIT, 55, prev_flags=BIT) is None

    def test_device_bit_does_not_need_a_transition(self):
        # The point of the device-bit path: the current event is sufficient, so
        # a stale prev_flags cannot suppress the decision. The old flag-diff
        # returned None here, which is exactly how a stopping press was lost.
        DOWN = MASK_OPTION | NX_DEVICERALTKEYMASK
        assert decode_trigger_event("flags_changed", 61, DOWN, 61, prev_flags=DOWN) == "press"


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

    def test_every_trigger_preset_names_the_key_it_is(self):
        """The menu bar and the daemon log both print this name back to the user.

        Right Option (61) used to come out as "f3", because the table carried
        f1-f4 over the right-hand modifier block.
        """
        from whispy.core.config import TRIGGER_PRESETS

        named = {label: keycode_to_name(code) for label, code in TRIGGER_PRESETS if code is not None}
        assert named == {
            "Right Command": "right_command",
            "Right Option": "right_option",
            "F13": "f13",
        }

    def test_the_keycodes_this_table_used_to_get_wrong(self):
        # Spot checks across the blocks that were shifted, one per block.
        assert keycode_to_name(9) == "v"  # was "w"
        assert keycode_to_name(18) == "1"  # was "2"
        assert keycode_to_name(36) == "enter"  # was "["
        assert keycode_to_name(49) == "space"  # was "/"
        assert keycode_to_name(59) == "control"  # was "f1"
        assert keycode_to_name(122) == "f1"  # was unmapped
        assert keycode_to_name(255) == "key255"  # was "command"

    def test_names_round_trip_back_to_their_keycode(self):
        # parse_trigger resolves a hand-written trigger through the reverse of
        # this table, so a duplicate name would silently bind the wrong key.
        from whispy.hardware.event_decode import _KEYCODE_TO_NAME

        assert len(set(_KEYCODE_TO_NAME.values())) == len(_KEYCODE_TO_NAME)
        for code, name in _KEYCODE_TO_NAME.items():
            assert parse_trigger(name) == (code, 0), name


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


class TestModifierTriggerDeviceBit:
    """The device-dependent bit path (fix-modifier-trigger-flag-desync).

    Flag values here are the ones captured on real hardware:
      Right Option  61 -> 0x00080140 pressed, 0x00000100 released
      Left  Option  58 -> 0x00080120 pressed
      Right Command 54 -> 0x00100110 pressed
    0x100 is NX_NONCOALSESCEDMASK, present on every event and not a modifier.
    """

    NONCOALESCED = 0x100
    R_OPT_DOWN = MASK_OPTION | NX_DEVICERALTKEYMASK | NONCOALESCED  # 0x00080140
    L_OPT_DOWN = MASK_OPTION | NX_DEVICELALTKEYMASK | NONCOALESCED  # 0x00080120
    ALL_UP = NONCOALESCED  # 0x00000100

    def test_press_from_device_bit(self):
        assert decode_trigger_event("flags_changed", 61, self.R_OPT_DOWN, 61) == "press"

    def test_release_from_device_bit(self):
        assert decode_trigger_event("flags_changed", 61, self.ALL_UP, 61) == "release"

    def test_press_decoded_although_prev_flags_already_carried_the_shared_mask(self):
        # Stale baseline that already has MASK_OPTION: the old diff produced
        # `changed == 0` and returned None. The device bit is unaffected.
        assert decode_trigger_event("flags_changed", 61, self.R_OPT_DOWN, 61, prev_flags=MASK_OPTION) == "press"

    def test_left_option_held_across_the_trigger_press(self):
        """The regression this change exists to prevent.

        Left Option is held (so MASK_OPTION is already set and prev_flags
        reflects it), then Right Option is pressed to stop a toggle-mode
        recording. Both keys share MASK_OPTION, so the flag-diff saw no change
        and swallowed the stopping press — the daemon log's exact signature.
        """
        both_down = self.R_OPT_DOWN | NX_DEVICELALTKEYMASK
        assert decode_trigger_event("flags_changed", 61, both_down, 61, prev_flags=self.L_OPT_DOWN) == "press"

    def test_trigger_release_while_the_other_side_is_still_held(self):
        # Right Option let go, Left Option still down: MASK_OPTION stays set but
        # 0x40 clears. Ambiguous from one event, so the diff resolves it.
        assert decode_trigger_event("flags_changed", 61, self.L_OPT_DOWN, 61, prev_flags=self.R_OPT_DOWN) == "release"

    def test_missed_event_does_not_strand_the_trigger(self):
        # A flags_changed was never delivered, so prev_flags is arbitrarily
        # stale. The next trigger event still decodes, with no resync step.
        assert decode_trigger_event("flags_changed", 61, self.R_OPT_DOWN, 61, prev_flags=0xDEAD) == "press"

    def test_right_command_uses_its_own_device_bit(self):
        down = MASK_COMMAND | NX_DEVICERCMDKEYMASK | self.NONCOALESCED
        assert decode_trigger_event("flags_changed", 54, down, 54, prev_flags=MASK_COMMAND) == "press"
        assert decode_trigger_event("flags_changed", 54, self.ALL_UP, 54) == "release"

    def test_keyboard_that_sets_no_device_bit_falls_back_to_the_diff(self):
        """A remapper or external keyboard that never sets device bits.

        Reading "bit clear" as a release there would mean a press never starts
        a recording — strictly worse than today. The modifier still being held
        while its device bit is absent is the tell, and the diff takes over.
        """
        press = decode_trigger_event("flags_changed", 61, MASK_OPTION, 61, prev_flags=0)
        release = decode_trigger_event("flags_changed", 61, 0, 61, prev_flags=MASK_OPTION)
        assert press == "press"
        assert release == "release"

    def test_unverified_modifier_keycode_still_uses_the_diff(self):
        # 55 (Left Command) has no entry in _TRIGGER_DEVICE_MASK.
        press = decode_trigger_event("flags_changed", 55, MASK_COMMAND, 55, prev_flags=0)
        release = decode_trigger_event("flags_changed", 55, 0, 55, prev_flags=MASK_COMMAND)
        assert press == "press"
        assert release == "release"

    def test_fn_default_trigger_is_untouched(self):
        assert decode_trigger_event("flags_changed", 63, NX_SECONDARYFNMASK, 63) == "press"
        assert decode_trigger_event("flags_changed", 63, 0, 63) == "release"

    def test_tuple_flags_are_normalized_on_the_device_path(self):
        assert decode_trigger_event("flags_changed", 61, (self.R_OPT_DOWN,), 61) == "press"

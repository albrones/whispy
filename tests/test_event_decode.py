"""Unit tests for the pure trigger-event decoding (no Quartz, no event tap)."""

import sys
from pathlib import Path

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.hardware.event_decode import (
    DEFAULT_TRIGGER_KEYCODE,
    NX_SECONDARYFNMASK,
    decode_key_match,
    decode_trigger_event,
    keycode_to_name,
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

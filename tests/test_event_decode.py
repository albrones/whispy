"""Unit tests for the pure trigger-event decoding (no Quartz, no event tap)."""

import sys
from pathlib import Path

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.hardware.event_decode import (
    DEFAULT_TRIGGER_KEYCODE,
    NX_SECONDARYFNMASK,
    decode_trigger_event,
    keycode_to_name,
)

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

    def test_flags_changed_non_fn_is_press(self):
        assert decode_trigger_event("flags_changed", 49, 0, 49) == "press"


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
        assert keycode_to_name(63) == "f5"
        assert keycode_to_name(0) == "a"

    def test_unknown_keycode_fallback(self):
        assert keycode_to_name(9999) == "key9999"

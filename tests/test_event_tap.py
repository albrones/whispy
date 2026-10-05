"""Unit tests for the EventTapListener shell (no Quartz, no device).

Covers the listener-side half of `fix-modifier-trigger-flag-desync`:
flag tracking that is not restricted to `flags_changed`, and the warning
that makes a trigger which decoded to nothing visible in the daemon log
instead of diagnosable only from the absence of later lines.

The decode itself is pure and lives in `test_event_decode.py`.
"""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_project_root = str(Path(__file__).parent.parent)
_src = Path(__file__).parent.parent / "src"
if _project_root in sys.path:
    sys.path.remove(_project_root)
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

if "Quartz" not in sys.modules:
    sys.modules["Quartz"] = MagicMock()

from whispy.hardware.event_tap import (  # noqa: E402
    EventTapListener,
    kCGEventFlagsChanged,
    kCGEventKeyDown,
    kCGEventKeyUp,
)

RIGHT_OPTION = 61
MASK_OPTION = 0x80000
MASK_COMMAND = 0x100000


def feed(listener, event_type, keycode, flags):
    """Drive one event through the callback with the Quartz reads faked."""
    with (
        patch("whispy.hardware.event_tap.CGEventGetType", return_value=event_type),
        patch("whispy.hardware.event_tap.CGEventGetIntegerValueField", return_value=keycode),
        patch("whispy.hardware.event_tap.CGEventGetFlags", return_value=flags),
    ):
        listener._event_callback(None, event_type, MagicMock(), None)


@pytest.fixture
def listener():
    return EventTapListener(
        trigger_keycode=RIGHT_OPTION,
        on_trigger_press=MagicMock(),
        on_trigger_release=MagicMock(),
    )


class TestFlagTracking:
    """Task 3.1 — every event that carries flags refreshes `_prev_flags`."""

    def test_key_down_refreshes_prev_flags(self, listener):
        """A keystroke carries live modifier state; it must not be discarded.

        Before this change `_prev_flags` advanced only on `flags_changed`, so a
        `flags_changed` the tap never received left the diff baseline stale
        until the next one arrived.
        """
        feed(listener, kCGEventKeyDown, 0, MASK_COMMAND)
        assert listener._prev_flags == MASK_COMMAND

    def test_key_up_refreshes_prev_flags(self, listener):
        feed(listener, kCGEventKeyUp, 0, MASK_OPTION)
        assert listener._prev_flags == MASK_OPTION

    def test_flags_changed_still_refreshes_prev_flags(self, listener):
        feed(listener, kCGEventFlagsChanged, RIGHT_OPTION, MASK_OPTION)
        assert listener._prev_flags == MASK_OPTION

    def test_press_then_keystroke_then_release_still_decodes(self, listener):
        """Tracking extra events must not break the press/release pair itself."""
        feed(listener, kCGEventFlagsChanged, RIGHT_OPTION, MASK_OPTION)
        assert listener._on_trigger_press.call_count == 1

        # Typing while the modifier is held: same flags, no decode change.
        feed(listener, kCGEventKeyDown, 0, MASK_OPTION)
        assert listener._on_trigger_release.call_count == 0

        feed(listener, kCGEventFlagsChanged, RIGHT_OPTION, 0)
        assert listener._on_trigger_release.call_count == 1


class TestUndecodableTriggerWarning:
    """Tasks 3.2-3.4 — a trigger event that resolves to nothing is reported."""

    def test_warns_when_trigger_event_decodes_to_nothing(self, listener, caplog):
        """The desync signature: the trigger's own bit did not move.

        This is what a swallowed stop-press looks like from inside the
        callback — the tap is healthy, the event arrived, and the decode
        produced neither press nor release.
        """
        listener._prev_flags = MASK_OPTION
        with caplog.at_level(logging.WARNING):
            feed(listener, kCGEventFlagsChanged, RIGHT_OPTION, MASK_OPTION)

        assert listener._on_trigger_press.call_count == 0
        assert listener._on_trigger_release.call_count == 0
        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("decoded to neither press nor release" in m for m in messages), messages
        assert any("keycode=61" in m for m in messages), messages

    def test_warning_is_rate_limited(self, listener, caplog):
        """A held modifier repeats flags_changed; the log must stay readable."""
        listener._prev_flags = MASK_OPTION
        with caplog.at_level(logging.WARNING):
            for _ in range(50):
                feed(listener, kCGEventFlagsChanged, RIGHT_OPTION, MASK_OPTION)

        warnings = [
            r for r in caplog.records if r.levelno == logging.WARNING and "decoded to neither" in r.getMessage()
        ]
        assert len(warnings) == 1, f"expected the burst to collapse to one line, got {len(warnings)}"
        assert listener._undecodable_suppressed == 49

    def test_suppressed_count_is_reported_on_the_next_line(self, listener, caplog):
        """A burst is still quantified, so 'once' reads differently from 'constantly'."""
        listener._prev_flags = MASK_OPTION
        with caplog.at_level(logging.WARNING):
            for _ in range(5):
                feed(listener, kCGEventFlagsChanged, RIGHT_OPTION, MASK_OPTION)
            # Move past the rate-limit window without sleeping.
            listener._undecodable_last_log -= 3600
            feed(listener, kCGEventFlagsChanged, RIGHT_OPTION, MASK_OPTION)

        messages = [
            r.getMessage()
            for r in caplog.records
            if r.levelno == logging.WARNING and "decoded to neither" in r.getMessage()
        ]
        assert len(messages) == 2, messages
        assert "4 more suppressed" in messages[1], messages[1]

    def test_no_warning_for_a_non_trigger_keycode(self, listener, caplog):
        """Task 3.4 — other keys are not this listener's business."""
        listener._prev_flags = MASK_OPTION
        with caplog.at_level(logging.WARNING):
            feed(listener, kCGEventFlagsChanged, 58, MASK_OPTION)

        assert not [
            r for r in caplog.records if r.levelno == logging.WARNING and "decoded to neither" in r.getMessage()
        ]

    def test_no_warning_on_a_normal_press(self, listener, caplog):
        """A decode that resolved is not an anomaly and must stay silent."""
        with caplog.at_level(logging.WARNING):
            feed(listener, kCGEventFlagsChanged, RIGHT_OPTION, MASK_OPTION)

        assert listener._on_trigger_press.call_count == 1
        assert not [
            r for r in caplog.records if r.levelno == logging.WARNING and "decoded to neither" in r.getMessage()
        ]

    def test_no_warning_for_a_combination_trigger_gate_rejection(self, caplog):
        """A combination trigger rejects ordinary keystrokes by design.

        With `required_mask` set, a key_down on the trigger's letter without
        the modifiers held is the gate working, not the trigger failing —
        warning there would fire on every such keystroke the user types.
        """
        combo = EventTapListener(
            trigger_keycode=14,  # "e"
            on_trigger_press=MagicMock(),
            on_trigger_release=MagicMock(),
        )
        combo._required_mask = MASK_COMMAND

        with caplog.at_level(logging.WARNING):
            feed(combo, kCGEventKeyDown, 14, 0)

        assert combo._on_trigger_press.call_count == 0
        assert not [
            r for r in caplog.records if r.levelno == logging.WARNING and "decoded to neither" in r.getMessage()
        ]

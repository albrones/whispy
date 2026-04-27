"""Tests for the Finite State Machine (state_machine module).

Covers:
- Valid transition chains
- Illegal transition rejection
- Callback invocation
- Thread safety under concurrent access
- Transition history tracking
- Convenience methods (start_recording, stop_recording, transcription_complete)
- to_dict() output format
"""

import sys
import threading
import time
from pathlib import Path

import pytest

# Ensure src/ is on the path, and remove project root to avoid whispy.py shadowing
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.core.state_machine import (
    InvalidTransitionError,
    State,
    StateMachine,
)


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------


class TestValidTransitions:
    """Test that valid transitions succeed."""

    def test_idle_to_recording(self, sm):
        assert sm.current_state == State.IDLE
        assert sm.start_recording() is True
        assert sm.is_recording is True
        assert sm.is_idle is False

    def test_recording_to_transcribing(self, sm):
        sm.start_recording()
        assert sm.stop_recording() is True
        assert sm.is_transcribing is True
        assert sm.is_recording is False

    def test_transcribing_to_idle(self, sm):
        sm.start_recording()
        sm.stop_recording()
        assert sm.transcription_complete() is True
        assert sm.is_idle is True
        assert sm.is_transcribing is False

    def test_full_lifecycle(self, sm):
        """IDLE -> RECORDING -> TRANSCRIBING -> IDLE."""
        assert sm.start_recording() is True
        assert sm.stop_recording() is True
        assert sm.transcription_complete() is True
        assert sm.is_idle is True

    def test_transition_to_same_state_returns_true(self, sm):
        """Transitioning to the current state is a no-op that returns True."""
        assert sm.transition_to(State.IDLE) is True
        assert sm.current_state == State.IDLE


# ---------------------------------------------------------------------------
# Illegal transitions
# ---------------------------------------------------------------------------


class TestIllegalTransitions:
    """Test that illegal transitions raise InvalidTransitionError."""

    def test_idle_to_transcribing_raises(self, sm):
        with pytest.raises(InvalidTransitionError):
            sm.transition_to(State.TRANSCRIBING)
        assert sm.current_state == State.IDLE

    def test_recording_to_recording_returns_false(self, sm):
        assert sm.start_recording() is True
        assert sm.start_recording() is False
        assert sm.is_recording is True

    def test_transcribing_to_recording_via_method_returns_false(self, sm):
        sm.start_recording()
        sm.stop_recording()
        # start_recording() catches InvalidTransitionError and returns False
        assert sm.start_recording() is False

    def test_transcribing_to_idle_via_method_works(self, sm):
        sm.start_recording()
        sm.stop_recording()
        assert sm.transcription_complete() is True
        assert sm.is_idle is True

    def test_idle_to_idle_via_transition_is_noop(self, sm):
        assert sm.transition_to(State.IDLE) is True

    def test_error_message_contains_context(self, sm):
        with pytest.raises(InvalidTransitionError) as exc_info:
            sm.transition_to(State.TRANSCRIBING)
        assert "IDLE" in str(exc_info.value)
        assert "TRANSCRIBING" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


class TestCallbacks:
    """Test state change callback invocation."""

    def test_callback_invoked_on_recording(self, sm):
        entered = []
        sm.on_state_change(State.RECORDING, lambda s: entered.append(s))
        sm.start_recording()
        assert State.RECORDING in entered

    def test_callback_invoked_on_transcribing(self, sm):
        entered = []
        sm.on_state_change(State.TRANSCRIBING, lambda s: entered.append(s))
        sm.start_recording()
        sm.stop_recording()
        assert State.TRANSCRIBING in entered

    def test_callback_invoked_on_idle(self, sm):
        entered = []
        sm.on_state_change(State.IDLE, lambda s: entered.append(s))
        sm.start_recording()
        sm.stop_recording()
        sm.transcription_complete()
        assert State.IDLE in entered

    def test_multiple_callbacks_all_invoked(self, sm):
        calls = []
        cb1 = lambda s: calls.append(("cb1", s))
        cb2 = lambda s: calls.append(("cb2", s))
        sm.on_state_change(State.RECORDING, cb1)
        sm.on_state_change(State.RECORDING, cb2)
        sm.start_recording()
        assert ("cb1", State.RECORDING) in calls
        assert ("cb2", State.RECORDING) in calls

    def test_callback_exception_does_not_break_fsm(self, sm):
        def bad_callback(state):
            raise ValueError("oops")

        sm.on_state_change(State.RECORDING, bad_callback)
        # Should not raise
        result = sm.start_recording()
        assert result is True
        assert sm.is_recording is True

    def test_callback_invocation_order(self, sm):
        order = []
        sm.on_state_change(State.RECORDING, lambda s: order.append("RECORDING"))
        sm.on_state_change(State.TRANSCRIBING, lambda s: order.append("TRANSCRIBING"))
        sm.on_state_change(State.IDLE, lambda s: order.append("IDLE"))
        sm.start_recording()
        sm.stop_recording()
        sm.transcription_complete()
        assert order == ["RECORDING", "TRANSCRIBING", "IDLE"]


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Test concurrent state transitions."""

    def test_concurrent_start_attempts(self):
        sm = StateMachine()
        successes = []
        failures = []
        lock = threading.Lock()

        def try_start():
            result = sm.start_recording()
            with lock:
                if result:
                    successes.append(threading.current_thread().name)
                else:
                    failures.append(threading.current_thread().name)

        threads = [threading.Thread(target=try_start, name=f"t{i}") for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(successes) == 1
        assert len(failures) == 9
        assert sm.is_recording is True

    def test_concurrent_stop_attempts(self):
        sm = StateMachine()
        sm.start_recording()
        successes = []
        failures = []
        lock = threading.Lock()

        def try_stop():
            result = sm.stop_recording()
            with lock:
                if result:
                    successes.append(threading.current_thread().name)
                else:
                    failures.append(threading.current_thread().name)

        threads = [threading.Thread(target=try_stop, name=f"t{i}") for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(successes) == 1
        assert len(failures) == 9
        assert sm.is_transcribing is True

    def test_concurrent_full_cycles(self):
        """Multiple threads doing full lifecycle cycles on separate instances."""
        errors = []
        lock = threading.Lock()

        def do_cycle():
            s = StateMachine()
            try:
                for _ in range(100):
                    s.start_recording()
                    s.stop_recording()
                    s.transcription_complete()
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=do_cycle, name=f"t{i}") for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_rapid_toggle(self):
        """Simulate rapid Fn key press/release."""
        sm = StateMachine()
        errors = []
        lock = threading.Lock()

        def toggle():
            try:
                for _ in range(200):
                    sm.start_recording()
                    sm.stop_recording()
                    sm.transcription_complete()
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=toggle, name=f"t{i}") for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert sm.current_state == State.IDLE

    def test_state_consistency_after_stress(self):
        sm = StateMachine()

        def worker():
            for _ in range(50):
                sm.start_recording()
                sm.stop_recording()
                sm.transcription_complete()

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sm.current_state == State.IDLE
        assert sm.is_idle is True
        assert sm.is_recording is False
        assert sm.is_transcribing is False


# ---------------------------------------------------------------------------
# Transition history
# ---------------------------------------------------------------------------


class TestTransitionHistory:
    """Test transition history tracking."""

    def test_history_tracks_transitions(self, sm):
        sm.start_recording()
        sm.stop_recording()
        sm.transcription_complete()
        history = sm.transition_history
        assert len(history) == 3
        assert "IDLE -> RECORDING" in history
        assert "RECORDING -> TRANSCRIBING" in history
        assert "TRANSCRIBING -> IDLE" in history

    def test_empty_history_initially(self, sm):
        assert sm.transition_history == []

    def test_history_is_copy(self, sm):
        sm.start_recording()
        history1 = sm.transition_history
        sm.stop_recording()
        history2 = sm.transition_history
        assert len(history2) == len(history1) + 1

    def test_history_resets_on_new_instance(self):
        sm1 = StateMachine()
        sm1.start_recording()
        sm2 = StateMachine()
        assert sm2.transition_history == []


# ---------------------------------------------------------------------------
# Convenience methods
# ---------------------------------------------------------------------------


class TestConvenienceMethods:
    """Test start_recording, stop_recording, transcription_complete."""

    def test_start_recording_from_idle(self, sm):
        assert sm.start_recording() is True

    def test_start_recording_from_recording_returns_false(self, sm):
        sm.start_recording()
        assert sm.start_recording() is False

    def test_start_recording_from_transcribing_returns_false(self, sm):
        sm.start_recording()
        sm.stop_recording()
        # start_recording() catches InvalidTransitionError and returns False
        assert sm.start_recording() is False

    def test_stop_recording_from_recording(self, sm):
        sm.start_recording()
        assert sm.stop_recording() is True

    def test_stop_recording_from_idle_returns_false(self, sm):
        assert sm.stop_recording() is False

    def test_stop_recording_from_transcribing_via_transition_raises(self, sm):
        sm.start_recording()
        sm.stop_recording()
        # stop_recording() catches InvalidTransitionError and returns False
        assert sm.stop_recording() is False

    def test_transcription_complete_from_transcribing(self, sm):
        sm.start_recording()
        sm.stop_recording()
        assert sm.transcription_complete() is True

    def test_transcription_complete_from_idle_returns_false(self, sm):
        assert sm.transcription_complete() is False

    def test_transcription_complete_from_recording_via_transition_raises(self, sm):
        sm.start_recording()
        # transcription_complete() catches InvalidTransitionError and returns False
        assert sm.transcription_complete() is False


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


class TestToDict:
    """Test to_dict() output format."""

    def test_idle_dict(self, sm):
        d = sm.to_dict()
        assert d["state"] == "IDLE"
        assert d["is_idle"] is True
        assert d["is_recording"] is False
        assert d["is_transcribing"] is False

    def test_recording_dict(self, sm):
        sm.start_recording()
        d = sm.to_dict()
        assert d["state"] == "RECORDING"
        assert d["is_idle"] is False
        assert d["is_recording"] is True
        assert d["is_transcribing"] is False

    def test_transcribing_dict(self, sm):
        sm.start_recording()
        sm.stop_recording()
        d = sm.to_dict()
        assert d["state"] == "TRANSCRIBING"
        assert d["is_idle"] is False
        assert d["is_recording"] is False
        assert d["is_transcribing"] is True

    def test_to_dict_is_thread_safe(self):
        sm = StateMachine()
        errors = []
        lock = threading.Lock()

        def read_dict():
            try:
                for _ in range(100):
                    d = sm.to_dict()
                    assert isinstance(d, dict)
                    assert "state" in d
            except Exception as e:
                with lock:
                    errors.append(e)

        def transition():
            for _ in range(100):
                sm.start_recording()
                sm.stop_recording()
                sm.transcription_complete()

        t1 = threading.Thread(target=read_dict)
        t2 = threading.Thread(target=transition)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(errors) == 0

"""Integration test for the core engine (engine + state_machine + audio).

Verifies that the FSM and AudioEngine work together correctly:
- State transitions follow valid paths only
- Recording start/stop works with FSM integration
- Illegal transitions are properly rejected

Run: python src/whispy/core/test_core.py
"""

import sys
from pathlib import Path

# Ensure src/ is on the path
src_dir = Path(__file__).parent.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from whispy.core.engine import DictationState, Engine
from whispy.core.state_machine import State, StateMachine, InvalidTransitionError


def test_state_machine_transitions():
    """Test valid state transitions."""
    sm = StateMachine()

    # Start in IDLE
    assert sm.current_state == State.IDLE
    assert sm.is_idle is True

    # IDLE -> RECORDING
    assert sm.start_recording() is True
    assert sm.is_recording is True

    # RECORDING -> TRANSCRIBING
    assert sm.stop_recording() is True
    assert sm.is_transcribing is True

    # TRANSCRIBING -> IDLE
    assert sm.transcription_complete() is True
    assert sm.is_idle is True

    print("  [OK] Valid transitions")


def test_state_machine_illegal_transitions():
    """Test that illegal transitions are rejected."""
    sm = StateMachine()

    # IDLE -> TRANSCRIBING is illegal
    try:
        sm.transition_to(State.TRANSCRIBING)
        assert False, "Should have raised InvalidTransitionError"
    except InvalidTransitionError:
        pass

    # IDLE -> RECORDING (valid)
    sm.start_recording()

    # RECORDING -> RECORDING is illegal (start_recording returns False)
    assert sm.start_recording() is False

    # RECORDING -> IDLE is illegal (must go through TRANSCRIBING)
    try:
        sm.transition_to(State.IDLE)
        assert False, "Should have raised InvalidTransitionError"
    except InvalidTransitionError:
        pass

    print("  [OK] Illegal transitions rejected")


def test_state_machine_callbacks():
    """Test that state change callbacks are invoked."""
    sm = StateMachine()
    entered_states = []

    def on_state_change(state):
        entered_states.append(state)

    sm.on_state_change(State.RECORDING, on_state_change)
    sm.on_state_change(State.TRANSCRIBING, on_state_change)
    sm.on_state_change(State.IDLE, on_state_change)

    sm.start_recording()
    assert State.RECORDING in entered_states

    sm.stop_recording()
    assert State.TRANSCRIBING in entered_states

    sm.transcription_complete()
    assert State.IDLE in entered_states

    print("  [OK] Callbacks invoked on state change")


def test_engine_with_state_machine():
    """Test Engine + DictationState integration."""
    ds = DictationState()
    engine = Engine(ds)

    status = engine.get_status()
    assert status["is_recording"] is False
    assert status["is_transcribing"] is False
    assert status["model_loaded"] is False

    print("  [OK] Engine status reporting")


def test_engine_status_callbacks():
    """Test that engine notifies callbacks on state changes."""
    ds = DictationState()
    engine = Engine(ds)
    notifications = []

    def on_change():
        notifications.append(engine.get_status())

    engine.on_status_change(on_change)

    # Trigger a status change (simulated — in real usage this comes from FSM)
    ds.is_recording = True
    engine._notify_status_change()

    assert len(notifications) == 1
    assert notifications[0]["is_recording"] is True

    print("  [OK] Engine status callbacks")


def test_full_lifecycle():
    """Test the full recording lifecycle via FSM."""
    sm = StateMachine()

    # Full cycle: IDLE -> RECORDING -> TRANSCRIBING -> IDLE
    assert sm.start_recording() is True  # IDLE -> RECORDING
    assert sm.stop_recording() is True  # RECORDING -> TRANSCRIBING
    assert sm.transcription_complete() is True  # TRANSCRIBING -> IDLE

    history = sm.transition_history
    assert len(history) == 3
    assert "IDLE -> RECORDING" in history
    assert "RECORDING -> TRANSCRIBING" in history
    assert "TRANSCRIBING -> IDLE" in history

    print("  [OK] Full lifecycle (IDLE->REC->TRANSC->IDLE)")


def test_audio_engine_integration():
    """Test AudioEngine FSM integration (without actual audio)."""
    from whispy.core.audio import AudioEngine

    sm = StateMachine()
    audio = AudioEngine(sm)

    # Not recording initially
    assert audio.is_recording is False
    assert audio.is_transcribing is False

    # Start recording (FSM transition)
    result = audio.start()
    assert result is True
    assert audio.is_recording is True

    # Can't start again (FSM blocks)
    result = audio.start()
    assert result is False

    # Stop (transitions to TRANSCRIBING)
    result = audio.stop()
    assert result is True
    assert audio.is_transcribing is True

    # Complete transcription (back to IDLE)
    sm.transcription_complete()
    assert audio.is_recording is False
    assert audio.is_transcribing is False

    print("  [OK] AudioEngine FSM integration")


if __name__ == "__main__":
    print("Running core engine tests...\n")

    tests = [
        ("State machine valid transitions", test_state_machine_transitions),
        ("State machine illegal transitions", test_state_machine_illegal_transitions),
        ("State machine callbacks", test_state_machine_callbacks),
        ("Engine with state machine", test_engine_with_state_machine),
        ("Engine status callbacks", test_engine_status_callbacks),
        ("Full lifecycle", test_full_lifecycle),
        ("AudioEngine FSM integration", test_audio_engine_integration),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        print(f"  {name}...", end=" ")
        try:
            test_fn()
            passed += 1
        except Exception as exc:
            print(f"FAILED: {exc}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    if failed > 0:
        sys.exit(1)
    print("All core engine tests passed!")

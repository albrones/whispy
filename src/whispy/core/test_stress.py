"""Stress tests for the core engine under concurrent access.

Tests rapid state transitions and thread safety.
Run: python src/whispy/core/test_stress.py
"""

import sys
import threading
import time
from pathlib import Path

src_dir = Path(__file__).parent.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from whispy.core.state_machine import State, StateMachine, InvalidTransitionError


def test_rapid_transitions():
    """Test rapid sequential state transitions."""
    sm = StateMachine()
    errors = []

    def do_cycle():
        try:
            sm.start_recording()
            sm.stop_recording()
            sm.transcription_complete()
        except Exception as e:
            errors.append(e)

    # Run 1000 cycles sequentially
    for _ in range(1000):
        do_cycle()

    assert sm.current_state == State.IDLE
    assert len(errors) == 0, f"Errors: {errors}"
    print("  [OK] 1000 sequential cycles")


def test_concurrent_start_attempts():
    """Test that concurrent start_recording calls are handled safely."""
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

    # Launch 10 threads to start recording simultaneously
    threads = [threading.Thread(target=try_start, name=f"t{i}") for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Only one should succeed
    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(failures) == 9, f"Expected 9 failures, got {len(failures)}"
    assert sm.is_recording is True
    print("  [OK] Concurrent start_recording (1 success, 9 failures)")


def test_concurrent_stop_attempts():
    """Test that concurrent stop_recording calls are handled safely."""
    sm = StateMachine()
    sm.start_recording()  # IDLE -> RECORDING

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

    # Launch 10 threads to stop recording simultaneously
    threads = [threading.Thread(target=try_stop, name=f"t{i}") for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Only one should succeed
    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(failures) == 9, f"Expected 9 failures, got {len(failures)}"
    assert sm.is_transcribing is True
    print("  [OK] Concurrent stop_recording (1 success, 9 failures)")


def test_concurrent_full_cycles():
    """Test multiple threads doing full IDLE->REC->TRANSC->IDLE cycles."""
    errors = []
    lock = threading.Lock()

    def do_cycle():
        sm = StateMachine()
        try:
            for _ in range(100):
                sm.start_recording()
                sm.stop_recording()
                sm.transcription_complete()
        except Exception as e:
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=do_cycle, name=f"t{i}") for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Errors: {errors}"
    print("  [OK] 5 threads x 100 cycles each")


def test_rapid_toggle():
    """Simulate rapid Fn key press/release (start/stop toggling)."""
    sm = StateMachine()
    errors = []

    def toggle():
        try:
            for _ in range(200):
                sm.start_recording()
                sm.stop_recording()
                sm.transcription_complete()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=toggle, name=f"t{i}") for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Errors: {errors}"
    print("  [OK] Rapid toggle (5 threads x 200 toggles)")


def test_state_consistency_after_stress():
    """Verify FSM is in valid state after stress testing."""
    sm = StateMachine()

    # Do a bunch of concurrent operations
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

    # Final state should be IDLE
    assert sm.current_state == State.IDLE, f"Expected IDLE, got {sm.current_state}"
    assert sm.is_idle is True
    assert sm.is_recording is False
    assert sm.is_transcribing is False
    print("  [OK] State consistency after stress (final: IDLE)")


if __name__ == "__main__":
    print("Running stress tests...\n")

    tests = [
        ("Rapid sequential transitions", test_rapid_transitions),
        ("Concurrent start attempts", test_concurrent_start_attempts),
        ("Concurrent stop attempts", test_concurrent_stop_attempts),
        ("Concurrent full cycles", test_concurrent_full_cycles),
        ("Rapid toggle", test_rapid_toggle),
        ("State consistency after stress", test_state_consistency_after_stress),
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
    print("All stress tests passed!")

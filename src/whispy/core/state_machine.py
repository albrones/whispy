"""Formal Finite State Machine for dictation lifecycle management.

Manages all state transitions (IDLE -> RECORDING -> TRANSCRIBING -> IDLE)
and prevents illegal transitions (e.g., starting recording while transcribing).
"""

import threading
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional


class State(Enum):
    """Possible states of the dictation system."""

    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()


class InvalidTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""

    pass


class StateMachine:
    """Thread-safe FSM that manages the dictation lifecycle.

    Valid transitions:
        IDLE -> RECORDING (start recording)
        RECORDING -> TRANSCRIBING (stop recording, begin transcription)
        TRANSCRIBING -> IDLE (transcription complete)

    Illegal transitions raise InvalidTransitionError:
        - RECORDING -> RECORDING (already recording)
        - TRANSCRIBING -> RECORDING (can't start while transcribing)
        - IDLE -> TRANSCRIBING (can't skip to transcription)
    """

    def __init__(self):
        self._current_state = State.IDLE
        self._lock = threading.Lock()
        self._transitions: List[str] = []
        self._callbacks: Dict[State, List[Callable]] = {}

    def on_state_change(self, state: State, callback: Callable) -> None:
        """Register a callback for when the FSM enters a specific state."""
        if state not in self._callbacks:
            self._callbacks[state] = []
        self._callbacks[state].append(callback)

    def _notify_callbacks(self, new_state: State) -> None:
        """Call all registered callbacks for the new state."""
        if new_state in self._callbacks:
            for cb in self._callbacks[new_state]:
                try:
                    cb(new_state)
                except Exception:
                    pass

    @property
    def current_state(self) -> State:
        """Get the current state (thread-safe)."""
        with self._lock:
            return self._current_state

    @property
    def is_idle(self) -> bool:
        return self.current_state == State.IDLE

    @property
    def is_recording(self) -> bool:
        return self.current_state == State.RECORDING

    @property
    def is_transcribing(self) -> bool:
        return self.current_state == State.TRANSCRIBING

    def to_dict(self) -> Dict[str, Any]:
        """Return current state as a dictionary."""
        with self._lock:
            return {
                "state": self._current_state.name,
                "is_idle": self._current_state == State.IDLE,
                "is_recording": self._current_state == State.RECORDING,
                "is_transcribing": self._current_state == State.TRANSCRIBING,
            }

    def transition_to(self, target: State) -> bool:
        """Attempt to transition to a new state.

        Returns True if the transition was successful, False if it was
        blocked by an invalid transition.

        Raises InvalidTransitionError for truly illegal transitions.
        """
        with self._lock:
            current = self._current_state

            # Define valid transitions
            valid_transitions = {
                State.IDLE: [State.RECORDING],
                State.RECORDING: [State.TRANSCRIBING],
                State.TRANSCRIBING: [State.IDLE],
            }

            allowed = valid_transitions.get(current, [])

            if target == current:
                # Already in this state — no-op, return True (idempotent)
                return True

            if target not in allowed:
                raise InvalidTransitionError(
                    f"Cannot transition from {current.name} to {target.name}. "
                    f"Allowed: {[s.name for s in allowed]}"
                )

            self._current_state = target
            self._transitions.append(f"{current.name} -> {target.name}")

        # Notify outside the lock to avoid deadlocks
        self._notify_callbacks(target)
        return True

    def start_recording(self) -> bool:
        """Transition from IDLE to RECORDING. Returns False if already recording."""
        with self._lock:
            if self._current_state == State.RECORDING:
                return False
        try:
            return self.transition_to(State.RECORDING)
        except InvalidTransitionError:
            return False

    def stop_recording(self) -> bool:
        """Transition from RECORDING to TRANSCRIBING. Returns False if not recording."""
        with self._lock:
            if self._current_state != State.RECORDING:
                return False
        try:
            return self.transition_to(State.TRANSCRIBING)
        except InvalidTransitionError:
            return False

    def transcription_complete(self) -> bool:
        """Transition from TRANSCRIBING to IDLE. Returns False if not transcribing."""
        with self._lock:
            if self._current_state != State.TRANSCRIBING:
                return False
        try:
            return self.transition_to(State.IDLE)
        except InvalidTransitionError:
            return False

    @property
    def transition_history(self) -> List[str]:
        """Return the history of state transitions."""
        with self._lock:
            return list(self._transitions)

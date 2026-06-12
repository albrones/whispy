"""Core engine — state management, model loading, and transcription orchestration.

Integrates the StateMachine, AudioEngine, EventTapListener, and TextInjector
into a unified interface for the UI and API layers.
"""

import logging
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel

from ..hardware.event_tap import DEFAULT_TRIGGER_KEYCODE, EventTapListener
from ..hardware.injection import TextInjector
from .audio import RECORDING_PATH, AudioEngine
from .config import (
    DEFAULT_CONFIG,
    MODEL_PRESETS,
    SUPPORTED_LANGUAGES,
    load_config,
    save_config,
)
from .state_machine import State, StateMachine
from .text_cleaner import clean_text

# Public API — re-exported for the UI and API layers (and kept out of ruff's
# unused-import sweep). Consumers import config constants from here.
__all__ = [
    "Engine",
    "DictationState",
    "load_model_async",
    "DEFAULT_CONFIG",
    "MODEL_PRESETS",
    "SUPPORTED_LANGUAGES",
    "load_config",
    "save_config",
    "DEFAULT_TRIGGER_KEYCODE",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------
# Config loading/saving are now in config.py with validation and migration.
# Model loading
# ---------------------------------------------------------------------------
def _load_model(config: dict[str, Any]) -> WhisperModel:
    """Instantiate WhisperModel from config dict. Always uses CPU int8."""
    cpu_threads = 0
    try:
        cpu_threads = max(2, os.cpu_count() // 2)
    except (TypeError, AttributeError):
        cpu_threads = 4
    return WhisperModel(
        config["model_size"],
        device="cpu",
        compute_type="int8",
        cpu_threads=cpu_threads,
    )


def load_model_async(engine: "Engine") -> None:
    """Load the whisper model in a background thread."""

    def _worker():
        engine.state.model_loading = True
        engine._notify_status_change()
        try:
            model_name = engine.state.config["model_size"]
            print(f"[model] Loading '{model_name}' with CPU int8...")
            new_model = _load_model(engine.state.config)
            engine.state.model = new_model
            print("[model] Loaded successfully")
        except Exception as exc:
            print(f"[model] Error loading model: {exc}", file=sys.stderr)
            engine.state.model = None
        finally:
            engine.state.model_loading = False
            engine._notify_status_change()

    threading.Thread(target=_worker, name="model-loader", daemon=True).start()


# ---------------------------------------------------------------------------
# DictationState (kept for backward compatibility)
# ---------------------------------------------------------------------------
class DictationState:
    """Shared state between threads for recording and transcription."""

    def __init__(self):
        self.recording_process: Any = None
        self.is_recording = False
        self.is_transcribing = False
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.fn_listener_active = False
        self.last_transcription: str | None = None
        self.model: WhisperModel | None = None
        self.model_loading = False
        self.config: dict[str, Any] = dict(DEFAULT_CONFIG)
        self.app: Any = None


# ---------------------------------------------------------------------------
# Core Engine
# ---------------------------------------------------------------------------
class Engine:
    """Central orchestrator that integrates FSM, audio, hardware, and injection.

    Responsibilities:
    - Manage the StateMachine lifecycle (IDLE -> RECORDING -> TRANSCRIBING -> IDLE)
    - Coordinate audio recording and transcription
    - Wire up the Fn key event tap listener to start/stop recording
    - Inject transcribed text via the TextInjector
    - Notify UI/API layers of state changes
    """

    def __init__(
        self,
        state: DictationState,
        config_path: Path | None = None,
    ) -> None:
        self.state = state
        self._status_callbacks: list[Callable] = []
        self._recording_start_callbacks: list[Callable] = []
        self._recording_stop_callbacks: list[Callable] = []
        self._fn_pressed_callbacks: list[Callable] = []
        self._fn_released_callbacks: list[Callable] = []
        self._config_path = config_path or (Path.home() / ".config" / "whispy" / "config.json")
        self._fn_pressed = False

        # Core components
        self._state_machine = StateMachine()
        self._audio_engine = AudioEngine(self._state_machine)
        self._text_injector = TextInjector(copy_to_clipboard=state.config.get("copy_to_clipboard", True))

        # Hardware listener (wired up later via start_fn_listener)
        self._fn_listener: EventTapListener | None = None

        # Transcription worker thread
        self._transcription_thread: threading.Thread | None = None
        self._transcription_running = False

        # Register FSM callbacks to keep DictationState in sync
        self._state_machine.on_state_change(State.RECORDING, self._on_fsm_recording)
        self._state_machine.on_state_change(State.TRANSCRIBING, self._on_fsm_transcribing)
        self._state_machine.on_state_change(State.IDLE, self._on_fsm_idle)

    def _on_fsm_recording(self, _state: State) -> None:
        """Sync DictationState when FSM enters RECORDING."""
        self.state.is_recording = True
        self.state.is_transcribing = False
        self._notify_recording_start()

    def _on_fsm_transcribing(self, _state: State) -> None:
        """Sync DictationState when FSM enters TRANSCRIBING."""
        self.state.is_recording = False
        self.state.is_transcribing = True
        self._notify_recording_stop()

    def _on_fsm_idle(self, _state: State) -> None:
        """Sync DictationState when FSM enters IDLE."""
        self.state.is_recording = False
        self.state.is_transcribing = False

    # -- Recording lifecycle callbacks --

    def on_recording_start(self, callback: Callable) -> None:
        """Register a callback to be called when recording starts."""
        self._recording_start_callbacks.append(callback)

    def on_recording_stop(self, callback: Callable) -> None:
        """Register a callback to be called when recording stops."""
        self._recording_stop_callbacks.append(callback)

    def _notify_recording_start(self) -> None:
        """Notify all registered callbacks of recording start."""
        for cb in list(self._recording_start_callbacks):
            try:
                cb()
            except Exception:
                logger.exception("[engine] Error in recording start callback")

    def _notify_recording_stop(self) -> None:
        """Notify all registered callbacks of recording stop."""
        for cb in list(self._recording_stop_callbacks):
            try:
                cb()
            except Exception:
                logger.exception("[engine] Error in recording stop callback")

    def on_fn_pressed(self, callback: Callable) -> None:
        """Register a callback to be called when FN key is pressed."""
        self._fn_pressed_callbacks.append(callback)

    def on_fn_released(self, callback: Callable) -> None:
        """Register a callback to be called when FN key is released."""
        self._fn_released_callbacks.append(callback)

    def _notify_fn_pressed(self) -> None:
        """Notify all registered callbacks of FN key press."""
        self._fn_pressed = True
        for cb in list(self._fn_pressed_callbacks):
            try:
                cb()
            except Exception:
                logger.exception("[engine] Error in fn-pressed callback")

    def _notify_fn_released(self) -> None:
        """Notify all registered callbacks of FN key release."""
        self._fn_pressed = False
        for cb in list(self._fn_released_callbacks):
            try:
                cb()
            except Exception:
                logger.exception("[engine] Error in fn-released callback")

    # -- Callback system --

    def on_status_change(self, callback: Callable) -> None:
        """Register a callback to be called when state changes."""
        self._status_callbacks.append(callback)

    def _notify_status_change(self) -> None:
        """Notify all registered callbacks of state changes."""
        for cb in list(self._status_callbacks):
            try:
                cb()
            except Exception:
                logger.exception("[engine] Error in status-change callback")

    def get_status(self) -> dict[str, Any]:
        """Return current engine status as a dict."""
        return {
            "is_recording": self.state.is_recording,
            "is_transcribing": self.state.is_transcribing,
            "fn_pressed": self._fn_pressed,
            "fn_listener_active": self.state.fn_listener_active,
            "model_loaded": self.state.model is not None,
            "model_loading": self.state.model_loading,
            "fsm": self._state_machine.to_dict(),
        }

    # -- Recording lifecycle --

    def start_recording(self) -> bool:
        """Start audio recording via FSM -> AudioEngine."""
        return self._audio_engine.start()

    def stop_recording(self) -> None:
        """Stop recording and transition to TRANSCRIBING."""
        self._audio_engine.stop()

    # -- Transcription --

    def run_transcription(self) -> str | None:
        """Execute transcription synchronously (called from worker thread)."""
        if self.state.model is None:
            print("[transcribe] Model not loaded, skipping", file=sys.stderr)
            return None

        if not os.path.exists(RECORDING_PATH):
            return None

        text = self._audio_engine.transcribe(
            audio_path=RECORDING_PATH,
            model=self.state.model,
            language=self.state.config.get("language", "fr"),
            beam_size=self.state.config.get("beam_size", 1),
            best_of=self.state.config.get("best_of", 2),
            auto_detect_min_duration=self.state.config.get("auto_detect_min_duration", 0.5),
        )

        if text:
            # Strip Whisper watermark credits before injection
            cleaned = clean_text(text)
            if cleaned:
                self.state.last_transcription = cleaned
                self._text_injector.inject(cleaned)
            self._audio_engine.cleanup_audio_file(RECORDING_PATH)

        return text

    # -- Fn key listener --

    def _trigger_keycode_from_config(self) -> int:
        """Always return the hardcoded Fn keycode (63)."""
        return DEFAULT_TRIGGER_KEYCODE

    def start_fn_listener(self) -> None:
        """Start the trigger key event tap listener."""
        trigger_keycode = self._trigger_keycode_from_config()

        def _on_trigger_press() -> None:
            """Handle trigger key press — start recording."""
            self._notify_fn_pressed()
            subprocess.Popen(
                ["afplay", "/System/Library/Sounds/Tink.aiff"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.start_recording()

        def _on_trigger_release() -> None:
            """Handle trigger key release — stop recording asynchronously."""
            self._notify_fn_released()
            self.stop_recording()
            self.state.stop_event.set()

        self._fn_listener = EventTapListener(
            trigger_keycode=trigger_keycode,
            on_trigger_press=_on_trigger_press,
            on_trigger_release=_on_trigger_release,
        )
        self._fn_listener.start()
        self.state.fn_listener_active = self._fn_listener.active

    def stop_fn_listener(self) -> None:
        """Stop the trigger key event tap listener."""
        if self._fn_listener:
            self._fn_listener.stop()
            self.state.fn_listener_active = False

    # -- Transcription worker --

    def start_transcription_worker(self) -> None:
        """Start the background transcription worker thread."""
        self._transcription_running = True

        def _worker() -> None:
            while self._transcription_running:
                self.state.stop_event.wait(timeout=0.1)
                if self.state.stop_event.is_set():
                    self.state.stop_event.clear()
                    self._notify_status_change()

                    text = self.run_transcription()
                    if text:
                        self._state_machine.transcription_complete()

                    self._notify_status_change()

                    subprocess.Popen(
                        ["afplay", "/System/Library/Sounds/Pop.aiff"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

        self._transcription_thread = threading.Thread(target=_worker, name="transcription-worker", daemon=True)
        self._transcription_thread.start()

    def stop_transcription_worker(self) -> None:
        """Stop the background transcription worker thread."""
        self._transcription_running = False
        if self._transcription_thread and self._transcription_thread.is_alive():
            self._transcription_thread.join(timeout=5.0)

    # -- Config --

    def update_config(self, updates: dict[str, Any]) -> bool:
        """Apply config updates. Returns True if model reload was triggered."""
        needs_reload = False
        for key, value in updates.items():
            if key in DEFAULT_CONFIG:
                self.state.config[key] = value
        save_config(self.state.config, self._config_path)

        if "copy_to_clipboard" in updates:
            self._text_injector.update_config(updates["copy_to_clipboard"])
        if "model_size" in updates:
            needs_reload = True
        return needs_reload

    # -- Lifecycle --

    def start(self) -> None:
        """Start all engine components."""
        self.start_fn_listener()
        self.start_transcription_worker()
        load_model_async(self)

    def stop(self) -> None:
        """Stop all engine components."""
        self.stop_transcription_worker()
        self.stop_fn_listener()

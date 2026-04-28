"""Core engine — state management, model loading, and transcription orchestration.

Integrates the StateMachine, AudioEngine, EventTapListener, and TextInjector
into a unified interface for the UI and API layers.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from faster_whisper import WhisperModel

from .audio import AudioEngine, RECORDING_PATH
from .state_machine import State, StateMachine
from ..hardware.event_tap import EventTapListener, DEFAULT_TRIGGER_KEYCODE, PRESET_TRIGGERS
from ..hardware.injection import TextInjector

DEFAULT_CONFIG: Dict[str, Any] = {
    "model_size": "small",
    "compute_key": "cpu-int8",
    "language": "fr",
    "beam_size": 1,
    "best_of": 2,
    "copy_to_clipboard": False,
    "auto_detect_min_duration": 0.5,
    "trigger_key": "fn",
}

MODEL_PRESETS: Dict[str, Dict[str, str]] = {
    "tiny": {
        "label": "Fast (tiny)",
        "description": "75 MB — fastest, limited quality",
    },
    "base": {
        "label": "Light (base)",
        "description": "142 MB — good speed/quality balance",
    },
    "small": {"label": "Normal (small)", "description": "466 MB — recommended"},
    "medium": {"label": "Accurate (medium)", "description": "1.5 GB — best quality"},
    "large-v3": {
        "label": "Maximum (large)",
        "description": "2.9 GB — maximum quality, slow",
    },
}

SUPPORTED_LANGUAGES: Dict[str, str] = {
    "auto": "Auto-detect (requires >= 1s audio for reliable detection)",
    "fr": "French",
    "en": "English",
}

COMPUTE_OPTIONS: Dict[str, Dict[str, str]] = {
    "cpu-int8": {"label": "CPU (int8)", "device": "cpu", "compute_type": "int8"},
    "cpu-float32": {
        "label": "CPU (float32)",
        "device": "cpu",
        "compute_type": "float32",
    },
    "cuda-float16": {
        "label": "CUDA (float16)",
        "device": "cuda",
        "compute_type": "float16",
    },
    "cuda-int8": {
        "label": "CUDA (int8)",
        "device": "cuda",
        "compute_type": "int8_float16",
    },
}


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------
def load_config(config_path: Path) -> Dict[str, Any]:
    """Load config from disk, falling back to defaults."""
    config = dict(DEFAULT_CONFIG)
    if config_path.exists():
        try:
            with open(config_path) as f:
                saved = json.load(f)
            config.update({k: saved[k] for k in saved if k in DEFAULT_CONFIG})
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[config] Failed to load {config_path}: {exc}", file=sys.stderr)
    return config


def save_config(config: Dict[str, Any], config_path: Path) -> None:
    """Persist config to disk atomically, filtering to known keys."""
    filtered: Dict[str, Any] = {}
    for key in DEFAULT_CONFIG:
        if key in config:
            filtered[key] = config[key]
        else:
            filtered[key] = DEFAULT_CONFIG[key]
    for key in config:
        if key not in DEFAULT_CONFIG:
            print(
                f"[config] Unknown config key '{key}' filtered out",
                file=sys.stderr,
            )
    config_dir = config_path.parent
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = config_path.with_suffix(".json.tmp")
        with open(tmp_path, "w") as f:
            json.dump(filtered, f, indent=2)
        os.replace(tmp_path, config_path)
    except OSError as exc:
        print(f"[config] Failed to save {config_path}: {exc}", file=sys.stderr)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
def _load_model(config: Dict[str, Any]) -> WhisperModel:
    """Instantiate WhisperModel from config dict."""
    compute = COMPUTE_OPTIONS.get(config["compute_key"], COMPUTE_OPTIONS["cpu-int8"])
    cpu_threads = 0
    if compute["device"] == "cpu":
        try:
            cpu_threads = max(2, os.cpu_count() // 2)
        except (TypeError, AttributeError):
            cpu_threads = 4
    return WhisperModel(
        config["model_size"],
        device=compute["device"],
        compute_type=compute["compute_type"],
        cpu_threads=cpu_threads,
    )


def load_model_async(engine: "Engine") -> None:
    """Load the whisper model in a background thread."""

    def _worker():
        engine.state.model_loading = True
        engine._notify_status_change()
        try:
            model_name = engine.state.config["model_size"]
            compute_key = engine.state.config["compute_key"]
            print(f"[model] Loading '{model_name}' with compute '{compute_key}'...")
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
        self._stop_event = threading.Event()
        self.fn_listener_active = False
        self.last_transcription: Optional[str] = None
        self.model: Optional[WhisperModel] = None
        self.model_loading = False
        self.config: Dict[str, Any] = dict(DEFAULT_CONFIG)
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
        config_path: Optional[Path] = None,
    ) -> None:
        self.state = state
        self._status_callbacks: List[Callable] = []
        self._config_path = config_path or (
            Path.home() / ".config" / "whispy" / "config.json"
        )

        # Core components
        self._state_machine = StateMachine()
        self._audio_engine = AudioEngine(self._state_machine)
        self._text_injector = TextInjector(
            copy_to_clipboard=state.config.get("copy_to_clipboard", True)
        )

        # Hardware listener (wired up later via start_fn_listener)
        self._fn_listener: Optional[EventTapListener] = None

        # Transcription worker thread
        self._transcription_thread: Optional[threading.Thread] = None
        self._transcription_running = False

        # Register FSM callbacks to keep DictationState in sync
        self._state_machine.on_state_change(State.RECORDING, self._on_fsm_recording)
        self._state_machine.on_state_change(
            State.TRANSCRIBING, self._on_fsm_transcribing
        )
        self._state_machine.on_state_change(State.IDLE, self._on_fsm_idle)

    def _on_fsm_recording(self, _state: State) -> None:
        """Sync DictationState when FSM enters RECORDING."""
        self.state.is_recording = True
        self.state.is_transcribing = False

    def _on_fsm_transcribing(self, _state: State) -> None:
        """Sync DictationState when FSM enters TRANSCRIBING."""
        self.state.is_recording = False
        self.state.is_transcribing = True

    def _on_fsm_idle(self, _state: State) -> None:
        """Sync DictationState when FSM enters IDLE."""
        self.state.is_recording = False
        self.state.is_transcribing = False

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
                pass

    def get_status(self) -> Dict[str, Any]:
        """Return current engine status as a dict."""
        return {
            "is_recording": self.state.is_recording,
            "is_transcribing": self.state.is_transcribing,
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

    def run_transcription(self) -> Optional[str]:
        """Execute transcription synchronously (called from worker thread)."""
        if self.state.model is None:
            print("[transcribe] Model not loaded, skipping", file=sys.stderr)
            return None

        if not os.path.exists(RECORDING_PATH):
            return None

        text = self._audio_engine.transcribe(
            audio_path=RECORDING_PATH,
            model=self.state.model,
            language=self.state.config.get("language", "auto"),
            beam_size=self.state.config.get("beam_size", 1),
            best_of=self.state.config.get("best_of", 2),
            auto_detect_min_duration=self.state.config.get(
                "auto_detect_min_duration", 0.5
            ),
        )

        if text:
            self.state.last_transcription = text
            self._text_injector.inject(text)
            self._audio_engine.cleanup_audio_file(RECORDING_PATH)

        return text

    # -- Fn key listener --

    def _trigger_keycode_from_config(self) -> int:
        """Convert the configured trigger_key to a keycode."""
        trigger_key = self.state.config.get("trigger_key", "fn")
        if trigger_key in PRESET_TRIGGERS:
            return PRESET_TRIGGERS[trigger_key][0]
        # Handle custom/learned keycodes stored as strings
        try:
            return int(trigger_key)
        except (ValueError, TypeError):
            return DEFAULT_TRIGGER_KEYCODE

    def start_fn_listener(self) -> None:
        """Start the trigger key event tap listener."""
        trigger_keycode = self._trigger_keycode_from_config()

        def _on_trigger_press() -> None:
            """Handle trigger key press — start recording."""
            subprocess.Popen(
                ["afplay", "/System/Library/Sounds/Tink.aiff"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.start_recording()

        def _on_trigger_release() -> None:
            """Handle trigger key release — stop recording asynchronously."""
            self.stop_recording()
            self.state._stop_event.set()

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
            # Stop learning mode if active
            self._fn_listener.stop_learning()
            self._fn_listener.stop()
            self.state.fn_listener_active = False

    def update_trigger_key(self, trigger_key: str) -> None:
        """Update the trigger key in config and restart the listener."""
        self.state.config["trigger_key"] = trigger_key
        save_config(self.state.config, self._config_path)
        # Restart the listener with the new trigger key
        self.stop_fn_listener()
        self.start_fn_listener()

    def start_learning(self) -> bool:
        """Start learning mode for the trigger key.

        Returns True if learning was started, False if event tap is not active.
        """
        if not self._fn_listener:
            return False
        self._fn_listener.start_learning()
        return True

    def stop_learning(self) -> Optional[int]:
        """Stop learning mode and return the learned keycode.

        Returns None if no keycode was learned or learning was not active.
        """
        if not self._fn_listener:
            return None
        return self._fn_listener.stop_learning()

    # -- Transcription worker --

    def start_transcription_worker(self) -> None:
        """Start the background transcription worker thread."""
        self._transcription_running = True

        def _worker() -> None:
            while self._transcription_running:
                self.state._stop_event.wait(timeout=0.1)
                if self.state._stop_event.is_set():
                    self.state._stop_event.clear()
                    self.state.is_transcribing = True
                    self._notify_status_change()

                    text = self.run_transcription()
                    if text:
                        self.state.last_transcription = text

                    self._state_machine.transcription_complete()
                    self.state.is_transcribing = False
                    self._notify_status_change()

                    subprocess.Popen(
                        ["afplay", "/System/Library/Sounds/Pop.aiff"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

        self._transcription_thread = threading.Thread(
            target=_worker, name="transcription-worker", daemon=True
        )
        self._transcription_thread.start()

    def stop_transcription_worker(self) -> None:
        """Stop the background transcription worker thread."""
        self._transcription_running = False

    # -- Config --

    def update_config(self, updates: Dict[str, Any]) -> bool:
        """Apply config updates. Returns True if model reload was triggered."""
        needs_reload = False
        for key, value in updates.items():
            if key in DEFAULT_CONFIG:
                self.state.config[key] = value
        save_config(self.state.config, self._config_path)

        if "copy_to_clipboard" in updates:
            self._text_injector.update_config(updates["copy_to_clipboard"])
        if any(k in updates for k in ("model_size", "compute_key")):
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

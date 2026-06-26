"""Core engine — state management, model loading, and transcription orchestration.

Integrates the StateMachine, AudioEngine, EventTapListener, and TextInjector
into a unified interface for the UI and API layers.
"""

import logging
import os
import queue
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel

from ..hardware.event_decode import DEFAULT_TRIGGER_KEYCODE
from ..platform import PlatformAdapters, detect
from .config import (
    DEFAULT_CONFIG,
    MODEL_PRESETS,
    SUPPORTED_LANGUAGES,
    TRIGGER_PRESETS,
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
    "TRIGGER_PRESETS",
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
    """Instantiate WhisperModel from config dict. Always uses CPU int8.

    Tries the local HuggingFace cache first (``local_files_only=True``): this
    avoids any network/SSL at startup, which matters inside the .app bundle
    where ``ssl.create_default_context`` otherwise fails on the missing CA file.
    Falls back to an online download only when the model isn't cached yet.
    """
    cpu_threads = 0
    try:
        cpu_threads = max(2, os.cpu_count() // 2)
    except (TypeError, AttributeError):
        cpu_threads = 4

    def _make(local_only: bool) -> WhisperModel:
        return WhisperModel(
            config["model_size"],
            device="cpu",
            compute_type="int8",
            cpu_threads=cpu_threads,
            local_files_only=local_only,
        )

    try:
        return _make(local_only=True)
    except Exception:
        # Not cached — fall back to an online download (needs SSL certs; the
        # daemon sets SSL_CERT_FILE from certifi at startup).
        return _make(local_only=False)


_MODEL_LOAD_RETRY_DELAY = 2.0  # seconds between the initial attempt and one retry


def load_model_async(engine: "Engine") -> None:
    """Load the whisper model in a background thread.

    Retries once on failure (transient download/SSL hiccups), then — instead of
    leaving the model silently unloaded forever — surfaces the failure through
    the engine's model-load-failed callback so the UI/log can tell the user.
    """

    def _worker():
        engine.state.model_loading = True
        engine._notify_status_change()
        model_name = engine.state.config["model_size"]
        last_exc: Exception | None = None
        for attempt in range(2):  # initial attempt + one retry
            try:
                print(f"[model] Loading '{model_name}' with CPU int8...")
                engine.state.model = _load_model(engine.state.config)
                last_exc = None
                print("[model] Loaded successfully")
                break
            except Exception as exc:
                last_exc = exc
                print(f"[model] Error loading model (attempt {attempt + 1}): {exc}", file=sys.stderr)
                if attempt == 0:
                    time.sleep(_MODEL_LOAD_RETRY_DELAY)
        if last_exc is not None:
            engine.state.model = None
            engine._notify_model_load_failed(str(last_exc))
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
        adapters: PlatformAdapters | None = None,
    ) -> None:
        self.state = state
        self._status_callbacks: list[Callable] = []
        self._recording_start_callbacks: list[Callable] = []
        self._recording_stop_callbacks: list[Callable] = []
        self._fn_pressed_callbacks: list[Callable] = []
        self._fn_released_callbacks: list[Callable] = []
        self._injection_denied_callbacks: list[Callable] = []
        self._model_load_failed_callbacks: list[Callable] = []
        self._config_path = config_path or (Path.home() / ".config" / "whispy" / "config.json")
        self._fn_pressed = False

        # Platform adapters bind the OS-coupled seams (hotkey, injection,
        # audio, sounds) at runtime; the engine depends only on the ports.
        self._adapters = adapters or detect()

        # Core components, obtained from the platform adapter set.
        self._state_machine = StateMachine()
        self._audio_engine = self._adapters.make_audio_recorder(self._state_machine)
        self._text_injector = self._adapters.make_text_injector(
            copy_to_clipboard=state.config.get("copy_to_clipboard", False)
        )
        # Forward keystroke-permission denials from the injector (macOS) to any
        # UI subscriber. The Linux adapter has no such hook; guard accordingly.
        if hasattr(self._text_injector, "set_permission_denied_callback"):
            self._text_injector.set_permission_denied_callback(self._notify_injection_denied)
        self._notifier = self._adapters.make_notifier()

        # Hardware listener (wired up later via start_fn_listener)
        self._fn_listener: Any = None

        # Transcription worker thread
        self._transcription_thread: threading.Thread | None = None
        self._transcription_running = False

        # --- Streaming / incremental transcription ---
        # When enabled, the audio engine emits silence/length-bounded chunks onto
        # this queue during RECORDING; a single chunk worker transcribes + injects
        # them in order while recording continues (FSM-1: the FSM stays RECORDING).
        self._streaming = bool(state.config.get("streaming_enabled", False))
        self._chunk_queue: queue.Queue[str] = queue.Queue()
        self._chunk_thread: threading.Thread | None = None
        self._chunk_worker_running = False
        # Reset per recording: whether any chunk has injected text yet (drives the
        # inter-chunk separating space) and whether any chunk produced text at all
        # (drives the single success sound on release).
        self._chunk_any_text = False
        # Chunk texts accumulate here during recording and are typed once on
        # release (avoids mid-recording focus disruption in full-screen apps).
        self._chunk_texts: list[str] = []
        self._apply_streaming_config()

        # Register FSM callbacks to keep DictationState in sync
        self._state_machine.on_state_change(State.RECORDING, self._on_fsm_recording)
        self._state_machine.on_state_change(State.TRANSCRIBING, self._on_fsm_transcribing)
        self._state_machine.on_state_change(State.IDLE, self._on_fsm_idle)

    def _on_fsm_recording(self, _state: State) -> None:
        """Sync DictationState when FSM enters RECORDING."""
        self.state.is_recording = True
        self.state.is_transcribing = False
        # Fresh per-recording streaming accounting.
        self._chunk_any_text = False
        self._chunk_texts = []
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

    def on_injection_permission_denied(self, callback: Callable) -> None:
        """Register a callback fired when text injection is denied a keystroke.

        The callback receives a remediation message (str). Only fires on macOS,
        where the injector classifies the osascript ``1002`` error; debounced to
        one call per permission-state transition.
        """
        self._injection_denied_callbacks.append(callback)

    def _notify_injection_denied(self, message: str) -> None:
        """Fan out an injection permission denial to registered callbacks."""
        for cb in list(self._injection_denied_callbacks):
            try:
                cb(message)
            except Exception:
                logger.exception("[engine] Error in injection-denied callback")

    def on_model_load_failed(self, callback: Callable) -> None:
        """Register a callback fired when the transcription model fails to load.

        The callback receives a message (str). Lets the UI surface a clear
        "model failed to load" state instead of every dictation silently
        returning nothing.
        """
        self._model_load_failed_callbacks.append(callback)

    def _notify_model_load_failed(self, message: str) -> None:
        """Fan out a model-load failure to registered callbacks."""
        logger.error("[engine] model load failed: %s", message)
        for cb in list(self._model_load_failed_callbacks):
            try:
                cb(message)
            except Exception:
                logger.exception("[engine] Error in model-load-failed callback")

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

    def stop_recording(self) -> bool:
        """Stop recording and transition to TRANSCRIBING.

        Returns True only if this actually transitioned RECORDING -> TRANSCRIBING
        (callers gate the transcription stop event on this so a stray release
        does not transcribe a stale/missing file).
        """
        return self._audio_engine.stop()

    def get_level(self) -> float:
        """Live mic input level (0.0-1.0) from the capture stream, for the UI waveform."""
        return self._audio_engine.get_level()

    # -- Transcription --

    def run_transcription(self) -> str | None:
        """Execute transcription synchronously (called from worker thread)."""
        if self.state.model is None:
            print("[transcribe] Model not loaded, skipping", file=sys.stderr)
            return None

        # Capture the path ONCE: if a new recording starts mid-transcription it
        # rebinds the engine's recording_path to a different file, but this local
        # keeps pointing at the file we are actually transcribing.
        path = self._audio_engine.recording_path
        if not path or not os.path.exists(path):
            return None

        # Bias the decoder toward the user's habitual terms, if any.
        vocab = self.state.config.get("custom_vocabulary") or []
        initial_prompt = ", ".join(vocab) if vocab else None

        text = self._audio_engine.transcribe(
            audio_path=path,
            model=self.state.model,
            language=self.state.config.get("language", "fr"),
            beam_size=self.state.config.get("beam_size", 1),
            best_of=self.state.config.get("best_of", 2),
            auto_detect_min_duration=self.state.config.get("auto_detect_min_duration", 0.5),
            min_recording_duration=self.state.config.get("min_recording_duration", 0.3),
            initial_prompt=initial_prompt,
        )

        if text:
            # Strip Whisper watermark credits before injection
            cleaned = clean_text(text)
            if cleaned:
                self.state.last_transcription = cleaned
                self._text_injector.inject(cleaned)
            self._audio_engine.cleanup_audio_file(path)

        return text

    # -- Streaming chunk pipeline (FSM-1: runs during RECORDING) --

    def _apply_streaming_config(self) -> None:
        """(Re)wire the audio engine's streaming from the current config.

        Called at init and whenever streaming config changes at runtime (e.g. the
        menu toggle). Sets ``self._streaming`` and pushes the segmentation params
        to the audio engine; the chunk-worker lifecycle is managed by the caller.
        """
        cfg = self.state.config
        self._streaming = bool(cfg.get("streaming_enabled", False))
        self._audio_engine.configure_streaming(
            self._streaming,
            self._enqueue_chunk,
            pause_ms=cfg.get("pause_ms", 600),
            min_chunk_s=cfg.get("min_chunk_s", 0.4),
            max_chunk_s=cfg.get("max_chunk_s", 12.0),
            aggressiveness=cfg.get("vad_aggressiveness", 2),
        )

    def _enqueue_chunk(self, path: str) -> None:
        """Audio-callback sink: queue a chunk WAV for the chunk worker.

        Runs on the capture-callback thread (and on ``stop()`` for the tail), so
        it must stay cheap — it only enqueues.
        """
        self._chunk_queue.put(path)

    def _transcribe_and_inject_chunk(self, path: str) -> None:
        """Transcribe one chunk and inject its text in order, append-only.

        Reuses the same decoder params, custom-vocabulary prompt, and cleaning as
        the whole-recording path; chunks stay independent (no previous-text
        feedback). Always removes the chunk file when done.
        """
        try:
            if self.state.model is None or not os.path.exists(path):
                return
            vocab = self.state.config.get("custom_vocabulary") or []
            initial_prompt = ", ".join(vocab) if vocab else None
            text = self._audio_engine.transcribe(
                audio_path=path,
                model=self.state.model,
                language=self.state.config.get("language", "fr"),
                beam_size=self.state.config.get("beam_size", 1),
                best_of=self.state.config.get("best_of", 2),
                auto_detect_min_duration=self.state.config.get("auto_detect_min_duration", 0.5),
                min_recording_duration=self.state.config.get("min_chunk_s", 0.4),
                initial_prompt=initial_prompt,
            )
            if not text:
                return
            cleaned = clean_text(text)
            if not cleaned:
                return
            self.state.last_transcription = cleaned
            self._chunk_any_text = True
            # Accumulate; the FSM worker types the assembled text once on release.
            # Typing mid-recording disrupts focus in full-screen apps.
            self._chunk_texts.append(cleaned)
        except Exception:
            logger.exception("[engine] chunk transcription failed")
        finally:
            self._audio_engine.cleanup_audio_file(path)

    def _chunk_worker_loop(self) -> None:
        """Single ordered consumer of the chunk queue (FIFO → in-order inject)."""
        while self._chunk_worker_running:
            try:
                path = self._chunk_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._transcribe_and_inject_chunk(path)
            finally:
                self._chunk_queue.task_done()

    def start_chunk_worker(self) -> None:
        """Start the streaming chunk worker (no-op when streaming is disabled)."""
        if not self._streaming or self._chunk_worker_running:
            return
        self._chunk_worker_running = True
        self._chunk_thread = threading.Thread(target=self._chunk_worker_loop, name="chunk-worker", daemon=True)
        self._chunk_thread.start()

    def stop_chunk_worker(self) -> None:
        """Stop the streaming chunk worker."""
        self._chunk_worker_running = False
        if self._chunk_thread and self._chunk_thread.is_alive():
            self._chunk_thread.join(timeout=5.0)

    def transcribe_file(self, audio_path: str) -> str | None:
        """Transcribe a given WAV with the current config — no inject, no delete.

        Runs the real model and the same decoder params / cleaning as the live
        path, but against an arbitrary file (a committed fixture) and WITHOUT
        injecting keystrokes or deleting the source. This is the deterministic
        seam the validation harness drives over ``POST /transcribe-file`` so that
        "transcription yields the expected text" is verifiable without a mic or a
        human. Returns the cleaned text (or ``None`` if the model is unloaded or
        the file is missing).
        """
        if self.state.model is None:
            return None
        if not os.path.exists(audio_path):
            return None

        vocab = self.state.config.get("custom_vocabulary") or []
        initial_prompt = ", ".join(vocab) if vocab else None

        text = self._audio_engine.transcribe(
            audio_path=audio_path,
            model=self.state.model,
            language=self.state.config.get("language", "fr"),
            beam_size=self.state.config.get("beam_size", 1),
            best_of=self.state.config.get("best_of", 2),
            auto_detect_min_duration=self.state.config.get("auto_detect_min_duration", 0.5),
            min_recording_duration=self.state.config.get("min_recording_duration", 0.3),
            initial_prompt=initial_prompt,
        )
        # Model ran and file was present: empty/None means "no speech" (e.g.
        # silence) → "". None is reserved for not-loaded / missing-file above.
        return clean_text(text) if text else ""

    def stream_file(self, audio_path: str) -> list[str] | None:
        """Deterministic streaming seam: replay a WAV through live segmentation.

        Drives the same segmenter + per-chunk transcription the live streaming
        path uses, against an arbitrary file, WITHOUT a mic, keystroke injection,
        or deleting the source. Returns the ordered list of cleaned chunk texts
        (empty list = no chunk yielded usable text), or ``None`` when the model is
        unloaded or the file is missing/unreadable. The validation harness drives
        this over ``POST /stream-file`` so streaming chunking is verifiable
        without a microphone.
        """
        import wave

        if self.state.model is None:
            return None
        if not os.path.exists(audio_path):
            return None
        try:
            with wave.open(audio_path, "rb") as wf:
                pcm = wf.readframes(wf.getnframes())
        except (OSError, wave.Error):
            return None

        cfg = self.state.config
        min_chunk_s = cfg.get("min_chunk_s", 0.4)
        paths = self._audio_engine.segment_pcm(
            pcm,
            pause_ms=cfg.get("pause_ms", 600),
            min_chunk_s=min_chunk_s,
            max_chunk_s=cfg.get("max_chunk_s", 12.0),
            aggressiveness=cfg.get("vad_aggressiveness", 2),
        )

        vocab = cfg.get("custom_vocabulary") or []
        initial_prompt = ", ".join(vocab) if vocab else None
        texts: list[str] = []
        for path in paths:
            try:
                text = self._audio_engine.transcribe(
                    audio_path=path,
                    model=self.state.model,
                    language=cfg.get("language", "fr"),
                    beam_size=cfg.get("beam_size", 1),
                    best_of=cfg.get("best_of", 2),
                    auto_detect_min_duration=cfg.get("auto_detect_min_duration", 0.5),
                    min_recording_duration=min_chunk_s,
                    initial_prompt=initial_prompt,
                )
                if text:
                    cleaned = clean_text(text)
                    if cleaned:
                        texts.append(cleaned)
            finally:
                self._audio_engine.cleanup_audio_file(path)
        return texts

    # -- Fn key listener --

    def resolve_trigger(self) -> Any:
        """Resolve the configured trigger, or the platform default if unset.

        Returns the macOS Fn keycode (63) by default on macOS and a documented
        push-to-talk key on Linux, unless the user set ``trigger`` in config.
        """
        trigger = self.state.config.get("trigger")
        if trigger is None or trigger == "":
            return self._adapters.default_trigger
        return trigger

    # Backward-compatible alias: the resolved trigger was historically a macOS
    # keycode. Kept so existing callers/tests keep working.
    def _trigger_keycode_from_config(self) -> Any:
        return self.resolve_trigger()

    def start_fn_listener(self) -> None:
        """Start the trigger key listener for the active platform."""
        trigger = self.resolve_trigger()

        def _on_trigger_press() -> None:
            """Handle trigger key press — start recording."""
            self._notify_fn_pressed()
            self._notifier.recording_started()
            self.start_recording()

        self._fn_listener = self._adapters.make_hotkey_listener(
            trigger=trigger,
            on_trigger_press=_on_trigger_press,
            on_trigger_release=self._handle_trigger_release,
        )
        self._fn_listener.start()
        self.state.fn_listener_active = self._fn_listener.active

    def _handle_trigger_release(self) -> None:
        """Handle trigger key release — stop recording, then wake the worker.

        Only signals the transcription worker when stopping actually transitioned
        RECORDING -> TRANSCRIBING. A stray release (no active recording) is a
        no-op, so the worker never transcribes a stale/missing file.
        """
        self._notify_fn_released()
        transitioned = self.stop_recording()
        if transitioned:
            self.state.stop_event.set()

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

                    produced_text = False
                    try:
                        if self._streaming:
                            # FSM-1 tail: chunks (incl. the tail flushed by
                            # stop()) are transcribed by the chunk worker. Wait
                            # for the queue to drain so the FSM leaves
                            # TRANSCRIBING only once all chunks are handled.
                            self._chunk_queue.join()
                            # Type the assembled text once, now that recording
                            # stopped (no mid-recording injection / focus steal).
                            assembled = " ".join(self._chunk_texts).strip()
                            if assembled:
                                self.state.last_transcription = assembled
                                self._text_injector.inject(assembled)
                            produced_text = self._chunk_any_text
                        else:
                            produced_text = bool(self.run_transcription())
                    except Exception:
                        # A transcription failure must not kill the worker or
                        # wedge the FSM in TRANSCRIBING — log and recover below.
                        logging.getLogger(__name__).exception("transcription failed")
                    finally:
                        # Always return the FSM to IDLE, even on empty output
                        # or error. transcription_complete() no-ops if the FSM
                        # is not in TRANSCRIBING, so this is safe.
                        self._state_machine.transcription_complete()
                        self._notify_status_change()

                    # Success sound only on a real transcription.
                    if produced_text:
                        self._notifier.transcription_succeeded()

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

        # Trigger change: restart the listener so the new key is live now, not
        # only after a Restart. start_fn_listener re-reads resolve_trigger(), so
        # it picks up the value just saved above. Guard on an active listener —
        # a config update before the engine starts is a no-op (the listener will
        # read the right trigger when it starts normally).
        if "trigger" in updates and self.state.fn_listener_active:
            self.stop_fn_listener()
            self.start_fn_listener()

        # Streaming toggle / param change: re-wire the audio engine and, if the
        # engine is already running, start or stop the chunk worker to match.
        streaming_keys = {
            "streaming_enabled",
            "pause_ms",
            "min_chunk_s",
            "max_chunk_s",
            "vad_aggressiveness",
        }
        if streaming_keys & updates.keys():
            self._apply_streaming_config()
            if self._transcription_running:  # engine has been started
                if self._streaming:
                    self.start_chunk_worker()
                else:
                    self.stop_chunk_worker()
        return needs_reload

    # -- Lifecycle --

    def start(self) -> None:
        """Start all engine components."""
        # Linux v1 requires X11; warn (don't block) on a Wayland session before
        # wiring up the global hotkey, which won't work under Wayland.
        if self._adapters.name == "linux":
            from ..platform.linux.session import warn_if_wayland

            warn_if_wayland()
        elif self._adapters.name == "macos":
            # Neither permission prompts on its own for a bundled menu-bar app,
            # so request both explicitly before wiring the hotkey/capture:
            #  - mic (AVFoundation): PortAudio capture won't trigger the prompt.
            #  - Input Monitoring (IOKit): the Fn CGEventTap fails silently
            #    without it and a background app gets no automatic prompt.
            from ..platform.macos.permissions import (
                ensure_accessibility_access,
                ensure_automation_access,
                ensure_input_monitoring_access,
                ensure_microphone_access,
            )

            ensure_microphone_access()
            ensure_input_monitoring_access()
            ensure_accessibility_access()
            ensure_automation_access()
        self.start_fn_listener()
        self.start_transcription_worker()
        self.start_chunk_worker()
        load_model_async(self)

    def stop(self) -> None:
        """Stop all engine components."""
        self.stop_transcription_worker()
        self.stop_chunk_worker()
        self.stop_fn_listener()

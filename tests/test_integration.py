"""Integration tests for multi-module interactions."""

import sys
import threading
from pathlib import Path

# Ensure src/ is on the path, and remove project root to avoid whispy.py shadowing
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.core.audio import AudioEngine
from whispy.core.engine import DictationState, Engine
from whispy.core.state_machine import State

# ---------------------------------------------------------------------------
# Full Engine lifecycle
# ---------------------------------------------------------------------------


class TestEngineLifecycle:
    """Test full Engine lifecycle."""

    def test_start_config_update_status_stop(self):
        ds = DictationState()
        engine = Engine(ds)

        # Initial status
        status = engine.get_status()
        assert status["is_recording"] is False
        assert status["is_transcribing"] is False

        # Update config
        needs_reload = engine.update_config({"model_size": "base"})
        assert needs_reload is True
        assert engine.state.config["model_size"] == "base"

        # Check status reflects config
        status = engine.get_status()
        assert "fsm" in status

        # Stop (graceful)
        engine.stop()


# ---------------------------------------------------------------------------
# Engine + AudioEngine + StateMachine integration
# ---------------------------------------------------------------------------


class TestEngineAudioFSMIntegration:
    """Test Engine + AudioEngine + StateMachine integration."""

    def test_recording_lifecycle(self, sm):
        """Test the full recording lifecycle through AudioEngine."""
        audio = AudioEngine(sm)

        # Start recording
        result = audio.start()
        assert result is True
        assert sm.is_recording is True

        # Stop recording
        result = audio.stop()
        assert result is True
        assert sm.is_transcribing is True

        # Complete transcription
        sm.transcription_complete()
        assert sm.is_idle is True

    def test_cannot_start_while_recording(self, sm):
        audio = AudioEngine(sm)
        audio.start()
        assert audio.start() is False

    def test_cannot_stop_while_idle(self, sm):
        audio = AudioEngine(sm)
        assert audio.stop() is False

    def test_audio_engine_properties(self, sm):
        audio = AudioEngine(sm)
        assert audio.is_recording is False
        assert audio.is_transcribing is False

        audio.start()
        assert audio.is_recording is True
        assert audio.is_transcribing is False

        audio.stop()
        assert audio.is_recording is False
        assert audio.is_transcribing is True


# ---------------------------------------------------------------------------
# Engine + TextInjector integration
# ---------------------------------------------------------------------------


class TestEngineInjectorIntegration:
    """Test Engine + TextInjector integration."""

    def test_injector_initialized_with_config(self, state):
        engine = Engine(state)
        assert engine._text_injector._copy_to_clipboard is False

    def test_injector_updated_on_config_change(self, state):
        engine = Engine(state)
        engine.update_config({"copy_to_clipboard": False})
        assert engine._text_injector._copy_to_clipboard is False

    def test_injector_switches_back_to_clipboard(self, state):
        engine = Engine(state)
        engine.update_config({"copy_to_clipboard": False})
        engine.update_config({"copy_to_clipboard": True})
        assert engine._text_injector._copy_to_clipboard is True


# ---------------------------------------------------------------------------
# Concurrent config updates
# ---------------------------------------------------------------------------


class TestConcurrentConfigUpdates:
    """Test that concurrent config updates are safe."""

    def test_concurrent_updates(self):
        ds = DictationState()
        engine = Engine(ds)
        errors = []
        lock = threading.Lock()

        def update_config(key, value):
            try:
                for _ in range(100):
                    engine.update_config({key: value})
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [
            threading.Thread(target=update_config, args=("model_size", "base")),
            threading.Thread(target=update_config, args=("language", "fr")),
            threading.Thread(target=update_config, args=("beam_size", 5)),
            threading.Thread(target=update_config, args=("best_of", 4)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert engine.state.config["model_size"] == "base"
        assert engine.state.config["language"] == "fr"
        assert engine.state.config["beam_size"] == 5
        assert engine.state.config["best_of"] == 4

    def test_concurrent_updates_different_keys(self):
        ds = DictationState()
        engine = Engine(ds)
        errors = []
        lock = threading.Lock()

        def updater(updates):
            try:
                for _ in range(50):
                    engine.update_config(updates)
            except Exception as e:
                with lock:
                    errors.append(e)

        update_sets = [
            {"model_size": "base"},
            {"language": "fr"},
            {"compute_key": "cpu-float32"},
            {"beam_size": 3},
            {"best_of": 5},
        ]
        threads = [threading.Thread(target=updater, args=(u,)) for u in update_sets]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ---------------------------------------------------------------------------
# Engine + AudioEngine with mocked subprocess
# ---------------------------------------------------------------------------


class TestEngineAudioWithMocks:
    """Test Engine + AudioEngine integration with mocked subprocess."""

    def test_run_transcription_with_no_model(self, state):
        engine = Engine(state)
        result = engine.run_transcription()
        assert result is None

    def test_run_transcription_with_no_audio_file(self, state, mock_whisper_model, tmp_dir):
        engine = Engine(state)
        state.model = mock_whisper_model
        # RECORDING_PATH doesn't exist
        result = engine.run_transcription()
        assert result is None

    def test_state_sync_on_fsm_transitions(self):
        """Test that DictationState is synced when Engine's FSM transitions."""
        ds = DictationState()
        engine = Engine(ds)

        # Use Engine's internal state machine to trigger callbacks
        engine._state_machine.transition_to(State.RECORDING)
        assert ds.is_recording is True
        assert ds.is_transcribing is False

        engine._state_machine.transition_to(State.TRANSCRIBING)
        assert ds.is_recording is False
        assert ds.is_transcribing is True

        engine._state_machine.transition_to(State.IDLE)
        assert ds.is_recording is False
        assert ds.is_transcribing is False


# ---------------------------------------------------------------------------
# Streaming end-to-end: capture callback -> chunk queue -> transcribe -> inject
# ---------------------------------------------------------------------------


class TestStreamingEndToEnd:
    """Drive the wired streaming path with a mocked model and fake capture."""

    @staticmethod
    def _speech(n: int = 1600) -> bytes:
        import numpy as np

        # Random noise reads as "speech" to webrtcvad across every frame.
        return np.random.RandomState(1).randint(-9000, 9000, n).astype(np.int16).tobytes()

    @staticmethod
    def _silence(n: int = 1600) -> bytes:
        return bytes(n * 2)

    def test_streaming_wires_callback_to_chunk_queue(self, config_path, mocker, tmp_path):
        import itertools

        import whispy.core.audio as audio_module

        ds = DictationState()
        ds.config["streaming_enabled"] = True
        ds.config["pause_ms"] = 200
        ds.config["min_chunk_s"] = 0.1
        ds.config["max_chunk_s"] = 10.0
        engine = Engine(ds, config_path)
        engine.state.model = mocker.MagicMock()

        counter = itertools.count()
        mocker.patch.object(engine._audio_engine, "transcribe", side_effect=lambda **k: f"w{next(counter)}")
        inject = mocker.patch.object(engine._text_injector, "inject")

        captured = {}
        real_factory = audio_module.sd.RawInputStream

        def _factory(*a, **kw):
            inst = real_factory(*a, **kw)
            captured["cb"] = kw.get("callback") or (a[3] if len(a) > 3 else None)
            return inst

        mocker.patch.object(audio_module.sd, "RawInputStream", side_effect=_factory)

        engine.start_chunk_worker()
        try:
            engine._on_fsm_recording(None)
            engine.start_recording()
            cb = captured["cb"]
            # Two utterances separated by a clear pause.
            for _ in range(5):
                cb(self._speech(), 1600, None, None)
            for _ in range(5):
                cb(self._silence(), 1600, None, None)
            for _ in range(5):
                cb(self._speech(), 1600, None, None)
            engine.stop_recording()  # flushes the tail onto the queue
            engine._chunk_queue.join()
        finally:
            engine.stop_chunk_worker()

        # Callback -> segmenter -> queue -> worker wiring produced ordered chunks,
        # buffered (not typed mid-recording). The release path types them once.
        inject.assert_not_called()
        assert len(engine._chunk_texts) >= 2
        assert engine._chunk_texts == sorted(engine._chunk_texts, key=lambda s: int(s[1:]))

    def test_streaming_disabled_uses_whole_file_path(self, config_path, mocker):
        # streaming off -> no chunk wiring; the legacy run_transcription path runs.
        ds = DictationState()
        ds.config["streaming_enabled"] = False
        engine = Engine(ds, config_path)
        assert engine._streaming is False
        # configure_streaming was never enabled on the audio engine.
        assert engine._audio_engine._streaming is False

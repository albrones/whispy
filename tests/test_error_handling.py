"""Tests for error handling: capture backend failures, unavailable microphone.

Covers graceful degradation when system dependencies are unavailable.
"""

import sys
from pathlib import Path

import whispy.core.audio as audio_module
from whispy.core.audio import AudioEngine
from whispy.core.engine import DictationState, Engine
from whispy.core.state_machine import StateMachine

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


class TestCaptureBackendFailure:
    """The capture stream failing to open degrades gracefully (never raises).

    The cross-platform contract: a failed/unavailable audio device stops the
    readiness wait and warns, rather than blocking or propagating an exception.
    """

    def test_start_graceful_when_stream_open_fails(self, mocker):
        sm = StateMachine()
        engine = AudioEngine(sm)
        mocker.patch.object(audio_module.sd, "RawInputStream", side_effect=OSError("no device"))
        assert engine.start() is True
        assert sm.is_recording is True

    def test_start_graceful_when_backend_absent(self, mocker):
        """With no sounddevice backend at all, start() still returns gracefully."""
        sm = StateMachine()
        engine = AudioEngine(sm)
        mocker.patch.object(audio_module, "sd", None)
        assert engine.start() is True
        assert sm.is_recording is True


class TestMicrophoneUnavailable:
    """Test graceful handling when microphone is unavailable."""

    def test_transcribe_with_none_model_returns_none(self):
        """Transcription should return None when model is None."""
        sm = StateMachine()
        engine = AudioEngine(sm)
        result = engine.transcribe("/tmp/whispy.wav", None)
        assert result is None

    def test_transcribe_with_empty_wav(self):
        """Transcription should handle empty WAV files gracefully."""
        sm = StateMachine()
        engine = AudioEngine(sm)
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF\x00\x00\x00\x00WAVEfmt\x00")  # Minimal WAV header
            f.flush()
            # With no model, should return None
            result = engine.transcribe(f.name, None)
            assert result is None

    def test_transcribe_with_nonexistent_file(self):
        """Transcription should handle nonexistent files gracefully."""
        sm = StateMachine()
        engine = AudioEngine(sm)
        result = engine.transcribe("/nonexistent/path/audio.wav", None)
        assert result is None


class TestEngineErrorHandling:
    """Test engine-level error handling."""

    def test_engine_with_no_model_returns_graceful_status(self):
        """Engine should return valid status dict even without model."""
        state = DictationState()
        engine = Engine(state)
        status = engine.get_status()
        assert "model_loaded" in status
        assert "fsm" in status  # status uses 'fsm' not 'state'
        assert status["model_loaded"] is False

    def test_engine_start_recording_without_model(self):
        """Engine should handle start_recording when model is not loaded."""
        state = DictationState()
        engine = Engine(state)
        # Model is None by default
        result = engine.start_recording()
        # Should not raise, should handle gracefully
        assert result is True  # Recording starts even without model

    def test_engine_stop_recording_without_model(self):
        """Engine should handle stop_recording when not recording (no raise)."""
        state = DictationState()
        engine = Engine(state)
        result = engine.stop_recording()
        # Not recording → no transition; returns False without raising. Callers
        # gate the transcription stop event on this (a stray release is a no-op).
        assert result is False

    def test_audio_engine_cleanup_handles_missing_file(self):
        """AudioEngine.cleanup_audio_file should not error on missing file."""
        sm = StateMachine()
        engine = AudioEngine(sm)
        # Should not raise even if file doesn't exist
        engine.cleanup_audio_file("/nonexistent/path/whispy.wav")

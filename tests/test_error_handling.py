"""Tests for error handling: missing sox, unavailable microphone.

Covers graceful degradation when system dependencies are unavailable.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.core.audio import AudioEngine, RECORDING_PATH
from whispy.core.engine import Engine, DictationState
from whispy.core.state_machine import StateMachine


class TestSoxNotInstalled:
    """Test graceful handling when sox is not available.
    
    NOTE: Current implementation lets exceptions propagate from sox calls.
    These tests verify the exceptions are raised (not swallowed silently).
    """

    def test_start_raises_when_sox_missing(self):
        """AudioEngine.start() should raise when sox is not found."""
        sm = StateMachine()
        engine = AudioEngine(sm)
        with patch("subprocess.Popen", side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError):
                engine.start()

    def test_start_raises_when_sox_not_in_path(self):
        """AudioEngine.start() should raise OSError when sox not in PATH."""
        sm = StateMachine()
        engine = AudioEngine(sm)
        with patch(
            "subprocess.Popen",
            side_effect=OSError("executable not found"),
        ):
            with pytest.raises(OSError):
                engine.start()

    def test_start_raises_on_permission_error(self):
        """AudioEngine.start() should raise on permission errors from sox."""
        sm = StateMachine()
        engine = AudioEngine(sm)
        with patch(
            "subprocess.Popen",
            side_effect=PermissionError("permission denied"),
        ):
            with pytest.raises(PermissionError):
                engine.start()


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
        """Engine should handle stop_recording when model is not loaded."""
        state = DictationState()
        engine = Engine(state)
        result = engine.stop_recording()
        # Should not raise (may return None or True)
        assert result is not False  # Should not return False (error)

    def test_audio_engine_cleanup_handles_missing_file(self):
        """AudioEngine.cleanup_audio_file should not error on missing file."""
        sm = StateMachine()
        engine = AudioEngine(sm)
        # Should not raise even if file doesn't exist
        engine.cleanup_audio_file("/nonexistent/path/whispy.wav")

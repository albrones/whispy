"""Tests for AudioEngine with mocked subprocess calls."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is on the path, and remove project root to avoid whispy.py shadowing
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from whispy.core.audio import AudioEngine
from whispy.core.state_machine import State


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------


class TestAudioStart:
    """Test AudioEngine.start() behavior."""

    def test_start_transitions_fsm_to_recording(self, sm):
        audio = AudioEngine(sm)
        audio.start()
        assert sm.is_recording is True

    def test_start_returns_true_when_idle(self, sm):
        audio = AudioEngine(sm)
        assert audio.start() is True

    def test_start_returns_false_when_already_recording(self, sm):
        audio = AudioEngine(sm)
        audio.start()
        assert audio.start() is False

    def test_start_spawns_sox_process(self, sm, mock_subprocess):
        _, popen_mock, _ = mock_subprocess
        audio = AudioEngine(sm)
        audio.start()
        assert popen_mock.called
        call_args = popen_mock.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "sox"


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------


class TestAudioStop:
    """Test AudioEngine.stop() behavior."""

    def test_stop_terminates_process(self, sm, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        popen_instance.poll.return_value = None
        audio = AudioEngine(sm)
        audio.start()
        audio.stop()
        assert popen_instance.terminate.called

    def test_stop_transitions_fsm_to_transcribing(self, sm):
        audio = AudioEngine(sm)
        audio.start()
        audio.stop()
        assert sm.is_transcribing is True

    def test_stop_returns_true_when_recording(self, sm):
        audio = AudioEngine(sm)
        audio.start()
        assert audio.stop() is True

    def test_stop_returns_false_when_not_recording(self, sm):
        audio = AudioEngine(sm)
        assert audio.stop() is False

    def test_stop_kills_on_timeout(self, sm, mock_subprocess):
        _, popen_mock, popen_instance = mock_subprocess
        popen_instance.poll.return_value = None
        popen_instance.wait.side_effect = subprocess.TimeoutExpired(
            cmd="sox", timeout=2
        )
        audio = AudioEngine(sm)
        audio.start()
        audio.stop()
        assert popen_instance.kill.called


# ---------------------------------------------------------------------------
# cleanup_audio_file()
# ---------------------------------------------------------------------------


class TestCleanupAudioFile:
    """Test cleanup_audio_file behavior."""

    def test_removes_existing_file(self, temp_audio_file):
        audio = AudioEngine(MagicMock())
        assert os.path.exists(temp_audio_file)
        audio.cleanup_audio_file(temp_audio_file)
        assert not os.path.exists(temp_audio_file)

    def test_does_not_error_on_missing_file(self):
        audio = AudioEngine(MagicMock())
        # Should not raise
        audio.cleanup_audio_file("/nonexistent/path/whispy.wav")

    def test_default_path_cleanup(self, mock_subprocess):
        """Test cleanup with default RECORDING_PATH."""
        audio = AudioEngine(MagicMock())
        # Just verify it doesn't crash with default path
        audio.cleanup_audio_file()


# ---------------------------------------------------------------------------
# transcribe()
# ---------------------------------------------------------------------------


class TestTranscribe:
    """Test AudioEngine.transcribe() behavior."""

    def test_none_model_returns_none(self, sm):
        audio = AudioEngine(sm)
        result = audio.transcribe("/tmp/test.wav", model=None)
        assert result is None

    def test_valid_model_calls_transcribe(self, sm, mock_whisper_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        # Mock segments to return text
        mock_segment = MagicMock()
        mock_segment.text = "hello world"
        mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

        result = audio.transcribe(audio_path, mock_whisper_model)
        assert result == "hello world"
        mock_whisper_model.transcribe.assert_called_once()

    def test_language_parameter_passed_through(self, sm, mock_whisper_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        mock_segment = MagicMock()
        mock_segment.text = "bonjour"
        mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

        audio.transcribe(audio_path, mock_whisper_model, language="fr")
        call_kwargs = mock_whisper_model.transcribe.call_args
        assert call_kwargs[1]["language"] == "fr"

    def test_beam_size_passed_through(self, sm, mock_whisper_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

        audio.transcribe(audio_path, mock_whisper_model, beam_size=5)
        call_kwargs = mock_whisper_model.transcribe.call_args
        assert call_kwargs[1]["beam_size"] == 5

    def test_best_of_passed_through(self, sm, mock_whisper_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

        audio.transcribe(audio_path, mock_whisper_model, best_of=4)
        call_kwargs = mock_whisper_model.transcribe.call_args
        assert call_kwargs[1]["best_of"] == 4

    def test_empty_result_returns_none(self, sm, mock_whisper_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        mock_whisper_model.transcribe.return_value = ([], MagicMock())
        result = audio.transcribe(audio_path, mock_whisper_model)
        assert result is None

    def test_exception_returns_none(self, sm, mock_whisper_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        mock_whisper_model.transcribe.side_effect = RuntimeError("transcription failed")
        result = audio.transcribe(audio_path, mock_whisper_model)
        assert result is None

    def test_multiple_segments_joined(self, sm, mock_whisper_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        seg1 = MagicMock()
        seg1.text = "hello"
        seg2 = MagicMock()
        seg2.text = "world"
        mock_whisper_model.transcribe.return_value = ([seg1, seg2], MagicMock())

        result = audio.transcribe(audio_path, mock_whisper_model)
        assert result == "hello world"

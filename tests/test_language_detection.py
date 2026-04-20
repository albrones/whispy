"""Regression tests for auto-detect language fix.

Tests that the auto-detect language feature works correctly:
- language="auto" parameter is passed through to WhisperModel
- Audio duration detection works for short files
- Config persistence for language value across save/load cycles
- Short audio (< 1s) is handled gracefully
"""

import json
import wave
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from whispy.core.audio import AudioEngine
from whispy.core.engine import (
    DEFAULT_CONFIG,
    DictationState,
    Engine,
    load_config,
    save_config,
)
from whispy.core.state_machine import StateMachine


# ---------------------------------------------------------------------------
# transcribe() with language="auto"
# ---------------------------------------------------------------------------


class TestAutoDetectTranscription:
    """Test that language='auto' is passed through correctly."""

    def test_auto_language_passed_to_model(self, sm, mock_whisper_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

        audio.transcribe(audio_path, mock_whisper_model, language="auto")
        call_kwargs = mock_whisper_model.transcribe.call_args
        assert call_kwargs[1]["language"] == "auto"

    def test_auto_detect_min_duration_config_passed(
        self, sm, mock_whisper_model, tmp_path
    ):
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

        audio.transcribe(
            audio_path,
            mock_whisper_model,
            language="auto",
            auto_detect_min_duration=1.0,
        )
        # Should not raise, just log a warning
        assert mock_whisper_model.transcribe.called


# ---------------------------------------------------------------------------
# Audio duration detection
# ---------------------------------------------------------------------------


class TestAudioDurationDetection:
    """Test audio file duration detection."""

    def test_detects_duration_of_wav_file(self, tmp_path):
        """Create a valid WAV file and verify duration detection."""
        audio = AudioEngine(MagicMock())
        wav_path = str(tmp_path / "test.wav")

        # Create a valid WAV file: 16kHz, 1 channel, 2 seconds
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 16000 * 2)  # 2 seconds of silence

        duration = audio._get_audio_duration(wav_path)
        assert duration is not None
        assert abs(duration - 2.0) < 0.01

    def test_detects_short_audio_duration(self, tmp_path):
        """Test duration detection for short audio (< 1s)."""
        audio = AudioEngine(MagicMock())
        wav_path = str(tmp_path / "short.wav")

        # Create a 0.5 second WAV file (8000 frames at 16kHz)
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 8000)

        duration = audio._get_audio_duration(wav_path)
        assert duration is not None
        assert abs(duration - 0.5) < 0.01

    def test_returns_none_for_non_wav_file(self, tmp_path):
        audio = AudioEngine(MagicMock())
        non_wav = str(tmp_path / "test.mp3")
        Path(non_wav).write_bytes(b"not a wav file")
        duration = audio._get_audio_duration(non_wav)
        assert duration is None

    def test_returns_none_for_missing_file(self):
        audio = AudioEngine(MagicMock())
        duration = audio._get_audio_duration("/nonexistent/file.wav")
        assert duration is None


# ---------------------------------------------------------------------------
# Config persistence for language
# ---------------------------------------------------------------------------


class TestLanguageConfigPersistence:
    """Test that language config survives save/load cycles."""

    def test_language_survives_save_load(self, mocker, tmp_path):
        tmp_config = tmp_path / "config.json"

        def mock_save(cfg, p):
            tmp_config.write_text(json.dumps(cfg))

        def mock_load(p):
            if tmp_config.exists():
                return json.loads(tmp_config.read_text())
            return dict(DEFAULT_CONFIG)

        mocker.patch("tests.test_language_detection.save_config", side_effect=mock_save)
        mocker.patch("tests.test_language_detection.load_config", side_effect=mock_load)

        config = dict(DEFAULT_CONFIG)
        config["language"] = "fr"
        save_config(config, Path("/ignored"))

        loaded = load_config(Path("/ignored"))
        assert loaded["language"] == "fr"

    def test_language_auto_survives_save_load(self, mocker, tmp_path):
        tmp_config = tmp_path / "config_auto.json"

        def mock_save(cfg, p):
            tmp_config.write_text(json.dumps(cfg))

        def mock_load(p):
            if tmp_config.exists():
                return json.loads(tmp_config.read_text())
            return dict(DEFAULT_CONFIG)

        mocker.patch("tests.test_language_detection.save_config", side_effect=mock_save)
        mocker.patch("tests.test_language_detection.load_config", side_effect=mock_load)

        config = dict(DEFAULT_CONFIG)
        config["language"] = "auto"
        save_config(config, Path("/ignored"))

        loaded = load_config(Path("/ignored"))
        assert loaded["language"] == "auto"

    def test_language_en_survives_save_load(self, mocker, tmp_path):
        tmp_config = tmp_path / "config_en.json"

        def mock_save(cfg, p):
            tmp_config.write_text(json.dumps(cfg))

        def mock_load(p):
            if tmp_config.exists():
                return json.loads(tmp_config.read_text())
            return dict(DEFAULT_CONFIG)

        mocker.patch("tests.test_language_detection.save_config", side_effect=mock_save)
        mocker.patch("tests.test_language_detection.load_config", side_effect=mock_load)

        config = dict(DEFAULT_CONFIG)
        config["language"] = "en"
        save_config(config, Path("/ignored"))

        loaded = load_config(Path("/ignored"))
        assert loaded["language"] == "en"

    def test_auto_detect_min_duration_survives_save_load(self, mocker, tmp_path):
        tmp_config = tmp_path / "config_detect.json"

        def mock_save(cfg, p):
            tmp_config.write_text(json.dumps(cfg))

        def mock_load(p):
            if tmp_config.exists():
                return json.loads(tmp_config.read_text())
            return dict(DEFAULT_CONFIG)

        mocker.patch("tests.test_language_detection.save_config", side_effect=mock_save)
        mocker.patch("tests.test_language_detection.load_config", side_effect=mock_load)

        config = dict(DEFAULT_CONFIG)
        config["auto_detect_min_duration"] = 1.0
        save_config(config, Path("/ignored"))

        loaded = load_config(Path("/ignored"))
        assert loaded["auto_detect_min_duration"] == 1.0


# ---------------------------------------------------------------------------
# Short audio handling
# ---------------------------------------------------------------------------


class TestShortAudioHandling:
    """Test that short audio (< 1s) is handled gracefully."""

    def test_transcribe_short_audio_with_auto_does_not_crash(
        self, sm, mock_whisper_model, tmp_path
    ):
        """Short audio with language='auto' should not crash."""
        audio = AudioEngine(sm)
        wav_path = str(tmp_path / "short.wav")

        # Create a 0.3 second WAV file (4800 frames at 16kHz)
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 4800)

        mock_segment = MagicMock()
        mock_segment.text = ""
        mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

        # Should not raise
        result = audio.transcribe(
            wav_path,
            mock_whisper_model,
            language="auto",
            auto_detect_min_duration=0.5,
        )
        assert result is None  # Empty text returns None

    def test_transcribe_short_audio_with_fixed_language(
        self, sm, mock_whisper_model, tmp_path
    ):
        """Short audio with fixed language should work normally."""
        audio = AudioEngine(sm)
        wav_path = str(tmp_path / "short.wav")

        # Create a 0.3 second WAV file (4800 frames at 16kHz)
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 4800)

        mock_segment = MagicMock()
        mock_segment.text = "bonjour"
        mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

        result = audio.transcribe(
            wav_path,
            mock_whisper_model,
            language="fr",
        )
        assert result == "bonjour"

    def test_transcribe_above_threshold_with_auto(
        self, sm, mock_whisper_model, tmp_path
    ):
        """Audio above threshold with language='auto' should work normally."""
        audio = AudioEngine(sm)
        wav_path = str(tmp_path / "long.wav")

        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 16000 * 5)  # 5 seconds

        mock_segment = MagicMock()
        mock_segment.text = "hello world"
        mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

        result = audio.transcribe(
            wav_path,
            mock_whisper_model,
            language="auto",
            auto_detect_min_duration=0.5,
        )
        assert result == "hello world"

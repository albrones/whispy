"""Tests for AudioEngine with a faked sounddevice capture backend."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure src/ is on the path, and remove project root to avoid whispy.py shadowing
_project_root = str(Path(__file__).parent.parent)
if _project_root in sys.path:
    sys.path.remove(_project_root)
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import whispy.core.audio as audio_module
from whispy.core.audio import AudioEngine


class _SpyStream:
    """Records start/stop/close and fires the capture callback once on start."""

    instances: list["_SpyStream"] = []

    def __init__(self, samplerate, channels, dtype, callback, **_kw):
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self._callback = callback
        self.started = False
        self.stopped = False
        self.closed = False
        _SpyStream.instances.append(self)

    def start(self):
        self.started = True
        frames = self.samplerate  # ~1 second of int16 silence
        data = bytes(frames * self.channels * audio_module.SAMPLE_WIDTH)
        if self._callback:
            self._callback(data, frames, None, None)

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


def _install_spy_sd(mocker):
    """Patch the audio module's sounddevice with a spy stream factory."""
    _SpyStream.instances = []
    fake_sd = MagicMock()
    fake_sd.RawInputStream = _SpyStream
    mocker.patch.object(audio_module, "sd", fake_sd)
    return _SpyStream

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

    def test_start_opens_sounddevice_stream(self, sm, mocker):
        spy = _install_spy_sd(mocker)
        audio = AudioEngine(sm)
        audio.start()
        assert len(spy.instances) == 1
        stream = spy.instances[0]
        assert stream.started is True
        assert stream.samplerate == audio_module.SAMPLE_RATE
        assert stream.channels == audio_module.CHANNELS

    def test_start_graceful_when_stream_open_fails(self, sm, mocker):
        """A failed stream open stops the readiness wait and does not raise."""
        fake_sd = MagicMock()
        fake_sd.RawInputStream.side_effect = RuntimeError("no device")
        mocker.patch.object(audio_module, "sd", fake_sd)
        audio = AudioEngine(sm)
        # Should return True (FSM already RECORDING) without blocking or raising.
        assert audio.start() is True
        assert sm.is_recording is True


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------


class TestAudioStop:
    """Test AudioEngine.stop() behavior."""

    def test_stop_closes_stream(self, sm, mocker):
        spy = _install_spy_sd(mocker)
        audio = AudioEngine(sm)
        audio.start()
        audio.stop()
        stream = spy.instances[0]
        assert stream.stopped is True
        assert stream.closed is True

    def test_stop_transitions_fsm_to_transcribing(self, sm, mocker):
        _install_spy_sd(mocker)
        audio = AudioEngine(sm)
        audio.start()
        audio.stop()
        assert sm.is_transcribing is True

    def test_stop_returns_true_when_recording(self, sm, mocker):
        _install_spy_sd(mocker)
        audio = AudioEngine(sm)
        audio.start()
        assert audio.stop() is True

    def test_stop_returns_false_when_not_recording(self, sm):
        audio = AudioEngine(sm)
        assert audio.stop() is False


# ---------------------------------------------------------------------------
# Thread-safety + per-recording file isolation (fix-capture-thread-races)
# ---------------------------------------------------------------------------


class TestCaptureThreadSafety:
    """Capture callback contains its own errors and never raises into PortAudio."""

    def test_callback_exception_is_contained(self, sm, mocker):
        # If opening/writing the WAV fails inside the callback, it must be
        # logged and swallowed (the callback runs in a C callback) — start()
        # must still return without raising and mark readiness.
        _install_spy_sd(mocker)
        mocker.patch.object(audio_module.wave, "open", side_effect=RuntimeError("disk full"))
        audio = AudioEngine(sm)
        assert audio.start() is True  # spy fires the callback synchronously
        assert audio._ready.is_set()

    def test_stop_during_capture_closes_cleanly_and_keeps_file(self, sm, mocker):
        _install_spy_sd(mocker)
        audio = AudioEngine(sm)
        audio.start()  # spy writes ~1s of silence to the unique path
        path = audio.recording_path
        assert audio.stop() is True
        # stop() closes the handle but leaves the file for transcription.
        assert os.path.exists(path)


class TestPerRecordingPath:
    """Each recording gets its own file so concurrent record/transcribe is safe."""

    def test_each_recording_uses_a_unique_path(self, sm, mocker):
        _install_spy_sd(mocker)
        audio = AudioEngine(sm)
        audio.start()
        first = audio.recording_path
        audio.stop()
        audio.start()
        second = audio.recording_path
        audio.stop()
        assert first != second
        assert first.endswith(".wav") and second.endswith(".wav")

    def test_recording_path_under_tempdir(self, sm, mocker):
        import tempfile

        _install_spy_sd(mocker)
        audio = AudioEngine(sm)
        audio.start()
        assert audio.recording_path.startswith(tempfile.gettempdir())


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

    def test_initial_prompt_passed_through(self, sm, mock_whisper_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

        audio.transcribe(audio_path, mock_whisper_model, initial_prompt="Whispy, ctranslate2")
        call_kwargs = mock_whisper_model.transcribe.call_args
        assert call_kwargs[1]["initial_prompt"] == "Whispy, ctranslate2"

    def test_initial_prompt_defaults_to_none(self, sm, mock_whisper_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

        audio.transcribe(audio_path, mock_whisper_model)
        call_kwargs = mock_whisper_model.transcribe.call_args
        assert call_kwargs[1]["initial_prompt"] is None

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

    def test_short_recording_discarded_without_transcribing(self, sm, mock_whisper_model, tmp_path):
        """A misclick-length clip is discarded before model.transcribe runs."""
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        audio._get_audio_duration = MagicMock(return_value=0.1)
        result = audio.transcribe(audio_path, mock_whisper_model, min_recording_duration=0.3)
        assert result is None
        mock_whisper_model.transcribe.assert_not_called()

    def test_long_enough_recording_passes_vad_filter(self, sm, mock_whisper_model, tmp_path):
        """A clip above the threshold is transcribed with vad_filter enabled."""
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        audio._get_audio_duration = MagicMock(return_value=1.0)
        mock_segment = MagicMock()
        mock_segment.text = "bonjour"
        mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

        result = audio.transcribe(audio_path, mock_whisper_model, min_recording_duration=0.3)
        assert result == "bonjour"
        call_kwargs = mock_whisper_model.transcribe.call_args[1]
        assert call_kwargs["vad_filter"] is True
        assert call_kwargs["condition_on_previous_text"] is False
        assert call_kwargs["temperature"] == 0

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


# ---------------------------------------------------------------------------
# Streaming segmentation (configure_streaming + capture-side chunk emission)
# ---------------------------------------------------------------------------


class TestStreamingCapture:
    """Streaming mode buffers PCM and emits chunks on silence/length boundaries."""

    @staticmethod
    def _block(level_int16: int, n: int = 1600) -> bytes:
        import numpy as np

        # level 0 -> digital silence; otherwise noise (reliably "speech" to the
        # WebRTC VAD across every frame, unlike a constant DC level).
        if level_int16 == 0:
            return bytes(n * 2)
        return np.random.RandomState(0).randint(-level_int16, level_int16, n).astype(np.int16).tobytes()

    def _start_streaming(self, sm, mocker, on_chunk, **kw):
        spy = _install_spy_sd(mocker)
        audio = AudioEngine(sm)
        audio.configure_streaming(True, on_chunk, **kw)
        audio.start()
        # The closure callback the spy captured; drive it with crafted blocks.
        return audio, spy.instances[-1]._callback

    def test_emits_chunk_on_silence_boundary(self, sm, mocker):
        chunks: list[str] = []
        audio, cb = self._start_streaming(
            sm, mocker, chunks.append, pause_ms=200, min_chunk_s=0.1, max_chunk_s=10.0
        )
        speech = self._block(8000)  # loud -> level ~1.0
        silence = self._block(0)
        for _ in range(5):  # 0.5s speech
            cb(speech, 1600, None, None)
        for _ in range(4):  # silence accumulates past pause_ms (0.2s)
            cb(silence, 1600, None, None)
        assert len(chunks) >= 1
        assert os.path.exists(chunks[0])

    def test_no_whole_file_written_in_streaming(self, sm, mocker):
        chunks: list[str] = []
        audio, cb = self._start_streaming(sm, mocker, chunks.append)
        # The legacy whole-recording WAV is never opened in streaming mode.
        assert audio._wave is None
        cb(self._block(8000), 1600, None, None)
        assert audio._wave is None

    def test_tail_flushed_on_stop(self, sm, mocker):
        chunks: list[str] = []
        audio, cb = self._start_streaming(
            sm, mocker, chunks.append, pause_ms=5000, min_chunk_s=0.1, max_chunk_s=60.0
        )
        # Speech with no closing pause -> nothing emitted until stop flushes tail.
        for _ in range(5):
            cb(self._block(8000), 1600, None, None)
        assert chunks == []
        audio.stop()
        assert len(chunks) == 1
        assert os.path.exists(chunks[0])

    def test_pure_silence_emits_nothing(self, sm, mocker):
        chunks: list[str] = []
        audio, cb = self._start_streaming(sm, mocker, chunks.append, pause_ms=200, min_chunk_s=0.1)
        for _ in range(20):
            cb(self._block(0), 1600, None, None)
        audio.stop()
        assert chunks == []

    def test_segmenter_error_is_contained(self, sm, mocker):
        # An error inside segmentation must be logged and swallowed, never raised
        # into the PortAudio callback.
        audio, cb = self._start_streaming(sm, mocker, lambda _p: None)
        mocker.patch.object(audio, "_feed_segmenter", side_effect=RuntimeError("boom"))
        # Calling the capture callback must not raise.
        cb(self._block(8000), 1600, None, None)

    def test_non_streaming_unchanged(self, sm, mocker):
        # With streaming off, the legacy single-file path still writes one WAV.
        _install_spy_sd(mocker)
        audio = AudioEngine(sm)
        audio.start()  # spy fires callback with ~1s silence
        path = audio.recording_path
        assert os.path.exists(path)
        audio.stop()


class TestSegmentPcm:
    """segment_pcm replays PCM through the real segmenter (validation seam)."""

    def test_emits_multiple_chunks_on_silence_gap(self, sm):
        import numpy as np

        audio = AudioEngine(sm)
        speech = (np.ones(1600, dtype=np.int16) * 8000).tobytes()
        silence = bytes(1600 * 2)
        # Lead-in silence (as in a real recording) seeds the noise floor low;
        # then: utterance, pause, utterance.
        pcm = silence * 3 + speech * 4 + silence * 5 + speech * 4
        paths = audio.segment_pcm(pcm, pause_ms=200, min_chunk_s=0.1, max_chunk_s=10.0)
        try:
            assert len(paths) >= 2
            for p in paths:
                assert os.path.exists(p)
        finally:
            for p in paths:
                if os.path.exists(p):
                    os.remove(p)

    def test_pure_silence_emits_no_chunks(self, sm):
        audio = AudioEngine(sm)
        paths = audio.segment_pcm(bytes(1600 * 2) * 20, pause_ms=200, min_chunk_s=0.1)
        assert paths == []

    def test_restores_live_state(self, sm):
        # segment_pcm must not leave the engine wired to its temporary sink.
        audio = AudioEngine(sm)
        audio.segment_pcm(bytes(1600 * 2) * 5)
        assert audio._on_chunk is None
        assert audio._segmenter is None

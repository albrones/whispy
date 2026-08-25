"""Tests for AudioEngine with a faked sounddevice capture backend."""

import os
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
# Device refresh (follow the system default input across device changes)
# ---------------------------------------------------------------------------


class TestDeviceRefresh:
    """PortAudio device list is refreshed before each stream open, with one
    retry, so capture follows the current system default input device."""

    def test_start_refreshes_devices_before_opening_stream(self, sm, mocker):
        # Pins the private _terminate/_initialize usage: a sounddevice upgrade
        # that removes them must fail here, not silently in production.
        calls: list[str] = []
        _SpyStream.instances = []
        fake_sd = MagicMock()
        fake_sd._terminate.side_effect = lambda: calls.append("terminate")
        fake_sd._initialize.side_effect = lambda: calls.append("initialize")

        def _factory(**kw):
            calls.append("open")
            return _SpyStream(**kw)

        fake_sd.RawInputStream = _factory
        mocker.patch.object(audio_module, "sd", fake_sd)
        audio = AudioEngine(sm)
        assert audio.start() is True
        assert calls == ["terminate", "initialize", "open"]
        assert audio.capture_failed is None

    def test_refresh_failure_does_not_block_stream_open(self, sm, mocker):
        _SpyStream.instances = []
        fake_sd = MagicMock()
        fake_sd._terminate.side_effect = RuntimeError("portaudio busy")
        fake_sd.RawInputStream = _SpyStream
        mocker.patch.object(audio_module, "sd", fake_sd)
        audio = AudioEngine(sm)
        assert audio.start() is True
        assert len(_SpyStream.instances) == 1
        assert _SpyStream.instances[0].started is True
        assert audio.capture_failed is None

    def test_open_retries_once_after_second_refresh(self, sm, mocker):
        _SpyStream.instances = []
        attempts: list[int] = []

        def _factory(**kw):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("Internal PortAudio error [PaErrorCode -9986]")
            return _SpyStream(**kw)

        fake_sd = MagicMock()
        fake_sd.RawInputStream = _factory
        mocker.patch.object(audio_module, "sd", fake_sd)
        audio = AudioEngine(sm)
        assert audio.start() is True
        assert len(attempts) == 2
        assert _SpyStream.instances[0].started is True
        assert audio.capture_failed is None
        # Two refreshes: the routine one plus the pre-retry one.
        assert fake_sd._terminate.call_count == 2
        assert fake_sd._initialize.call_count == 2

    def test_open_gives_up_after_single_retry(self, sm, mocker):
        fake_sd = MagicMock()
        fake_sd.RawInputStream = MagicMock(side_effect=RuntimeError("no device"))
        mocker.patch.object(audio_module, "sd", fake_sd)
        audio = AudioEngine(sm)
        assert audio.start() is True
        assert fake_sd.RawInputStream.call_count == 2
        assert audio.capture_failed is not None
        assert "no device" in audio.capture_failed
        assert sm.is_recording is True

    def test_capture_failed_resets_on_next_start(self, sm, mocker):
        fake_sd = MagicMock()
        fake_sd.RawInputStream = MagicMock(side_effect=RuntimeError("no device"))
        mocker.patch.object(audio_module, "sd", fake_sd)
        audio = AudioEngine(sm)
        audio.start()
        assert audio.capture_failed is not None
        audio.stop()
        sm.transcription_complete()
        _SpyStream.instances = []
        fake_sd.RawInputStream = _SpyStream
        assert audio.start() is True
        assert audio.capture_failed is None


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
# Recording WAV permissions (privacy: never world-readable, whatever the umask)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permission bits only")
class TestRecordingFilePermissions:
    """Every recording WAV must be created 0o600, regardless of the umask."""

    def test_new_recording_wav_is_owner_only(self, sm, mocker):
        _install_spy_sd(mocker)
        old_umask = os.umask(0o022)  # a permissive umask a real system might have
        try:
            audio = AudioEngine(sm)
            audio.start()  # spy fires the callback synchronously, opening the WAV
        finally:
            os.umask(old_umask)
        mode = os.stat(audio.recording_path).st_mode & 0o777
        assert mode == 0o600

    def test_chunk_wav_is_owner_only(self, sm):
        audio = AudioEngine(sm)
        chunks: list[str] = []
        audio._on_chunk = chunks.append
        audio._chunk_buf = bytearray(b"\x00" * 3200)
        old_umask = os.umask(0o022)
        try:
            audio._emit_chunk()
        finally:
            os.umask(old_umask)
        assert len(chunks) == 1
        mode = os.stat(chunks[0]).st_mode & 0o777
        assert mode == 0o600


# ---------------------------------------------------------------------------
# Stale recording sweep (privacy: crashes must not leak WAVs forever)
# ---------------------------------------------------------------------------


class TestStaleRecordingSweep:
    """AudioEngine startup removes leftover whispy-*.wav files from a crash."""

    def test_sweeps_stale_whispy_wavs_on_init(self, sm):
        import tempfile
        import uuid

        stale = os.path.join(tempfile.gettempdir(), f"whispy-{uuid.uuid4().hex}.wav")
        with open(stale, "wb") as f:
            f.write(b"\x00" * 100)
        assert os.path.exists(stale)

        AudioEngine(sm)

        assert not os.path.exists(stale)

    def test_sweep_failure_does_not_break_startup(self, mocker):
        # A listing/removal error must never prevent the AudioEngine from
        # starting up.
        mocker.patch.object(audio_module.glob, "glob", side_effect=OSError("boom"))
        AudioEngine(MagicMock())  # must not raise


# ---------------------------------------------------------------------------
# transcribe()
# ---------------------------------------------------------------------------


class TestTranscribe:
    """Test AudioEngine.transcribe() behavior."""

    @staticmethod
    def _clip(tmp_path):
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)
        return audio_path

    def test_none_model_returns_none(self, sm):
        audio = AudioEngine(sm)
        result = audio.transcribe("/tmp/test.wav", model=None)
        assert result is None

    def test_valid_model_calls_recognize(self, sm, mock_asr_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        mock_asr_model.recognize.return_value = "hello world"

        result = audio.transcribe(audio_path, mock_asr_model)
        assert result == "hello world"
        mock_asr_model.recognize.assert_called_once_with(audio_path)

    def test_no_decoder_arguments_are_forwarded(self, sm, mock_asr_model, tmp_path):
        """The transducer takes audio and nothing else.

        Guards the requirement directly: a forced language made the previous
        backend translate instead of recognize, and disabling previous-text
        conditioning without VAD truncated long recordings. Neither knob may
        come back through this call.
        """
        audio = AudioEngine(sm)
        mock_asr_model.recognize.return_value = "bonjour"

        audio.transcribe(self._clip(tmp_path), mock_asr_model)

        _args, kwargs = mock_asr_model.recognize.call_args
        assert kwargs == {}, f"unexpected decoder arguments: {kwargs}"

    def test_result_is_stripped(self, sm, mock_asr_model, tmp_path):
        audio = AudioEngine(sm)
        mock_asr_model.recognize.return_value = "  bonjour  "
        assert audio.transcribe(self._clip(tmp_path), mock_asr_model) == "bonjour"

    def test_empty_result_returns_none(self, sm, mock_asr_model, tmp_path):
        audio = AudioEngine(sm)
        mock_asr_model.recognize.return_value = ""
        assert audio.transcribe(self._clip(tmp_path), mock_asr_model) is None

    def test_whitespace_only_result_returns_none(self, sm, mock_asr_model, tmp_path):
        audio = AudioEngine(sm)
        mock_asr_model.recognize.return_value = "   "
        assert audio.transcribe(self._clip(tmp_path), mock_asr_model) is None

    def test_none_result_returns_none(self, sm, mock_asr_model, tmp_path):
        audio = AudioEngine(sm)
        mock_asr_model.recognize.return_value = None
        assert audio.transcribe(self._clip(tmp_path), mock_asr_model) is None

    def test_exception_returns_none(self, sm, mock_asr_model, tmp_path):
        audio = AudioEngine(sm)
        mock_asr_model.recognize.side_effect = RuntimeError("onnxruntime session failed")
        assert audio.transcribe(self._clip(tmp_path), mock_asr_model) is None

    def test_short_recording_discarded_without_transcribing(self, sm, mock_asr_model, tmp_path):
        """A misclick-length clip is discarded before the model runs."""
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)

        audio._get_audio_duration = MagicMock(return_value=0.1)
        result = audio.transcribe(audio_path, mock_asr_model, min_recording_duration=0.3)
        assert result is None
        mock_asr_model.recognize.assert_not_called()

    def test_long_enough_recording_proceeds(self, sm, mock_asr_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)

        audio._get_audio_duration = MagicMock(return_value=1.0)
        mock_asr_model.recognize.return_value = "bonjour"

        result = audio.transcribe(audio_path, mock_asr_model, min_recording_duration=0.3)
        assert result == "bonjour"
        mock_asr_model.recognize.assert_called_once()

    def test_near_silent_clip_discarded_without_transcribing(self, sm, mock_asr_model, tmp_path):
        """Near-silence must not reach the model.

        Parakeet invents short fillers ("Yeah.", "Okay.", "Mm-hmm.") on quiet
        audio, which would be typed into the user's active field.
        """
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        audio._get_audio_duration = MagicMock(return_value=2.0)
        audio._get_audio_rms = MagicMock(return_value=0.0006)

        assert audio.transcribe(audio_path, mock_asr_model) is None
        mock_asr_model.recognize.assert_not_called()

    def test_audible_clip_passes_the_silence_gate(self, sm, mock_asr_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        audio._get_audio_duration = MagicMock(return_value=2.0)
        audio._get_audio_rms = MagicMock(return_value=0.15)
        mock_asr_model.recognize.return_value = "bonjour"

        assert audio.transcribe(audio_path, mock_asr_model) == "bonjour"

    def test_unmeasurable_rms_does_not_block_transcription(self, sm, mock_asr_model, tmp_path):
        """An unmeasurable clip is transcribed rather than silently dropped."""
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        audio._get_audio_rms = MagicMock(return_value=None)
        mock_asr_model.recognize.return_value = "bonjour"

        assert audio.transcribe(audio_path, mock_asr_model) == "bonjour"

    def test_unreadable_duration_does_not_block_transcription(self, sm, mock_asr_model, tmp_path):
        """A clip whose duration cannot be measured is still attempted."""
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)

        audio._get_audio_duration = MagicMock(return_value=None)
        mock_asr_model.recognize.return_value = "bonjour"

        assert audio.transcribe(audio_path, mock_asr_model) == "bonjour"


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
        audio, cb = self._start_streaming(sm, mocker, chunks.append, pause_ms=200, min_chunk_s=0.1, max_chunk_s=10.0)
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
        audio, cb = self._start_streaming(sm, mocker, chunks.append, pause_ms=5000, min_chunk_s=0.1, max_chunk_s=60.0)
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


# ---------------------------------------------------------------------------
# Audio duration detection (relocated from the deleted test_language_detection.py,
# which existed for the auto-detect-language feature; these cover
# _get_audio_duration, which outlived it as the short-clip discard guard.)
# ---------------------------------------------------------------------------


class TestAudioDurationDetection:
    """Test audio file duration detection."""

    @staticmethod
    def _wav(path, seconds, rate=16000):
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(b"\x00\x00" * int(rate * seconds))
        return str(path)

    def test_detects_duration_of_wav_file(self, tmp_path):
        audio = AudioEngine(MagicMock())
        duration = audio._get_audio_duration(self._wav(tmp_path / "test.wav", 2.0))
        assert duration is not None
        assert abs(duration - 2.0) < 0.01

    def test_detects_short_audio_duration(self, tmp_path):
        audio = AudioEngine(MagicMock())
        duration = audio._get_audio_duration(self._wav(tmp_path / "short.wav", 0.5))
        assert duration is not None
        assert abs(duration - 0.5) < 0.01

    def test_returns_none_for_non_wav_file(self, tmp_path):
        audio = AudioEngine(MagicMock())
        non_wav = tmp_path / "test.mp3"
        non_wav.write_bytes(b"not a wav file")
        assert audio._get_audio_duration(str(non_wav)) is None

    def test_returns_none_for_missing_file(self):
        audio = AudioEngine(MagicMock())
        assert audio._get_audio_duration("/nonexistent/file.wav") is None


class TestAudioRms:
    """RMS measurement backing the silence gate."""

    @staticmethod
    def _wav(path, samples, rate=16000):
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(samples.astype("<i2").tobytes())
        return str(path)

    def test_digital_silence_measures_zero(self, tmp_path):
        import numpy as np

        audio = AudioEngine(MagicMock())
        path = self._wav(tmp_path / "sil.wav", np.zeros(16000))
        assert audio._get_audio_rms(path) == 0.0

    def test_full_scale_tone_measures_near_one(self, tmp_path):
        import numpy as np

        audio = AudioEngine(MagicMock())
        loud = np.full(16000, np.iinfo(np.int16).max)
        rms = audio._get_audio_rms(self._wav(tmp_path / "loud.wav", loud))
        assert rms is not None and rms > 0.9

    def test_quiet_noise_stays_below_the_gate(self, tmp_path):
        import numpy as np

        from whispy.core.audio import SILENCE_RMS_THRESHOLD

        audio = AudioEngine(MagicMock())
        # ~0.002 of full scale: the realistic quiet-room floor that made the
        # model emit "Okay." / "Mm-hmm." / "No." in the real-model tier.
        quiet = np.full(16000, int(0.002 * np.iinfo(np.int16).max))
        rms = audio._get_audio_rms(self._wav(tmp_path / "quiet.wav", quiet))
        assert rms is not None and rms < SILENCE_RMS_THRESHOLD

    def test_returns_none_for_non_wav_file(self, tmp_path):
        audio = AudioEngine(MagicMock())
        bad = tmp_path / "x.mp3"
        bad.write_bytes(b"not a wav")
        assert audio._get_audio_rms(str(bad)) is None

    def test_returns_none_for_missing_file(self):
        audio = AudioEngine(MagicMock())
        assert audio._get_audio_rms("/nonexistent/file.wav") is None

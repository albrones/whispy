"""Tests for AudioEngine with a faked sounddevice capture backend."""

import logging
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
from whispy.core.audio import SILENCE_RMS_THRESHOLD, AudioEngine
from whispy.core.segmentation import CONTINUATION, SENTENCE


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
        chunks: list[tuple[str, str]] = []
        audio._on_chunk = lambda path, reason: chunks.append((path, reason))
        audio._chunk_buf = bytearray(b"\x00" * 3200)
        old_umask = os.umask(0o022)
        try:
            audio._emit_chunk(SENTENCE)
        finally:
            os.umask(old_umask)
        assert len(chunks) == 1
        mode = os.stat(chunks[0][0]).st_mode & 0o777
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
        audio._get_peak_rms = MagicMock(return_value=0.0006)

        assert audio.transcribe(audio_path, mock_asr_model) is None
        mock_asr_model.recognize.assert_not_called()

    def test_audible_clip_passes_the_silence_gate(self, sm, mock_asr_model, tmp_path):
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        audio._get_audio_duration = MagicMock(return_value=2.0)
        audio._get_peak_rms = MagicMock(return_value=0.15)
        mock_asr_model.recognize.return_value = "bonjour"

        assert audio.transcribe(audio_path, mock_asr_model) == "bonjour"

    def test_unmeasurable_rms_does_not_block_transcription(self, sm, mock_asr_model, tmp_path):
        """An unmeasurable clip is transcribed rather than silently dropped."""
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        audio._get_peak_rms = MagicMock(return_value=None)
        mock_asr_model.recognize.return_value = "bonjour"

        assert audio.transcribe(audio_path, mock_asr_model) == "bonjour"

    def test_unreadable_duration_does_not_block_transcription(self, sm, mock_asr_model, tmp_path):
        """A clip whose duration cannot be measured is still attempted."""
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)

        audio._get_audio_duration = MagicMock(return_value=None)
        mock_asr_model.recognize.return_value = "bonjour"

        assert audio.transcribe(audio_path, mock_asr_model) == "bonjour"

    # -----------------------------------------------------------------------
    # Empty-result retry on the untrimmed original (fix-dictation-text-fidelity)
    # -----------------------------------------------------------------------

    def test_empty_trimmed_result_retries_on_the_untrimmed_original(self, sm, mock_asr_model, tmp_path):
        """A trimmed clip that comes back empty gets one retry on the original.

        Trimming is the only transformation between the gates and the model
        call, so it is the first suspect for a lost result; the untrimmed
        original is tried once more before giving up.
        """
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        trimmed_path = audio_path + ".trim.wav"
        audio._get_audio_duration = MagicMock(return_value=2.0)
        audio._get_peak_rms = MagicMock(return_value=0.15)
        audio._speech_span = MagicMock(return_value=(0.1, 1.5, 1.0))
        audio._trim_to_speech = MagicMock(return_value=trimmed_path)
        mock_asr_model.recognize.side_effect = ["", "hello world"]

        result = audio.transcribe(audio_path, mock_asr_model)

        assert result == "hello world"
        assert mock_asr_model.recognize.call_count == 2
        calls = [c.args[0] for c in mock_asr_model.recognize.call_args_list]
        assert calls == [trimmed_path, audio_path]

    def test_untrimmed_clip_is_never_retried_when_empty(self, sm, mock_asr_model, tmp_path):
        """A clip that was sent untrimmed (trimming was a no-op) gets no retry."""
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        audio._get_audio_duration = MagicMock(return_value=2.0)
        audio._get_peak_rms = MagicMock(return_value=0.15)
        audio._speech_span = MagicMock(return_value=(0.1, 1.5, 1.0))
        audio._trim_to_speech = MagicMock(return_value=audio_path)  # no-op trim
        mock_asr_model.recognize.return_value = ""

        result = audio.transcribe(audio_path, mock_asr_model)

        assert result is None
        mock_asr_model.recognize.assert_called_once_with(audio_path)

    def test_both_calls_empty_logs_a_warning_with_the_measurements(self, sm, mock_asr_model, tmp_path, caplog):
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        trimmed_path = audio_path + ".trim.wav"
        audio._get_audio_duration = MagicMock(return_value=2.0)
        audio._get_peak_rms = MagicMock(return_value=0.15)
        audio._speech_span = MagicMock(return_value=(0.1, 1.5, 1.0))
        audio._trim_to_speech = MagicMock(return_value=trimmed_path)
        mock_asr_model.recognize.return_value = ""

        with caplog.at_level(logging.WARNING, logger="whispy.core.audio"):
            result = audio.transcribe(audio_path, mock_asr_model)

        assert result is None
        assert mock_asr_model.recognize.call_count == 2
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "2.00" in warnings[0].getMessage()
        assert "0.150000" in warnings[0].getMessage()
        assert "1.00" in warnings[0].getMessage()

    def test_quiet_clip_empty_twice_is_retried_louder(self, sm, mock_asr_model, tmp_path):
        """Quiet dictation the model missed twice gets a last try at normalized loudness."""
        import numpy as np

        audio = AudioEngine(sm)
        audio_path = str(tmp_path / "quiet.wav")
        quiet_voice = (np.sin(np.linspace(0, 2000, 32000)) * 0.012 * 32768 * 1.414).astype(np.int16)
        with wave.open(audio_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(quiet_voice.tobytes())
        audio._get_peak_rms = MagicMock(return_value=0.012)
        audio._speech_span = MagicMock(return_value=(0.1, 1.5, 1.0))
        audio._trim_to_speech = MagicMock(return_value=audio_path + ".trim.wav")
        heard_rms = []

        def recognize(path):
            if path.endswith(".louder.wav"):
                with wave.open(path, "rb") as wf:
                    pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16) / 32768
                heard_rms.append(float(np.sqrt(np.mean(pcm**2))))
                return "bonjour"
            return ""

        mock_asr_model.recognize.side_effect = recognize

        assert audio.transcribe(audio_path, mock_asr_model) == "bonjour"
        assert mock_asr_model.recognize.call_count == 3
        assert abs(heard_rms[0] - 0.05) < 0.005
        assert not os.path.exists(audio_path + ".louder.wav")

    def _lose(self, sm, mock_asr_model, tmp_path, name="test.wav"):
        audio = AudioEngine(sm)
        audio_path = str(tmp_path / name)
        with open(audio_path, "wb") as f:
            f.write(name.encode())
        audio._get_audio_duration = MagicMock(return_value=2.0)
        audio._get_peak_rms = MagicMock(return_value=0.15)
        audio._speech_span = MagicMock(return_value=(0.1, 1.5, 1.0))
        audio._trim_to_speech = MagicMock(return_value=audio_path)
        mock_asr_model.recognize.return_value = ""
        return audio.transcribe(audio_path, mock_asr_model)

    def test_lost_clip_is_kept_and_named_in_the_warning(self, sm, mock_asr_model, tmp_path, caplog, lost_clips_dir):
        with caplog.at_level(logging.WARNING, logger="whispy.core.audio"):
            assert self._lose(sm, mock_asr_model, tmp_path) is None

        kept = list(lost_clips_dir.glob("lost-*.wav"))
        assert len(kept) == 1
        assert kept[0].read_bytes() == b"test.wav"
        assert kept[0].name in caplog.records[-1].getMessage()

    def test_only_the_newest_lost_clips_are_kept(self, sm, mock_asr_model, tmp_path, lost_clips_dir):
        from whispy.core import audio as audio_module

        lost_clips_dir.mkdir()
        oldest = lost_clips_dir / "lost-00000000-000000-000000000.wav"
        oldest.write_bytes(b"old")
        for index in range(audio_module.LOST_CLIPS_KEPT - 1):
            (lost_clips_dir / f"lost-00000001-000000-{index:09d}.wav").write_bytes(b"old")

        self._lose(sm, mock_asr_model, tmp_path)

        assert len(list(lost_clips_dir.glob("lost-*.wav"))) == audio_module.LOST_CLIPS_KEPT
        assert not oldest.exists()

    def test_transcribed_clip_logs_a_success_without_its_text(self, sm, mock_asr_model, tmp_path, caplog):
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        audio._get_audio_duration = MagicMock(return_value=2.0)
        audio._get_peak_rms = MagicMock(return_value=0.15)
        audio._speech_span = MagicMock(return_value=(0.1, 1.5, 1.0))
        audio._trim_to_speech = MagicMock(return_value=audio_path)
        mock_asr_model.recognize.return_value = "bonjour"

        with caplog.at_level(logging.INFO, logger="whispy.core.audio"):
            audio.transcribe(audio_path, mock_asr_model)

        message = caplog.records[-1].getMessage()
        assert "Transcribed a 2.00s clip" in message
        assert "bonjour" not in message


class TestGateRejectionLogging:
    """A clip stopped by a gate keeps that gate's own (non-loss) log level.

    The empty-result WARNING added for the trimming retry names a loss: the
    clip cleared every gate and the model still returned nothing. A clip
    stopped BY a gate is a routine, expected discard and must keep logging at
    its existing level, never emit that loss warning, and never reach the
    model.
    """

    @staticmethod
    def _clip(tmp_path):
        audio_path = str(tmp_path / "test.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)
        return audio_path

    def test_duration_guard_rejection_is_not_a_loss_warning(self, sm, mock_asr_model, tmp_path, caplog):
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        audio._get_audio_duration = MagicMock(return_value=0.1)

        with caplog.at_level(logging.INFO, logger="whispy.core.audio"):
            result = audio.transcribe(audio_path, mock_asr_model, min_recording_duration=0.3)

        assert result is None
        mock_asr_model.recognize.assert_not_called()
        assert not any(r.levelno == logging.WARNING for r in caplog.records)
        assert any(r.levelno == logging.INFO for r in caplog.records)

    def test_rms_gate_rejection_is_not_a_loss_warning(self, sm, mock_asr_model, tmp_path, caplog):
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        audio._get_audio_duration = MagicMock(return_value=2.0)
        audio._get_peak_rms = MagicMock(return_value=0.0006)

        with caplog.at_level(logging.INFO, logger="whispy.core.audio"):
            result = audio.transcribe(audio_path, mock_asr_model)

        assert result is None
        mock_asr_model.recognize.assert_not_called()
        assert not any(r.levelno == logging.WARNING for r in caplog.records)
        assert any(r.levelno == logging.INFO for r in caplog.records)

    def test_voiced_duration_gate_rejection_is_not_a_loss_warning(self, sm, mock_asr_model, tmp_path, caplog):
        audio = AudioEngine(sm)
        audio_path = self._clip(tmp_path)
        audio._get_audio_duration = MagicMock(return_value=2.0)
        audio._get_peak_rms = MagicMock(return_value=0.15)
        audio._speech_span = MagicMock(return_value=(0.0, 0.1, 0.05))  # below MIN_SPEECH_DURATION_S

        with caplog.at_level(logging.INFO, logger="whispy.core.audio"):
            result = audio.transcribe(audio_path, mock_asr_model)

        assert result is None
        mock_asr_model.recognize.assert_not_called()
        assert not any(r.levelno == logging.WARNING for r in caplog.records)
        assert any(r.levelno == logging.INFO for r in caplog.records)


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
        chunks: list[tuple[str, str]] = []
        audio, cb = self._start_streaming(
            sm,
            mocker,
            lambda path, reason: chunks.append((path, reason)),
            pause_ms=200,
            min_speech_s=0.05,
            max_chunk_s=10.0,
        )
        speech = self._block(8000)  # loud -> level ~1.0
        silence = self._block(0)
        for _ in range(5):  # 0.5s speech
            cb(speech, 1600, None, None)
        for _ in range(4):  # silence accumulates past pause_ms (0.2s)
            cb(silence, 1600, None, None)
        assert len(chunks) >= 1
        path, reason = chunks[0]
        assert os.path.exists(path)
        # pause_ms == sentence_break_ms here (default), so a qualifying pause
        # closes the chunk as a sentence boundary.
        assert reason == SENTENCE

    def test_forced_cut_reports_continuation(self, sm, mocker):
        # Continuous speech with no closing gap: only the unconditional
        # ceiling (max_chunk_s * HARD_MAX_FACTOR) can close this chunk, and
        # that cut is always a CONTINUATION, never a SENTENCE.
        chunks: list[tuple[str, str]] = []
        audio, cb = self._start_streaming(
            sm,
            mocker,
            lambda path, reason: chunks.append((path, reason)),
            pause_ms=600,
            min_speech_s=0.05,
            max_chunk_s=0.2,
        )
        speech = self._block(8000)
        for _ in range(10):  # 1.0s of continuous speech, no gap
            cb(speech, 1600, None, None)
        assert len(chunks) >= 1
        path, reason = chunks[0]
        assert os.path.exists(path)
        assert reason == CONTINUATION

    def test_no_whole_file_written_in_streaming(self, sm, mocker):
        chunks: list[str] = []
        audio, cb = self._start_streaming(sm, mocker, chunks.append)
        # The legacy whole-recording WAV is never opened in streaming mode.
        assert audio._wave is None
        cb(self._block(8000), 1600, None, None)
        assert audio._wave is None

    def test_tail_flushed_on_stop(self, sm, mocker):
        chunks: list[tuple[str, str]] = []
        audio, cb = self._start_streaming(
            sm,
            mocker,
            lambda path, reason: chunks.append((path, reason)),
            pause_ms=5000,
            min_speech_s=0.05,
            max_chunk_s=60.0,
        )
        # Speech with no closing pause -> nothing emitted until stop flushes tail.
        for _ in range(5):
            cb(self._block(8000), 1600, None, None)
        assert chunks == []
        audio.stop()
        assert len(chunks) == 1
        path, reason = chunks[0]
        assert os.path.exists(path)
        # The tail always flushes as a sentence: the recording ended.
        assert reason == SENTENCE

    def test_pure_silence_emits_nothing(self, sm, mocker):
        chunks: list[str] = []
        audio, cb = self._start_streaming(sm, mocker, chunks.append, pause_ms=200, min_speech_s=0.05)
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

    def _feed_until_ceiling_then_gap(self, sm, mocker, soft_gap_ms, max_gap_frames=20):
        """Drive the live segmenter past max_chunk_s, then feed silence frames
        one at a time (via the real capture callback) until a boundary fires.

        Returns (chunks, gap_frames_needed). WebRTC VAD carries roughly two
        frames of hangover after loud speech before it will call a frame
        silent, so the released boundary needs a handful of gap frames, not
        exactly one -- this drives real frames rather than asserting on the
        segmenter's raw silence-seconds counter.
        """
        speech = self._block(8000, n=480)  # one 30ms VAD frame, reliably "speech"
        silence = self._block(0, n=480)  # one 30ms VAD frame of digital silence
        chunks: list[tuple[str, str]] = []
        audio, cb = self._start_streaming(
            sm,
            mocker,
            lambda path, reason: chunks.append((path, reason)),
            pause_ms=100_000,  # never closes on its own
            min_speech_s=0.01,
            max_chunk_s=1.0,  # ~34 frames
            soft_gap_ms=soft_gap_ms,
        )
        # start() fires the spy stream's callback once with ~1s of silence
        # before we drive it ourselves; clear that out of the fresh segmenter
        # so the frame math below starts from a clean chunk.
        audio._segmenter.reset_chunk()
        audio._segmenter._pending = bytearray()
        audio._chunk_buf = bytearray()
        for _ in range(34):  # past the 1.0s ceiling, still speaking
            cb(speech, 480, None, None)
        assert chunks == []
        for i in range(max_gap_frames):
            cb(silence, 480, None, None)
            if chunks:
                audio.stop()
                return chunks, i + 1
        audio.stop()
        return chunks, None

    def test_configure_streaming_threads_soft_gap_ms_release(self, sm, mocker):
        # A soft_gap_ms just past WebRTC VAD's ~2-frame hangover releases the
        # ceiling cut at the first qualifying silence, well before the
        # unconditional hard cap (1.5x max_chunk_s) could explain it.
        chunks, gap_frames = self._feed_until_ceiling_then_gap(sm, mocker, soft_gap_ms=120)
        assert gap_frames is not None and gap_frames <= 8
        assert chunks[0][1] == CONTINUATION

    def test_configure_streaming_threads_soft_gap_ms_hold(self, sm, mocker):
        # A soft_gap_ms far longer than any gap fed here is NOT released by
        # it; proves configure_streaming actually threads the value to the
        # live segmenter rather than a constructor default it ignores --
        # otherwise this would cut at the same point as the low value above.
        chunks, gap_frames = self._feed_until_ceiling_then_gap(sm, mocker, soft_gap_ms=5000)
        assert gap_frames is not None and gap_frames > 8
        assert chunks[0][1] == CONTINUATION


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
        paths = audio.segment_pcm(pcm, pause_ms=200, min_speech_s=0.05, max_chunk_s=10.0)
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
        paths = audio.segment_pcm(bytes(1600 * 2) * 20, pause_ms=200, min_speech_s=0.05)
        assert paths == []

    def test_restores_live_state(self, sm):
        # segment_pcm must not leave the engine wired to its temporary sink.
        audio = AudioEngine(sm)
        audio.segment_pcm(bytes(1600 * 2) * 5)
        assert audio._on_chunk is None
        assert audio._segmenter is None

    def test_segment_pcm_honours_soft_gap_ms(self, sm):
        # 34 frames of speech (past the 1.0s ceiling) followed by 20 frames of
        # silence -- more gap than either case needs. A low soft_gap_ms (120ms,
        # just past WebRTC VAD's ~2-frame hangover) releases the cut at the
        # first qualifying gap, well short of the 1.5s hard cap; a high one
        # (5000ms) is never satisfied by this gap, so the cut only lands at
        # the unconditional hard cap instead. Both replays emit exactly one
        # chunk (the remaining silence never contains speech, so nothing
        # follows) -- the WAV duration is what tells them apart.
        import numpy as np

        speech_frame = np.random.RandomState(0).randint(-8000, 8000, 480).astype(np.int16).tobytes()
        silence_frame = bytes(480 * 2)
        pcm = speech_frame * 34 + silence_frame * 20

        audio = AudioEngine(sm)
        released = audio.segment_pcm(
            pcm, pause_ms=100_000, min_speech_s=0.01, max_chunk_s=1.0, soft_gap_ms=120, block_frames=480
        )
        held = audio.segment_pcm(
            pcm, pause_ms=100_000, min_speech_s=0.01, max_chunk_s=1.0, soft_gap_ms=5000, block_frames=480
        )
        try:
            assert len(released) == 1
            assert len(held) == 1
            released_duration = wave.open(released[0]).getnframes() / 16000
            held_duration = wave.open(held[0]).getnframes() / 16000
            assert released_duration < 1.4  # released well before the 1.5s hard cap
            assert held_duration >= 1.45  # held through the gap, cut only at the hard cap
        finally:
            for p in (*released, *held):
                if os.path.exists(p):
                    os.remove(p)


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


class TestPeakRms:
    """The near-silence gate measures the loudest window, not the clip mean.

    Live-drive case: one word held by the segmenter for context, then flushed
    inside 10 s of silence, averaged 0.00496 -- under the 0.005 gate by 1% --
    and was discarded. The word itself was ~0.025 RMS.
    """

    def _wav(self, path, samples, rate=16000):
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(samples.astype("<i2").tobytes())
        return str(path)

    def _word_in_silence(self, tmp_path, silence_s=10.0, word_s=0.4, level=0.025):
        import numpy as np

        rate = 16000
        t = np.arange(int(word_s * rate)) / rate
        word = np.sin(2 * np.pi * 200 * t) * level * np.sqrt(2) * np.iinfo(np.int16).max
        clip = np.concatenate([np.zeros(int(silence_s * rate / 2)), word, np.zeros(int(silence_s * rate / 2))])
        return self._wav(tmp_path / "word.wav", clip)

    def test_one_word_in_long_silence_clears_the_gate(self, tmp_path):
        audio = AudioEngine(MagicMock())
        path = self._word_in_silence(tmp_path)
        assert audio._get_audio_rms(path) < SILENCE_RMS_THRESHOLD  # the old metric lost it
        assert audio._get_peak_rms(path) > SILENCE_RMS_THRESHOLD  # the gate now keeps it

    def test_quiet_noise_still_fails_the_gate(self, tmp_path):
        import numpy as np

        audio = AudioEngine(MagicMock())
        quiet = np.random.default_rng(3).normal(0, 0.002 * np.iinfo(np.int16).max, 16000 * 3)
        path = self._wav(tmp_path / "quiet.wav", quiet)
        assert audio._get_peak_rms(path) < SILENCE_RMS_THRESHOLD

    def test_digital_silence_measures_zero(self, tmp_path):
        import numpy as np

        audio = AudioEngine(MagicMock())
        assert audio._get_peak_rms(self._wav(tmp_path / "sil.wav", np.zeros(16000))) == 0.0

    def test_clip_shorter_than_window_is_measured_whole(self, tmp_path):
        import numpy as np

        audio = AudioEngine(MagicMock())
        short = np.full(1000, int(0.1 * np.iinfo(np.int16).max))
        path = self._wav(tmp_path / "short.wav", short)
        assert audio._get_peak_rms(path) == pytest.approx(audio._get_audio_rms(path))

    def test_uniform_clip_peak_equals_mean(self, tmp_path):
        import numpy as np

        audio = AudioEngine(MagicMock())
        loud = np.full(16000, int(0.3 * np.iinfo(np.int16).max))
        path = self._wav(tmp_path / "flat.wav", loud)
        assert audio._get_peak_rms(path) == pytest.approx(audio._get_audio_rms(path), rel=1e-6)

    def test_returns_none_for_unreadable_file(self, tmp_path):
        audio = AudioEngine(MagicMock())
        bad = tmp_path / "x.mp3"
        bad.write_bytes(b"not a wav")
        assert audio._get_peak_rms(str(bad)) is None
        assert audio._get_peak_rms("/nonexistent/file.wav") is None

    def test_returns_none_for_missing_file(self):
        audio = AudioEngine(MagicMock())
        assert audio._get_audio_rms("/nonexistent/file.wav") is None


def _requires_vad():
    """Skip when webrtcvad is absent.

    Its absence is a supported configuration -- `speech_duration_s` returns None
    and every caller fails open -- so a test asserting that something *is*
    rejected has to skip rather than fail there. Only the rejection assertions
    need this; the fail-open ones hold either way.
    """
    import whispy.core.segmentation as seg_mod

    return pytest.mark.skipif(seg_mod.webrtcvad is None, reason="webrtcvad not installed")


requires_vad = _requires_vad()


class TestSpeechGate:
    """`_carries_speech` — the VAD gate for non-speech that clears the RMS gate."""

    @staticmethod
    def _wav(path, samples, rate=16000, width=2, channels=1):
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(width)
            wf.setframerate(rate)
            wf.writeframes(samples.astype("<i2").tobytes())
        return str(path)

    @staticmethod
    def _voiced(seconds=1.0, rate=16000):
        import numpy as np

        t = np.arange(int(rate * seconds)) / rate
        # A harmonic stack: webrtcvad reads every frame of this as speech.
        return sum(np.sin(2 * np.pi * (120 * h) * t) / h for h in range(1, 12)) * 8000

    def test_voiced_audio_passes(self, tmp_path):
        audio = AudioEngine(MagicMock())
        assert audio._carries_speech(self._wav(tmp_path / "v.wav", self._voiced())) is True

    @requires_vad
    def test_non_speech_above_the_rms_gate_is_rejected(self, tmp_path):
        """Room noise that clears the RMS gate but carries no voiced frames.

        Sigma 500 puts this at ~0.015 normalized RMS: 3x over the RMS gate, and
        inside the band where the real-model tier measured the model answering
        noise with a filler. Above roughly 0.04 RMS webrtcvad calls steady noise
        voiced and this gate stops discriminating — that ceiling is deliberate,
        see MIN_SPEECH_DURATION_S.
        """
        import numpy as np

        audio = AudioEngine(MagicMock())
        noise = np.random.default_rng(7).normal(0, 500, 32000)
        path = self._wav(tmp_path / "noise.wav", noise)
        assert audio._get_audio_rms(path) > SILENCE_RMS_THRESHOLD
        assert audio._carries_speech(path) is False

    @requires_vad
    def test_digital_silence_is_rejected(self, tmp_path):
        import numpy as np

        audio = AudioEngine(MagicMock())
        assert audio._carries_speech(self._wav(tmp_path / "s.wav", np.zeros(16000))) is False

    @requires_vad
    def test_a_rejected_clip_never_reaches_the_model(self, tmp_path, sm, mock_asr_model):
        import numpy as np

        audio = AudioEngine(sm)
        path = self._wav(tmp_path / "s.wav", np.zeros(16000))
        assert audio.transcribe(path, mock_asr_model) is None
        mock_asr_model.recognize.assert_not_called()

    def test_fails_open_on_a_non_wav_file(self, tmp_path):
        audio = AudioEngine(MagicMock())
        bad = tmp_path / "x.mp3"
        bad.write_bytes(b"not a wav")
        assert audio._carries_speech(str(bad)) is True

    def test_fails_open_on_a_missing_file(self):
        audio = AudioEngine(MagicMock())
        assert audio._carries_speech("/nonexistent/file.wav") is True

    def test_fails_open_on_an_unsupported_sample_width(self, tmp_path):
        """8-bit PCM cannot be framed for the VAD; it must not be dropped."""
        import numpy as np

        path = str(tmp_path / "w8.wav")
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(1)
            wf.setframerate(16000)
            wf.writeframes(np.full(16000, 128, dtype=np.uint8).tobytes())
        assert AudioEngine(MagicMock())._carries_speech(path) is True

    def test_fails_open_without_webrtcvad(self, tmp_path, monkeypatch):
        import numpy as np

        import whispy.core.segmentation as seg_mod

        monkeypatch.setattr(seg_mod, "webrtcvad", None)
        audio = AudioEngine(MagicMock())
        assert audio._carries_speech(self._wav(tmp_path / "s.wav", np.zeros(16000))) is True


@requires_vad
class TestSpeechGateAgainstCommittedAudio:
    """The gate thresholds, checked against real recordings on every platform.

    `MIN_SPEECH_DURATION_S` and `SILENCE_RMS_THRESHOLD` were both calibrated on
    macOS, against `say` synthesis and one microphone. The committed fixtures are
    real recordings, this runs in the default tier, and CI runs that tier on
    ubuntu as well as macOS — so a threshold that creeps up into real speech, or
    a platform where webrtcvad hears less of it, fails here rather than in
    someone's editor.

    No model involved: this measures what the gates see, not what they produce.
    """

    FIXTURES = Path(__file__).parent / "fixtures" / "audio"

    @staticmethod
    def _voiced(path):
        from whispy.core.segmentation import speech_duration_s

        with wave.open(str(path)) as w:
            return speech_duration_s(w.readframes(w.getnframes()), sample_rate=w.getframerate())

    @pytest.mark.parametrize("fixture", ["en_speech.wav", "fr_speech.wav"])
    def test_recorded_speech_clears_both_gates_with_room(self, fixture):
        from whispy.core.audio import MIN_SPEECH_DURATION_S

        path = self.FIXTURES / fixture
        audio = AudioEngine(MagicMock())

        rms = audio._get_audio_rms(str(path))
        assert rms is not None and rms > SILENCE_RMS_THRESHOLD * 5, f"{fixture} RMS {rms} is close to the gate"

        voiced = self._voiced(path)
        assert voiced is not None
        assert voiced > MIN_SPEECH_DURATION_S * 3, f"{fixture} carries only {voiced:.2f}s of voiced audio"
        assert audio._carries_speech(str(path)) is True

    def test_recorded_silence_is_rejected(self):
        path = self.FIXTURES / "silence.wav"
        audio = AudioEngine(MagicMock())
        assert audio._carries_speech(str(path)) is False


@requires_vad
class TestTrimToSpeech:
    """The model sees the clip cut to its voiced span, not the silence around it.

    Measured (`scripts/asr-bench/probe_lone_word.py`): an isolated word with
    10 s of trailing silence was recognized 3-5/15, trimmed 10/15. The live
    drive's lone "test" arrived with seconds of silence and came back empty
    7 times out of 9.
    """

    FIXTURE = Path(__file__).parent / "fixtures" / "audio" / "fr_speech.wav"

    def _padded(self, tmp_path, lead_s, tail_s, gap_s=None):
        import numpy as np

        with wave.open(str(self.FIXTURE)) as w:
            rate = w.getframerate()
            speech = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        parts = [np.zeros(int(lead_s * rate), dtype=np.int16), speech]
        if gap_s is not None:
            parts += [np.zeros(int(gap_s * rate), dtype=np.int16), speech]
        parts.append(np.zeros(int(tail_s * rate), dtype=np.int16))
        path = tmp_path / "padded.wav"
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(np.concatenate(parts).tobytes())
        return str(path), rate

    def _model(self, captured):
        model = MagicMock()

        def recognize(path):
            with wave.open(path) as w:
                captured.append((path, w.getnframes() / w.getframerate()))
            return "bonjour"

        model.recognize.side_effect = recognize
        return model

    def test_long_silence_around_speech_is_cut_before_the_model(self, tmp_path):
        from whispy.core.audio import TRIM_MARGIN_S

        audio = AudioEngine(MagicMock())
        path, _ = self._padded(tmp_path, lead_s=3.0, tail_s=10.0)
        seen = []

        assert audio.transcribe(path, self._model(seen)) == "bonjour"

        ((model_path, model_s),) = seen
        assert model_path != path  # a trimmed copy went to the model
        speech_s = wave.open(str(self.FIXTURE)).getnframes() / 16000
        assert model_s < speech_s + 2 * TRIM_MARGIN_S + 0.5  # the padding is gone
        assert model_s > speech_s - 0.5  # the speech is not
        assert not Path(model_path).exists()  # copy removed after the call
        assert Path(path).exists()  # the caller's file untouched

    def test_internal_silence_is_kept(self, tmp_path):
        audio = AudioEngine(MagicMock())
        path, _ = self._padded(tmp_path, lead_s=2.0, tail_s=2.0, gap_s=3.0)
        seen = []

        audio.transcribe(path, self._model(seen))

        ((_, model_s),) = seen
        speech_s = wave.open(str(self.FIXTURE)).getnframes() / 16000
        assert model_s > 2 * speech_s + 3.0 - 0.5  # both utterances and the gap between them

    def test_clip_already_tight_is_sent_as_is(self, tmp_path):
        audio = AudioEngine(MagicMock())
        path, _ = self._padded(tmp_path, lead_s=0.0, tail_s=0.0)
        seen = []

        audio.transcribe(path, self._model(seen))

        ((model_path, _),) = seen
        assert model_path == path

    def test_unmeasurable_span_sends_the_original(self, tmp_path):
        audio = AudioEngine(MagicMock())
        path, _ = self._padded(tmp_path, lead_s=3.0, tail_s=3.0)
        audio._speech_span = MagicMock(return_value=None)
        seen = []

        audio.transcribe(path, self._model(seen))

        ((model_path, _),) = seen
        assert model_path == path

    def test_trim_failure_falls_back_to_the_original(self, tmp_path, monkeypatch):
        audio = AudioEngine(MagicMock())
        path, _ = self._padded(tmp_path, lead_s=3.0, tail_s=3.0)
        real_open = wave.open

        def failing_open(p, mode="rb"):
            if mode == "wb":
                raise OSError("disk full")
            return real_open(p, mode)

        monkeypatch.setattr("whispy.core.audio.wave.open", failing_open)
        seen = []

        assert audio.transcribe(path, self._model(seen)) == "bonjour"
        ((model_path, _),) = seen
        assert model_path == path


class TestCaptureDiagnosticsLog:
    """Each recording logs what it listened to and how loud it got.

    Live drive, 2026-09-14: 84 s of room noise (RMS 0.0036) and seven
    recordings with no speech frame at all, and nothing in the log said which
    input device was open or how quiet the capture had been.
    """

    def _engine(self, mocker):
        spy = _install_spy_sd(mocker)
        audio_module.sd.query_devices.return_value = {"name": "Micro MacBook Pro", "default_samplerate": 44100.0}
        return AudioEngine(MagicMock()), spy

    def test_start_logs_the_input_device(self, mocker, caplog):
        audio, _ = self._engine(mocker)
        with caplog.at_level(logging.INFO, logger="whispy.core.audio"):
            audio.start()
        assert "capture open: input 'Micro MacBook Pro' (native 44100 Hz), stream 16000 Hz" in caplog.text

    def test_device_query_failure_does_not_break_start(self, mocker, caplog):
        audio, _ = self._engine(mocker)
        audio_module.sd.query_devices.side_effect = RuntimeError("no default input")
        with caplog.at_level(logging.INFO, logger="whispy.core.audio"):
            assert audio.start() is True
        assert "capture open: input unknown (no default input)" in caplog.text

    def test_stop_logs_peak_level_with_a_noise_floor_hint_on_silence(self, mocker, caplog):
        audio, _ = self._engine(mocker)
        audio.start()  # the spy stream feeds one second of digital silence
        with caplog.at_level(logging.INFO, logger="whispy.core.audio"):
            audio.stop()
        assert "capture closed: 1.0s, peak level 0.000 -- at the noise floor, check the input device" in caplog.text

    def test_stop_logs_peak_level_without_hint_on_speech_level_audio(self, mocker, caplog):
        import numpy as np

        audio, spy = self._engine(mocker)
        audio.start()
        loud = (np.full(1600, 0.05 * 32767)).astype("<i2").tobytes()  # RMS 0.05 -> level 0.5
        spy.instances[-1]._callback(loud, 1600, None, None)
        with caplog.at_level(logging.INFO, logger="whispy.core.audio"):
            audio.stop()
        assert "peak level 0.500" in caplog.text
        assert "noise floor" not in caplog.text


class TestUnheardInput:
    """A recording that only caught the noise floor names its input device so
    the engine can warn the user (live, 2026-10-09: four deaf takes in a row,
    no text, no sound, and the user relaunched believing Whispy had crashed)."""

    def _record_at_level(self, mocker, level: float):
        import numpy as np

        spy = _install_spy_sd(mocker)
        audio_module.sd.query_devices.return_value = {"name": "Micro MacBook Pro", "default_samplerate": 44100.0}
        audio = AudioEngine(MagicMock())
        audio.start()  # one second of digital silence
        block = np.full(1600, level / 10 * 32767).astype("<i2").tobytes()  # level = RMS x10
        spy.instances[-1]._callback(block, 1600, None, None)
        return audio

    def test_the_72_second_take_of_2026_10_09_is_unheard(self, mocker):
        audio = self._record_at_level(mocker, 0.055)
        audio.stop()
        assert audio.unheard_input == "Micro MacBook Pro"

    def test_speech_level_is_heard(self, mocker):
        audio = self._record_at_level(mocker, 0.2)
        audio.stop()
        assert audio.unheard_input is None

    def test_an_accidental_tap_is_not_reported(self, mocker):
        audio = self._record_at_level(mocker, 0.0)
        audio._frames_written = 1600  # 0.1 s: released before anyone could speak
        audio.stop()
        assert audio.unheard_input is None

    def test_the_next_recording_starts_clear(self, mocker):
        audio = self._record_at_level(mocker, 0.0)
        audio.stop()
        audio.start()
        assert audio.unheard_input is None


@requires_vad
class TestModelInputCeiling:
    """No single model call receives more than MODEL_INPUT_MAX_S of audio.

    A 180 s clip in one call peaked at 3.5 GB on CPU and 25 GB under CoreML --
    the latter panicked the machine (2026-09-29).
    """

    FIXTURE = Path(__file__).parent / "fixtures" / "audio" / "fr_speech.wav"

    def test_long_recording_reaches_the_model_in_bounded_pieces(self, tmp_path):
        import numpy as np

        from whispy.core.audio import MODEL_INPUT_MAX_S

        with wave.open(str(self.FIXTURE)) as w:
            speech = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        pause = np.zeros(16000, dtype=np.int16)
        parts = []
        while sum(len(p) for p in parts) < 100 * 16000:
            parts += [speech, pause]
        path = tmp_path / "long.wav"
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(16000)
            out.writeframes(np.concatenate(parts).tobytes())

        seen = []

        def recognize(model_path):
            with wave.open(model_path) as w:
                seen.append(w.getnframes() / w.getframerate())
            return "bonjour"

        model = MagicMock()
        model.recognize.side_effect = recognize

        text = AudioEngine(MagicMock()).transcribe(str(path), model)

        assert len(seen) > 1
        assert max(seen) <= MODEL_INPUT_MAX_S
        assert text == " ".join(["bonjour"] * len(seen))
